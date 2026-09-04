"""L'adresse e-mail d'un compte est obligatoire et professionnelle."""

import io
import json
import tempfile
from pathlib import Path

import pyotp
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import override_settings
from rest_framework import status

from accounts.models import Role

from .test_scoping import ScopingTestCase


class EmailProfessionnelTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.siege)

    def creer(self, **champs):
        return self.client.post(
            "/api/users/",
            {
                "username": "kofi.innov", "password": "Provisoire-2026-Ghana",
                "role": Role.MANAGER, "countries": [self.togo.pk], **champs,
            },
            format="json",
        )

    def test_l_email_est_requis(self):
        for charge in ({}, {"email": ""}):
            with self.subTest(charge=charge):
                response = self.creer(**charge)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("email", response.data)
        self.assertFalse(User.objects.filter(username="kofi.innov").exists())

    def test_un_domaine_etranger_est_refuse_avec_un_message_clair(self):
        response = self.creer(email="kofi@gmail.com")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("innovpharma.net", response.data["email"][0])

    def test_l_adresse_est_normalisee_en_minuscules(self):
        response = self.creer(email="Kofi.Mensah@InnovPharma.NET")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "kofi.mensah@innovpharma.net")
        self.assertEqual(User.objects.get(username="kofi.innov").email, "kofi.mensah@innovpharma.net")

    def test_la_modification_applique_la_meme_regle(self):
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"email": "togo@yahoo.fr"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.rep_togo.refresh_from_db()
        self.assertEqual(self.rep_togo.email, "togo.innov@innovpharma.net")

    @override_settings(ALLOWED_EMAIL_DOMAINS=["innovpharma.net", "innov-pharma.ci"])
    def test_plusieurs_domaines_peuvent_etre_admis(self):
        response = self.creer(email="kofi@innov-pharma.ci")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SeedUsersEmailTests(ScopingTestCase):
    """La commande d'amorçage est un chemin d'écriture comme un autre."""

    def seed(self, users):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "seed.json"
            fichier.write_text(json.dumps({"users": users}), encoding="utf-8")
            call_command("seed_users", file=str(fichier), verbosity=0)

    def test_un_domaine_etranger_est_refuse(self):
        with self.assertRaisesMessage(CommandError, "innovpharma.net"):
            self.seed([{
                "username": "kofi.innov", "password": "Provisoire-2026-Ghana",
                "email": "kofi@gmail.com", "role": "manager", "countries": ["TG-02"],
            }])
        self.assertFalse(User.objects.filter(username="kofi.innov").exists())

    def test_l_email_est_requis(self):
        with self.assertRaisesMessage(CommandError, "requise"):
            self.seed([{
                "username": "kofi.innov", "password": "Provisoire-2026-Ghana",
                "role": "manager", "countries": ["TG-02"],
            }])

    def test_une_adresse_professionnelle_est_normalisee(self):
        self.seed([{
            "username": "kofi.innov", "password": "Provisoire-2026-Ghana",
            "email": "Kofi@InnovPharma.net", "role": "manager", "countries": ["TG-02"],
        }])

        self.assertEqual(User.objects.get(username="kofi.innov").email, "kofi@innovpharma.net")

    def test_un_compte_existant_garde_son_adresse_si_le_fichier_n_en_donne_pas(self):
        self.seed([{"username": "togo.innov", "role": "manager", "countries": ["TG-02"]}])

        self.rep_togo.refresh_from_db()
        self.assertEqual(self.rep_togo.email, "togo.innov@innovpharma.net")


class SeedUsersTotpTests(SeedUsersEmailTests):
    """``totp_secret`` enrôle d'emblée : pour les environnements jetables."""

    SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"

    def compte(self, **extra):
        return {
            "username": "captures.ci", "password": "Provisoire-2026-CI",
            "email": "captures.ci@innovpharma.net", "role": "super_admin",
            "must_change_password": False, **extra,
        }

    def test_le_secret_enrole_et_confirme_sans_l_afficher(self):
        sortie = io.StringIO()
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "seed.json"
            fichier.write_text(
                json.dumps({"users": [self.compte(totp_secret=self.SECRET.lower())]}),
                encoding="utf-8",
            )
            call_command("seed_users", file=str(fichier), stdout=sortie)

        profil = User.objects.get(username="captures.ci").profile
        self.assertEqual(profil.totp_secret, self.SECRET)
        self.assertIsNotNone(profil.totp_confirmed_at)
        self.assertNotIn(self.SECRET, sortie.getvalue())
        self.assertNotIn(self.SECRET.lower(), sortie.getvalue())

        # Un script se connecte avec le code calculé depuis le même secret.
        connexion = self.client.post(
            "/api/token-auth/",
            {"username": "captures.ci", "password": "Provisoire-2026-CI",
             "code": pyotp.TOTP(self.SECRET).now()},
        )
        self.assertEqual(connexion.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {connexion.data['token']}")
        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)

    def test_sans_la_cle_le_compte_reste_a_enroler(self):
        self.seed([self.compte()])

        profil = User.objects.get(username="captures.ci").profile
        self.assertEqual(profil.totp_secret, "")
        self.assertIsNone(profil.totp_confirmed_at)

    def test_relancee_avec_le_meme_secret_elle_ne_change_rien(self):
        self.seed([self.compte(totp_secret=self.SECRET)])
        confirme = User.objects.get(username="captures.ci").profile.totp_confirmed_at

        self.seed([self.compte(totp_secret=self.SECRET)])

        profil = User.objects.get(username="captures.ci").profile
        self.assertEqual(profil.totp_confirmed_at, confirme)

    def test_un_secret_invalide_est_refuse(self):
        for secret in ("", "pas du base32 !"):
            with self.subTest(secret=secret):
                with self.assertRaisesMessage(CommandError, "base32"):
                    self.seed([self.compte(totp_secret=secret)])
        self.assertFalse(User.objects.filter(username="captures.ci").exists())
