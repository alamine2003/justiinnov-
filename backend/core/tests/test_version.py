"""``APP_VERSION`` : la version du serveur, lue dans le menu du compte.

Réservée au siège authentifié, sans verrou transverse actif (pentest,
cycle 2) : le dépôt GitHub est public, le SHA exact en service ne doit pas
se lire depuis un pays, ni avant d'avoir prouvé son identité. La forme de
la valeur elle-même (``lire_version``) est testée séparément, fonction pure,
dans ``config/tests/test_version_env.py``.
"""

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user


class VersionTests(APITestCase):
    def setUp(self):
        user = make_user("siege.version", Role.SUPER_ADMIN, [])
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_defaut_dev(self):
        """Sans ``APP_VERSION`` (CI, développement), le repli est ``dev``."""
        self.assertEqual(self.client.get("/api/me/").data["api_version"], "dev")
        self.assertEqual(
            self.client.get("/api/configuration/").data["systeme"]["version_api"], "dev"
        )

    @override_settings(APP_VERSION="sha-abc123def456")
    def test_suit_l_environnement(self):
        me = self.client.get("/api/me/")
        configuration = self.client.get("/api/configuration/")

        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["api_version"], "sha-abc123def456")
        self.assertEqual(configuration.data["systeme"]["version_api"], "sha-abc123def456")

    def test_anonyme_refuse(self):
        """Un anonyme ne voit pas la version : ``/api/me/`` exige un jeton."""
        self.client.credentials()
        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sante_a_deux_cles_exactement(self):
        """``/api/health/`` reste inchangée : aucune fuite de version à un anonyme."""
        self.client.credentials()
        response = self.client.get("/api/health/")
        self.assertEqual(set(response.data.keys()), {"status", "database"})

    @override_settings(APP_VERSION="sha-abc123def456")
    def test_manager_ne_voit_jamais_la_version(self):
        """Un manager de pays n'est pas un compte du siège : le SHA en
        service, visible depuis un dépôt public, ne se lit pas depuis un
        pays."""
        user = make_user("pays.manager", Role.MANAGER, [])
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["api_version"], "")

    @override_settings(APP_VERSION="sha-abc123def456")
    def test_siege_sans_verrou_voit_la_version(self):
        """Administrateur, DM et DF : comptes du siège, aucun verrou actif."""
        for role in (Role.ADMIN, Role.DM, Role.DF):
            with self.subTest(role=role):
                user = make_user(f"siege.{role}", role, [])
                token = Token.objects.create(user=user)
                self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

                response = self.client.get("/api/me/")

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["api_version"], "sha-abc123def456")

    @override_settings(APP_VERSION="sha-abc123def456")
    def test_mot_de_passe_provisoire_masque_la_version(self):
        """Un compte du siège au mot de passe encore provisoire ne peut rien
        faire d'autre que le changer (``ProvisionalPasswordMiddleware``,
        route ``/api/me/`` exemptée) : ``api_version`` ne doit pas fuiter
        avant ce changement."""
        user = make_user(
            "siege.provisoire", Role.ADMIN, [], must_change_password=True
        )
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["api_version"], "")

    @override_settings(APP_VERSION="sha-abc123def456", TOTP_REQUIRED=True)
    def test_totp_exige_et_non_confirme_masque_la_version(self):
        """Politique ``TOTP_REQUIRED`` : un compte du siège pas encore
        enrôlé n'a pas fini de prouver son identité."""
        user = make_user("siege.non_enrole", Role.ADMIN, [], totp_confirmed=False)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["api_version"], "")

    @override_settings(APP_VERSION="sha-abc123def456", TOTP_REQUIRED=True)
    def test_totp_exige_et_confirme_laisse_voir_la_version(self):
        user = make_user("siege.enrole", Role.ADMIN, [], totp_confirmed=True)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["api_version"], "sha-abc123def456")

    @override_settings(APP_VERSION="sha-abc123def456")
    def test_couplage_mot_de_passe_provisoire_middleware_et_api_version(self):
        """Preuve du couplage (pentest, cycle 3) : ``accounts.middleware.
        verrou_actif`` est le même prédicat des deux côtés. Tant que le
        middleware refuse ce compte du siège sur une route ordinaire,
        ``api_version`` reste vide sur son propre ``/api/me/`` ; dès que le
        mot de passe redevient personnel, le middleware laisse passer et la
        version revient, sans nouveau jeton."""
        user = make_user("siege.couplage.mdp", Role.ADMIN, [], must_change_password=True)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        refuse = self.client.get("/api/countries/")
        self.assertEqual(refuse.status_code, status.HTTP_403_FORBIDDEN)
        # ``JsonResponse`` du middleware, pas une réponse DRF : ``.json()``,
        # pas ``.data``.
        self.assertTrue(refuse.json().get("must_change_password"))
        self.assertEqual(self.client.get("/api/me/").data["api_version"], "")

        user.profile.must_change_password = False
        user.profile.save(update_fields=["must_change_password"])

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get("/api/me/").data["api_version"], "sha-abc123def456"
        )

    @override_settings(APP_VERSION="sha-abc123def456", TOTP_REQUIRED=True)
    def test_couplage_totp_non_confirme_middleware_et_api_version(self):
        """Même preuve, second verrou : double authentification exigée et
        non confirmée."""
        user = make_user("siege.couplage.totp", Role.ADMIN, [], totp_confirmed=False)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        refuse = self.client.get("/api/countries/")
        self.assertEqual(refuse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(refuse.json().get("totp_setup_required"))
        self.assertEqual(self.client.get("/api/me/").data["api_version"], "")

        user.profile.totp_confirmed_at = timezone.now()
        user.profile.save(update_fields=["totp_confirmed_at"])

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get("/api/me/").data["api_version"], "sha-abc123def456"
        )

    @override_settings(APP_VERSION="sha-abc123def456")
    def test_manager_dm_df_n_ont_jamais_acces_a_la_configuration(self):
        """Le champ ``version_api`` ne rouvre pas ``/api/configuration/`` : la
        capacité ``configuration.manage`` reste fixée aux administrateurs
        (verrou, décision produit) — même les comptes du siège qui lisent
        ``api_version`` sur leur propre profil restent dehors, et rien ne
        fuit dans le refus."""
        for role in (Role.MANAGER, Role.DM, Role.DF):
            with self.subTest(role=role):
                user = make_user(f"siege.{role}", role, [])
                token = Token.objects.create(user=user)
                self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

                configuration = self.client.get("/api/configuration/")

                # La configuration reste fermée : ni la version, ni aucun
                # autre réglage n'est rendu dans le refus.
                self.assertEqual(configuration.status_code, status.HTTP_403_FORBIDDEN)
                self.assertNotIn("systeme", configuration.data)
                self.assertEqual(set(configuration.data.keys()), {"detail"})
