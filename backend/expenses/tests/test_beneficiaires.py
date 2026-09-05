"""Cloisonnement du référentiel des bénéficiaires.

Il était commun à tous les pays : un pays lisait les fournisseurs et les
prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
"""

from rest_framework import status

from expenses.models import Beneficiary

from .base import ExpenseTestCase


class BeneficiaireScopeTests(ExpenseTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.fournisseur_togo = Beneficiary.objects.create(
            country=cls.togo, name="Station Lomé", kind=Beneficiary.Kind.SUPPLIER
        )
        cls.prospect_ivoire = Beneficiary.objects.create(
            country=cls.ivoire, name="Groupe Abidjan", kind=Beneficiary.Kind.PROSPECT
        )

    def test_un_pays_ne_voit_que_ses_beneficiaires(self):
        """Régression : la liste était commune."""
        self.login(self.rep_ivoire)

        response = self.client.get("/api/beneficiaries/")

        noms = [b["name"] for b in response.data["results"]]
        self.assertEqual(noms, ["Groupe Abidjan"])

    def test_acces_direct_a_celui_d_un_autre_pays_refuse(self):
        self.login(self.rep_ivoire)

        response = self.client.get(
            f"/api/beneficiaries/{self.fournisseur_togo.pk}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_le_siege_les_voit_tous(self):
        self.login(self.controller)

        response = self.client.get("/api/beneficiaries/")

        self.assertEqual(response.data["count"], 2)

    def test_creation_chez_le_voisin_refusee(self):
        self.login(self.rep_ivoire)

        response = self.client.post(
            "/api/beneficiaries/",
            {"country": self.togo.pk, "name": "Fournisseur pirate"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Beneficiary.objects.filter(name="Fournisseur pirate").exists())

    def test_le_manager_ne_cree_pas_de_beneficiaire(self):
        """Le référentiel des pays, bénéficiaires compris, est tenu par la RH :
        le manager choisit parmi ceux qui existent."""
        self.login(self.owner)

        response = self.client.post(
            "/api/beneficiaries/",
            {"country": self.togo.pk, "name": "Pharmacie du Port"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Beneficiary.objects.filter(name="Pharmacie du Port").exists())

    def test_deux_pays_peuvent_declarer_le_meme_fournisseur(self):
        """Le nom était unique globalement : le second pays était refusé."""
        self.login(self.doo)

        response = self.client.post(
            "/api/beneficiaries/",
            {"country": self.togo.pk, "name": "Groupe Abidjan",
             "kind": Beneficiary.Kind.SUPPLIER},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_le_meme_nom_deux_fois_dans_un_pays_est_refuse(self):
        self.login(self.doo)

        response = self.client.post(
            "/api/beneficiaries/",
            {"country": self.togo.pk, "name": "Station Lomé"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("existe déjà", str(response.data))

    def test_suppression_impossible(self):
        """Rien ne se supprime dans un référentiel : on désactive. Testé avec
        qui a le droit d'écrire, sinon c'est le rôle qui répondrait (403)."""
        self.login(self.doo)

        response = self.client.delete(
            f"/api/beneficiaries/{self.fournisseur_togo.pk}/"
        )

        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
