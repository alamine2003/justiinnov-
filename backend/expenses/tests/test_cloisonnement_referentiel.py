"""Le référentiel du pays voisin n'existe pas pour le demandeur.

Un identifiant de projet, de bénéficiaire ou de manager d'un autre pays
répond exactement comme un identifiant inconnu : sans cela, un manager
énumérait le référentiel des autres filiales par leurs numéros.
"""

from datetime import date

from rest_framework import status

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from core.models import ExpenseTitle, Manager, MarketingCategory, Project
from expenses.models import Beneficiary, Dossier

from .base import ExpenseTestCase


class CloisonnementDuReferentielTests(ExpenseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.projet_ivoire = Project.objects.create(country=cls.ivoire, name="Projet CI")
        cls.intitule_ivoire = ExpenseTitle.objects.create(country=cls.ivoire, label="Intitulé CI")
        cls.categorie_ivoire = MarketingCategory.objects.create(country=cls.ivoire, name="Catégorie CI")
        cls.beneficiaire_ivoire = Beneficiary.objects.create(country=cls.ivoire, name="Pharmacie CI")
        cls.manager_ivoire = Manager.objects.create(name="Awa Koné")
        cls.manager_ivoire.countries.add(cls.ivoire)

    def _ligne(self, **champs):
        self.login(self.owner)
        charge = {
            "dossier": self.dossier.pk, "country": self.togo.pk, "team": self.team.pk,
            "date": "2026-03-15T10:00:00Z", "title": "Carburant", "amount": "1000.00",
        }
        charge.update(champs)
        return self.client.post("/api/expenses/", charge, format="json")

    def test_un_identifiant_voisin_repond_comme_un_identifiant_inconnu(self):
        inexistant = 987654
        for champ, voisin in (
            ("project", self.projet_ivoire.pk), ("expense_title", self.intitule_ivoire.pk),
            ("marketing_category", self.categorie_ivoire.pk), ("beneficiary", self.beneficiaire_ivoire.pk),
            ("owner", self.manager_ivoire.pk),
        ):
            with self.subTest(champ=champ):
                reponse_voisin = self._ligne(**{champ: voisin})
                reponse_inconnu = self._ligne(**{champ: inexistant})

                self.assertEqual(reponse_voisin.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(reponse_inconnu.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(champ, reponse_voisin.data)
                # Même forme de refus, sans « autre pays » qui trahirait l'existence.
                self.assertNotIn("autre pays", str(reponse_voisin.data[champ]))
                self.assertEqual(
                    str(reponse_voisin.data[champ]).replace(str(voisin), "N"),
                    str(reponse_inconnu.data[champ]).replace(str(inexistant), "N"),
                )

    def test_un_compte_des_deux_pays_garde_la_verification_de_coherence(self):
        """Pour un manager rattaché aux deux pays, l'identifiant voisin
        existe : c'est alors l'incohérence pays qui est nommée."""
        deux_pays = make_user("deux.pays", Role.MANAGER, [self.togo, self.ivoire])
        self.dossier.created_by = deux_pays.username
        self.dossier.save()
        self.login(deux_pays)
        response = self.client.post("/api/expenses/", {
            "dossier": self.dossier.pk, "country": self.togo.pk, "team": self.team.pk,
            "date": "2026-03-15T10:00:00Z", "title": "Carburant", "amount": "1000.00",
            "project": self.projet_ivoire.pk,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", response.data)


class ChangementDePaysTests(ExpenseTestCase):
    """Une ligne en brouillon qui passe dans un dossier d'un autre pays ne
    garde rien de l'ancien ; un dossier, lui, ne change jamais de pays.

    Les relations déjà portées par la ligne ou le dossier — équipe,
    projet, bénéficiaire, manager — sont rejugées contre le nouveau pays,
    pas seulement celles de la charge utile. Le seul compte qui puisse le
    tenter est un manager rattaché aux deux pays, auteur des brouillons.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.deux_pays = make_user("deux.pays", Role.MANAGER, [cls.togo, cls.ivoire])
        cls.dossier_ivoire = Dossier.objects.create(
            number="N-CI-1", label="Mission Abidjan", country=cls.ivoire,
            date=date(cls.year, 3, 1), created_by=cls.deux_pays.username,
        )
        cls.projet_togo = Project.objects.create(country=cls.togo, name="Projet TG")

    def setUp(self):
        super().setUp()
        self.login(self.deux_pays)

    def test_la_ligne_ne_garde_ni_equipe_ni_projet_ni_manager_de_l_ancien_pays(self):
        ligne = self.make_expense(project=self.projet_togo, created_by=self.deux_pays.username)

        for retirer in ({}, {"team": None}, {"team": None, "project": None}):
            with self.subTest(retirer=retirer):
                response = self.client.patch(
                    f"/api/expenses/{ligne.pk}/",
                    {"country": self.ivoire.pk, "dossier": self.dossier_ivoire.pk, **retirer},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        ligne.refresh_from_db()
        self.assertEqual(ligne.country, self.togo)

    def test_la_ligne_change_de_pays_une_fois_ses_relations_retirees(self):
        ligne = self.make_expense(project=self.projet_togo, created_by=self.deux_pays.username)

        response = self.client.patch(
            f"/api/expenses/{ligne.pk}/",
            {
                "country": self.ivoire.pk, "dossier": self.dossier_ivoire.pk,
                "team": None, "project": None, "owner": None,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_le_dossier_ne_change_pas_de_pays(self):
        """Attribué à un pays une fois pour toutes (décision 89), même vide
        et même pour son auteur rattaché aux deux pays."""
        dossier = Dossier.objects.create(
            number="N-0002", label="Sans équipe", country=self.togo, owner=self.manager,
            date=date(self.year, 3, 1), created_by=self.deux_pays.username,
        )

        response = self.client.patch(
            f"/api/dossiers/{dossier.pk}/", {"country": self.ivoire.pk}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("country", response.data)
        dossier.refresh_from_db()
        self.assertEqual(dossier.country, self.togo)
