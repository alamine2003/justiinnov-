"""Tests des enveloppes, des réallocations et de la conversion en FCFA."""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from budget.aggregates import (
    CENTS,
    consolidation_par_pays,
    convert,
    current_rates,
    to_xof,
)
from budget.models import Budget, BudgetReallocation, ExchangeRate, OverrunPolicy
from core.models import Country, Manager, Project, Team
from expenses.models import Dossier, Expense
from expenses.workflow import Status


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
        # La direction seule attribue et arbitre (BUDGET_WRITE_ROLES =
        # super administrateurs). Deux comptes distincts : celui qui demande
        # une réallocation ne peut pas la décider.
        self.siege = make_user("ceo.innov", Role.SUPER_ADMIN)
        self.doo = make_user("do.innov", Role.SUPER_ADMIN)
        # Une direction restreinte au Togo : le périmètre n'est effectif que
        # sous ``direction_restreinte()``, voir plus bas.
        self.doo_togo = make_user("do.togo", Role.SUPER_ADMIN, [self.togo])
        # Le DF constate les dépenses ; il n'attribue ni n'arbitre, global
        # ou restreint.
        self.df = make_user("df.innov", Role.DF)
        self.df_togo = make_user("df.togo", Role.DF, [self.togo])
        self.rep_togo = make_user("togo.innov", Role.MANAGER, [self.togo])

        self.budget_togo = Budget.objects.create(
            country=self.togo, year=2026, amount=Decimal("10000000.00")
        )
        self.budget_ivoire = Budget.objects.create(
            country=self.ivoire, year=2026, amount=Decimal("25000000.00")
        )

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def direction_restreinte(self):
        """Rend effective la restriction de périmètre de ``doo_togo``.

        Aucun rôle habilité à écrire une enveloppe ne se restreint
        aujourd'hui : les super administrateurs sont toujours globaux
        (``ALWAYS_GLOBAL_ROLES``). Les validateurs de périmètre
        (``PerimetreMixin``, ``_verrouiller``) restent en place pour le jour
        où cela existera ; ces tests les couvrent en levant, le temps d'un
        appel, la règle qui rend la direction toujours globale.
        """
        return mock.patch("accounts.models.ALWAYS_GLOBAL_ROLES", frozenset())

    def imputer(self, budget, amount, statut=Status.SUBMITTED):
        """Une dépense imputée à l'enveloppe, dans l'état demandé."""
        dossier = Dossier.objects.create(
            number=f"D-{Expense.objects.count() + 1:04d}", label="Mission",
            country=budget.country, date=date(budget.year, 3, 1),
            status=Status.SUBMITTED,
        )
        return Expense.objects.create(
            dossier=dossier, country=budget.country, budget=budget,
            date=timezone.now(), title="Carburant",
            amount=Decimal(amount), status=statut,
        )


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

    def test_le_df_n_attribue_pas_d_enveloppe(self):
        """Le DF constate ce qui a été dépensé ; il ne fixe pas ce qui peut
        l'être. Global ou restreint à son pays, il lit les enveloppes et
        n'en écrit aucune — ni création, ni montant."""
        for compte in (self.df, self.df_togo):
            with self.subTest(compte=compte.username):
                self.login(compte)

                lecture = self.client.get("/api/budgets/")
                creation = self.client.post(
                    "/api/budgets/",
                    {"country": self.togo.pk, "year": 2027, "amount": "1.00"},
                )
                montant = self.client.patch(
                    f"/api/budgets/{self.budget_togo.pk}/", {"amount": "1.00"}
                )

                self.assertEqual(lecture.status_code, status.HTTP_200_OK)
                self.assertEqual(creation.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(montant.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Budget.objects.filter(year=2027).exists())
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("10000000.00"))

    def test_la_rh_n_attribue_pas_d_enveloppe(self):
        """L'administrateur tient les comptes et le référentiel ; l'argent
        est l'affaire de la direction."""
        self.login(make_user("rh.innov", Role.ADMIN))

        response = self.client.post(
            "/api/budgets/",
            {"country": self.togo.pk, "year": 2027, "amount": "1.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pays_hors_perimetre_simplement_invalide(self):
        """Une direction restreinte au Togo ne crée rien en Côte d'Ivoire —
        et la réponse ne distingue pas « hors périmètre » d'« inexistant »."""
        self.login(self.doo_togo)

        with self.direction_restreinte():
            response = self.client.post(
                "/api/budgets/",
                {"country": self.ivoire.pk, "year": 2027, "amount": "1.00"},
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("country", response.data)
        self.assertNotIn("périmètre", str(response.data))

    def test_manager_hors_perimetre_simplement_invalide(self):
        manager = Manager.objects.create(name="Awa Diallo")
        self.ivoire.managers.add(manager)
        self.login(self.doo_togo)

        with self.direction_restreinte():
            response = self.client.post(
                "/api/budgets/",
                {
                    "country": self.togo.pk, "year": 2027,
                    "manager": manager.pk, "amount": "1.00",
                },
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manager", response.data)

    def test_manager_doit_etre_rattache_au_pays(self):
        """Un manager n'a pas de pays propre : c'est ``Country.managers``
        qui le rattache. Une sous-enveloppe pour un manager étranger au pays
        ne recevrait jamais de dépense."""
        manager = Manager.objects.create(name="Awa Diallo")
        self.ivoire.managers.add(manager)
        self.login(self.siege)

        response = self.client.post(
            "/api/budgets/",
            {
                "country": self.togo.pk, "year": 2027,
                "manager": manager.pk, "amount": "1.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manager", response.data)

    def test_liste_cloisonnee_sans_distinct(self):
        """Le pays est porté par l'enveloppe : le filtre de périmètre ne
        multiplie aucune ligne, et un DISTINCT sur les agrégats de
        consommation ne ferait que coûter un tri."""
        self.login(self.rep_togo)

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get("/api/budgets/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        requetes_budget = [
            q["sql"] for q in captured.captured_queries
            if '"budget_budget"' in q["sql"] and "SELECT" in q["sql"]
        ]
        self.assertTrue(requetes_budget)
        for sql in requetes_budget:
            self.assertNotIn("DISTINCT", sql)


class EnveloppeImputeeTests(BudgetTestCase):
    """Une enveloppe qui porte des dépenses ne se déplace plus."""

    def setUp(self):
        super().setUp()
        self.imputer(self.budget_togo, "50000.00")
        self.login(self.siege)

    def test_annee_et_pays_figes(self):
        response = self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"year": 2027}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("year", response.data)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.year, 2026)

    def test_decoupage_fige(self):
        projet = Project.objects.create(country=self.togo, name="Projet TG")

        response = self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"project": projet.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", response.data)

    def test_le_montant_reste_modifiable(self):
        """Seul le rattachement est figé : réviser l'enveloppe reste
        possible, et tracé."""
        response = self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/", {"amount": "12000000.00"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_renvoyer_la_meme_valeur_n_est_pas_un_deplacement(self):
        response = self.client.patch(
            f"/api/budgets/{self.budget_togo.pk}/",
            {"country": self.togo.pk, "year": 2026, "amount": "12000000.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


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


    def test_consolidation_porte_sur_l_annee_en_cours_par_defaut(self):
        """Sans ``?year=``, la consolidation additionnait toutes les années
        d'un pays comme une seule enveloppe."""
        Budget.objects.create(
            country=self.togo, year=2025, amount=Decimal("7000000.00")
        )
        self.login(self.doo)

        sans_annee = self.client.get("/api/budgets/summary/")
        annee_2025 = self.client.get("/api/budgets/summary/", {"year": 2025})

        togo = next(r for r in sans_annee.data["countries"] if r["country_ref"] == "TG-02")
        self.assertEqual(togo["allocated"], "10000000.00")
        togo_2025 = next(
            r for r in annee_2025.data["countries"] if r["country_ref"] == "TG-02"
        )
        self.assertEqual(togo_2025["allocated"], "7000000.00")

    def test_meme_calcul_que_le_tableau_de_bord(self):
        """Résumé et tableau de bord passent par ``consolidation_par_pays`` :
        deux implémentations avaient fini par diverger."""
        self.ivoire.currency = "MAD"
        self.ivoire.save()
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("60.000000"), valid_from=date(2026, 1, 1)
        )
        self.imputer(self.budget_ivoire, "5000000.00", Status.JUSTIFIED)
        self.login(self.doo)

        resume = self.client.get("/api/budgets/summary/")
        tableau = self.client.get("/api/dashboard/", {"year": 2026})

        lignes_resume = {r["country_ref"]: r for r in resume.data["countries"]}
        lignes_tableau = {r["country_ref"]: r for r in tableau.data["countries"]}
        for ref, ligne in lignes_resume.items():
            for cle in ("allocated", "engaged", "consumed", "remaining", "remaining_xof"):
                self.assertEqual(ligne[cle], lignes_tableau[ref][cle], (ref, cle))
        self.assertEqual(
            resume.data["total_remaining_xof"],
            tableau.data["consolidated_xof"]["remaining"],
        )

    def test_consolidation_n_additionne_qu_en_fcfa(self):
        """Des dirhams et des francs ne s'additionnent pas : au niveau
        global, seul le consolidé en FCFA a un sens, et une devise sans taux
        en est exclue, nommément."""
        self.ivoire.currency = "MAD"
        self.ivoire.save()
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("60.000000"), valid_from=date(2026, 1, 1)
        )
        ghana = Country.objects.create(
            name="Guinée", code="GN", country_ref="GN-03", currency="GNF",
            timezone="Africa/Conakry",
        )
        Budget.objects.create(country=ghana, year=2026, amount=Decimal("1000.00"))
        budgets = Budget.objects.select_related("country").filter(year=2026)

        rows, consolidated = consolidation_par_pays(budgets, rates=current_rates())

        self.assertEqual(
            [row["remaining_xof"] for row in rows],
            [Decimal("1500000000.00"), None, Decimal("10000000.00")],
        )
        self.assertEqual(consolidated["remaining"], Decimal("1510000000.00"))
        self.assertEqual(consolidated["allocated"], Decimal("1510000000.00"))
        self.assertEqual(consolidated["unconverted_currencies"], ["GNF"])
        self.assertNotIn("currency", consolidated)


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
        self.assertIsNone(to_xof(Decimal("10"), "GNF"))

    def test_devise_de_consolidation(self):
        self.assertEqual(to_xof(Decimal("1500"), "XOF"), Decimal("1500.00"))

    def test_total_signale_les_devises_non_converties(self):
        self.ivoire.currency = "GNF"
        self.ivoire.save()
        self.login(self.doo)

        response = self.client.get("/api/budgets/summary/")

        self.assertEqual(response.data["unconverted_currencies"], ["GNF"])
        self.assertEqual(response.data["total_remaining_xof"], "10000000.00")

    def test_un_taux_date_du_futur_ne_s_applique_pas_encore(self):
        """Le taux « courant » est le dernier en vigueur *aujourd'hui*, pas le
        plus récent saisi : un taux daté de demain attend son jour."""
        demain = timezone.localdate() + timedelta(days=1)
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("60.000000"), valid_from=date(2026, 1, 1)
        )
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("99.000000"), valid_from=demain
        )

        self.assertEqual(to_xof(Decimal("10"), "MAD"), Decimal("600.00"))
        self.assertEqual(current_rates(), {"MAD": Decimal("60.000000")})
        self.assertEqual(current_rates(on_date=demain), {"MAD": Decimal("99.000000")})

    def test_taux_courants_en_une_requete(self):
        for devise, taux in (("MAD", "60"), ("EUR", "655.957"), ("GNF", "45")):
            for jour in (date(2025, 1, 1), date(2026, 1, 1)):
                ExchangeRate.objects.create(
                    currency=devise, rate_to_xof=Decimal(taux), valid_from=jour
                )

        with self.assertNumQueries(1):
            rates = current_rates()

        self.assertEqual(set(rates), {"MAD", "EUR", "GNF"})
        self.assertEqual(rates["EUR"], Decimal("655.957000"))
        # Le jeu de taux fourni fait foi : plus aucune requête.
        with self.assertNumQueries(0):
            self.assertEqual(to_xof(Decimal("2"), "MAD", rates=rates), Decimal("120.00"))
            self.assertIsNone(to_xof(Decimal("2"), "USD", rates=rates))

    def test_la_liste_ne_relit_pas_les_taux_par_enveloppe(self):
        """Régression N+1 : chaque enveloppe hors FCFA interrogeait deux fois
        la table des taux."""
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("60"), valid_from=date(2026, 1, 1)
        )
        self.ivoire.currency = "MAD"
        self.ivoire.save()
        self.login(self.doo)

        def requetes():
            with CaptureQueriesContext(connection) as captured:
                response = self.client.get("/api/budgets/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return len(captured.captured_queries)

        peu = requetes()
        for year in (2023, 2024, 2025):
            Budget.objects.create(country=self.ivoire, year=year, amount=Decimal("1.00"))
        self.assertEqual(requetes(), peu)

    def test_le_taux_fige_est_celui_reellement_applique(self):
        """Rejouer « montant d'origine × taux figé » doit redonner le montant
        enregistré : le taux est arrondi avant la multiplication."""
        ExchangeRate.objects.create(
            currency="EUR", rate_to_xof=Decimal("655.957"), valid_from=date(2026, 1, 1)
        )
        ExchangeRate.objects.create(
            currency="MAD", rate_to_xof=Decimal("61.3"), valid_from=date(2026, 1, 1)
        )

        converti, taux = convert(Decimal("12345.67"), "EUR", "MAD")

        self.assertEqual(taux, Decimal("10.700767"))
        self.assertEqual(converti, (Decimal("12345.67") * taux).quantize(CENTS))

    def test_seule_la_direction_saisit_un_taux(self):
        """Un taux change la valeur consolidée de toutes les enveloppes : il
        relève de ceux qui les attribuent. Le DF et la RH lisent les taux,
        n'en posent aucun."""
        rh = make_user("rh.innov", Role.ADMIN)
        for compte in (self.df, self.df_togo, rh):
            with self.subTest(compte=compte.username):
                self.login(compte)

                lecture = self.client.get("/api/exchange-rates/")
                ecriture = self.client.post(
                    "/api/exchange-rates/",
                    {"currency": "MAD", "rate_to_xof": "60", "valid_from": "2026-01-01"},
                )

                self.assertEqual(lecture.status_code, status.HTTP_200_OK)
                self.assertEqual(ecriture.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ExchangeRate.objects.filter(currency="MAD").exists())

    def test_taux_nul_ou_negatif_refuse(self):
        self.login(self.doo)

        for taux in ("0", "-1"):
            response = self.client.post(
                "/api/exchange-rates/",
                {"currency": "MAD", "rate_to_xof": taux, "valid_from": "2026-01-01"},
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, taux)
            self.assertIn("rate_to_xof", response.data)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            ExchangeRate.objects.create(
                currency="MAD", rate_to_xof=Decimal("0"), valid_from=date(2026, 1, 1)
            )

    def test_taux_date_du_futur_refuse(self):
        self.login(self.doo)
        demain = timezone.localdate() + timedelta(days=1)

        response = self.client.post(
            "/api/exchange-rates/",
            {"currency": "MAD", "rate_to_xof": "60", "valid_from": demain.isoformat()},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("valid_from", response.data)

    def test_devise_normalisee_en_majuscules(self):
        self.login(self.doo)

        response = self.client.post(
            "/api/exchange-rates/",
            {"currency": " mad ", "rate_to_xof": "60", "valid_from": "2026-01-01"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["currency"], "MAD")


class ReallocationTests(BudgetTestCase):
    def setUp(self):
        super().setUp()
        self.projet = Project.objects.create(country=self.togo, name="Projet TG")
        self.sous_enveloppe = Budget.objects.create(
            country=self.togo, year=2026, project=self.projet, amount=Decimal("0.00")
        )
        # Le siège demande, la direction des opérations décide.
        self.login(self.doo)

    def _demander(
        self, amount="1000000.00", reason="Renfort du projet",
        source=None, target=None, par=None,
    ):
        self.login(par or self.siege)
        response = self.client.post(
            "/api/reallocations/",
            {
                "source": (source or self.budget_togo).pk,
                "target": (target or self.sous_enveloppe).pk,
                "amount": amount,
                "reason": reason,
            },
        )
        self.login(self.doo)
        return response

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

    def test_pas_d_auto_approbation(self):
        """Demander et décider sont deux regards, même au siège."""
        realloc_id = self._demander(par=self.doo).data["id"]

        approbation = self.client.post(f"/api/reallocations/{realloc_id}/approve/")
        refus = self.client.post(
            f"/api/reallocations/{realloc_id}/reject/", {"note": "Non"}
        )

        self.assertEqual(approbation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refus.status_code, status.HTTP_403_FORBIDDEN)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("10000000.00"))
        self.assertEqual(
            BudgetReallocation.objects.get(pk=realloc_id).status,
            BudgetReallocation.Status.PENDING,
        )

    def test_reallocation_inter_devises_refusee(self):
        """Les montants sont dans la devise du pays : transférer des francs
        vers une enveloppe en dirhams créerait de l'argent."""
        self.ivoire.currency = "MAD"
        self.ivoire.save()

        response = self._demander(target=self.budget_ivoire)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target", response.data)
        self.assertIn("devise", str(response.data["target"]))

    def test_l_argent_deja_sorti_ne_se_transfere_pas(self):
        """L'enveloppe source doit couvrir consommé et engagé après le
        transfert : 100 000 alloués, 80 000 soumis, 50 000 ne partent pas."""
        self.budget_togo.amount = Decimal("100000.00")
        self.budget_togo.save()
        self.imputer(self.budget_togo, "80000.00", Status.SUBMITTED)

        response = self._demander(amount="50000.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)

    def test_l_approbation_reverifie_le_disponible(self):
        """Une dépense peut sortir entre la demande et la décision."""
        self.budget_togo.amount = Decimal("100000.00")
        self.budget_togo.save()
        realloc_id = self._demander(amount="50000.00").data["id"]
        self.imputer(self.budget_togo, "80000.00", Status.SUBMITTED)

        response = self.client.post(f"/api/reallocations/{realloc_id}/approve/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("100000.00"))
        self.assertEqual(
            BudgetReallocation.objects.get(pk=realloc_id).status,
            BudgetReallocation.Status.PENDING,
        )

    def test_le_df_ne_decide_pas_d_une_reallocation(self):
        """Demander, approuver, refuser : trois écritures budgétaires, toutes
        réservées à la direction. Le DF, global ou restreint, reçoit 403 et
        les enveloppes ne bougent pas."""
        realloc_id = self._demander().data["id"]
        for compte in (self.df, self.df_togo):
            with self.subTest(compte=compte.username):
                self.login(compte)

                lecture = self.client.get("/api/reallocations/")
                demande = self.client.post(
                    "/api/reallocations/",
                    {
                        "source": self.budget_togo.pk, "target": self.sous_enveloppe.pk,
                        "amount": "1.00", "reason": "Essai",
                    },
                )
                approbation = self.client.post(
                    f"/api/reallocations/{realloc_id}/approve/"
                )
                refus = self.client.post(
                    f"/api/reallocations/{realloc_id}/reject/", {"note": "Non"}
                )

                self.assertEqual(lecture.status_code, status.HTTP_200_OK)
                self.assertEqual(demande.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(approbation.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(refus.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(BudgetReallocation.objects.count(), 1)
        self.assertEqual(
            BudgetReallocation.objects.get(pk=realloc_id).status,
            BudgetReallocation.Status.PENDING,
        )
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("10000000.00"))

    def test_enveloppe_hors_perimetre_simplement_invalide(self):
        """Une direction restreinte au Togo ne touche pas une enveloppe
        ivoirienne, ni en source ni en destination — sans apprendre qu'elle
        existe."""
        with self.direction_restreinte():
            vers_ivoire = self._demander(target=self.budget_ivoire, par=self.doo_togo)
            depuis_ivoire = self._demander(
                source=self.budget_ivoire, target=self.budget_togo, par=self.doo_togo
            )

        self.assertEqual(vers_ivoire.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target", vers_ivoire.data)
        self.assertEqual(depuis_ivoire.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("source", depuis_ivoire.data)
        self.assertNotIn("périmètre", str(vers_ivoire.data) + str(depuis_ivoire.data))

    def test_decision_hors_perimetre_repond_404(self):
        """Le queryset filtre sur le pays de la source : la destination doit
        être vérifiée aussi, sinon une direction togolaise approuverait un
        transfert vers la Côte d'Ivoire."""
        realloc_id = self._demander(target=self.budget_ivoire).data["id"]
        self.login(self.doo_togo)

        with self.direction_restreinte():
            response = self.client.post(f"/api/reallocations/{realloc_id}/approve/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.budget_togo.refresh_from_db()
        self.assertEqual(self.budget_togo.amount, Decimal("10000000.00"))

    def test_direction_restreinte_decide_dans_son_perimetre(self):
        realloc_id = self._demander().data["id"]
        self.login(self.doo_togo)

        with self.direction_restreinte():
            response = self.client.post(f"/api/reallocations/{realloc_id}/approve/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["decided_by"], "do.togo")


class ReallocationLockTests(BudgetTestCase):
    """Le verrou est pris sur la réallocation **avant** la lecture du statut.

    Couvre l'ordre des opérations dans une transaction, en lisant le SQL
    émis : la réallocation est relue ``FOR UPDATE`` avant toute écriture, et
    les deux enveloppes sont verrouillées en une requête triée par
    identifiant (donc dans le même ordre pour A→B et B→A). La course réelle
    entre deux connexions est jouée dans ``test_verrous``.
    """

    def setUp(self):
        super().setUp()
        self.projet = Project.objects.create(country=self.togo, name="Projet TG")
        self.sous_enveloppe = Budget.objects.create(
            country=self.togo, year=2026, project=self.projet, amount=Decimal("0.00")
        )
        self.login(self.siege)
        self.realloc_id = self.client.post(
            "/api/reallocations/",
            {
                "source": self.budget_togo.pk, "target": self.sous_enveloppe.pk,
                "amount": "1000.00", "reason": "Renfort",
            },
        ).data["id"]
        self.login(self.doo)

    def _sql(self, action, data=None):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.post(
                f"/api/reallocations/{self.realloc_id}/{action}/", data or {}
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [q["sql"] for q in captured.captured_queries]

    def _verifier_verrou(self, sql):
        verrou = next(
            i for i, s in enumerate(sql)
            if '"budget_budgetreallocation"' in s and "FOR UPDATE" in s
        )
        # Seules les écritures métier comptent : le cache de limitation de
        # débit, lui, écrit avant même que la vue ne s'exécute.
        ecritures = [
            i for i, s in enumerate(sql)
            if (s.startswith("UPDATE") or s.startswith("INSERT"))
            and ('"budget_' in s or '"core_changelog"' in s)
        ]
        self.assertTrue(ecritures)
        self.assertLess(verrou, min(ecritures))

    def test_approbation_verrouille_la_reallocation_puis_les_enveloppes(self):
        sql = self._sql("approve")

        self._verifier_verrou(sql)
        verrou_enveloppes = [
            s for s in sql if '"budget_budget"' in s and "FOR UPDATE" in s
        ]
        self.assertEqual(len(verrou_enveloppes), 1)
        self.assertIn('ORDER BY "budget_budget"."id" ASC', verrou_enveloppes[0])

    def test_refus_verrouille_la_reallocation(self):
        self._verifier_verrou(self._sql("reject", {"note": "Non"}))


class ModelConstraintTests(BudgetTestCase):
    """La base est le dernier rempart : elle refuse ce que l'API refuse."""

    def _refuse(self, creer):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            creer()

    def test_montant_d_enveloppe_negatif(self):
        self._refuse(lambda: Budget.objects.create(
            country=self.togo, year=2027, amount=Decimal("-1.00")
        ))

    def test_reallocation_nulle_ou_vers_elle_meme(self):
        cible = Budget.objects.create(
            country=self.togo, year=2027, amount=Decimal("0.00")
        )
        self._refuse(lambda: BudgetReallocation.objects.create(
            source=self.budget_togo, target=cible, amount=Decimal("0.00"), reason="x"
        ))
        self._refuse(lambda: BudgetReallocation.objects.create(
            source=self.budget_togo, target=self.budget_togo,
            amount=Decimal("1.00"), reason="x",
        ))

    def test_decision_sans_date(self):
        cible = Budget.objects.create(
            country=self.togo, year=2027, amount=Decimal("0.00")
        )
        self._refuse(lambda: BudgetReallocation.objects.create(
            source=self.budget_togo, target=cible, amount=Decimal("1.00"),
            reason="x", status=BudgetReallocation.Status.APPROVED,
        ))

    def test_le_referentiel_d_une_enveloppe_est_protege(self):
        """Supprimer un pays ou un projet emportait ses enveloppes en
        cascade, montants compris."""
        projet = Project.objects.create(country=self.togo, name="Projet TG")
        Budget.objects.create(
            country=self.togo, year=2026, project=projet, amount=Decimal("1.00")
        )

        with self.assertRaises(ProtectedError):
            projet.delete()
        with self.assertRaises(ProtectedError):
            self.togo.delete()

    def test_politique_par_defaut_litterale(self):
        """Le champ porte « bloquer » ; la configuration du circuit n'est
        consultée qu'à la création par l'API."""
        self.assertEqual(
            Budget._meta.get_field("overrun_policy").default, OverrunPolicy.BLOCK
        )
        self.assertEqual(Budget._meta.ordering[-1], "-pk")
        self.assertEqual(BudgetReallocation._meta.ordering[-1], "-pk")


class SubEnvelopeTests(BudgetTestCase):
    """§5.2 : une enveloppe se décline par projet, équipe ou manager."""

    def setUp(self):
        super().setUp()
        self.equipe = Team.objects.create(country=self.togo, name="Équipe Lomé")
        self.manager = Manager.objects.create(name="Kodjo Mensah")
        # Un manager n'a pas de pays propre : c'est le pays qui le rattache.
        self.togo.managers.add(self.manager)
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
