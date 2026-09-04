"""Double authentification : enrôlement, connexion, réinitialisation, politique.

Le mécanisme est toujours là ; son obligation est une politique
(``TOTP_REQUIRED``). Les tests du verrou la posent explicitement ; ceux de
la fin vérifient ce qui reste vrai quand elle n'est pas exigée.
"""

import base64
from datetime import timedelta

import pyotp
from django.db.models import Max
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import Role
from core.models import ChangeLog

from .test_scoping import ScopingTestCase, make_user

MOT_DE_PASSE = "Motdepasse-2026-test"


def code_courant(secret):
    return pyotp.TOTP(secret).now()


def code_perime(secret):
    """Un code d'il y a cinq minutes : hors fenêtre, à coup sûr.

    Mieux qu'un « 000000 » qui, une fois sur un million, serait le bon.
    """
    return pyotp.TOTP(secret).at(timezone.now() - timedelta(minutes=5))


@override_settings(TOTP_REQUIRED=True)
class VerrouDeDoubleAuthentificationTests(ScopingTestCase):
    """Quand la politique l'exige, un compte non enrôlé ne fait rien d'autre
    que s'enrôler."""

    def setUp(self):
        super().setUp()
        self.repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.nouveau = make_user(
            "nouveau.innov", Role.MANAGER, [self.togo], totp_confirmed=False,
        )
        self.login(self.nouveau)

    def entrees(self, action):
        return ChangeLog.objects.filter(
            pk__gt=self.repere, action=action, object_id=self.nouveau.pk,
        )

    def test_la_plateforme_est_fermee(self):
        for url in ("/api/countries/", "/api/teams/", "/api/dossiers/"):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertTrue(response.json()["totp_setup_required"])

    def test_les_sorties_restent_ouvertes(self):
        """Le profil, le mot de passe, l'enrôlement et la déconnexion : sans
        eux, le verrou n'aurait pas d'issue."""
        profil = self.client.get("/api/me/")
        self.assertEqual(profil.status_code, status.HTTP_200_OK)
        self.assertFalse(profil.data["totp_confirmed"])

        mot_de_passe = self.client.post(
            "/api/me/password/",
            {"current_password": MOT_DE_PASSE, "new_password": "Personnel-2026-Togo"},
        )
        self.assertEqual(mot_de_passe.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {mot_de_passe.data['token']}")

        self.assertEqual(
            self.client.post("/api/me/2fa/enrol/").status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            self.client.post("/api/logout/").status_code, status.HTTP_204_NO_CONTENT
        )

    def test_l_enrolement_rend_un_qr_libelle_par_l_email(self):
        response = self.client.post("/api/me/2fa/enrol/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uri = response.data["otpauth_uri"]
        self.assertTrue(uri.startswith("otpauth://totp/JUSTI%20INNOV:nouveau.innov%40innovpharma.net?"))
        self.assertIn("issuer=JUSTI%20INNOV", uri)
        self.assertIn(f"secret={response.data['secret']}", uri)
        png = base64.b64decode(response.data["qr_png_base64"])
        self.assertTrue(png.startswith(b"\x89PNG"))
        # Le secret n'est engagé qu'à la confirmation.
        self.nouveau.profile.refresh_from_db()
        self.assertEqual(self.nouveau.profile.totp_secret, response.data["secret"])
        self.assertIsNone(self.nouveau.profile.totp_confirmed_at)

    def test_la_confirmation_ouvre_la_plateforme_et_laisse_une_trace(self):
        secret = self.client.post("/api/me/2fa/enrol/").data["secret"]

        response = self.client.post(
            "/api/me/2fa/confirm/", {"code": code_courant(secret)},
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["totp_confirmed"])
        self.assertTrue(self.client.get("/api/me/").data["totp_confirmed"])
        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)
        trace = self.entrees(ChangeLog.Actions.TOTP_CONFIRMED).get()
        self.assertEqual(trace.performed_by, "nouveau.innov")
        self.assertEqual(trace.ip_address, "203.0.113.7")
        self.assertNotIn(secret, str(trace.__dict__))

    def test_un_code_faux_est_refuse_et_journalise(self):
        secret = self.client.post("/api/me/2fa/enrol/").data["secret"]

        response = self.client.post("/api/me/2fa/confirm/", {"code": code_perime(secret)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertTrue(self.entrees(ChangeLog.Actions.LOGIN_FAILED).exists())
        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_403_FORBIDDEN)

    def test_confirmer_sans_enrolement_est_refuse(self):
        response = self.client.post("/api/me/2fa/confirm/", {"code": "123456"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_le_mot_de_passe_provisoire_passe_avant(self):
        """Le QR d'enrôlement ne s'affiche pas à qui n'a que le mot de passe
        distribué par le siège."""
        provisoire = make_user(
            "frais.innov", Role.MANAGER, [self.togo],
            must_change_password=True, totp_confirmed=False,
        )
        self.login(provisoire)

        for url, methode in (("/api/countries/", "get"), ("/api/me/2fa/enrol/", "post")):
            with self.subTest(url=url):
                response = getattr(self.client, methode)(url)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertTrue(response.json()["must_change_password"])
                self.assertNotIn("totp_setup_required", response.json())

    def test_un_compte_confirme_ne_se_reenrole_pas(self):
        """Le secret actif ne se remplace pas sans trace : c'est le siège
        qui réinitialise."""
        self.login(self.rep_togo)
        avant = self.rep_togo.profile.totp_secret

        response = self.client.post("/api/me/2fa/enrol/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.rep_togo.profile.refresh_from_db()
        self.assertEqual(self.rep_togo.profile.totp_secret, avant)


class ConnexionAvecCodeTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.user = make_user("dina.innov", Role.DF)
        self.secret = self.user.profile.totp_secret

    def connexion(self, **extra):
        return self.client.post(
            "/api/token-auth/",
            {"username": "dina.innov", "password": MOT_DE_PASSE, **extra},
        )

    def test_sans_code_la_connexion_est_refusee(self):
        response = self.connexion()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], ["Code de double authentification requis."])
        self.assertTrue(response.data["totp_required"])
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_un_mauvais_mot_de_passe_ne_demande_pas_de_code(self):
        """La réponse ne doit pas dire à l'attaquant que le mot de passe
        était le bon."""
        response = self.client.post(
            "/api/token-auth/", {"username": "dina.innov", "password": "mauvais"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("totp_required", response.data)
        self.assertNotIn("code", response.data)

    def test_un_code_faux_est_refuse_et_journalise(self):
        response = self.connexion(code=code_perime(self.secret), REMOTE_ADDR="203.0.113.9")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], ["Code de double authentification invalide."])
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        echec = ChangeLog.objects.filter(
            pk__gt=self.repere, action=ChangeLog.Actions.LOGIN_FAILED,
        ).get()
        self.assertEqual(echec.object_id, self.user.pk)
        self.assertEqual(echec.changed_fields, ["totp"])
        self.assertEqual(echec.performed_by, "dina.innov")

    def test_un_code_valide_rend_le_jeton(self):
        response = self.connexion(code=code_courant(self.secret))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], Token.objects.get(user=self.user).key)
        self.assertTrue(
            ChangeLog.objects.filter(pk__gt=self.repere, action=ChangeLog.Actions.LOGIN).exists()
        )

    def test_la_fenetre_tolere_le_code_precedent_mais_pas_plus(self):
        precedent = pyotp.TOTP(self.secret).at(timezone.now() - timedelta(seconds=30))
        self.assertEqual(self.connexion(code=precedent).status_code, status.HTTP_200_OK)

        Token.objects.filter(user=self.user).delete()
        trop_vieux = pyotp.TOTP(self.secret).at(timezone.now() - timedelta(seconds=90))
        self.assertEqual(self.connexion(code=trop_vieux).status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_compte_non_enrole_se_connecte_sans_code(self):
        """C'est le middleware qui le cantonne à l'enrôlement quand la
        politique l'exige, pas la connexion : sans jeton, il ne pourrait pas
        s'enrôler."""
        make_user("nouveau.innov", Role.MANAGER, [self.togo], totp_confirmed=False)

        response = self.client.post(
            "/api/token-auth/", {"username": "nouveau.innov", "password": MOT_DE_PASSE}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(TOTP_REQUIRED=True)
class ReinitialisationTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.admin = make_user("admin.innov", Role.ADMIN)
        self.login(self.admin)

    def test_un_admin_reinitialise_et_le_jeton_tombe(self):
        jeton = Token.objects.create(user=self.rep_togo)

        response = self.client.post(
            f"/api/users/{self.rep_togo.pk}/reset-2fa/", REMOTE_ADDR="203.0.113.7"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["totp_confirmed"])
        self.rep_togo.profile.refresh_from_db()
        self.assertEqual(self.rep_togo.profile.totp_secret, "")
        self.assertIsNone(self.rep_togo.profile.totp_confirmed_at)
        self.assertFalse(Token.objects.filter(key=jeton.key).exists())
        trace = ChangeLog.objects.filter(
            pk__gt=self.repere, action=ChangeLog.Actions.TOTP_RESET,
            object_id=self.rep_togo.pk,
        ).get()
        self.assertEqual(trace.performed_by, "admin.innov")
        self.assertEqual(trace.ip_address, "203.0.113.7")
        self.assertEqual(trace.diff, {"totp_confirmed": [True, False]})

        # Le titulaire se reconnecte sans code, et ne peut que se réenrôler.
        self.client.credentials()
        connexion = self.client.post(
            "/api/token-auth/", {"username": "togo.innov", "password": MOT_DE_PASSE}
        )
        self.assertEqual(connexion.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {connexion.data['token']}")
        ferme = self.client.get("/api/countries/")
        self.assertEqual(ferme.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ferme.json()["totp_setup_required"])

    def test_un_admin_ne_reinitialise_pas_un_super_admin(self):
        response = self.client.post(f"/api/users/{self.siege.pk}/reset-2fa/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.siege.profile.refresh_from_db()
        self.assertTrue(self.siege.profile.totp_confirmed)

    def test_un_super_admin_reinitialise_un_pair(self):
        self.login(self.siege)
        pair = make_user("dg.innov", Role.SUPER_ADMIN)

        response = self.client.post(f"/api/users/{pair.pk}/reset-2fa/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_un_pays_ne_reinitialise_rien(self):
        self.login(self.rep_togo)

        response = self.client.post(f"/api/users/{self.rep_togo.pk}/reset-2fa/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_la_liste_des_comptes_dit_qui_est_enrole(self):
        make_user("nouveau.innov", Role.MANAGER, [self.togo], totp_confirmed=False)

        response = self.client.get("/api/users/")

        etats = {u["username"]: u["totp_confirmed"] for u in response.data["results"]}
        self.assertTrue(etats["togo.innov"])
        self.assertFalse(etats["nouveau.innov"])


@override_settings(TOTP_REQUIRED=False)
class PolitiqueNonExigeeTests(ScopingTestCase):
    """Sans obligation, l'enrôlement reste proposé — et un compte enrôlé de
    son plein gré fournit toujours son code : un second facteur qu'on a
    choisi d'activer ne se contourne pas."""

    def setUp(self):
        super().setUp()
        self.nouveau = make_user(
            "nouveau.innov", Role.MANAGER, [self.togo], totp_confirmed=False,
        )

    def test_un_compte_non_enrole_se_connecte_sans_code(self):
        response = self.client.post(
            "/api/token-auth/", {"username": "nouveau.innov", "password": MOT_DE_PASSE}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], Token.objects.get(user=self.nouveau).key)

    def test_la_plateforme_est_ouverte_sans_enrolement(self):
        self.login(self.nouveau)

        for url in ("/api/countries/", "/api/teams/", "/api/dossiers/"):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_le_profil_dit_que_la_politique_n_est_pas_exigee(self):
        """L'interface lit la politique et l'état du compte séparément : elle
        propose l'enrôlement sans y conduire de force."""
        self.login(self.nouveau)

        profil = self.client.get("/api/me/").data

        self.assertFalse(profil["totp_required"])
        self.assertFalse(profil["totp_confirmed"])

    @override_settings(TOTP_REQUIRED=True)
    def test_le_profil_dit_quand_la_politique_est_exigee(self):
        self.login(self.nouveau)

        profil = self.client.get("/api/me/").data

        self.assertTrue(profil["totp_required"])
        self.assertFalse(profil["totp_confirmed"])

    def test_un_compte_enrole_fournit_toujours_son_code(self):
        secret = self.rep_togo.profile.totp_secret

        sans = self.client.post(
            "/api/token-auth/", {"username": "togo.innov", "password": MOT_DE_PASSE}
        )
        faux = self.client.post(
            "/api/token-auth/",
            {"username": "togo.innov", "password": MOT_DE_PASSE, "code": code_perime(secret)},
        )
        bon = self.client.post(
            "/api/token-auth/",
            {"username": "togo.innov", "password": MOT_DE_PASSE, "code": code_courant(secret)},
        )

        self.assertEqual(sans.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(sans.data["totp_required"])
        self.assertEqual(faux.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(bon.status_code, status.HTTP_200_OK)

    def test_l_enrolement_volontaire_reste_possible(self):
        """Un titulaire qui veut protéger son compte le peut, et son code
        est exigé dès la connexion suivante."""
        self.login(self.nouveau)
        secret = self.client.post("/api/me/2fa/enrol/").data["secret"]
        confirmation = self.client.post(
            "/api/me/2fa/confirm/", {"code": code_courant(secret)}
        )
        self.assertEqual(confirmation.status_code, status.HTTP_200_OK)
        self.assertTrue(self.client.get("/api/me/").data["totp_confirmed"])

        self.client.credentials()
        response = self.client.post(
            "/api/token-auth/", {"username": "nouveau.innov", "password": MOT_DE_PASSE}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["totp_required"])
