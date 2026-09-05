"""Le siège rattache un compte à des équipes : bornées à ses pays, exposées
avec leur détail."""

from rest_framework import status

from accounts.models import Role
from core.models import Team

from .test_scoping import ScopingTestCase, make_user


class EquipesDuCompteTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.team_kara = Team.objects.create(country=self.togo, name="Équipe Kara")
        self.login(self.siege)

    def test_la_creation_pose_les_equipes(self):
        response = self.client.post(
            "/api/users/",
            {
                "username": "kofi.innov", "email": "kofi@innovpharma.net",
                "password": "Provisoire-2026-Ghana", "role": Role.MANAGER,
                "countries": [self.togo.pk], "teams": [self.team_togo.pk],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["teams"], [self.team_togo.pk])
        self.assertEqual(
            response.data["teams_detail"],
            [{"id": self.team_togo.pk, "name": "Équipe Lomé", "country": self.togo.pk}],
        )

    def test_une_equipe_d_un_autre_pays_est_refusee(self):
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"teams": [self.team_ivoire.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Équipe Abidjan", response.data["teams"][0])
        self.assertFalse(self.rep_togo.profile.teams.exists())

    def test_retirer_un_pays_sans_retirer_ses_equipes_est_refuse(self):
        """Le périmètre résultant est vérifié, pas seulement la charge utile."""
        self.rep_togo.profile.teams.set([self.team_togo])

        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"countries": [self.ivoire.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("teams", response.data)
        # En une seule écriture, pays et équipes cohérents : accepté.
        response = self.client.patch(
            f"/api/users/{self.rep_togo.pk}/",
            {"countries": [self.ivoire.pk], "teams": [self.team_ivoire.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["teams"], [self.team_ivoire.pk])

    def test_les_equipes_se_lisent_dans_la_liste(self):
        make_user("kofi.innov", Role.MANAGER, [self.togo], teams=[self.team_kara])

        response = self.client.get("/api/users/")

        comptes = {u["username"]: u for u in response.data["results"]}
        self.assertEqual(comptes["kofi.innov"]["teams"], [self.team_kara.pk])
        self.assertEqual(comptes["ceo.innov"]["teams"], [])
        self.assertEqual(comptes["ceo.innov"]["teams_detail"], [])

    def test_le_profil_expose_le_fuseau_et_la_devise_de_chaque_pays(self):
        """Un compte pays borne ses périodes dans l'heure de son pays."""
        self.login(self.rep_togo)

        response = self.client.get("/api/me/")

        self.assertEqual(
            response.data["countries"],
            [{
                "id": self.togo.pk, "name": "Togo", "code": "TG", "country_ref": "TG-02",
                "timezone": "Africa/Lome", "currency": "XOF",
            }],
        )
