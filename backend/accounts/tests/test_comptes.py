"""Gestion des comptes : trace, jetons, hiérarchie des rôles."""

from datetime import timedelta
from unittest.mock import patch

import pyotp
from django.contrib.auth.models import User
from django.db.models import Max
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.authentication import JetonAuthentication
from accounts.models import Role, UserProfile
from accounts.permissions import get_access
from core.models import ChangeLog

from .test_scoping import ScopingTestCase, make_user

MOT_DE_PASSE = "Motdepasse-2026-test"


#: Le journal est en ajout seul, jusque dans la base : on ne l'efface pas
#: entre deux tests, on ignore ce qui a été écrit avant le test.
_repere = {"pk": 0}


def entrees(user=None, **filtres):
    queryset = ChangeLog.objects.filter(
        pk__gt=_repere["pk"], model_name=ChangeLog.Models.USER, **filtres
    )
    if user is not None:
        queryset = queryset.filter(object_id=user.pk)
    return queryset.order_by("id")


class TraceDesComptesTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("admin.innov", Role.ADMIN)
        _repere["pk"] = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.login(self.siege)

    def test_la_creation_est_tracee(self):
        response = self.client.post(
            "/api/users/",
            {
                "username": "kofi.innov", "email": "kofi@innovpharma.net",
                "password": "Provisoire-2026-Ghana", "role": Role.MANAGER,
                "countries": [self.togo.pk],
            },
            format="json",
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="kofi.innov")
        entry = entrees(user, action=ChangeLog.Actions.CREATED).get()
        self.assertEqual(entry.performed_by, self.siege.username)
        self.assertEqual(entry.ip_address, "203.0.113.7")
        self.assertIsNone(entry.country)
        # Le périmètre initial est tracé aussi, avec avant/après.
        perimetre = entrees(user, changed_fields=["countries"]).get()
        self.assertEqual(perimetre.diff, {"countries": [[], ["Togo (TG)"]]})

    def test_la_modification_porte_avant_et_apres(self):
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"role": Role.DM, "email": "togo@innovpharma.net"},
            format="json",
            REMOTE_ADDR="203.0.113.7",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Le rôle est journalisé par le profil lui-même (``accounts.signals``),
        # le compte par la vue : deux entrées, chacune avec avant/après.
        diffs = [e.diff for e in entrees(self.rep_togo, action=ChangeLog.Actions.UPDATED)]
        self.assertIn({"role": [Role.MANAGER, Role.DM]}, diffs)
        self.assertIn(
            {"email": ["togo.innov@innovpharma.net", "togo@innovpharma.net"]}, diffs
        )
        for entry in entrees(self.rep_togo, action=ChangeLog.Actions.UPDATED):
            self.assertEqual(entry.ip_address, "203.0.113.7")
            self.assertEqual(entry.performed_by, self.siege.username)

    def test_le_changement_de_perimetre_est_trace(self):
        """Donner accès aux dépenses d'un autre pays doit se relire."""
        self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"countries": [self.togo.pk, self.ivoire.pk]},
            format="json",
        )

        entry = entrees(self.rep_togo, changed_fields=["countries"]).get()
        self.assertEqual(
            entry.diff, {"countries": [["Togo (TG)"], ["Côte d'Ivoire (CI)", "Togo (TG)"]]}
        )

    def test_le_changement_d_equipes_est_trace(self):
        """Restreindre ou élargir la vue d'un manager à des équipes se relit
        comme un changement de pays."""
        self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"teams": [self.team_togo.pk]},
            format="json",
        )

        entry = entrees(self.rep_togo, changed_fields=["teams"]).get()
        self.assertEqual(entry.diff, {"teams": [[], ["Équipe Lomé (TG)"]]})

    def test_le_nom_de_compte_est_immuable(self):
        """Les traces et la règle des quatre yeux comparent sur ce nom."""
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"username": "autre.innov", "first_name": "Kossi"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.rep_togo.refresh_from_db()
        self.assertEqual(self.rep_togo.username, "togo.innov")
        self.assertEqual(self.rep_togo.first_name, "")
        self.assertFalse(entrees(self.rep_togo).exists())

    def test_le_meme_nom_de_compte_repasse_sans_bruit(self):
        """Un formulaire renvoie tout le compte, nom compris : identique, il
        n'est ni refusé ni journalisé. Prénom et nom restent libres."""
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"username": "togo.innov", "first_name": "Kossi", "last_name": "Mensah"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = entrees(self.rep_togo, action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(sorted(entry.changed_fields), ["first_name", "last_name"])
        self.assertNotIn("username", entry.diff)

    def test_un_role_change_par_l_admin_django_est_trace_et_realigne_le_compte(self):
        """L'admin Django enregistre le profil sans passer par l'API : la
        trace et les drapeaux du compte ne doivent pas en dépendre."""
        profil = self.rep_togo.profile
        profil.role = Role.ADMIN
        profil.language = "en"
        profil.save()

        self.rep_togo.refresh_from_db()
        self.assertTrue(self.rep_togo.is_staff)
        self.assertFalse(self.rep_togo.is_superuser)
        entry = entrees(self.rep_togo, action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(
            entry.diff,
            {"role": [Role.MANAGER, Role.ADMIN], "language": ["fr", "en"]},
        )
        # Hors requête API, l'auteur est celui de la requête courante — ici
        # le siège connecté par jeton n'a pas encore été résolu : l'entrée
        # existe, c'est l'essentiel ; ``seed_users`` la signe de son nom.

    def test_la_langue_choisie_par_le_titulaire_est_tracee(self):
        self.login(self.rep_togo)

        self.client.patch("/api/me/", {"language": "en"}, format="json")

        entry = entrees(self.rep_togo, changed_fields=["language"]).get()
        self.assertEqual(entry.diff, {"language": ["fr", "en"]})
        self.assertEqual(entry.performed_by, "togo.innov")

    def test_une_modification_sans_changement_ne_trace_rien(self):
        self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"role": Role.MANAGER}, format="json"
        )

        self.assertFalse(entrees(self.rep_togo).exists())

    def test_la_desactivation_est_tracee_et_revoque_le_jeton(self):
        Token.objects.create(user=self.rep_togo)

        self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"is_active": False}, format="json"
        )

        entry = entrees(self.rep_togo, action=ChangeLog.Actions.DEACTIVATED).get()
        self.assertEqual(entry.diff, {"is_active": [True, False]})
        self.assertFalse(entrees(self.rep_togo, action=ChangeLog.Actions.UPDATED).exists())
        self.assertFalse(Token.objects.filter(user=self.rep_togo).exists())

    def test_la_reactivation_est_tracee(self):
        self.rep_togo.is_active = False
        self.rep_togo.save()

        self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"is_active": True}, format="json"
        )

        self.assertTrue(entrees(self.rep_togo, action=ChangeLog.Actions.REACTIVATED).exists())

    def test_la_reinitialisation_du_mot_de_passe(self):
        """Tracée, sans jamais le mot de passe ; le jeton tombe ; le mot de
        passe redevient provisoire."""
        ancien = Token.objects.create(user=self.rep_togo)

        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"password": "Nouveau-Provisoire-2026"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = entrees(self.rep_togo, action=ChangeLog.Actions.PASSWORD_RESET).get()
        self.assertEqual(entry.changed_fields, ["password"])
        self.assertNotIn("Nouveau-Provisoire-2026", str(entry.__dict__))
        self.assertFalse(Token.objects.filter(key=ancien.key).exists())
        self.rep_togo.profile.refresh_from_db()
        self.assertTrue(self.rep_togo.profile.must_change_password)
        self.assertTrue(response.data["must_change_password"])

    def test_must_change_password_n_est_pas_modifiable(self):
        """Le siège ne peut pas déclarer personnel un mot de passe qu'il
        connaît."""
        creation = self.client.post(
            "/api/users/",
            {
                "username": "kofi.innov", "email": "kofi@innovpharma.net", "password": "Provisoire-2026-Ghana",
                "role": Role.MANAGER, "must_change_password": False,
            },
            format="json",
        )
        self.assertTrue(creation.data["must_change_password"])

        modification = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"password": "Nouveau-Provisoire-2026", "must_change_password": False},
            format="json",
        )
        self.assertTrue(modification.data["must_change_password"])

    def test_les_drapeaux_django_suivent_le_role(self):
        """Un super administrateur rétrogradé ne doit pas garder l'admin."""
        self.client.post(
            "/api/users/",
            {"username": "dg.innov", "email": "dg@innovpharma.net", "password": "Provisoire-2026-DG", "role": Role.SUPER_ADMIN},
            format="json",
        )
        dg = User.objects.get(username="dg.innov")
        self.assertTrue(dg.is_superuser)
        self.assertTrue(dg.is_staff)

        self.client.patch(f"/api/users/{dg.pk}/", {"role": Role.DF}, format="json")

        dg.refresh_from_db()
        self.assertFalse(dg.is_superuser)
        self.assertFalse(dg.is_staff)


