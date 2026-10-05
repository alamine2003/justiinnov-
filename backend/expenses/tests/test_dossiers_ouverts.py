"""Filtres ``ouverts`` et ``exercice`` de la liste des dossiers (décision 117).

La tuile « Dossiers ouverts » du tableau de bord ouvrait la liste entière,
clôturés et autres exercices compris : la liste ne disait pas le chiffre
de la tuile.
"""

from datetime import date

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from core.models import Team
from expenses.models import Dossier
from expenses.workflow import Status

from .base import ExpenseTestCase


class DossiersOuvertsTests(ExpenseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Le dossier de base (N-0001) est un brouillon de l'exercice courant.
        cls.clos = Dossier.objects.create(
            number="N-0090", label="Mission close", country=cls.togo,
            team=cls.team, date=date(cls.year, 2, 1), status=Status.CLOSED,
            created_by=cls.owner.username,
        )
        cls.ancien = Dossier.objects.create(
            number="N-0091", label="Mission de l'an passé", country=cls.togo,
            team=cls.team, date=date(cls.year - 1, 12, 31), status=Status.SUBMITTED,
            created_by=cls.owner.username,
        )
        cls.suivant = Dossier.objects.create(
            number="N-0093", label="Mission de l'an prochain", country=cls.togo,
            team=cls.team, date=date(cls.year + 1, 1, 1), status=Status.SUBMITTED,
            created_by=cls.owner.username,
        )
        cls.ivoirien = Dossier.objects.create(
            number="N-0092", label="Mission Abidjan", country=cls.ivoire,
            date=date(cls.year, 6, 1), status=Status.SUBMITTED,
            created_by=cls.rep_ivoire.username,
        )

    def numeros(self, **params):
        self.login(self.controller)
        reponse = self.client.get("/api/dossiers/", params)
        self.assertEqual(reponse.status_code, 200, reponse.data)
        return {d["number"] for d in reponse.data["results"]}

    def test_ouverts_ecarte_les_dossiers_clotures(self):
        numeros = self.numeros(ouverts="true")

        self.assertNotIn("N-0090", numeros)
        self.assertTrue({"N-0001", "N-0091", "N-0092"} <= numeros)

    def test_ouverts_lit_aussi_la_forme_de_l_adresse(self):
        """L'interface écrit ``ouverts=1`` : l'API le comprend, comme
        ``true``, au lieu de l'ignorer en silence."""
        self.assertNotIn("N-0090", self.numeros(ouverts="1"))

    def test_exercice_borne_la_date_du_dossier(self):
        numeros = self.numeros(exercice=self.year)

        self.assertNotIn("N-0091", numeros)
        self.assertNotIn("N-0093", numeros)
        self.assertTrue({"N-0001", "N-0090", "N-0092"} <= numeros)

    def test_un_exercice_decimal_est_refuse(self):
        self.login(self.controller)
        reponse = self.client.get("/api/dossiers/", {"exercice": "2026.5"})
        self.assertEqual(reponse.status_code, 400, reponse.data)

    def test_une_annee_hors_calendrier_ne_renvoie_rien(self):
        self.assertEqual(self.numeros(exercice=99999), set())

    def test_les_onglets_par_pays_comptent_avec_les_memes_filtres(self):
        self.login(self.controller)
        reponse = self.client.get(
            "/api/dossiers/par-pays/", {"ouverts": "true", "exercice": self.year}
        )

        comptes = {p["code"]: p["count"] for p in reponse.data["pays"]}
        self.assertEqual(comptes, {"CI": 1, "TG": 1})

    def test_la_tuile_et_la_liste_disent_le_meme_chiffre(self):
        """Le compte du tableau de bord et celui de la liste filtrée, pour
        le même exercice et le même pays."""
        self.login(self.controller)
        tableau = self.client.get(
            "/api/dashboard/", {"year": self.year, "country": self.togo.pk}
        )
        liste = self.client.get(
            "/api/dossiers/",
            {"ouverts": "true", "exercice": self.year, "country": self.togo.pk},
        )

        self.assertEqual(tableau.status_code, 200, tableau.data)
        self.assertEqual(tableau.data["workload"]["dossiers_open"], liste.data["count"])
        self.assertEqual(liste.data["count"], 1)

    def test_le_meme_chiffre_pour_un_manager_rattache_a_une_equipe(self):
        """Tuile et liste cloisonnent toutes deux par équipe : un dossier
        d'une autre équipe du pays n'entre ni dans l'une ni dans l'autre."""
        autre = Team.objects.create(country=self.togo, name="Équipe Kara")
        Dossier.objects.create(
            number="N-0094", label="Mission Kara", country=self.togo, team=autre,
            date=date(self.year, 5, 1), status=Status.SUBMITTED,
            created_by=self.owner.username,
        )
        manager = make_user("lome.togo", Role.MANAGER, [self.togo], teams=[self.team])
        self.login(manager)

        tableau = self.client.get("/api/dashboard/", {"year": self.year})
        liste = self.client.get("/api/dossiers/", {"ouverts": "1", "exercice": self.year})

        self.assertEqual(tableau.data["workload"]["dossiers_open"], liste.data["count"])
        self.assertNotIn("N-0094", {d["number"] for d in liste.data["results"]})
