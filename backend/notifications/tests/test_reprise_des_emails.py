"""Une notification n'annule jamais l'action qu'elle signale ; son e-mail
part après la validation de la transaction et se reprend s'il n'est pas parti.

Audit du 8 septembre 2026, §3.1 : les déclencheurs de notification étaient
appelés **dans** la transaction de la transition, leur échec avalé par un
``except Exception`` nu, et le titre d'une notification (200 caractères)
ne pouvait pas contenir un libellé de dépense (250) précédé de « Dépense
refusée — ». Sur un tel libellé, PostgreSQL levait, ``_safe`` avalait,
Django commitait une transaction déjà avortée : le refus et sa trace
d'audit disparaissaient, l'API répondait 200 avec ``status: unjustified``.
"""

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.utils import timezone, translation
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy
from rest_framework import status

from budget.models import Budget
from core.management.commands.run_scheduler import JOBS
from core.models import Country, Project
from accounts.permissions import get_access
from core.journal import Trace
from expenses import transitions
from expenses.models import AuditLog
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status
from notifications import services
from notifications.models import TITRE_MAX, Notification
from notifications.services import AGE_MAX_DE_REPRISE, DELAI_DE_REPRISE, ESSAIS_MAX

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

    def test_le_pire_titre_tient_dans_la_colonne(self):
        """Le titre le plus long que l'application compose : le seuil le plus
        haut, sur l'enveloppe d'un projet, dans un pays au nom le plus long
        possible — en français et en anglais."""
        pays = Country.objects.create(
            name="P" * Country._meta.get_field("name").max_length, code="SN",
            country_ref="SN-99", currency="XOF", timezone="Africa/Dakar",
        )
        projet = Project.objects.create(
            country=pays, name="X" * Project._meta.get_field("name").max_length
        )
        enveloppe = Budget.objects.create(
            country=pays, project=projet, year=self.year, amount=1
        )
        prefixes = (
            gettext_lazy("Seuil {threshold} % atteint — {budget}"),
            gettext_lazy("Dépassement — {budget}"),
            gettext_lazy("Dépense refusée — {title}"),
        )
        for langue in ("fr", "en"):
            with translation.override(langue):
                for prefixe in prefixes:
                    titre = str(
                        format_lazy(
                            prefixe, threshold=100, budget=enveloppe, title=LIBELLE_DE_250
                        )
                    )
                    with self.subTest(langue=langue, titre=titre[:40]):
                        self.assertLessEqual(len(titre), TITRE_MAX)


class NotificationEnEchecTests(RefusTestCase):
    def test_une_erreur_de_base_dans_la_notification_n_annule_pas_la_transition(self):
        """L'erreur de base la plus générale : la transaction est avortée par
        la notification. Le point de reprise de ``_safe`` la contient ; la
        transition et sa trace restent acquises, la notification manque et le
        journal le dit."""

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

    def test_une_transition_annulee_ne_laisse_ni_notification_ni_e_mail(self):
        """La ligne in-app est écrite dans la transaction de l'action et
        l'e-mail attend son commit : une transaction défaite après la
        notification n'en laisse aucune trace, et aucun e-mail ne part."""
        with self.captureOnCommitCallbacks(execute=True), \
                self.assertRaises(RuntimeError), transaction.atomic():
            transitions.trancher(
                self.expense, "reject", get_access(self.controller),
                note="Aucun reçu joint", trace=Trace.depuis_compte(self.controller),
            )
            self.assertTrue(Notification.objects.filter(recipient=self.owner).exists())
            raise RuntimeError("annulation après notification")

        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.SUBMITTED)
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())
        self.assertEqual(mail.outbox, [])

    def test_une_trace_impossible_annule_l_etat_et_la_notification(self):
        """Ni mutation sans trace, ni trace d'une mutation annulée : la trace
        d'audit rendue impossible, rien ne subsiste."""
        with mock.patch(
            "expenses.transitions.record", side_effect=DatabaseError("journal indisponible")
        ), self.assertRaises(DatabaseError):
            self.refuser()

        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, Status.SUBMITTED)
        self.assertFalse(
            AuditLog.objects.filter(
                object_id=self.expense.pk, action=AuditLog.Action.UNJUSTIFIED
            ).exists()
        )
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())
        self.assertEqual(mail.outbox, [])


