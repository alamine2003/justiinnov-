"""Alertes calculées : référence, délai de grâce, enveloppes vides."""

from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from budget.models import Budget
from core.models import WorkflowConfiguration
from expenses.models import Dossier
from expenses.workflow import Status
from reporting import alerts as alert_rules
from reporting.tests.test_dashboard import DashboardTestCase


class DepenseInhabituelleTests(DashboardTestCase):
    def _alertes(self):
        self.login(self.doo)
        response = self.client.get("/api/dashboard/", {"year": self.year})
        return [a for a in response.data["alerts"] if a["kind"] == "unusual_expense"]

    def test_la_reference_est_celle_du_perimetre_et_de_l_exercice(self):
        """Régression : la moyenne se calculait sur toute la table. Une
        dépense énorme d'un exercice passé masquait celles de l'année."""
        self.make_expense(amount="2000000.00", status=Status.JUSTIFIED, budget=self.budget)
        ancienne = Dossier.objects.create(
            number="N-ANCIEN", label="Exercice passé", country=self.togo,
            date=date(self.year - 1, 6, 1), status=Status.CLOSED,
        )
        self.make_expense(
            dossier=ancienne, amount="100000000.00", status=Status.CLOSED,
            budget=self.budget,
            date=timezone.make_aware(timezone.datetime(self.year - 1, 6, 1, 10)),
        )

        alertes = self._alertes()

        self.assertEqual(len(alertes), 1)
        self.assertIn("2000000", alertes[0]["detail"])

    def test_une_seule_depense_n_est_jamais_inhabituelle(self):
        self.soumise.delete()

        self.assertEqual(self._alertes(), [])


class DelaiDeGraceTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        configuration = WorkflowConfiguration.charger()
        configuration.unjustified_alert_days = 30
        configuration.save()

    def _manquants(self):
        dossiers = Dossier.objects.filter(country=self.togo)
        return [
            a for a in alert_rules.proof_alerts(dossiers) if a["kind"] == "proof_missing"
        ]

    def test_un_dossier_recent_n_est_pas_encore_signale(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.date = timezone.now().date()
        self.dossier.save()

        self.assertEqual(self._manquants(), [])

    def test_le_delai_ecoule_declenche_l_alerte(self):
        self.dossier.status = Status.SUBMITTED
        self.dossier.date = timezone.now().date() - timedelta(days=40)
        self.dossier.save()

        self.assertEqual(len(self._manquants()), 1)

    def test_le_delai_est_applique_dans_la_requete(self):
        """Les dossiers récents ne doivent même pas être chargés : les tester
        en mémoire annotait et parcourait toute la table pour rien."""
        self.dossier.status = Status.SUBMITTED
        self.dossier.date = timezone.now().date()
        self.dossier.save()
        dossiers = Dossier.objects.filter(country=self.togo)

        with CaptureQueriesContext(connection) as captured:
            alert_rules.proof_alerts(dossiers)

        requete = next(
            q["sql"] for q in captured.captured_queries
            if 'FROM "expenses_dossier"' in q["sql"]
        )
        self.assertIn('"expenses_dossier"."date" <=', requete)


class EnveloppeVideTests(DashboardTestCase):
    def test_une_enveloppe_a_zero_avec_des_depenses_est_un_depassement(self):
        self.budget.amount = Decimal("0.00")
        self.budget.save()
        self.login(self.doo)

        response = self.client.get("/api/dashboard/", {"year": self.year})

        alerte = next(a for a in response.data["alerts"] if a["kind"] == "budget_overrun")
        self.assertEqual(alerte["level"], "critical")
        self.assertIn("500000.00", alerte["detail"])
        # Un pourcentage d'une enveloppe nulle n'a pas de sens : il est tu.
        self.assertNotIn("%", alerte["detail"])

    def test_une_enveloppe_a_zero_sans_depense_ne_dit_rien(self):
        self.budget_ivoire.amount = Decimal("0.00")
        self.budget_ivoire.save()
        self.login(self.doo)

        response = self.client.get("/api/dashboard/", {"year": self.year})

        self.assertFalse(
            any(a["country"] == self.ivoire.pk for a in response.data["alerts"])
        )

    def test_une_enveloppe_desactivee_ne_declenche_rien(self):
        Budget.objects.filter(pk=self.budget.pk).update(
            amount=Decimal("100000.00"), is_active=False
        )
        self.login(self.doo)

        response = self.client.get("/api/dashboard/", {"year": self.year})

        self.assertFalse(
            any(a["kind"] == "budget_overrun" for a in response.data["alerts"])
        )
        self.assertNotIn(
            self.togo.pk, [row["country"] for row in response.data["countries"]]
        )
