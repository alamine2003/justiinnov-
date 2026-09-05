"""L'admin Django obéit aux mêmes verrous que l'API : mot de passe
provisoire, puis double authentification quand la politique l'exige."""

from django.test import TestCase, override_settings

from accounts.models import Role, aligner_drapeaux

from .test_scoping import make_user


@override_settings(APP_BASE_URL="https://controle.example.org")
class AdminVerrouilleTests(TestCase):
    def super_admin(self, **etat):
        user = make_user("dg.innov", Role.SUPER_ADMIN, **etat)
        aligner_drapeaux(user, Role.SUPER_ADMIN)
        user.save()
        self.client.force_login(user)
        return user

    def test_un_mot_de_passe_provisoire_ferme_l_admin(self):
        """Régression : connecté par session, un super administrateur au mot
        de passe provisoire avait tous les droits sur le back-office."""
        self.super_admin(must_change_password=True)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://controle.example.org")

    @override_settings(TOTP_REQUIRED=True)
    def test_l_enrolement_manquant_ferme_l_admin_quand_la_politique_l_exige(self):
        self.super_admin(totp_confirmed=False)

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://controle.example.org")

    @override_settings(TOTP_REQUIRED=False)
    def test_sans_obligation_un_compte_non_enrole_entre(self):
        self.super_admin(totp_confirmed=False)

        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_un_compte_en_regle_entre(self):
        self.super_admin()

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)

    def test_la_connexion_et_la_deconnexion_restent_joignables(self):
        """Sans elles, l'admin n'aurait ni entrée ni sortie."""
        self.super_admin(must_change_password=True)
        self.assertEqual(self.client.post("/admin/logout/").status_code, 200)

        # Déconnecté, le formulaire s'affiche ; connecté, Django renvoie
        # lui-même vers l'index — que le verrou ferme.
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)

    def test_un_anonyme_est_toujours_renvoye_au_formulaire(self):
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/login/"))
