"""Cloisonnement par pays : un pays ne doit jamais voir les données d'un autre."""

import pyotp
from django.contrib.auth.models import User
from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from core.models import ChangeLog, Country, Team


def make_user(username, role, countries=(), must_change_password=False, *,
              teams=(), totp_confirmed=True, email=None):
    """Compte de test, mot de passe déjà personnalisé et 2FA déjà confirmée.

    Le modèle exige un changement de mot de passe à la première connexion,
    et la plateforme est fermée tant qu'il n'a pas eu lieu — de même pour
    l'enrôlement TOTP quand la politique l'exige (``TOTP_REQUIRED``). Les
    tests portent sur l'usage courant : leurs comptes sont donc des comptes
    en service, pas des comptes fraîchement créés. Les tests du verrou
    lui-même passent ``totp_confirmed=False``.
    """
    user = User.objects.create_user(
        username=username, password="Motdepasse-2026-test",
        email=email if email is not None else f"{username}@innovpharma.net",
    )
    profile = UserProfile.objects.create(
        user=user, role=role, must_change_password=must_change_password,
        totp_secret=pyotp.random_base32() if totp_confirmed else "",
        totp_confirmed_at=timezone.now() if totp_confirmed else None,
    )
    profile.countries.set(countries)
    profile.teams.set(teams)
    return user


class ScopingTestCase(APITestCase):
    """Deux pays, une équipe par pays, un manager du Togo et le siège.

    Planté une fois par classe (``setUpTestData``) : chaque test en reçoit
    une copie et sa transaction est annulée derrière lui.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", country_ref="CT-01",
            currency="XOF", timezone="Africa/Abidjan",
        )
        cls.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        cls.team_ivoire = Team.objects.create(country=cls.ivoire, name="Équipe Abidjan")
        cls.team_togo = Team.objects.create(country=cls.togo, name="Équipe Lomé")

        # Le pays : un manager, seul rôle côté pays. Le siège : la direction,
        # qui supervise, et l'administrateur, qui contrôle (décision 89).
        cls.rep_togo = make_user("togo.innov", Role.MANAGER, [cls.togo])
        cls.siege = make_user("ceo.innov", Role.SUPER_ADMIN)
        cls.controleur = make_user("rh.innov", Role.ADMIN)

    def login(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


class CountryScopeTests(ScopingTestCase):
    def test_representant_ne_voit_que_son_pays(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/countries/")

        refs = [c["country_ref"] for c in response.data["results"]]
        self.assertEqual(refs, ["TG-02"])

    def test_acces_direct_a_un_autre_pays_refuse(self):
        """Le filtrage porte sur le queryset : l'objet hors périmètre est
        introuvable, sans révéler son existence."""
        self.login(self.rep_togo)

        response = self.client.get(f"/api/countries/{self.ivoire.pk}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_modification_d_un_autre_pays_refusee(self):
        """Doublement bloqué : le rôle n'autorise pas l'écriture sur un pays
        (403), et le pays serait de toute façon hors périmètre."""
        self.login(self.rep_togo)

        response = self.client.patch(
            f"/api/countries/{self.ivoire.pk}/", {"is_active": False}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.ivoire.refresh_from_db()
        self.assertTrue(self.ivoire.is_active)

    def test_le_siege_voit_tous_les_pays(self):
        self.login(self.siege)

        response = self.client.get("/api/countries/")

        self.assertEqual(response.data["count"], 2)

    def test_controleur_voit_tous_les_pays(self):
        """Dina contrôle les justificatifs de l'ensemble des pays."""
        self.login(self.controleur)

        response = self.client.get("/api/countries/")

        self.assertEqual(response.data["count"], 2)

    def test_le_siege_ne_se_restreint_pas(self):
        """Un pays rattaché en base à un compte du siège ne le restreint
        pas : le siège contrôle et supervise tous les pays (décision 89)."""
        for role in (Role.ADMIN, Role.SUPER_ADMIN):
            with self.subTest(role=role):
                self.login(make_user(f"{role}.togo", role, [self.togo]))

                liste = self.client.get("/api/countries/")
                profil = self.client.get("/api/me/")

                self.assertEqual(liste.data["count"], 2)
                self.assertTrue(profil.data["has_global_scope"])

    def test_les_administrateurs_ne_se_restreignent_pas(self):
        """Des pays rattachés par erreur à un administrateur ne lui ferment
        rien : le siège administre l'ensemble."""
        for role in (Role.SUPER_ADMIN, Role.ADMIN):
            with self.subTest(role=role):
                self.login(make_user(f"{role}.restreint", role, [self.togo]))

                self.assertEqual(self.client.get("/api/countries/").data["count"], 2)


