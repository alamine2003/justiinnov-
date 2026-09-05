"""Le drapeau ``supervision`` : l'interface ne propose Grafana que là où il est."""

from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user


class SupervisionTests(APITestCase):
    def setUp(self):
        user = make_user("siege.supervision", Role.SUPER_ADMIN, [])
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_absent_par_defaut(self):
        """Sans ``SUPERVISION=1`` (CI, développement), le drapeau est faux."""
        self.assertIs(self.client.get("/api/me/").data["supervision"], False)
        self.assertIs(self.client.get("/api/configuration/").data["supervision"], False)

    @override_settings(SUPERVISION=True)
    def test_expose_quand_la_pile_le_declare(self):
        me = self.client.get("/api/me/")
        configuration = self.client.get("/api/configuration/")

        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertIs(me.data["supervision"], True)
        self.assertIs(configuration.data["supervision"], True)

    @override_settings(SUPERVISION=True)
    def test_un_manager_le_voit_aussi_sur_son_profil(self):
        """Un réglage de déploiement, pas un droit : chacun sait si le lien
        existe ; ce sont les droits qui disent qui peut le suivre."""
        user = make_user("pays.supervision", Role.MANAGER, [])
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertIs(self.client.get("/api/me/").data["supervision"], True)
