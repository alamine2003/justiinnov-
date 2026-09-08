"""Des chiffres cohérents et reproductibles.

Audit du 8 septembre 2026, §4.1 et §4.2 : un exercice clos se consolidait
au taux du jour ; les taux se modifiaient rétroactivement ; l'export
totalisait des brouillons que l'écran excluait ; désactiver une enveloppe
faisait disparaître son consommé ; un pays sans enveloppe de pays affichait
un attribué nul et un disponible négatif ; un taux croisé était arrondi
avant la multiplication.
"""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.utils import timezone
from rest_framework import status

from budget.aggregates import (
    consolidation_par_pays,
    convert,
    current_rates,
    date_de_reference,
)
from budget.models import Budget, ExchangeRate
from core.models import Country, Project
from expenses.tests.base import ExpenseTestCase
from expenses.workflow import Status


class DateDeReferenceTests(ExpenseTestCase):
    def test_un_exercice_clos_se_lit_a_sa_cloture(self):
        self.assertEqual(date_de_reference(self.year - 1), date(self.year - 1, 12, 31))

    def test_l_exercice_en_cours_se_lit_ce_jour(self):
        self.assertEqual(date_de_reference(self.year), timezone.localdate())


class StabiliteHistoriqueTests(ExpenseTestCase):
    """Un rapport sur un exercice clos donne le même chiffre l'an prochain."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.senegal = Country.objects.create(
            name="Sénégal", code="SN", country_ref="SN-01", currency="EUR",
            timezone="Africa/Dakar",
        )
        cls.passe = cls.year - 1
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("655.957000"),
            valid_from=date(cls.passe, 1, 1),
        )
        cls.enveloppe_passee = Budget.objects.create(
            country=cls.senegal, year=cls.passe, amount=Decimal("1000.00")
        )
        cls.enveloppe_courante = Budget.objects.create(
            country=cls.senegal, year=cls.year, amount=Decimal("1000.00")
        )

    def _summary(self, year):
        self.login(self.doo)
        response = self.client.get("/api/budgets/summary/", {"year": year})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return next(r for r in response.data["countries"] if r["currency"] == "EUR")

    def test_un_nouveau_taux_ne_change_pas_l_exercice_clos(self):
        self.assertEqual(self._summary(self.passe)["remaining_xof"], "655957.00")

        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("900.000000"), valid_from=timezone.localdate()
        )

        self.assertEqual(self._summary(self.passe)["remaining_xof"], "655957.00")
        self.assertEqual(self._summary(self.year)["remaining_xof"], "900000.00")

    def test_le_tableau_de_bord_et_la_consolidation_disent_la_meme_chose(self):
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("900.000000"), valid_from=timezone.localdate()
        )
        self.login(self.doo)

        tableau = self.client.get("/api/dashboard/", {"year": self.passe}).data
        summary = self.client.get("/api/budgets/summary/", {"year": self.passe}).data

        self.assertEqual(
            str(tableau["consolidated_xof"]["remaining"]), summary["total_remaining_xof"]
        )
        self.assertEqual(tableau["totals"]["allocated"], "655957.00")

    def test_la_liste_des_enveloppes_lit_chaque_exercice_a_sa_date(self):
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("900.000000"), valid_from=timezone.localdate()
        )
        self.login(self.doo)

        response = self.client.get("/api/budgets/", {"country": self.senegal.pk})

        par_exercice = {r["year"]: r["figures"]["amount_xof"] for r in response.data["results"]}
        self.assertEqual(par_exercice[self.passe], "655957.00")
        self.assertEqual(par_exercice[self.year], "900000.00")

    def test_la_revalorisation_se_demande_et_se_nomme(self):
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("900.000000"), valid_from=timezone.localdate()
        )
        historique, revalorise = StringIO(), StringIO()

        call_command("consolidation", annee=self.passe, stdout=historique)
        call_command("consolidation", annee=self.passe, taux_du_jour=True, stdout=revalorise)

        self.assertIn("rapport historique", historique.getvalue())
        self.assertIn(f"31/12/{self.passe}", historique.getvalue())
        self.assertIn("655957.00", historique.getvalue())
        self.assertIn("REVALORISATION", revalorise.getvalue())
        self.assertIn("900000.00", revalorise.getvalue())


class TauxImmuablesTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.doo)
        self.taux = ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("655.957000"),
            valid_from=timezone.localdate() - timedelta(days=30),
        )

    def test_un_taux_publie_ne_se_modifie_pas(self):
        for methode in (self.client.patch, self.client.put):
            response = methode(
                f"/api/exchange-rates/{self.taux.pk}/",
                {"currency": "EUR", "rate_to_xof": "1.000000", "valid_from": str(self.taux.valid_from)},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.taux.refresh_from_db()
        self.assertEqual(self.taux.rate_to_xof, Decimal("655.957000"))

    def test_un_taux_ne_se_publie_pas_avant_le_dernier(self):
        response = self.client.post(
            "/api/exchange-rates/",
            {"currency": "EUR", "rate_to_xof": "600.000000",
             "valid_from": str(self.taux.valid_from - timedelta(days=1))},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("valid_from", response.data)

    def test_un_taux_se_publie_apres_le_dernier(self):
        response = self.client.post(
            "/api/exchange-rates/",
            {"currency": "EUR", "rate_to_xof": "900.000000", "valid_from": str(timezone.localdate())},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class EnveloppeDesactiveeTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.doo)

    def test_une_enveloppe_avec_des_lignes_declarees_ne_se_desactive_pas(self):
        self.make_expense(status=Status.SUBMITTED, budget=self.budget)

        response = self.client.patch(f"/api/budgets/{self.budget.pk}/", {"is_active": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data)
        self.budget.refresh_from_db()
        self.assertTrue(self.budget.is_active)

    def test_une_enveloppe_sans_ligne_declaree_se_desactive(self):
        self.make_expense(status=Status.DRAFT)

        response = self.client.patch(f"/api/budgets/{self.budget.pk}/", {"is_active": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class PaysSansEnveloppeDePaysTests(ExpenseTestCase):
    def test_les_sous_enveloppes_sont_l_attribue_du_pays(self):
        projet = Project.objects.create(country=self.ivoire, name="Salon Abidjan")
        self.budget_ivoire.delete()
        Budget.objects.create(
            country=self.ivoire, year=self.year, amount=Decimal("300000.00"), project=projet
        )
        budgets = Budget.objects.select_related("country").filter(country=self.ivoire, year=self.year)

        rows, _ = consolidation_par_pays(budgets, rates=current_rates())

        (ligne,) = rows
        self.assertEqual(ligne["allocated"], Decimal("300000.00"))
        self.assertEqual(ligne["sub_allocated"], Decimal("300000.00"))
        self.assertEqual(ligne["remaining"], Decimal("300000.00"))
        self.assertEqual(ligne["execution_rate"], Decimal("0.0000"))


class TauxCroiseTests(ExpenseTestCase):
    def test_le_montant_est_calcule_sur_le_rapport_exact(self):
        aujourd_hui = timezone.localdate()
        ExchangeRate.objects.create(currency="GNF", rate_to_xof=Decimal("0.076000"), valid_from=aujourd_hui)
        ExchangeRate.objects.create(currency="EUR", rate_to_xof=Decimal("655.957000"), valid_from=aujourd_hui)

        montant, taux = convert(Decimal("10000000.00"), "GNF", "EUR", aujourd_hui)

        exact = (Decimal("10000000.00") * Decimal("0.076000") / Decimal("655.957000")).quantize(Decimal("0.01"))
        self.assertEqual(montant, exact)
        self.assertEqual(montant, Decimal("1158.61"))
        self.assertEqual(taux, Decimal("0.000116"))  # indicatif, six décimales

    def test_vers_le_fcfa_rien_ne_change(self):
        aujourd_hui = timezone.localdate()
        ExchangeRate.objects.create(currency="EUR", rate_to_xof=Decimal("655.957000"), valid_from=aujourd_hui)

        montant, taux = convert(Decimal("100.00"), "EUR", "XOF", aujourd_hui)

        self.assertEqual((montant, taux), (Decimal("65595.70"), Decimal("655.957000")))