class SubEntityScopeTests(ScopingTestCase):
    def test_les_equipes_sont_filtrees(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/teams/")

        noms = [t["name"] for t in response.data["results"]]
        self.assertEqual(noms, ["Équipe Lomé"])

    def test_la_rh_gere_le_referentiel_de_tous_les_pays(self):
        rh = make_user("rh.admin", Role.ADMIN)
        self.login(rh)

        togo = self.client.post(
            "/api/teams/", {"country": self.togo.pk, "name": "Équipe Kara"}
        )
        ivoire = self.client.post(
            "/api/teams/", {"country": self.ivoire.pk, "name": "Équipe Bouaké"}
        )

        self.assertEqual(togo.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ivoire.status_code, status.HTTP_201_CREATED)

    def test_le_manager_ne_modifie_pas_le_referentiel(self):
        """Le manager déclare dans un cadre que le siège a posé ; il ne le
        redessine pas, même pour son propre pays."""
        self.login(self.rep_togo)

        creation = self.client.post(
            "/api/teams/", {"country": self.togo.pk, "name": "Équipe Kara"}
        )
        modification = self.client.patch(
            f"/api/teams/{self.team_togo.pk}/", {"name": "Équipe renommée"}
        )

        self.assertEqual(creation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(modification.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Team.objects.filter(name="Équipe Kara").exists())

    def test_creation_dans_un_autre_pays_refusee(self):
        """Doublement bloqué : le rôle n'écrit pas le référentiel, et le pays
        serait de toute façon hors périmètre. Sans la revalidation de la
        charge utile, un rôle qui écrit chez lui pourrait créer une entité
        chez le voisin."""
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/teams/", {"country": self.ivoire.pk, "name": "Équipe pirate"}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Team.objects.filter(name="Équipe pirate").exists())

    def test_transfert_vers_un_autre_pays_refuse(self):
        self.login(self.rep_togo)

        response = self.client.patch(
            f"/api/teams/{self.team_togo.pk}/", {"country": self.ivoire.pk}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.team_togo.refresh_from_db()
        self.assertEqual(self.team_togo.country, self.togo)


class RolePermissionTests(ScopingTestCase):
    def test_representant_ne_cree_pas_de_pays(self):
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/countries/",
            {"name": "Bénin", "code": "BJ", "currency": "XOF", "timezone": "Africa/Porto-Novo"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_pays_ne_modifie_pas_le_referentiel(self):
        """Le manager déclare : il ne redessine pas l'organisation de son
        pays, qui revient à la RH."""
        self.login(self.rep_togo)

        lecture = self.client.get("/api/teams/")
        ecriture = self.client.post(
            "/api/teams/", {"country": self.togo.pk, "name": "Équipe X"}
        )

        self.assertEqual(lecture.status_code, status.HTTP_200_OK)
        self.assertEqual(ecriture.status_code, status.HTTP_403_FORBIDDEN)

    def test_le_pays_ne_gere_ni_comptes_ni_referentiel(self):
        """Comptes, pays, managers, référentiel : la RH et la direction. Le
        refus vient du rôle (403), pas du périmètre."""
        ecritures = (
            ("/api/users/", {
                "username": "x.innov", "email": "x@innovpharma.net",
                "password": "Provisoire-2026-X", "role": Role.MANAGER,
                "countries": [self.togo.pk],
            }),
            ("/api/countries/", {
                "name": "Bénin", "code": "BJ", "currency": "XOF",
                "timezone": "Africa/Porto-Novo",
            }),
            ("/api/managers/", {"name": "Awa Diop"}),
            ("/api/projects/", {"country": self.togo.pk, "name": "Projet X"}),
            ("/api/beneficiaries/", {
                "country": self.togo.pk, "name": "Pharmacie X", "kind": "supplier",
            }),
        )
        for compte in (self.rep_togo,):
            self.login(compte)
            for route, charge in ecritures:
                with self.subTest(role=compte.profile.role, route=route):
                    response = self.client.post(route, charge, format="json")

                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            with self.subTest(role=compte.profile.role, route="/api/users/ (lecture)"):
                # La liste des comptes est elle-même un écran d'administration.
                self.assertEqual(
                    self.client.get("/api/users/").status_code, status.HTTP_403_FORBIDDEN
                )
        self.assertFalse(User.objects.filter(username="x.innov").exists())
        self.assertFalse(Country.objects.filter(code="BJ").exists())

    def test_role_pays_sans_perimetre_ne_voit_rien(self):
        """L'absence de périmètre ne doit jamais valoir autorisation générale."""
        orphelin = make_user("sans-pays.innov", Role.MANAGER)
        self.login(orphelin)

        response = self.client.get("/api/countries/")

        self.assertEqual(response.data["count"], 0)

    def test_gestion_des_comptes_reservee_au_siege(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class HistoryScopeTests(ScopingTestCase):
    def test_le_siege_lit_l_historique_de_tous_les_pays(self):
        """Le siège n'est jamais restreint : l'historique de chaque pays lui
        est ouvert."""
        # Le journal ne s'efface pas : on ne regarde que ce que le test écrit.
        repere = ChangeLog.objects.aggregate(Max("pk"))["pk__max"] or 0
        self.ivoire.timezone = "Africa/Bouake"
        self.ivoire.save()
        self.togo.timezone = "Africa/Kara"
        self.togo.save()

        self.login(self.controleur)
        response = self.client.get("/api/history/")

        recentes = [
            e for e in response.data["results"]
            if e["id"] > repere and e["country"] is not None
        ]
        self.assertEqual({e["country_name"] for e in recentes}, {"Togo", "Côte d'Ivoire"})

    def test_le_manager_ne_lit_pas_l_historique(self):
        """Le manager saisit des dépenses ; l'organisation du pays ne le
        regarde pas."""
        self.login(self.rep_togo)

        response = self.client.get("/api/history/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MeTests(ScopingTestCase):
    def test_profil_courant(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/me/")

        self.assertEqual(response.data["role"], Role.MANAGER)
        self.assertEqual(response.data["role_display"], "Manager (pays)")
        self.assertFalse(response.data["has_global_scope"])
        self.assertEqual(
            [c["country_ref"] for c in response.data["countries"]], ["TG-02"]
        )
        self.assertFalse(response.data["permissions"]["countries.create"])
        self.assertFalse(response.data["permissions"]["referentiel.update"])
        self.assertTrue(response.data["permissions"]["expenses.create"])
        self.assertFalse(response.data["permissions"]["expenses.review"])
        self.assertFalse(response.data["permissions"]["expenses.validate"])

    def test_profil_de_l_administrateur(self):
        """L'administrateur contrôle de bout en bout sans déclarer."""
        self.login(self.controleur)

        permissions = self.client.get("/api/me/").data["permissions"]

        for cle in ("expenses.review", "expenses.validate", "expenses.close",
                    "proofs.review", "dossiers.reopen", "audit.read"):
            self.assertTrue(permissions[cle], cle)
        for cle in ("expenses.create", "proofs.upload", "dossiers.submit", "data.import"):
            self.assertFalse(permissions[cle], cle)

    def test_profil_du_super_administrateur(self):
        """Le super administrateur supervise : il lit tout, relit l'audit,
        administre, mais ne déclare ni ne contrôle (décision 89)."""
        self.login(self.siege)

        permissions = self.client.get("/api/me/").data["permissions"]

        for cle in ("audit.read", "users.update", "configuration.manage", "data.export"):
            self.assertTrue(permissions[cle], cle)
        for cle in ("expenses.create", "proofs.upload", "expenses.review",
                    "expenses.validate", "expenses.close", "dossiers.reopen"):
            self.assertFalse(permissions[cle], cle)

    def test_compte_sans_profil_garde_une_reponse_complete(self):
        """Un compte technique hérité n'a pas de profil : la liste des comptes
        doit rester exploitable plutôt que d'omettre les clés attendues."""
        User.objects.create_user(username="legacy", password="Motdepasse-2026-test")
        self.login(self.siege)

        response = self.client.get("/api/users/")

        legacy = next(u for u in response.data["results"] if u["username"] == "legacy")
        self.assertIsNone(legacy["role"])
        self.assertEqual(legacy["countries_detail"], [])
        self.assertFalse(legacy["must_change_password"])

    def test_profil_du_siege(self):
        self.login(self.siege)

        response = self.client.get("/api/me/")

        self.assertTrue(response.data["has_global_scope"])
        self.assertTrue(response.data["permissions"]["users.update"])

    def test_changement_de_mot_de_passe(self):
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/me/password/",
            {
                "current_password": "Motdepasse-2026-test",
                "new_password": "Nouveau-Motdepasse-2026",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rep_togo.refresh_from_db()
        self.assertTrue(self.rep_togo.check_password("Nouveau-Motdepasse-2026"))
        self.assertFalse(self.rep_togo.profile.must_change_password)
        # Le client repart avec un jeton neuf.
        self.assertEqual(response.data["token"], Token.objects.get(user=self.rep_togo).key)


class BackOfficeTests(ScopingTestCase):
    """Le back-office est réservé au siège."""

    def test_la_configuration_est_lisible_par_le_siege(self):
        self.login(self.siege)

        response = self.client.get("/api/configuration/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("seuils", response.data["alertes"])
        self.assertIn(".pdf", response.data["justificatifs"]["formats_acceptes"])

    def test_un_pays_n_accede_pas_a_la_configuration(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/configuration/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_l_administrateur_accede_au_back_office(self):
        """L'administrateur contrôle et administre : la matrice lui est ouverte."""
        self.login(self.controleur)

        response = self.client.get("/api/permissions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_la_matrice_reflete_les_droits_appliques(self):
        """Régression : la matrice affichée doit être celle qui est appliquée,
        sinon le back-office documenterait une fiction."""
        self.login(self.siege)
        matrice = self.client.get("/api/permissions/").data

        capacites = {c["key"]: c["roles"] for c in matrice["capabilities"]}
        # Le contrôle est à l'administrateur seul, la matrice doit le dire.
        self.assertEqual(capacites["expenses.validate"], [Role.ADMIN])
        self.assertEqual(capacites["expenses.review"], [Role.ADMIN])
        # La déclaration est au pays seul.
        self.assertEqual(capacites["expenses.create"], [Role.MANAGER])
        # La RH tient le référentiel de tous les pays, pas le manager.
        self.assertIn(Role.ADMIN, capacites["referentiel.update"])
        self.assertNotIn(Role.MANAGER, capacites["referentiel.update"])
        # Les enveloppes comme le journal d'audit sont aux administrateurs,
        # RH et direction.
        self.assertEqual(sorted(capacites["budgets.update"]), [Role.ADMIN, Role.SUPER_ADMIN])
        self.assertEqual(sorted(capacites["audit.read"]), [Role.ADMIN, Role.SUPER_ADMIN])

        # Et elle doit concorder avec les droits annoncés à chaque titulaire —
        # pas seulement au super administrateur, qui a tout et ne prouve rien.
        for role in Role:
            with self.subTest(role=role):
                self.login(make_user(f"{role}.matrice", role, [self.togo]))
                profil = self.client.get("/api/me/").data

                self.assertEqual(profil["role"], role)
                for capability in matrice["capabilities"]:
                    self.assertEqual(
                        profil["permissions"][capability["key"]],
                        role in capability["roles"],
                        f"désaccord sur {capability['key']} pour {role}",
                    )

    def test_la_matrice_dit_qui_est_au_siege_et_qui_ne_se_restreint_pas(self):
        """Le siège est global : des pays rattachés ne le restreignent pas,
        et le back-office doit pouvoir le dire avant qu'on ne l'essaie."""
        self.login(self.siege)

        roles = {r["value"]: r for r in self.client.get("/api/permissions/").data["roles"]}

        self.assertEqual(set(roles), {Role.SUPER_ADMIN, Role.ADMIN, Role.MANAGER})
        for role in (Role.ADMIN, Role.SUPER_ADMIN):
            self.assertTrue(roles[role]["siege"], role)
            self.assertTrue(roles[role]["always_global"], role)
        self.assertFalse(roles[Role.MANAGER]["siege"])
        self.assertFalse(roles[Role.MANAGER]["always_global"])

    def test_la_matrice_se_modifie_par_patch_seulement(self):
        """Elle est modifiable (décision 43), mais par ``PATCH`` : un ``POST``
        ne remplace pas la matrice entière."""
        self.login(self.siege)

        lecture = self.client.get("/api/permissions/")
        ecriture = self.client.post("/api/permissions/", {})

        self.assertEqual(lecture.status_code, status.HTTP_200_OK)
        self.assertEqual(ecriture.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class SelfLockoutTests(ScopingTestCase):
    """On ne se retire pas ses propres droits : personne ne pourrait les rendre."""

    def test_desactivation_de_son_propre_compte_refusee(self):
        self.login(self.siege)

        response = self.client.patch(
            f"/api/users/{self.siege.pk}/", {"is_active": False}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.siege.refresh_from_db()
        self.assertTrue(self.siege.is_active)

    def test_declassement_de_son_propre_role_refuse(self):
        self.login(self.siege)

        response = self.client.patch(
            f"/api/users/{self.siege.pk}/",
            {"role": Role.MANAGER, "countries": [self.togo.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)
        self.siege.profile.refresh_from_db()
        self.assertEqual(self.siege.profile.role, Role.SUPER_ADMIN)

    def test_desactivation_d_un_autre_compte_autorisee(self):
        self.login(self.siege)

        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/", {"is_active": False}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rep_togo.refresh_from_db()
        self.assertFalse(self.rep_togo.is_active)
