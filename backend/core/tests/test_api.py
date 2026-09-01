"""Tests de l'API : authentification, limitation de débit, non-suppression."""

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from core.models import ChangeLog, Country, Team

PASSWORD = "Motdepasse-de-test-2026"


class ApiTestCase(APITestCase):
    def setUp(self):
        # Les compteurs de débit vivent dans le cache : ils doivent repartir de
        # zéro à chaque test.
        cache.clear()
        self.user = User.objects.create_user(username="admin.test", password=PASSWORD)
        # Les vues exigent un profil : sans rôle, aucun droit.
        UserProfile.objects.create(user=self.user, role=Role.SUPER_ADMIN)
        self.token = Token.objects.create(user=self.user)
        self.country = Country.objects.create(
            name="Togo", code="TG", currency="XOF", timezone="Africa/Lome"
        )

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")


class AuthenticationTests(ApiTestCase):
    def test_acces_anonyme_refuse(self):
        response = self.client.get("/api/countries/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_retourne_un_jeton(self):
        response = self.client.post(
            "/api/token-auth/",
            {"username": "admin.test", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], self.token.key)

    def test_login_limite_le_bourrage_d_identifiants(self):
        """``ObtainAuthToken`` neutralise les limites globales de DRF : la
        limitation doit être explicitement rattachée à la vue."""
        payload = {"username": "admin.test", "password": "mauvais"}

        for _ in range(10):
            response = self.client.post("/api/token-auth/", payload)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post("/api/token-auth/", payload)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class NoDestroyTests(ApiTestCase):
    """La désactivation remplace la suppression : ``DELETE`` n'est pas exposé."""

    def setUp(self):
        super().setUp()
        self.authenticate()
        self.team = Team.objects.create(country=self.country, name="Équipe Lomé")

    def test_suppression_d_un_pays_refusee(self):
        response = self.client.delete(f"/api/countries/{self.country.pk}/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Country.objects.filter(pk=self.country.pk).exists())

    def test_suppression_d_une_sous_entite_refusee(self):
        response = self.client.delete(f"/api/teams/{self.team.pk}/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_desactivation_reste_possible(self):
        response = self.client.patch(
            f"/api/countries/{self.country.pk}/", {"is_active": False}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.country.refresh_from_db()
        self.assertFalse(self.country.is_active)


class HistoryTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def test_historique_du_pays_contient_ses_propres_evenements(self):
        """Régression : les événements portant sur le pays lui-même n'étaient
        rattachés à aucun pays et n'apparaissaient donc jamais ici."""
        self.client.patch(f"/api/countries/{self.country.pk}/", {"is_active": False})

        response = self.client.get("/api/history/", {"country": self.country.pk})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        actions = [entry["action"] for entry in response.data["results"]]
        self.assertIn(ChangeLog.Actions.DEACTIVATED, actions)

    def test_auteur_de_l_action_est_enregistre(self):
        self.client.patch(
            f"/api/countries/{self.country.pk}/", {"timezone": "Africa/Abidjan"}
        )

        entry = ChangeLog.objects.filter(action=ChangeLog.Actions.UPDATED).first()
        self.assertEqual(entry.performed_by, "admin.test")
