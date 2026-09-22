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
    niveau_d_execution,
    seuil_d_alerte,
)
from budget.models import Budget, ExchangeRate
from core.models import Country, Project, WorkflowConfiguration
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


class EnveloppesDejaDesactiveesTests(ExpenseTestCase):
    """L'interdiction ne corrige pas l'existant : ce qui a déjà été
    désactivé avec des dépenses déclarées doit être trouvable."""

    def test_l_existant_est_inventorie_sans_etre_modifie(self):
        self.make_expense(status=Status.SUBMITTED, budget=self.budget, amount="70000.00")
        # Désactivée par un chemin qui ne passe pas par l'API (avant le
        # correctif, ou par un script) : c'est le cas à rattraper.
        Budget.objects.filter(pk=self.budget.pk).update(is_active=False)
        sortie = StringIO()

        call_command("enveloppes_desactivees", stdout=sortie)

        texte = sortie.getvalue()
        self.assertIn("1 ligne(s) déclarée(s)", texte)
        self.assertIn("70000.00", texte)
        self.assertIn("1 enveloppe(s) désactivée(s)", texte)
        self.budget.refresh_from_db()
        self.assertFalse(self.budget.is_active, "la commande ne modifie rien")

    def test_une_enveloppe_desactivee_sans_ligne_declaree_n_est_pas_signalee(self):
        Budget.objects.filter(pk=self.budget.pk).update(is_active=False)
        sortie = StringIO()

        call_command("enveloppes_desactivees", stdout=sortie)

        self.assertIn("Aucune enveloppe désactivée", sortie.getvalue())


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


class NonRepartiTests(ExpenseTestCase):
    """``unallocated`` : ce que l'enveloppe du pays n'a pas encore découpé.

    L'interface le calculait elle-même (``allocated - sub_allocated``), contre
    la règle « rien ne se calcule dans l'interface » : le serveur le publie.
    """

    def test_la_part_non_decoupee_est_publiee(self):
        projet = Project.objects.create(country=self.ivoire, name="Salon Abidjan")
        Budget.objects.create(
            country=self.ivoire, year=self.year, amount=Decimal("300000.00"), project=projet
        )
        budgets = Budget.objects.select_related("country").filter(
            country=self.ivoire, year=self.year
        )

        rows, _ = consolidation_par_pays(budgets, rates=current_rates())

        (ligne,) = rows
        self.assertEqual(
            ligne["unallocated"], ligne["allocated"] - ligne["sub_allocated"]
        )
        self.assertEqual(ligne["sub_allocated"], Decimal("300000.00"))

    def test_un_pays_sans_enveloppe_de_pays_n_a_rien_a_repartir(self):
        # Les sous-enveloppes deviennent alors l'attribué du pays : il ne
        # reste rien à découper, et non un négatif.
        projet = Project.objects.create(country=self.ivoire, name="Salon Abidjan")
        self.budget_ivoire.delete()
        Budget.objects.create(
            country=self.ivoire, year=self.year, amount=Decimal("300000.00"), project=projet
        )
        budgets = Budget.objects.select_related("country").filter(
            country=self.ivoire, year=self.year
        )

        rows, _ = consolidation_par_pays(budgets, rates=current_rates())

        (ligne,) = rows
        self.assertEqual(ligne["unallocated"], Decimal("0.00"))

    def test_un_decoupage_qui_depasse_l_enveloppe_se_voit(self):
        # Un négatif dit que les sous-enveloppes dépassent l'enveloppe du
        # pays. Le masquer par un plancher à zéro cacherait le fait.
        projet = Project.objects.create(country=self.ivoire, name="Salon Abidjan")
        Budget.objects.create(
            country=self.ivoire,
            year=self.year,
            amount=self.budget_ivoire.amount + Decimal("1000.00"),
            project=projet,
        )
        budgets = Budget.objects.select_related("country").filter(
            country=self.ivoire, year=self.year
        )

        rows, _ = consolidation_par_pays(budgets, rates=current_rates())

        (ligne,) = rows
        self.assertEqual(ligne["unallocated"], Decimal("-1000.00"))


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


