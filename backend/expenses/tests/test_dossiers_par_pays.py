"""Onglets par pays de la liste des dossiers (``/api/dossiers/par-pays/``)."""

from datetime import date

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from core.models import Country, Team
from expenses.models import Dossier
from expenses.workflow import Status

from .base import ExpenseTestCase

URL = "/api/dossiers/par-pays/"


class DossiersParPaysTests(ExpenseTestCase):
    """Le compte de chaque onglet vient de la base, dans le périmètre du compte."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        jour = date(cls.year, 4, 2)
        Dossier.objects.create(
            number="N-0002", label="Achat Lomé", country=cls.togo,
            team=cls.team, date=jour, status=Status.SUBMITTED,
            created_by=cls.owner.username,
        )
        Dossier.objects.create(
            number="N-0003", label="Mission Abidjan", country=cls.ivoire,
            date=jour, created_by=cls.rep_ivoire.username,
        )
        # Un pays désactivé sans dossier n'a pas d'onglet ; un pays actif
        # sans dossier en a un, à zéro.
        cls.benin = Country.objects.create(
            name="Bénin", code="BJ", currency="XOF", timezone="Africa/Porto-Novo",
        )
        Country.objects.create(
            name="Gabon", code="GA", currency="XAF", timezone="Africa/Libreville",
            is_active=False,
        )

    def comptes(self, reponse):
        return {p["code"]: p["count"] for p in reponse.data["pays"]}

    def test_le_siege_voit_chaque_pays_actif_avec_son_compte(self):
        self.login(self.controller)
        reponse = self.client.get(URL)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(self.comptes(reponse), {"BJ": 0, "CI": 1, "TG": 2})
        self.assertEqual(reponse.data["total"], 3)
        # Dans l'ordre des noms, comme le reste de l'interface.
        self.assertEqual(
            [p["name"] for p in reponse.data["pays"]],
            ["Bénin", "Côte d'Ivoire", "Togo"],
        )

    def test_les_filtres_de_la_liste_s_appliquent_aux_comptes(self):
        self.login(self.controller)
        reponse = self.client.get(URL, {"status": Status.SUBMITTED})
        self.assertEqual(self.comptes(reponse), {"BJ": 0, "CI": 0, "TG": 1})
        self.assertEqual(reponse.data["total"], 1)

        reponse = self.client.get(URL, {"search": "Abidjan"})
        self.assertEqual(self.comptes(reponse), {"BJ": 0, "CI": 1, "TG": 0})

    def test_un_manager_ne_voit_que_son_pays(self):
        self.login(self.owner)
        reponse = self.client.get(URL)
        self.assertEqual(self.comptes(reponse), {"TG": 2})
        self.assertEqual(reponse.data["total"], 2)

    def test_un_manager_d_equipe_ne_compte_que_les_dossiers_de_son_equipe(self):
        autre = Team.objects.create(country=self.togo, name="Équipe Kara")
        Dossier.objects.create(
            number="N-0004", label="Mission Kara", country=self.togo,
            team=autre, date=date(self.year, 5, 1), created_by=self.owner.username,
        )
        restreint = make_user(
            "kara.togo", Role.MANAGER, [self.togo], teams=[autre],
        )
        self.login(restreint)
        reponse = self.client.get(URL)
        self.assertEqual(self.comptes(reponse), {"TG": 1})

    def test_un_pays_desactive_garde_son_onglet_tant_qu_il_a_des_dossiers(self):
        self.ivoire.is_active = False
        self.ivoire.save(update_fields=["is_active"])
        self.login(self.controller)
        self.assertIn("CI", self.comptes(self.client.get(URL)))

    def test_sans_connexion_rien(self):
        self.assertEqual(self.client.get(URL).status_code, 401)
