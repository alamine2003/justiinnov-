"""``api_version`` : la version du serveur, aux administrateurs (décision 126)."""

from django.test import SimpleTestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from config.settings import lire_la_version


@override_settings(APP_VERSION="2.4.4")
class VersionDuServeurTests(APITestCase):
    _comptes = 0

    def _me(self, role, **options):
        user = make_user(f"version.{role}.{self._comptes}", role, [], **options)
        self._comptes += 1
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        reponse = self.client.get("/api/me/")
        self.assertEqual(reponse.status_code, 200)
        return reponse.data

    def test_les_administrateurs_la_voient(self):
        for role in (Role.ADMIN, Role.SUPER_ADMIN):
            with self.subTest(role=role):
                self.assertEqual(self._me(role)["api_version"], "2.4.4")

    def test_le_pays_ne_la_voit_pas(self):
        """Champ présent, valeur nulle : la réponse garde sa forme."""
        me = self._me(Role.MANAGER)
        self.assertIn("api_version", me)
        self.assertIsNone(me["api_version"])

    def test_pas_tant_que_le_mot_de_passe_est_provisoire(self):
        self.assertIsNone(self._me(Role.ADMIN, must_change_password=True)["api_version"])

    @override_settings(TOTP_REQUIRED=True)
    def test_pas_tant_que_la_double_authentification_exigee_manque(self):
        self.assertIsNone(self._me(Role.ADMIN, totp_confirmed=False)["api_version"])

    def test_une_double_authentification_proposee_ne_retient_rien(self):
        """Non exigée (le défaut), son absence ne ferme rien."""
        self.assertEqual(self._me(Role.ADMIN, totp_confirmed=False)["api_version"], "2.4.4")


class LectureDeLaVersionTests(SimpleTestCase):
    def test_une_version_de_paquet_passe(self):
        self.assertEqual(lire_la_version("2.4.4"), "2.4.4")
        self.assertEqual(lire_la_version(" 2.5.0-rc.1 "), "2.5.0-rc.1")

    def test_absente_ou_vide_elle_vaut_dev(self):
        for valeur in (None, "", "   "):
            with self.subTest(valeur=valeur):
                self.assertEqual(lire_la_version(valeur), "dev")

    def test_une_forme_inattendue_vaut_dev(self):
        for valeur in ("<script>", "2.4.4 ; rm", "-2.4.4", "x" * 41):
            with self.subTest(valeur=valeur):
                self.assertEqual(lire_la_version(valeur), "dev")