class HierarchieDesRolesTests(ScopingTestCase):
    """Seul un super administrateur touche à un compte de ce niveau."""

    def setUp(self):
        super().setUp()
        self.admin = make_user("admin.innov", Role.ADMIN)
        self.login(self.admin)

    def test_un_admin_ne_cree_pas_de_super_admin(self):
        response = self.client.post(
            "/api/users/",
            {"username": "dg.innov", "email": "dg@innovpharma.net", "password": "Provisoire-2026-DG", "role": Role.SUPER_ADMIN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="dg.innov").exists())

    def test_un_admin_n_attribue_pas_le_role(self):
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"role": Role.SUPER_ADMIN}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_un_admin_ne_modifie_pas_un_super_admin(self):
        for charge in ({"email": "x@innovpharma.net"}, {"password": "Pirate-2026-mdp"},
                       {"is_active": False}):
            with self.subTest(charge=charge):
                response = self.client.patch(
                    f"/api/users/{self.siege.pk}/", charge, format="json"
                )

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.siege.refresh_from_db()
        self.assertTrue(self.siege.is_active)
        self.assertTrue(self.siege.check_password(MOT_DE_PASSE))

    def test_un_admin_gere_les_autres_comptes(self):
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"role": Role.ADMIN}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_un_super_admin_gere_ses_pairs(self):
        self.login(self.siege)

        creation = self.client.post(
            "/api/users/",
            {"username": "dg.innov", "email": "dg@innovpharma.net", "password": "Provisoire-2026-DG", "role": Role.SUPER_ADMIN},
            format="json",
        )
        modification = self.client.patch(
            f"/api/users/{creation.data['id']}/", {"email": "dg@innovpharma.net"}, format="json"
        )

        self.assertEqual(creation.status_code, status.HTTP_201_CREATED)
        self.assertEqual(modification.status_code, status.HTTP_200_OK)


