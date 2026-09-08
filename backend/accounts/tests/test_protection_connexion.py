"""La limite anti-bourrage ne se contourne pas avec un jeton, et le TOTP
mal formé ne provoque pas de 500.

Audit du 8 septembre 2026, §3.5 et §6 (TOTP non-ASCII).
"""

from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts import totp
from accounts.models import Role
from accounts.tests.test_scoping import make_user

# Limites resserrées : deux tentatives par adresse et par compte suffisent à
# prouver le comptage sans lancer des dizaines de requêtes.
THROTTLE = override_settings(
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "accounts.authentication.JetonAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
        "DEFAULT_THROTTLE_RATES": {
            "user": "2000/hour", "login": "2/min", "login_user": "50/min",
            "password": "10/min", "health": "60/min",
        },
        "NUM_PROXIES": 0,
    }
)


@THROTTLE
class LimiteDeConnexionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_user("manager.togo", Role.MANAGER)
        cls.cible = make_user("dg.innov", Role.SUPER_ADMIN)

    def setUp(self):
        cache.clear()

    def _tenter(self, username, jeton=None):
        if jeton is not None:
            self.client.credentials(HTTP_AUTHORIZATION=f"Token {jeton}")
        else:
            self.client.credentials()
        return self.client.post(
            "/api/token-auth/", {"username": username, "password": "faux-mot-de-passe"}
        )

    def test_la_limite_par_adresse_finit_par_repondre_429(self):
        self.assertEqual(self._tenter("dg.innov").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._tenter("dg.innov").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._tenter("dg.innov").status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_un_jeton_valide_ne_leve_pas_la_limite(self):
        """Le contournement de l'audit : se connecter avec son compte, puis
        pulvériser un mot de passe sur d'autres comptes en présentant son
        jeton. La limite par adresse doit tenir quand même."""
        jeton = Token.objects.create(user=self.manager).key

        # Deux tentatives sur deux comptes différents épuisent la limite
        # *par adresse* (login 2/min) : la troisième est refusée, quel que
        # soit le compte visé — le jeton n'y change rien.
        self.assertEqual(self._tenter("dg.innov", jeton).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._tenter("dg.innov", jeton).status_code, status.HTTP_400_BAD_REQUEST)
        troisieme = self._tenter("rh.innov", jeton)
        self.assertEqual(troisieme.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_un_jeton_invalide_ne_change_rien(self):
        self._tenter("dg.innov", "jeton-inexistant")
        self._tenter("dg.innov", "jeton-inexistant")
        self.assertEqual(
            self._tenter("dg.innov", "jeton-inexistant").status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )


@override_settings(REST_FRAMEWORK={
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.JetonAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": "2000/hour", "login": "50/min", "login_user": "2/min",
        "password": "10/min", "health": "60/min",
    },
    "NUM_PROXIES": 0,
})
class LimiteParCompteTests(APITestCase):
    """``login_user`` (par nom de compte) protège un compte visé depuis
    plusieurs adresses : la limite par nom est serrée, l'adresse varie."""

    @classmethod
    def setUpTestData(cls):
        cls.cible = make_user("dg.innov", Role.SUPER_ADMIN)

    def setUp(self):
        cache.clear()

    def test_un_compte_vise_est_protege_toutes_adresses_confondues(self):
        adresses = iter(["10.0.0.1", "10.0.0.2", "10.0.0.3"])

        def adresse_variable(request):
            return next(adresses, "10.0.0.9")

        with mock.patch("accounts.views.client_ip", side_effect=adresse_variable):
            self.assertEqual(self._tenter().status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(self._tenter().status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(self._tenter().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def _tenter(self):
        self.client.credentials()
        return self.client.post(
            "/api/token-auth/", {"username": "dg.innov", "password": "faux"}
        )


class CodeTotpMalFormeTests(APITestCase):
    """``.isdigit()`` accepte des chiffres non-ASCII que ``compare_digest``
    refuse par une exception : un code arabo-indien renvoyait un 500."""

    SECRET = totp.generer_secret()

    def test_un_code_non_ascii_ne_leve_pas(self):
        # Chiffres arabo-indiens : isdigit() est vrai, ce ne sont pas des ASCII.
        self.assertIsNone(totp.compteur_du_code(self.SECRET, "١٢٣٤٥٦"))
        # Exposants : isdigit() est vrai aussi.
        self.assertIsNone(totp.compteur_du_code(self.SECRET, "¹²³⁴⁵⁶"))

    def test_un_code_ascii_valide_donne_un_compteur(self):
        import pyotp

        code = pyotp.TOTP(self.SECRET).now()
        self.assertIsNotNone(totp.compteur_du_code(self.SECRET, code))
