"""L'obligation de double authentification peut ne viser que certains rôles.

CLAUDE.md recommandait de l'imposer aux comptes privilégiés avant
l'ouverture aux filiales, « c'est un réglage de déploiement ». Il n'existait
pas : ``DJANGO_TOTP_REQUIRED`` était tout ou rien, et imposer aux
administrateurs imposait aux dix-sept filiales. ``DJANGO_TOTP_REQUIRED_ROLES``
(décision 86) ferme la plateforme aux seuls rôles nommés ; la politique
vaut pour le verrou, l'admin Django et ``GET /api/me/`` — une seule
fonction, ``accounts.middleware.totp_exige_pour``, tranche pour les trois.
"""

from django.test import override_settings
from rest_framework import status

from accounts.middleware import totp_exige_pour
from accounts.models import Role

from .test_scoping import ScopingTestCase, make_user


@override_settings(TOTP_REQUIRED=False, TOTP_REQUIRED_ROLES=frozenset({"admin", "super_admin"}))
class ObligationParRoleTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("rh.totp.innov", Role.ADMIN, totp_confirmed=False)
        self.manager = make_user("pays.totp.innov", Role.MANAGER, [self.togo], totp_confirmed=False)

    def test_la_politique_vise_les_roles_nommes(self):
        self.assertTrue(totp_exige_pour(self.admin.profile))
        self.assertFalse(totp_exige_pour(self.manager.profile))
        self.assertFalse(totp_exige_pour(None))

    def test_un_administrateur_non_enrole_est_cantonne_a_l_enrolement(self):
        self.login(self.admin)

        response = self.client.get("/api/countries/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(response.json()["totp_setup_required"])
        self.assertEqual(self.client.post("/api/me/2fa/enrol/").status_code, status.HTTP_200_OK)

    def test_un_manager_non_enrole_travaille(self):
        self.login(self.manager)

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)

    def test_le_profil_dit_la_politique_de_ce_compte(self):
        self.login(self.admin)
        self.assertTrue(self.client.get("/api/me/").data["totp_required"])

        self.login(self.manager)
        self.assertFalse(self.client.get("/api/me/").data["totp_required"])

    @override_settings(TOTP_REQUIRED=True)
    def test_l_obligation_pour_tous_l_emporte_sur_la_liste(self):
        self.assertTrue(totp_exige_pour(self.manager.profile))
        self.login(self.manager)

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_403_FORBIDDEN)


class RoleInconnuTests(ScopingTestCase):
    def test_un_role_inconnu_est_refuse_au_demarrage(self):
        """Une faute de frappe dans .env ne doit pas laisser croire que les
        administrateurs sont protégés."""
        import importlib
        import os
        import sys
        from unittest import mock

        from django.core.exceptions import ImproperlyConfigured

        with mock.patch.dict(os.environ, {"DJANGO_TOTP_REQUIRED_ROLES": "admin,auditeur"}), \
                mock.patch.object(sys, "argv", ["manage.py", "test"]):
            import config.settings

            with self.assertRaises(ImproperlyConfigured) as erreur:
                importlib.reload(config.settings)
        self.assertIn("auditeur", str(erreur.exception))
        with mock.patch.dict(os.environ, {"DJANGO_TOTP_REQUIRED_ROLES": ""}), \
                mock.patch.object(sys, "argv", ["manage.py", "test"]):
            importlib.reload(config.settings)


class RolesConnusTests(ScopingTestCase):
    def test_la_liste_des_reglages_suit_les_roles_du_modele(self):
        """Les réglages ne peuvent pas importer le modèle : leur liste est
        recopiée. Elle doit dire la même chose que lui — un ``dm`` ou un
        ``df`` d'avant la décision 89 est refusé au démarrage."""
        from config import settings as reglages

        from accounts.models import Role

        self.assertEqual(reglages._ROLES_CONNUS, set(Role.values))
