"""Tests des enveloppes, des réallocations et de la conversion en FCFA."""

from datetime import date
from decimal import Decimal

from django.core.cache import cache
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.aggregates import to_xof
from budget.models import Budget, BudgetReallocation, ExchangeRate
from core.models import Country, Project


class BudgetTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", country_ref="CT-01",
            currency="XOF", timezone="Africa/Abidjan",
        )
        self.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.doo = make_user("do.innov", Role.SUPER_ADMIN)
        self.rep_togo = make_user("togo.innov", Role.COUNTRY_MANAGER, [self.togo])

        self.budget_togo = Budget.objects.create(
            country=self.togo, year=2026, amount=Decimal("10000000.00")
        )
        self.budget_ivoire = Budget.objects.create(
            country=self.ivoire, year=2026, amount=Decimal("25000000.00")
        )

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


class BudgetAccessTests(BudgetTestCase):
    def test_attribution_par_le_siege(self):
        self.login(self.doo)

        response = self.client.post(
            "/api/budgets/",
            {"country": self.ivoire.pk, "year": 2027, "amount": "30000000.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_representant_pays_ne_cree_pas_de_budget(self):
        """L'attribution des enveloppes relève du DO (§4)."""
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/budgets/",
            {"country": self.togo.pk, "year": 2027, "amount": "500.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_representant_pays_voit_son_budget_seulement(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/budgets/")

        refs = [b["country_ref"] for b in response.data["results"]]
        self.assertEqual(refs, ["TG-02"])

    def test_enveloppe_unique_par_pays_et_annee(self):
        self.login(self.doo)

        response = self.client.post(
            "/api/budgets/",
            {"country": self.togo.pk, "year": 2026, "amount": "1.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sous_enveloppe_doit_appartenir_au_pays(self):
        projet_ivoire = Project.objects.create(country=self.ivoire, name="Projet CI")
        self.login(self.doo)

        response = self.client.post(
            "/api/budgets/",
            {
                "country": self.togo.pk, "year": 2026,
                "project": projet_ivoire.pk, "amount": "1000.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", response.data)


class BudgetFiguresTests(BudgetTestCase):
    def test_solde_disponible_calcule_cote_serveur(self):
        self.login(self.doo)

        response = self.client.get(f"/api/budgets/{self.budget_togo.pk}/")

        figures = response.data["figures"]
        # Aucune dépense n'existe encore : le disponible égale l'enveloppe.
        self.assertEqual(figures["consumed"], "0.00")
        self.assertEqual(figures["remaining"], "10000000.00")

    def test_champs_nullables_toujours_presents(self):
        """Le contrat de l'API ne doit pas varier selon les données : une
        enveloppe de pays renvoie `project_name: null`, pas une clé absente."""
        self.login(self.doo)

        response = self.client.get(f"/api/budgets/{self.budget_togo.pk}/")

        self.assertIn("project_name", response.data)
        self.assertIsNone(response.data["project_name"])

    def test_consolidation_par_pays(self):
        self.login(self.doo)

        response = self.client.get("/api/budgets/summary/")

        rows = {row["country_ref"]: row for row in response.data["countries"]}
        self.assertEqual(rows["TG-02"]["remaining"], "10000000.00")
        self.assertEqual(response.data["total_remaining_xof"], "35000000.00")
        self.assertEqual(response.data["unconverted_currencies"], [])

    def test_consolidation_ignore_les_sous_enveloppes(self):
        """Une sous-enveloppe découpe l'enveloppe pays : l'additionner
        compterait deux fois le même argent."""
        projet = Project.objects.create(country=self.togo, name="Projet TG")
        Budget.objects.create(
            country=self.togo, year=2026, project=projet, amount=Decimal("4000000.00")
        )
        self.login(self.doo)

        response = self.client.get("/api/budgets/summary/")

        togo = next(r for r in response.data["countries"] if r["country_ref"] == "TG-02")
        self.assertEqual(togo["allocated"], "10000000.00")
        self.assertEqual(togo["sub_allocated"], "4000000.00")


class ExchangeRateTests(BudgetTestCase):
    def test_conversion_au_taux_en_vigueur_a_la_date(self):
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("655.957"), valid_from=date(2026, 1, 1)
        )
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("700.000000"), valid_from=date(2026, 6, 1)
        )

        self.assertEqual(to_xof(Decimal("10"), "MAD", date(2026, 3, 1)), Decimal("6559.57"))
        self.assertEqual(to_xof(Decimal("10"), "MAD", date(2026, 9, 1)), Decimal("7000.00"))

    def test_devise_sans_taux_n_est_pas_convertie(self):
        """Renvoyer None plutôt que zéro : un total consolidé ne doit pas
        absorber silencieusement une devise inconnue."""
        self.assertIsNone(to_xof(Decimal("10"), "GHS"))

    def test_devise_de_consolidation(self):
        self.assertEqual(to_xof(Decimal("1500"), "XOF"), Decimal("1500.00"))

    def test_total_signale_les_devises_non_converties(self):
        self.ivoire.currency = "GHS"
        self.ivoire.save()
        self.login(self.doo)

        response = self.client.get("/api/budgets/summary/")

        self.assertEqual(response.data["unconverted_currencies"], ["GHS"])
        self.assertEqual(response.data["total_remaining_xof"], "10000000.00")


class ReallocationTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        self.projet = Project.objects.create(country=self.togo, name="Projet TG")
        self.sous_enveloppe = Budget.objects.create(
            country=self.togo, year=2026, project=self.projet, amount=Decimal("0.00")
        )
        self.login(self.doo)

    def _demander(self, amount="1000000.00", reason="Renfort du projet"):
        return self.client.post(
            "/api/reallocations/",
            {
                "source": self.budget_togo.pk,
                "target": self.sous_enveloppe.pk,
                "amount": amount,
                "reason": reason,
            },
        )

    def test_justification_obligatoire(self):
        response = self._demander(reason="   ")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)

    def test_montant_superieur_a_la_source_refuse(self):
        response = self._demander(amount="99000000.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approbation_transfere_les_montants(self):
        realloc_id = self._demander().data["id"]

        response = self.client.post(f"/api/reallocations/{realloc_id}/approve/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.budget_togo.refresh_from_db()
        self.sous_enveloppe.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("9000000.00"))
        self.assertEqual(self.sous_enveloppe.amount, Decimal("1000000.00"))
        self.assertEqual(response.data["decided_by"], "do.innov")

    def test_refus_sans_motif_impossible(self):
        realloc_id = self._demander().data["id"]

        response = self.client.post(f"/api/reallocations/{realloc_id}/reject/", {"note": ""})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("10000000.00"))

    def test_refus_motive(self):
        realloc_id = self._demander().data["id"]

        response = self.client.post(
            f"/api/reallocations/{realloc_id}/reject/", {"note": "Hors priorité 2026"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], BudgetReallocation.Status.REJECTED)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("10000000.00"))

    def test_double_approbation_impossible(self):
        realloc_id = self._demander().data["id"]
        self.client.post(f"/api/reallocations/{realloc_id}/approve/")

        response = self.client.post(f"/api/reallocations/{realloc_id}/approve/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("9000000.00"))


class SubEnvelopeTests(BudgetTestCase):
    """§5.2 : une enveloppe se décline par projet, équipe ou manager."""

    def setUp(self):
        super().setUp()
        from core.models import Manager, Team

        self.equipe = Team.objects.create(country=self.togo, name="Équipe Lomé")
        self.manager = Manager.objects.create(name="Kodjo Mensah")
        self.login(self.doo)

    def _creer(self, **dimension):
        payload = {
            "country": self.togo.pk,
            "year": self.budget_togo.year,
            "amount": "100000.00",
        }
        payload.update(dimension)
        return self.client.post("/api/budgets/", payload)

    def test_sous_enveloppe_par_equipe(self):
        response = self._creer(team=self.equipe.pk)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["scope_kind"], "team")
        self.assertEqual(response.data["scope_label"], "Équipe Équipe Lomé")

    def test_sous_enveloppe_par_manager(self):
        response = self._creer(manager=self.manager.pk)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["scope_kind"], "manager")

    def test_une_seule_dimension_a_la_fois(self):
        """Deux dimensions rendraient l'imputation d'une dépense ambiguë."""
        projet = Project.objects.create(country=self.togo, name="Projet")

        response = self._creer(team=self.equipe.pk, project=projet.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_doublon_sur_la_meme_equipe_refuse(self):
        self._creer(team=self.equipe.pk)

        response = self._creer(team=self.equipe.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("équipe", str(response.data))

    def test_equipe_d_un_autre_pays_refusee(self):
        from core.models import Team

        autre = Team.objects.create(country=self.ivoire, name="Équipe Abidjan")

        response = self._creer(team=autre.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_les_sous_enveloppes_ne_gonflent_pas_le_total(self):
        self._creer(team=self.equipe.pk)

        response = self.client.get("/api/budgets/summary/")

        togo = next(
            r for r in response.data["countries"] if r["country_ref"] == "TG-02"
        )
        self.assertEqual(togo["allocated"], "10000000.00")
        self.assertEqual(togo["sub_allocated"], "100000.00")