class JetonsTests(ScopingTestCase):
    def test_la_deconnexion_supprime_le_jeton(self):
        self.login(self.rep_togo)

        response = self.client.post("/api/logout/", REMOTE_ADDR="203.0.113.7")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(user=self.rep_togo).exists())
        entry = entrees(self.rep_togo, action=ChangeLog.Actions.LOGOUT).get()
        self.assertEqual(entry.ip_address, "203.0.113.7")
        # Le jeton ne vaut plus rien.
        self.assertEqual(
            self.client.get("/api/me/").status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_le_changement_de_mot_de_passe_remplace_le_jeton(self):
        self.login(self.rep_togo)
        ancien = Token.objects.get(user=self.rep_togo).key

        response = self.client.post(
            "/api/me/password/",
            {"current_password": MOT_DE_PASSE, "new_password": "Nouveau-Motdepasse-2026"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data["token"], ancien)
        self.assertFalse(Token.objects.filter(key=ancien).exists())
        self.assertTrue(entrees(self.rep_togo, action=ChangeLog.Actions.PASSWORD_CHANGED).exists())
        # L'ancien jeton est refusé, le nouveau accepté.
        self.assertEqual(self.client.get("/api/me/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get("/api/me/").status_code, status.HTTP_200_OK)

    def _vieillir(self, user, jours):
        Token.objects.filter(user=user).update(created=timezone.now() - timedelta(days=jours))

    def test_un_jeton_trop_vieux_est_refuse(self):
        self.login(self.rep_togo)
        self._vieillir(self.rep_togo, 31)

        response = self.client.get("/api/countries/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("expiré", response.data["detail"])

    def test_un_jeton_recent_est_accepte(self):
        self.login(self.rep_togo)
        self._vieillir(self.rep_togo, 29)

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)

    @override_settings(TOKEN_MAX_AGE_DAYS=0)
    def test_zero_desactive_la_limite(self):
        self.login(self.rep_togo)
        self._vieillir(self.rep_togo, 400)

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)

    def test_la_connexion_renouvelle_un_jeton_expire(self):
        """``get_or_create`` rendrait indéfiniment le même jeton périmé."""
        ancien = Token.objects.create(user=self.rep_togo).key
        self._vieillir(self.rep_togo, 31)

        response = self.client.post(
            "/api/token-auth/",
            {
                "username": "togo.innov", "password": MOT_DE_PASSE,
                "code": pyotp.TOTP(self.rep_togo.profile.totp_secret).now(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data["token"], ancien)

    def test_le_jeton_n_est_verifie_qu_une_fois_par_requete(self):
        """Le middleware authentifie pour le verrou du mot de passe ; DRF
        reprend son résultat au lieu de refaire les requêtes."""
        self.login(self.rep_togo)
        original = JetonAuthentication.authenticate_credentials

        with patch.object(
            JetonAuthentication, "authenticate_credentials", autospec=True,
            side_effect=original,
        ) as verification:
            response = self.client.get("/api/countries/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(verification.call_count, 1)


class PerimetreEnMemoireTests(ScopingTestCase):
    def test_get_access_ne_requete_qu_une_fois(self):
        user = User.objects.get(pk=self.rep_togo.pk)

        access = get_access(user)
        with self.assertNumQueries(0):
            self.assertIs(get_access(user), access)

        self.assertEqual(access.country_ids, [self.togo.pk])

    def test_un_compte_sans_profil_n_a_aucun_acces(self):
        """Le superutilisateur d'amorçage n'est pas un acteur du cahier des
        charges : ses drapeaux Django ne donnent aucun droit sur l'API."""
        technique = User.objects.create_superuser("root", password=MOT_DE_PASSE)

        self.assertIsNone(get_access(technique))


class CompteSansProfilTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.technique = User.objects.create_superuser("root", password=MOT_DE_PASSE)
        self.login(self.technique)

    def test_l_api_est_fermee(self):
        for url in ("/api/countries/", "/api/me/", "/api/users/"):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertTrue(response.json()["no_profile"])

    def test_la_deconnexion_et_la_sante_restent_ouvertes(self):
        self.assertEqual(self.client.get("/api/health/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post("/api/logout/").status_code, status.HTTP_204_NO_CONTENT)

    def test_le_profil_reprend_ses_droits(self):
        UserProfile.objects.create(
            user=self.technique, role=Role.SUPER_ADMIN, must_change_password=False,
            totp_secret=pyotp.random_base32(), totp_confirmed_at=timezone.now(),
        )

        self.assertEqual(self.client.get("/api/countries/").status_code, status.HTTP_200_OK)