class PanneSmtpTests(RefusTestCase):
    def _refuser_serveur_en_panne(self):
        with mock.patch.object(
            services.EmailMessage, "send", side_effect=OSError("SMTP injoignable")
        ), self.assertLogs("notifications.services", level="ERROR"):
            return self.refuser()

    def test_une_panne_smtp_ne_change_ni_la_reponse_ni_l_etat(self):
        response = self._refuser_serveur_en_panne()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_refus_acquis()
        notification = Notification.objects.get(recipient=self.owner)
        self.assertIsNone(notification.emailed_at, "rien n'est parti, rien ne le prétend")
        self.assertIsNotNone(notification.email_attempted_at)
        self.assertEqual(notification.email_attempts, 1)
        self.assertEqual(mail.outbox, [])

    def test_l_ordonnanceur_reprend_un_e_mail_qui_n_est_pas_parti(self):
        self._refuser_serveur_en_panne()
        notification = Notification.objects.get(recipient=self.owner)

        # Trop tôt : l'envoi précédent pourrait encore être en cours.
        call_command("envoyer_emails", verbosity=0)
        self.assertEqual(mail.outbox, [])

        Notification.objects.filter(pk=notification.pk).update(
            email_attempted_at=timezone.now() - DELAI_DE_REPRISE - timedelta(seconds=1)
        )
        call_command("envoyer_emails", verbosity=0)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        notification.refresh_from_db()
        self.assertIsNotNone(notification.emailed_at)
        self.assertEqual(notification.email_attempts, 2)

    def test_un_e_mail_parti_ne_repart_pas(self):
        self.refuser()
        self.assertEqual(len(mail.outbox), 1)
        Notification.objects.update(
            email_attempted_at=timezone.now() - DELAI_DE_REPRISE - timedelta(seconds=1)
        )

        call_command("envoyer_emails", verbosity=0)

        self.assertEqual(len(mail.outbox), 1)

    def test_les_essais_sont_bornes(self):
        self._refuser_serveur_en_panne()
        Notification.objects.update(
            email_attempts=ESSAIS_MAX,
            email_attempted_at=timezone.now() - DELAI_DE_REPRISE - timedelta(seconds=1),
        )

        call_command("envoyer_emails", verbosity=0)

        self.assertEqual(mail.outbox, [])

    def test_une_notification_trop_ancienne_n_est_pas_reprise(self):
        """Les lignes antérieures à la reprise, ou vieilles de plusieurs
        jours, ne partent pas en bloc au premier passage de l'ordonnanceur."""
        self._refuser_serveur_en_panne()
        Notification.objects.update(
            email_attempted_at=None,
            created_at=timezone.now() - AGE_MAX_DE_REPRISE - timedelta(hours=1),
        )

        call_command("envoyer_emails", verbosity=0)

        self.assertEqual(mail.outbox, [])

    def test_un_envoi_reussi_reste_acquis_quand_le_suivant_echoue(self):
        """Chaque message est marqué un par un : un échec sur la deuxième
        adresse ne fait pas repartir la première."""
        self.doo.email = "doo@example.org"
        self.doo.save()

        def envoi_selectif(message_self, fail_silently=False):
            if message_self.to == ["doo@example.org"]:
                raise OSError("adresse refusée")
            mail.outbox.append(message_self)
            return 1

        with mock.patch.object(
            services.EmailMessage, "send", autospec=True, side_effect=envoi_selectif
        ), self.assertLogs("notifications.services", level="ERROR"), \
                self.captureOnCommitCallbacks(execute=True):
            services.notify(
                [self.owner, self.doo],
                kind=Notification.Kind.PROOF_MISSING,
                title="Justificatif manquant — N-0001",
                dedup_key="evenement:partiel",
                country=self.togo,
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(Notification.objects.get(recipient=self.owner).emailed_at)
        self.assertIsNone(Notification.objects.get(recipient=self.doo).emailed_at)


class OrdonnanceurTests(ExpenseTestCase):
    def test_la_reprise_est_planifiee(self):
        reprise = next(job for job in JOBS if job["command"][0] == "envoyer_emails")
        self.assertEqual(reprise["cron"], "SCHEDULE_EMAILS")

    def test_sans_rien_a_faire_la_commande_se_tait(self):
        call_command("envoyer_emails", verbosity=0)
        self.assertEqual(mail.outbox, [])
