"""Filtres ``ouverts`` et ``exercice`` de la liste des dossiers (décision 117).

La tuile « Dossiers ouverts » du tableau de bord ouvrait la liste entière,
clôturés et autres exercices compris : la liste ne disait pas le chiffre
de la tuile.
"""

from datetime import date

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

    def test_exercice_borne_la_date_du_dossier(self):
        numeros = self.numeros(exercice=self.year)

        self.assertNotIn("N-0091", numeros)
        self.assertTrue({"N-0001", "N-0090", "N-0092"} <= numeros)

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
