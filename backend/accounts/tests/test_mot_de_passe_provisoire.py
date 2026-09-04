"""Un mot de passe posé par le siège doit être remplacé avant tout usage."""

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from core.models import Country


class MotDePasseProvisoireTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.pays = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.user = User.objects.create_user(
            "togo.innov", password="Provisoire-2026-siege"
        )
        profil = UserProfile.objects.create(
            user=self.user, role=Role.COUNTRY_MANAGER, must_change_password=True
        )
        profil.countries.set([self.pays])
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_la_plateforme_est_fermee(self):
        """Régression : l'interface affichait une bannière que l'on pouvait
        fermer, et l'API restait entièrement ouverte."""
        for url in ("/api/countries/", "/api/dossiers/", "/api/expenses/"):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_l_ecriture_est_fermee_aussi(self):
        response = self.client.post(
            "/api/dossiers/",
            {"number": "N-1", "label": "Mission", "country": self.pays.pk,
             "date": "2026-01-01"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_profil_reste_lisible(self):
        """Sans lui, l'interface ne saurait pas quoi afficher."""
        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["must_change_password"])

    def test_le_changement_de_mot_de_passe_reste_ouvert(self):
        """Sans lui, le blocage n'aurait pas de sortie."""
        response = self.client.post(
            "/api/me/password/",
            {
                "current_password": "Provisoire-2026-siege",
                "new_password": "Personnel-2026-Togo",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_le_changement_rouvre_la_plateforme(self):
        change = self.client.post(
            "/api/me/password/",
            {
                "current_password": "Provisoire-2026-siege",
                "new_password": "Personnel-2026-Togo",
            },
        )
        # L'ancien jeton est révoqué avec l'ancien mot de passe.
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {change.data['token']}")

        response = self.client.get("/api/countries/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_la_deconnexion_reste_possible(self):
        """Sans elle, un compte verrouillé garderait un jeton vivant."""
        response = self.client.post("/api/logout/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_un_compte_deja_personnel_n_est_pas_gene(self):
        self.user.profile.must_change_password = False
        self.user.profile.save()

        response = self.client.get("/api/countries/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
