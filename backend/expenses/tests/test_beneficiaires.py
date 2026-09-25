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
             "kind": Beneficiary.Kind.SUPPLIER, "phone": "+228 22 21 00 00"},
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


class ContactsTests(ExpenseTestCase):
    """Décision 93 : un bénéficiaire a un téléphone ou un e-mail.

    Exigé à la création et à toute modification ; un bénéficiaire saisi
    avant la décision reste valide jusqu'à ce qu'on le modifie, et se
    retrouve dans la liste des bénéficiaires à compléter.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ancien = Beneficiary.objects.create(
            country=cls.togo, name="Clinique de Kara", kind=Beneficiary.Kind.PROSPECT
        )
        cls.complet = Beneficiary.objects.create(
            country=cls.togo, name="Pharmacie du Port", phone="+228 90 00 00 00"
        )

    def creer(self, **champs):
        self.login(self.doo)
        return self.client.post(
            "/api/beneficiaries/", {"country": self.togo.pk, "name": "Station Lomé", **champs}
        )

    def test_sans_telephone_ni_e_mail_la_creation_est_refusee(self):
        response = self.creer()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("téléphone ou une adresse e-mail", str(response.data["non_field_errors"]))
        self.assertFalse(Beneficiary.objects.filter(name="Station Lomé").exists())

    def test_un_telephone_ou_un_e_mail_suffit(self):
        par_telephone = self.creer(phone="  +228   22 21 00 00 ")
        par_email = self.creer(name="Station Kara", email="station.kara@exemple.org")

        self.assertEqual(par_telephone.status_code, status.HTTP_201_CREATED, par_telephone.data)
        self.assertEqual(par_telephone.data["phone"], "+228 22 21 00 00")
        self.assertFalse(par_telephone.data["contact_manquant"])
        self.assertEqual(par_email.status_code, status.HTTP_201_CREATED, par_email.data)

    def test_un_contact_mal_forme_est_refuse(self):
        for champs, cle in (
            ({"phone": "12"}, "phone"),
            ({"phone": "appelez Awa"}, "phone"),
            ({"email": "awa.exemple.org"}, "email"),
        ):
            with self.subTest(champs=champs):
                response = self.creer(**champs)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(cle, response.data)

    def test_l_ancien_reste_valide_mais_se_complete_a_la_modification(self):
        self.login(self.doo)
        url = f"/api/beneficiaries/{self.ancien.pk}/"

        lu = self.client.get(url)
        renomme = self.client.patch(url, {"name": "Clinique de Kara-Nord"})
        complete = self.client.patch(url, {"name": "Clinique de Kara-Nord", "email": "clinique@exemple.org"})

        self.assertTrue(lu.data["contact_manquant"])
        self.assertEqual(renomme.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(complete.status_code, status.HTTP_200_OK, complete.data)
        self.assertFalse(complete.data["contact_manquant"])

    def test_on_desactive_un_ancien_sans_lui_trouver_de_contact(self):
        self.login(self.doo)

        response = self.client.patch(
            f"/api/beneficiaries/{self.ancien.pk}/", {"is_active": False}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_l_ecran_desactive_un_ancien_en_renvoyant_tout_le_formulaire(self):
        """L'interface renvoie tous les champs, inchangés, avec l'interrupteur."""
        self.login(self.doo)

        response = self.client.patch(
            f"/api/beneficiaries/{self.ancien.pk}/",
            {"country": self.togo.pk, "name": "Clinique de Kara", "kind": "prospect",
             "phone": "", "email": "", "contact": "", "is_active": False},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_on_ne_retire_pas_le_dernier_contact(self):
        self.login(self.doo)

        response = self.client.patch(
            f"/api/beneficiaries/{self.complet.pk}/", {"phone": ""}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_liste_retrouve_ceux_a_completer(self):
        self.login(self.doo)

        response = self.client.get("/api/beneficiaries/", {"contact_manquant": "1"})

        self.assertEqual([b["name"] for b in response.data["results"]], ["Clinique de Kara"])

