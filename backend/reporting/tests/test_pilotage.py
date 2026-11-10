"""Agrégats du pilotage, appelés sans passer par HTTP.

``reporting.pilotage`` calcule ce que ``/api/dashboard/`` et
``/api/dashboard/breakdown/`` rendent (décision 124). Appelé directement
sur les mêmes querysets cloisonnés, il doit redonner la réponse au
caractère près : chaînes de montants et de taux, clés, ordre.
"""

import json

from django.utils import timezone

from accounts.permissions import get_access
from budget.aggregates import current_rates, date_de_reference
from expenses.workflow import Status
from reporting import pilotage
from reporting.scope import fuseau_de, querysets_pour

from .test_dashboard import DashboardTestCase


def _texte(valeur):
    return json.dumps(valeur, ensure_ascii=False)


class PilotageCommeLeTableauDeBordTests(DashboardTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # De quoi remplir chaque tuile de la charge de travail.
        cls.make_expense(cls, amount="12345.67", status=Status.DRAFT)
        cls.make_expense(cls, amount="70000.00", status=Status.UNJUSTIFIED, budget=cls.budget)

    def test_memes_chiffres_que_le_tableau_de_bord(self):
        self.login(self.doo)
        reponse = json.loads(
            self.client.get("/api/dashboard/", {"year": self.year}).content
        )

        budgets, dossiers, expenses = querysets_pour(get_access(self.doo), self.year)
        rates = current_rates(on_date=date_de_reference(self.year))
        rows, consolidated = pilotage.par_pays(budgets, rates)

        self.assertEqual(_texte(rows), _texte(reponse["countries"]))
        self.assertEqual(_texte(consolidated), _texte(reponse["consolidated_xof"]))
        self.assertEqual(
            _texte(pilotage.totaux_consolides(rows, rates)), _texte(reponse["totals"])
        )
        self.assertEqual(
            _texte(pilotage.charge_de_travail(dossiers, expenses)),
            _texte(reponse["workload"]),
        )
        self.assertEqual(reponse["workload"]["expenses_unjustified"], 1)

    def test_memes_repartitions_que_la_vue(self):
        self.login(self.doo)
        reponse = json.loads(
            self.client.get(
                "/api/dashboard/breakdown/", {"year": self.year, "country": self.togo.pk}
            ).content
        )

        expenses = querysets_pour(get_access(self.doo), self.year, self.togo.pk)[2]
        repartition = pilotage.repartition(
            pilotage.depenses_comptees(expenses), fuseau_de(self.togo)
        )

        self.assertEqual(_texte({"year": self.year, **repartition}), _texte(reponse))


class TotauxConsolidesTests(DashboardTestCase):
    """Fonction pure sur des lignes déjà rendues."""

    LIGNE = {
        "allocated": "1000.00", "engaged": "100.00", "consumed": "400.00",
        "justified": "300.00", "remaining": "500.00",
    }

    def test_une_devise_sans_taux_est_ecartee_et_nommee(self):
        rates = current_rates(on_date=timezone.localdate())
        totaux = pilotage.totaux_consolides(
            [{**self.LIGNE, "currency": "XOF"}, {**self.LIGNE, "currency": "GNF"}], rates
        )

        self.assertEqual(totaux["currency"], "XOF")
        self.assertEqual(totaux["allocated"], "1000.00")
        self.assertEqual(totaux["gap"], "100.00")
        self.assertEqual(totaux["execution_rate"], "0.5000")
        self.assertEqual(totaux["justification_rate"], "0.7500")
        self.assertEqual(totaux["unconverted_currencies"], ["GNF"])

    def test_sans_ligne_les_montants_sont_a_zero(self):
        totaux = pilotage.totaux_consolides([], {})

        self.assertEqual(totaux["allocated"], "0.00")
        self.assertIsNone(totaux["execution_rate"])
        self.assertIsNone(totaux["justification_rate"])
        self.assertEqual(totaux["unconverted_currencies"], [])
