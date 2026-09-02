"""Périmètre géographique : la plateforme ne suit que des pays africains."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from core.africa import AFRICAN_COUNTRY_CODES, validate_african_country
from core.models import Country


class ValidateurTests(APITestCase):
    def test_un_code_africain_passe(self):
        for code in ("CI", "TG", "SN", "MA", "ZA"):
            validate_african_country(code)

    def test_un_code_hors_afrique_est_refuse(self):
        for code in ("FR", "BE", "US", "CN"):
            with self.assertRaises(ValidationError, msg=code):
                validate_african_country(code)

    def test_la_casse_n_ouvre_pas_une_porte_derobee(self):
        """« fr » ne doit pas passer là où « FR » est refusé."""
        with self.assertRaises(ValidationError):
            validate_african_country("fr")
        validate_african_country("ci")

    def test_le_senegal_est_dans_la_liste(self):
        """Le siège est au Sénégal : il n'est pas un pays suivi, mais son code
        doit rester acceptable si un jour il en devient un."""
        self.assertIn("SN", AFRICAN_COUNTRY_CODES)


class CreationParApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        user = User.objects.create_user(username="ceo.innov", password="Motdepasse-2026-test")
        UserProfile.objects.create(user=user, role=Role.SUPER_ADMIN)
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def payload(self, **overrides):
        data = {
            "name": "Bénin",
            "code": "BJ",
            "currency": "XOF",
            "timezone": "Africa/Porto-Novo",
        }
        data.update(overrides)
        return data

    def test_le_siege_ajoute_un_pays_africain(self):
        """Les superadmins doivent pouvoir créer les comptes pays à venir."""
        response = self.client.post("/api/countries/", self.payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Country.objects.filter(code="BJ").exists())

    def test_un_pays_hors_afrique_est_refuse(self):
        response = self.client.post(
            "/api/countries/", self.payload(name="France", code="FR", currency="EUR")
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertFalse(Country.objects.filter(name="France").exists())

    def test_le_code_est_normalise_en_majuscules(self):
        """Sans normalisation, « bj » et « BJ » cohabiteraient malgré
        la contrainte d'unicité."""
        response = self.client.post("/api/countries/", self.payload(code="bj"))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Country.objects.get(name="Bénin").code, "BJ")

    def test_un_pays_existant_ne_bascule_pas_hors_afrique(self):
        pays = Country.objects.create(
            name="Togo", code="TG", currency="XOF", timezone="Africa/Lome"
        )

        response = self.client.patch(f"/api/countries/{pays.pk}/", {"code": "FR"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        pays.refresh_from_db()
        self.assertEqual(pays.code, "TG")


class PaysDisponiblesTests(CreationParApiTests):
    """La liste proposée au formulaire de création."""

    def test_elle_ne_propose_que_des_pays_africains(self):
        response = self.client.get("/api/countries/disponibles/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {p["code"] for p in response.data}
        self.assertTrue(codes.issubset(AFRICAN_COUNTRY_CODES))
        self.assertNotIn("FR", codes)

    def test_elle_exclut_les_pays_deja_suivis(self):
        """Proposer un pays existant mènerait à un refus d'unicité."""
        Country.objects.create(
            name="Togo", code="TG", currency="XOF", timezone="Africa/Lome"
        )

        response = self.client.get("/api/countries/disponibles/")

        self.assertNotIn("TG", {p["code"] for p in response.data})

    def test_un_pays_ne_voit_pas_la_liste(self):
        """Ajouter un pays est un geste du siège."""
        rep = User.objects.create_user(
            username="togo.innov", password="Motdepasse-2026-test"
        )
        UserProfile.objects.create(user=rep, role=Role.COUNTRY_MANAGER)
        token, _ = Token.objects.get_or_create(user=rep)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/countries/disponibles/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
