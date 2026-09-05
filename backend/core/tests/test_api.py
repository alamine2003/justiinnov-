"""Tests de l'API : authentification, limitation de débit, non-suppression."""

import pyotp
from django.contrib.auth.models import User
from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from core.models import ChangeLog, Country, Team

PASSWORD = "Motdepasse-de-test-2026"


class ApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="admin.test", password=PASSWORD)
        # Les vues exigent un profil : sans rôle, aucun droit.
        # Compte en service : mot de passe personnel et 2FA confirmée. La
        # connexion exige donc un code (cf. accounts.tests).
        cls.secret = pyotp.random_base32()
        UserProfile.objects.create(
            user=cls.user, role=Role.SUPER_ADMIN, must_change_password=False,
            totp_secret=cls.secret, totp_confirmed_at=timezone.now(),
        )
        cls.token = Token.objects.create(user=cls.user)
        cls.country = Country.objects.create(
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
            {"username": "admin.test", "password": PASSWORD, "code": pyotp.TOTP(self.secret).now()},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], self.token.key)

    def test_login_limite_le_bourrage_d_identifiants_par_adresse(self):
        """``ObtainAuthToken`` neutralise les limites globales de DRF : la
        limitation doit être explicitement rattachée à la vue."""
        for index in range(10):
            response = self.client.post(
                "/api/token-auth/", {"username": f"compte{index}", "password": "mauvais"}
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            "/api/token-auth/", {"username": "compte11", "password": "mauvais"}
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_login_limite_le_bourrage_d_identifiants_par_compte(self):
        """Un compte visé depuis plusieurs adresses est protégé aussi."""
        payload = {"username": "admin.test", "password": "mauvais"}

        for index in range(5):
            response = self.client.post(
                "/api/token-auth/", payload, REMOTE_ADDR=f"203.0.113.{index + 1}"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post("/api/token-auth/", payload, REMOTE_ADDR="203.0.113.99")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_la_connexion_est_journalisee(self):
        self.client.post(
            "/api/token-auth/",
            {"username": "admin.test", "password": PASSWORD, "code": pyotp.TOTP(self.secret).now()},
            REMOTE_ADDR="203.0.113.7",
        )

        entry = ChangeLog.objects.get(action=ChangeLog.Actions.LOGIN)
        self.assertEqual(entry.model_name, ChangeLog.Models.USER)
        self.assertEqual(entry.object_id, self.user.pk)
        self.assertEqual(entry.performed_by, "admin.test")
        self.assertEqual(entry.ip_address, "203.0.113.7")

    def test_l_echec_de_connexion_est_journalise(self):
        """C'est la première trace d'une intrusion : nom essayé et adresse."""
        self.client.post(
            "/api/token-auth/",
            {"username": "inconnu", "password": "mauvais"},
            REMOTE_ADDR="203.0.113.8",
        )

        entry = ChangeLog.objects.get(action=ChangeLog.Actions.LOGIN_FAILED)
        self.assertEqual(entry.label, "inconnu")
        self.assertEqual(entry.performed_by, "inconnu")
        self.assertIsNone(entry.object_id)
        self.assertEqual(entry.ip_address, "203.0.113.8")

    def test_le_point_de_sante_ne_declenche_pas_de_limite_anonyme(self):
        """Interrogé toutes les trente secondes par Docker, il ne doit jamais
        répondre 429."""
        for _ in range(70):
            response = self.client.get("/api/health/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)


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

    def test_une_entree_porte_la_difference_et_l_adresse(self):
        """Qui, quoi, depuis où, avant et après : l'historique le dit, et
        l'interface n'a pas à le deviner."""
        self.client.patch(
            f"/api/countries/{self.country.pk}/", {"is_active": False},
            REMOTE_ADDR="203.0.113.7",
        )

        response = self.client.get("/api/history/", {"country": self.country.pk})

        entry = next(
            e for e in response.data["results"]
            if e["action"] == ChangeLog.Actions.DEACTIVATED
        )
        self.assertEqual(entry["diff"], {"is_active": [True, False]})
        self.assertEqual(entry["ip_address"], "203.0.113.7")
        self.assertEqual(entry["changed_fields"], ["is_active"])

    def test_entree_sans_pays_conserve_la_cle_country_name(self):
        """Un événement sans pays (un manager) doit renvoyer `country_name:
        null` et non omettre la clé."""
        self.client.post("/api/managers/", {"name": "Awa Diop"})

        response = self.client.get("/api/history/", {"model_name": "manager"})

        entry = response.data["results"][0]
        self.assertIn("country_name", entry)
        self.assertIsNone(entry["country_name"])

    def test_auteur_de_l_action_est_enregistre(self):
        self.client.patch(
            f"/api/countries/{self.country.pk}/", {"timezone": "Africa/Abidjan"}
        )

        entry = ChangeLog.objects.filter(action=ChangeLog.Actions.UPDATED).first()
        self.assertEqual(entry.performed_by, "admin.test")


class HistoryScopeTests(ApiTestCase):
    """Qui lit l'historique, et lequel."""

    def _compte(self, username, role, countries=()):
        user = User.objects.create_user(username=username, password=PASSWORD)
        profile = UserProfile.objects.create(user=user, role=role, must_change_password=False,
            totp_confirmed_at=timezone.now())
        profile.countries.set(countries)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
        return user

    def test_un_owner_ne_lit_pas_l_historique(self):
        self._compte("owner.test", Role.MANAGER, [self.country])

        response = self.client.get("/api/history/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_dm_et_le_df_ne_lisent_pas_l_historique_des_comptes(self):
        """La liste des comptes leur est fermée ; son historique — qui a été
        promu, qui n'a pas confirmé sa 2FA — le serait sinon par la bande."""
        for role in (Role.DF, Role.DM):
            with self.subTest(role=role):
                self._compte(f"{role}.hist", role, [])
                repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
                ChangeLog.objects.create(
                    model_name=ChangeLog.Models.USER, object_id=1,
                    label="kofi.innov", action=ChangeLog.Actions.CREATED,
                )
                ChangeLog.objects.create(
                    model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION, object_id=1,
                    label="Configuration", action=ChangeLog.Actions.UPDATED,
                )

                response = self.client.get("/api/history/", {"model_name": "user"})
                caches = [e for e in response.data["results"] if e["id"] > repere]

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(caches, [])
                tout = self.client.get("/api/history/")
                labels = {e["model_name"] for e in tout.data["results"] if e["id"] > repere}
                self.assertFalse(labels & {"user", "workflow_configuration"})

    def test_un_siege_restreint_voit_aussi_les_entrees_sans_pays(self):
        """Taux de change et autres entrées sans pays étaient invisibles pour
        un rôle du siège limité à quelques pays — le DF comme le DM. La
        configuration du workflow et les comptes, eux, relèvent de
        l'administration et restent hors de leur vue."""
        autre = Country.objects.create(name="Bénin", code="BJ", currency="XOF")
        # Un fuseau différent à chaque tour : sans changement, rien ne
        # s'écrit dans le journal.
        for role, fuseau in ((Role.DF, "Africa/Accra"), (Role.DM, "Africa/Lagos")):
            with self.subTest(role=role):
                self._compte(f"{role}.test", role, [self.country])
                # Le journal est en ajout seul : on ne le vide pas, on retient
                # un repère et on ne juge que ce qui vient après.
                repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
                ChangeLog.objects.create(
                    model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION, object_id=1,
                    label="Configuration", action=ChangeLog.Actions.UPDATED,
                )
                ChangeLog.objects.create(
                    model_name=ChangeLog.Models.EXCHANGE_RATE, object_id=1,
                    label="EUR", action=ChangeLog.Actions.CREATED,
                )
                self.country.timezone = fuseau
                self.country.save()
                autre.timezone = fuseau
                autre.save()

                response = self.client.get("/api/history/")

                nouvelles = [e for e in response.data["results"] if e["id"] > repere]
                labels = {e["model_name"] for e in nouvelles}
                self.assertEqual(labels, {"exchange_rate", "country"})
                pays = {e["country"] for e in nouvelles}
                self.assertEqual(pays, {None, self.country.pk})


class PaginationTests(ApiTestCase):
    """Sans taille de page réglable, l'interface paginerait dans le vide."""

    def setUp(self):
        super().setUp()
        self.authenticate()
        for index in range(7):
            Team.objects.create(country=self.country, name=f"Équipe {index}")

    def test_la_taille_de_page_demandee_est_respectee(self):
        response = self.client.get("/api/teams/", {"page_size": 3})

        self.assertEqual(len(response.data["results"]), 3)
        self.assertEqual(response.data["count"], 7)
        self.assertIsNotNone(response.data["next"])

    def test_la_taille_de_page_est_plafonnee(self):
        """Une requête ne doit pas pouvoir réclamer la table entière."""
        response = self.client.get("/api/teams/", {"page_size": 100000})

        self.assertEqual(len(response.data["results"]), 7)

    def test_navigation_entre_les_pages(self):
        premiere = self.client.get("/api/teams/", {"page_size": 4, "page": 1})
        seconde = self.client.get("/api/teams/", {"page_size": 4, "page": 2})

        noms = {t["name"] for t in premiere.data["results"]} | {
            t["name"] for t in seconde.data["results"]
        }
        self.assertEqual(len(noms), 7)
        self.assertIsNotNone(seconde.data["previous"])
