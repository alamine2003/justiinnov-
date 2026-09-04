"""Plateforme bilingue : messages en anglais sur demande, français sinon."""

from django.test import override_settings
from rest_framework import status

from accounts.models import Role

from .test_scoping import ScopingTestCase


class LangueDesReponsesTests(ScopingTestCase):
    def test_une_permission_refusee_se_lit_en_anglais(self):
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/countries/",
            {"name": "Bénin", "code": "BJ", "currency": "XOF", "timezone": "Africa/Porto-Novo"},
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "Your role does not allow this action.")

    def test_sans_en_tete_le_francais_reste_la_reference(self):
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/countries/",
            {"name": "Bénin", "code": "BJ", "currency": "XOF", "timezone": "Africa/Porto-Novo"},
        )

        self.assertEqual(response.data["detail"], "Votre rôle ne permet pas cette action.")

    def test_une_validation_se_lit_en_anglais(self):
        self.login(self.siege)

        response = self.client.post(
            "/api/users/",
            {
                "username": "kofi.innov", "password": "Provisoire-2026-Ghana",
                "role": Role.MANAGER, "email": "kofi@gmail.com",
            },
            format="json",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("company domain", response.data["email"][0])

    @override_settings(TOTP_REQUIRED=True)
    def test_le_verrou_du_middleware_se_lit_en_anglais(self):
        self.rep_togo.profile.totp_confirmed_at = None
        self.rep_togo.profile.save()
        self.login(self.rep_togo)

        response = self.client.get("/api/countries/", HTTP_ACCEPT_LANGUAGE="en")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Two-factor authentication is required", response.json()["detail"])

    def test_les_libelles_de_roles_sont_traduits(self):
        self.login(self.rep_togo)

        en = self.client.get("/api/me/", HTTP_ACCEPT_LANGUAGE="en").data
        fr = self.client.get("/api/me/").data

        self.assertEqual(en["role_display"], "Manager (country)")
        self.assertEqual(fr["role_display"], "Manager (pays)")


class PreferenceDeLangueTests(ScopingTestCase):
    def test_le_titulaire_regle_sa_langue(self):
        self.login(self.rep_togo)

        response = self.client.patch("/api/me/", {"language": "en"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["language"], "en")
        self.rep_togo.profile.refresh_from_db()
        self.assertEqual(self.rep_togo.profile.language, "en")

    def test_le_defaut_est_le_francais(self):
        self.login(self.rep_togo)

        self.assertEqual(self.client.get("/api/me/").data["language"], "fr")

    def test_une_langue_inconnue_est_refusee(self):
        self.login(self.rep_togo)

        response = self.client.patch("/api/me/", {"language": "de"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_la_preference_ne_change_pas_la_langue_de_la_reponse(self):
        """La préférence sert à l'interface ; la langue d'une réponse suit
        l'en-tête envoyé, pour que le même client reste cohérent."""
        self.rep_togo.profile.language = "en"
        self.rep_togo.profile.save()
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/countries/",
            {"name": "Bénin", "code": "BJ", "currency": "XOF", "timezone": "Africa/Porto-Novo"},
        )

        self.assertEqual(response.data["detail"], "Votre rôle ne permet pas cette action.")

    def test_le_reste_du_profil_n_est_pas_modifiable_ici(self):
        self.login(self.rep_togo)

        response = self.client.patch("/api/me/", {"role": Role.SUPER_ADMIN}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rep_togo.profile.refresh_from_db()
        self.assertEqual(self.rep_togo.profile.role, Role.MANAGER)
