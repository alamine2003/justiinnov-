"""Cloisonnement par pays : un pays ne doit jamais voir les données d'un autre."""

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserProfile
from core.models import ChangeLog, Country, Team


def make_user(username, role, countries=(), must_change_password=False):
    """Compte de test, mot de passe déjà personnalisé par défaut.

    Le modèle exige un changement à la première connexion, et la plateforme
    est fermée tant qu'il n'a pas eu lieu. Les tests portent sur l'usage
    courant : leurs comptes sont donc des comptes en service, pas des comptes
    fraîchement créés.
    """
    user = User.objects.create_user(username=username, password="Motdepasse-2026-test")
    profile = UserProfile.objects.create(
        user=user, role=role, must_change_password=must_change_password
    )
    profile.countries.set(countries)
    return user


class ScopingTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", country_ref="CT-01",
            currency="XOF", timezone="Africa/Abidjan",
        )
        self.togo = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-02",
            currency="XOF", timezone="Africa/Lome",
        )
        self.team_ivoire = Team.objects.create(country=self.ivoire, name="Équipe Abidjan")
        self.team_togo = Team.objects.create(country=self.togo, name="Équipe Lomé")

        self.rep_togo = make_user("togo.innov", Role.COUNTRY_MANAGER, [self.togo])
        self.siege = make_user("ceo.innov", Role.SUPER_ADMIN)
        self.controleur = make_user("rh.innov", Role.CONTROLLER)

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


class SubEntityScopeTests(ScopingTestCase):
    def test_les_equipes_sont_filtrees(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/teams/")

        noms = [t["name"] for t in response.data["results"]]
        self.assertEqual(noms, ["Équipe Lomé"])

    def test_creation_dans_son_pays_autorisee(self):
        self.login(self.rep_togo)

        response = self.client.post(
            "/api/teams/", {"country": self.togo.pk, "name": "Équipe Kara"}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_creation_dans_un_autre_pays_refusee(self):
        """Sans cette validation, la charge utile permettrait de créer une
        entité chez le voisin."""
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

    def test_auditeur_est_en_lecture_seule(self):
        auditeur = make_user("audit.innov", Role.AUDITOR)
        self.login(auditeur)

        lecture = self.client.get("/api/teams/")
        ecriture = self.client.post(
            "/api/teams/", {"country": self.togo.pk, "name": "Équipe X"}
        )

        self.assertEqual(lecture.status_code, status.HTTP_200_OK)
        self.assertEqual(ecriture.status_code, status.HTTP_403_FORBIDDEN)

    def test_role_pays_sans_perimetre_ne_voit_rien(self):
        """L'absence de périmètre ne doit jamais valoir autorisation générale."""
        orphelin = make_user("sans-pays.innov", Role.COUNTRY_MANAGER)
        self.login(orphelin)

        response = self.client.get("/api/countries/")

        self.assertEqual(response.data["count"], 0)

    def test_gestion_des_comptes_reservee_au_siege(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class HistoryScopeTests(ScopingTestCase):
    def test_historique_filtre_par_perimetre(self):
        ChangeLog.objects.all().delete()
        self.ivoire.timezone = "Africa/Bouake"
        self.ivoire.save()
        self.togo.timezone = "Africa/Kara"
        self.togo.save()

        self.login(self.rep_togo)
        response = self.client.get("/api/history/")

        pays = {e["country_name"] for e in response.data["results"]}
        self.assertEqual(pays, {"Togo"})


class MeTests(ScopingTestCase):
    def test_profil_courant(self):
        self.login(self.rep_togo)

        response = self.client.get("/api/me/")

        self.assertEqual(response.data["role"], Role.COUNTRY_MANAGER)
        self.assertFalse(response.data["has_global_scope"])
        self.assertEqual(
            [c["country_ref"] for c in response.data["countries"]], ["TG-02"]
        )
        self.assertFalse(response.data["permissions"]["manage_countries"])
        self.assertTrue(response.data["permissions"]["manage_subentities"])

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
        self.assertTrue(response.data["permissions"]["manage_users"])

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

    def test_le_controle_n_accede_pas_au_back_office(self):
        """Dina contrôle les justificatifs, elle n'administre pas la plateforme."""
        self.login(self.controleur)

        response = self.client.get("/api/permissions/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_la_matrice_reflete_les_droits_appliques(self):
        """Régression : la matrice affichée doit être celle qui est appliquée,
        sinon le back-office documenterait une fiction."""
        self.login(self.siege)
        matrice = self.client.get("/api/permissions/").data

        justification = next(
            c for c in matrice["capabilities"] if c["key"] == "validate_expenses"
        )
        # Le pays est exclu de la justification, la matrice doit le dire.
        self.assertNotIn(Role.COUNTRY_MANAGER, justification["roles"])
        self.assertIn(Role.CONTROLLER, justification["roles"])

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

    def test_la_matrice_n_est_pas_modifiable(self):
        self.login(self.siege)

        lecture = self.client.get("/api/permissions/")
        ecriture = self.client.post("/api/permissions/", {})

        self.assertFalse(lecture.data["editable"])
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
            f"/api/users/{self.siege.pk}/", {"role": Role.AUDITOR}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
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
