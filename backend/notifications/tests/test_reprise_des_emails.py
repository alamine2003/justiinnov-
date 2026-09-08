"""Une notification n'annule jamais l'action qu'elle signale.

Audit du 8 septembre 2026, §3.1 : les déclencheurs de notification étaient
appelés **dans** la transaction de la transition, leur échec avalé par un
``except Exception`` nu, et le titre d'une notification (200 caractères)
ne pouvait pas contenir un libellé de dépense (250) précédé de « Dépense
refusée — ». Sur un tel libellé, PostgreSQL levait, ``_safe`` avalait,
Django commitait une transaction déjà avortée : le refus et sa trace
d'audit disparaissaient, l'API répondait 200 avec ``status: unjustified``.
"""

from unittest import mock

from django.core import mail
from django.db import connection
from rest_framework import status

from expenses.models import AuditLog
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status
from notifications import services
from notifications.models import Notification

#: Un libellé à la longueur maximale de ``Expense.title``.
LIBELLE_DE_250 = ("Frais de mission pharmaceutique Abidjan " * 7)[:250]
assert len(LIBELLE_DE_250) == 250


class RefusTestCase(ExpenseTestCase):
    """Un dossier déclaré, une ligne soumise, le DF qui la refuse."""

    dossier_status = Status.SUBMITTED

    def setUp(self):
        super().setUp()
        self.expense = self.make_expense(title=LIBELLE_DE_250, status=Status.SUBMITTED)
        self.login(self.controller)

    def refuser(self):
        """Le refus, e-mails inclus : les rappels après commit sont joués."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                f"/api/expenses/{self.expense.pk}/reject/", {"note": "Aucun reçu joint"}
            )

    def assert_refus_acquis(self):
        """Ce que la réponse a dit est ce que la base a : état et trace."""
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.UNJUSTIFIED)
        self.assertTrue(
            AuditLog.objects.filter(
                object_type="Expense", object_id=self.expense.pk,
                action=AuditLog.Action.UNJUSTIFIED,
            ).exists(),
            "la trace d'audit du refus manque",
        )


class TitreLongTests(RefusTestCase):
    def test_un_libelle_de_250_caracteres_ne_fait_pas_disparaitre_le_refus(self):
        """Le défaut de l'audit, rejoué : avant le correctif, ce test échouait
        sur une transaction avortée ; en production, il répondait 200 pour
        une transition que la base n'avait pas."""
        response = self.refuser()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Status.UNJUSTIFIED)
        self.assert_refus_acquis()

        notification = Notification.objects.get(
            recipient=self.owner, kind=Notification.Kind.EXPENSE_REJECTED
        )
        # Le libellé est repris tel quel — jamais tronqué.
        self.assertIn(LIBELLE_DE_250, notification.title)
        self.assertIsNotNone(notification.emailed_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(LIBELLE_DE_250, mail.outbox[0].subject)


class NotificationEnEchecTests(RefusTestCase):
    def test_une_erreur_de_base_dans_la_notification_n_annule_pas_la_transition(self):
        """L'erreur de base la plus générale : la transaction est avortée par
        la notification. La transition et sa trace doivent rester acquises,
        la notification manquer et le journal le dire."""

        def transaction_avortee(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1/0")

        with mock.patch.object(
            services.Notification.objects, "bulk_create", side_effect=transaction_avortee
        ), self.assertLogs("notifications.triggers", level="ERROR"):
            response = self.refuser()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_refus_acquis()
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())
        self.assertEqual(mail.outbox, [])
