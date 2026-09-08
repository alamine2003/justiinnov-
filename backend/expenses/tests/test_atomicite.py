"""Une écriture et sa trace réussissent ou échouent ensemble.

Audit du 8 septembre 2026, §4.3 : hors transaction, ``serializer.save()``
commitait puis la trace s'écrivait à part. Une trace impossible laissait la
modification sans trace ; l'historique du référentiel, écrit en
``pre_save``, attestait d'un mouvement que l'écriture suivante pouvait ne
jamais faire. Chaque ``create`` et ``update`` de l'API tient désormais
dans une seule transaction (``core.mixins.NoDestroyModelViewSet``).
"""

from unittest import mock

from django.db import DatabaseError
from django.utils import timezone

from core.models import ChangeLog, Team
from expenses.models import AuditLog, Dossier, Expense
from expenses.tests.base import ExpenseTestCase

JOURNAL_INDISPONIBLE = DatabaseError("journal indisponible")


class TraceDesDepensesTests(ExpenseTestCase):
    def payload(self, **extra):
        data = {
            "dossier": self.dossier.pk, "country": self.togo.pk,
            "date": timezone.now().isoformat(), "title": "Carburant",
            "amount": "1000.00", "team": self.team.pk, "owner": self.manager.pk,
        }
        data.update(extra)
        return data

    def test_une_creation_dont_la_trace_echoue_n_est_pas_creee(self):
        self.login(self.owner)

        with mock.patch("expenses.views.record", side_effect=JOURNAL_INDISPONIBLE), \
                self.assertRaises(DatabaseError):
            self.client.post("/api/expenses/", self.payload(title="Sans trace"))

        self.assertFalse(Expense.objects.filter(title="Sans trace").exists())

    def test_une_modification_dont_la_trace_echoue_n_est_pas_ecrite(self):
        expense = self.make_expense(title="Carburant")
        self.login(self.owner)

        with mock.patch("expenses.views.record", side_effect=JOURNAL_INDISPONIBLE), \
                self.assertRaises(DatabaseError):
            self.client.patch(f"/api/expenses/{expense.pk}/", {"title": "Sans trace"})

        expense.refresh_from_db()
        self.assertEqual(expense.title, "Carburant")

    def test_une_creation_de_dossier_dont_la_trace_echoue_n_est_pas_creee(self):
        self.login(self.owner)

        with mock.patch("expenses.views.record", side_effect=JOURNAL_INDISPONIBLE), \
                self.assertRaises(DatabaseError):
            self.client.post(
                "/api/dossiers/",
                {
                    "number": "N-0002", "label": "Sans trace", "country": self.togo.pk,
                    "team": self.team.pk, "owner": self.manager.pk,
                    "date": f"{self.year}-04-01",
                },
            )

        self.assertFalse(Dossier.objects.filter(number="N-0002").exists())
        self.assertFalse(AuditLog.objects.filter(label__contains="N-0002").exists())


class HistoriqueDuReferentielTests(ExpenseTestCase):
    def test_une_ecriture_qui_echoue_apres_sa_trace_ne_laisse_pas_la_trace(self):
        """Le ``ChangeLog`` d'une modification est écrit en ``pre_save``,
        avant l'``UPDATE`` : si celui-ci échoue, l'entrée doit disparaître
        avec lui. ``_save_table`` est l'écriture elle-même, après les
        signaux — c'est là qu'une base qui refuse se manifeste."""
        self.login(self.doo)
        avant = ChangeLog.objects.filter(
            model_name=ChangeLog.Models.TEAM, object_id=self.team.pk
        ).count()

        with mock.patch.object(Team, "_save_table", side_effect=JOURNAL_INDISPONIBLE), \
                self.assertRaises(DatabaseError):
            self.client.patch(f"/api/teams/{self.team.pk}/", {"name": "Équipe Kara"})

        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Équipe Lomé")
        self.assertEqual(
            ChangeLog.objects.filter(
                model_name=ChangeLog.Models.TEAM, object_id=self.team.pk
            ).count(),
            avant,
            "l'historique atteste d'une modification que la base n'a pas",
        )