class NiveauDExecutionTests(ExpenseTestCase):
    """``execution_level`` : le taux jugé côté serveur, contre les seuils
    d'alerte de la configuration, pour que l'interface colore sans les
    recopier."""

    def _configurer(self, seuils):
        configuration = WorkflowConfiguration.charger()
        configuration.alert_thresholds = seuils
        configuration.save()

    def test_le_niveau_suit_le_dernier_seuil_sous_cent(self):
        self._configurer([70, 90, 100])
        seuil = seuil_d_alerte()

        self.assertEqual(seuil, 90)
        self.assertEqual(niveau_d_execution(Decimal("0.85"), seuil), "ok")
        self.assertEqual(niveau_d_execution(Decimal("0.90"), seuil), "warning")
        self.assertEqual(niveau_d_execution(Decimal("1.01"), seuil), "exceeded")
        self.assertEqual(niveau_d_execution(None, seuil), "ok")

    def test_sans_seuil_sous_cent_le_repli_est_quatre_vingts(self):
        self._configurer([100, 120])

        self.assertEqual(seuil_d_alerte(), 80)
        self.assertEqual(niveau_d_execution(Decimal("0.79")), "ok")
        self.assertEqual(niveau_d_execution(Decimal("0.80")), "warning")

    def test_le_niveau_est_publie_partout_ou_le_taux_l_est(self):
        """Enveloppe, ligne de pays du tableau de bord, totaux consolidés :
        chacun porte ``execution_level`` à côté d'``execution_rate``."""
        self._configurer([70, 90, 100])
        # 950 000 consommés sur 1 000 000 : 95 %, au-dessus de 90.
        self.make_expense(amount="950000.00", status=Status.JUSTIFIED, budget=self.budget)
        self.login(self.doo)

        enveloppe = self.client.get(f"/api/budgets/{self.budget.pk}/").data["figures"]
        tableau = self.client.get("/api/dashboard/", {"year": self.year, "country": self.togo.pk}).data

        self.assertEqual(enveloppe["execution_rate"], "0.9500")
        self.assertEqual(enveloppe["execution_level"], "warning")
        self.assertEqual(tableau["countries"][0]["execution_level"], "warning")
        self.assertEqual(tableau["totals"]["execution_level"], "warning")


class TauxCourantTests(ExpenseTestCase):
    """``is_current`` : le taux applicable aujourd'hui, jamais un taux futur."""

    def test_le_taux_du_jour_est_courant_et_le_futur_ne_l_est_pas(self):
        aujourd_hui = timezone.localdate()
        ancien = ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("650.000000"),
            valid_from=aujourd_hui - timedelta(days=30),
        )
        courant = ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("655.957000"), valid_from=aujourd_hui
        )
        # L'API refuse une date future : le cas ne peut venir que de la base.
        futur = ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("700.000000"),
            valid_from=aujourd_hui + timedelta(days=1),
        )
        self.login(self.doo)

        response = self.client.get("/api/exchange-rates/", {"currency": "EUR"})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        courants = {row["id"]: row["is_current"] for row in response.data["results"]}
        self.assertEqual(courants, {ancien.pk: False, courant.pk: True, futur.pk: False})


class EnveloppeInactiveHorsDesTotauxTests(ExpenseTestCase):
    """Une enveloppe désactivée sort de la consolidation comme du tableau
    de bord : deux écrans, un chiffre."""

    def setUp(self):
        super().setUp()
        Budget.objects.filter(pk=self.budget_ivoire.pk).update(is_active=False)
        self.login(self.doo)

    def test_la_consolidation_et_le_tableau_de_bord_l_ignorent(self):
        summary = self.client.get("/api/budgets/summary/", {"year": self.year})
        dashboard = self.client.get("/api/dashboard/", {"year": self.year})

        self.assertEqual([r["country_ref"] for r in summary.data["countries"]], ["TG-02"])
        self.assertEqual([r["country_ref"] for r in dashboard.data["countries"]], ["TG-02"])
        self.assertEqual(summary.data["total_remaining_xof"], "1000000.00")
        self.assertEqual(dashboard.data["totals"]["allocated"], "1000000.00")
        self.assertEqual(
            summary.data["countries"][0]["remaining"],
            dashboard.data["countries"][0]["remaining"],
        )

    def test_elle_reste_lisible_quand_on_la_demande(self):
        summary = self.client.get(
            "/api/budgets/summary/", {"year": self.year, "is_active": "false"}
        )

        self.assertEqual([r["country_ref"] for r in summary.data["countries"]], ["CT-01"])
