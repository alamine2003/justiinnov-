"""Le drapeau ``supervision`` : l'interface ne propose Grafana que là où il est."""

from accounts.models import Role
from accounts.tests.test_scoping import make_user
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


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


class LienDuBITests(APITestCase):
    """``bi_url`` : le lien « BI de pilotage » (décision 122)."""

    _comptes = 0

    def _me(self, role):
        user = make_user(f"bi.{role}.{self._comptes}", role, [])
        self._comptes += 1
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return self.client.get("/api/me/").data

    @override_settings(SUPERVISION=True, BI_URL="https://bi.exemple.org")
    def test_la_direction_recoit_la_vue_d_ensemble(self):
        me = self._me(Role.SUPER_ADMIN)
        self.assertEqual(me["bi_url"], "https://bi.exemple.org/d/bi-vue-ensemble")
        self.assertIs(me["permissions"]["bi.consulter"], True)

    @override_settings(SUPERVISION=True, BI_URL="https://bi.exemple.org")
    def test_ni_la_rh_par_defaut_ni_le_pays(self):
        for role in (Role.ADMIN, Role.MANAGER):
            with self.subTest(role=role):
                self.assertIsNone(self._me(role)["bi_url"])

    @override_settings(SUPERVISION=True, BI_URL="https://bi.exemple.org")
    def test_la_matrice_l_ouvre_a_la_rh(self):
        from core.models import WorkflowConfiguration

        configuration = WorkflowConfiguration.charger()
        configuration.capability_roles = {"bi.consulter": ["super_admin", "admin"]}
        configuration.save()
        self.assertEqual(self._me(Role.ADMIN)["bi_url"], "https://bi.exemple.org/d/bi-vue-ensemble")

    def test_rien_sans_grafana_dans_la_pile(self):
        with override_settings(SUPERVISION=False, BI_URL="https://bi.exemple.org"):
            self.assertIsNone(self._me(Role.SUPER_ADMIN)["bi_url"])
        with override_settings(SUPERVISION=True, BI_URL=""):
            self.assertIsNone(self._me(Role.SUPER_ADMIN)["bi_url"])
