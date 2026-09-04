"""Un manager rattaché à des équipes ne voit et n'écrit que pour elles."""

from types import SimpleNamespace

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import GenericViewSet

from accounts.models import Role
from accounts.scoping import CountryScopedMixin
from core.models import Team

from .test_scoping import ScopingTestCase, make_user


class VueParEquipe(CountryScopedMixin, GenericViewSet):
    """Vue de test cloisonnée par équipe, à l'image des vues des dépenses."""

    queryset = Team.objects.all()
    team_lookup = "pk"


class VueSansEquipe(CountryScopedMixin, GenericViewSet):
    queryset = Team.objects.all()


def vue(classe, user):
    instance = classe()
    instance.request = SimpleNamespace(user=user)
    return instance


class CloisonnementParEquipeTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.team_kara = Team.objects.create(country=self.togo, name="Équipe Kara")
        self.manager = make_user(
            "kofi.innov", Role.MANAGER, [self.togo], teams=[self.team_togo]
        )

    def test_un_manager_ne_voit_que_ses_equipes(self):
        self.login(self.manager)

        liste = self.client.get("/api/teams/")
        autre = self.client.get(f"/api/teams/{self.team_kara.pk}/")

        self.assertEqual([t["name"] for t in liste.data["results"]], ["Équipe Lomé"])
        # Hors périmètre : introuvable, sans révéler son existence.
        self.assertEqual(autre.status_code, status.HTTP_404_NOT_FOUND)

    def test_un_manager_sans_equipe_voit_tout_son_pays(self):
        """Choix documenté : l'équipe est une subdivision facultative ; un
        pays qui n'en a pas déclaré n'a pas à en inventer une."""
        libre = make_user("ama.innov", Role.MANAGER, [self.togo])
        self.login(libre)

        response = self.client.get("/api/teams/")

        self.assertEqual(
            sorted(t["name"] for t in response.data["results"]),
            ["Équipe Kara", "Équipe Lomé"],
        )

    def test_le_dm_n_est_pas_cloisonne_par_equipe(self):
        """Seul le manager l'est : le siège couvre le pays entier, même si
        une équipe lui est rattachée."""
        dm = make_user("dm.togo", Role.DM, [self.togo], teams=[self.team_togo])
        self.login(dm)

        response = self.client.get("/api/teams/")

        self.assertEqual(response.data["count"], 2)

    def test_le_profil_expose_les_equipes(self):
        self.login(self.manager)

        response = self.client.get("/api/me/")

        self.assertEqual(
            response.data["teams"],
            [{"id": self.team_togo.pk, "name": "Équipe Lomé", "country": self.togo.pk}],
        )

    def test_une_ecriture_vers_une_autre_equipe_est_refusee(self):
        """La charge utile n'est pas limitée au périmètre : elle est revalidée."""
        v = vue(VueParEquipe, self.manager)

        with self.assertRaises(PermissionDenied):
            v._check_country_scope(
                SimpleNamespace(validated_data={"country": self.togo, "team": self.team_kara})
            )
        # Son équipe, ou pas d'équipe dans la charge utile : rien à redire.
        v._check_country_scope(
            SimpleNamespace(validated_data={"country": self.togo, "team": self.team_togo})
        )
        v._check_country_scope(SimpleNamespace(validated_data={"country": self.togo}))

    def test_une_vue_sans_team_lookup_n_est_pas_filtree(self):
        """Le cloisonnement par équipe est un choix de chaque ressource."""
        sans = vue(VueSansEquipe, self.manager)
        avec = vue(VueParEquipe, self.manager)

        self.assertEqual(sans.get_queryset().count(), 2)
        self.assertEqual(list(avec.get_queryset()), [self.team_togo])
        sans._check_country_scope(
            SimpleNamespace(validated_data={"country": self.togo, "team": self.team_kara})
        )
