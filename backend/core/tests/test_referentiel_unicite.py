"""Nom d'équipe et nom de projet uniques par pays.

Deux « Équipe Lomé » au Togo ne se distinguent ni à l'écran ni dans un
classeur importé. Le même nom reste possible dans deux pays : le référentiel
est cloisonné, et « Équipe commerciale » existe partout.
"""

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework import status

from core.models import Country, Project, Team

from .test_api import ApiTestCase


class UniciteParPaysTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()
        self.ivoire = Country.objects.create(
            name="Côte d'Ivoire", code="CI", currency="XOF", timezone="Africa/Abidjan"
        )
        self.equipe = Team.objects.create(country=self.country, name="Équipe Lomé")
        self.projet = Project.objects.create(country=self.country, name="Campagne T1")

    # -- Base -----------------------------------------------------------------

    def test_la_base_refuse_deux_equipes_homonymes_dans_un_pays(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Team.objects.create(country=self.country, name="Équipe Lomé")

    def test_la_base_refuse_deux_projets_homonymes_dans_un_pays(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Project.objects.create(country=self.country, name="Campagne T1")

    def test_le_meme_nom_existe_dans_deux_pays(self):
        Team.objects.create(country=self.ivoire, name="Équipe Lomé")
        Project.objects.create(country=self.ivoire, name="Campagne T1")

        self.assertEqual(Team.objects.filter(name="Équipe Lomé").count(), 2)
        self.assertEqual(Project.objects.filter(name="Campagne T1").count(), 2)

    # -- API ------------------------------------------------------------------

    def test_l_api_refuse_une_equipe_homonyme_avec_un_message_clair(self):
        response = self.client.post(
            "/api/teams/", {"country": self.country.pk, "name": "Équipe Lomé"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("existe déjà pour ce pays", str(response.data))

    def test_l_api_refuse_un_projet_homonyme_avec_un_message_clair(self):
        response = self.client.post(
            "/api/projects/", {"country": self.country.pk, "name": "Campagne T1"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("existe déjà pour ce pays", str(response.data))

    def test_l_api_accepte_le_nom_dans_un_autre_pays(self):
        response = self.client.post(
            "/api/teams/", {"country": self.ivoire.pk, "name": "Équipe Lomé"}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_renommer_vers_un_nom_pris_est_refuse(self):
        autre = Team.objects.create(country=self.country, name="Équipe Kara")

        response = self.client.patch(f"/api/teams/{autre.pk}/", {"name": "Équipe Lomé"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        autre.refresh_from_db()
        self.assertEqual(autre.name, "Équipe Kara")

    def test_modifier_une_equipe_sans_la_renommer_passe(self):
        """La validation ne doit pas compter l'équipe modifiée elle-même."""
        response = self.client.patch(
            f"/api/teams/{self.equipe.pk}/", {"description": "Lomé et sa banlieue"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


AVANT = [("core", "0009_historique_immuable")]
APRES = [("core", "0010_equipe_et_projet_uniques_par_pays")]


class RenommageDesDoublonsTests(TransactionTestCase):
    """La migration renomme les doublons existants avant de contraindre.

    Une base en service peut porter deux « Équipe Lomé » au Togo : sans
    reprise, la contrainte échouerait et bloquerait tout déploiement. Rien
    n'est supprimé ni fusionné — des dépenses y sont peut-être rattachées.
    """

    def _migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.migrate(cible)
        executor.loader.build_graph()
        return executor.loader.project_state(cible).apps

    def test_les_homonymes_recoivent_un_suffixe_et_le_plus_ancien_garde_son_nom(self):
        apps = self._migrer(AVANT)
        try:
            Country = apps.get_model("core", "Country")
            Team = apps.get_model("core", "Team")
            Project = apps.get_model("core", "Project")
            togo = Country.objects.create(
                name="Togo", code="TG", currency="XOF", timezone="Africa/Lome"
            )
            ivoire = Country.objects.create(
                name="Côte d'Ivoire", code="CI", currency="XOF", timezone="Africa/Abidjan"
            )
            premiere = Team.objects.create(country=togo, name="Équipe Lomé")
            seconde = Team.objects.create(country=togo, name="Équipe Lomé")
            troisieme = Team.objects.create(country=togo, name="Équipe Lomé")
            voisine = Team.objects.create(country=ivoire, name="Équipe Lomé")
            # Un nom qui occupe déjà le suffixe : la migration doit sauter
            # par-dessus, sans créer un nouveau doublon.
            Project.objects.create(country=togo, name="Campagne (2)")
            campagne_a = Project.objects.create(country=togo, name="Campagne")
            campagne_b = Project.objects.create(country=togo, name="Campagne")

            apps = self._migrer(APRES)
            Team = apps.get_model("core", "Team")
            Project = apps.get_model("core", "Project")

            self.assertEqual(Team.objects.get(pk=premiere.pk).name, "Équipe Lomé")
            self.assertEqual(Team.objects.get(pk=seconde.pk).name, "Équipe Lomé (2)")
            self.assertEqual(Team.objects.get(pk=troisieme.pk).name, "Équipe Lomé (3)")
            self.assertEqual(Team.objects.get(pk=voisine.pk).name, "Équipe Lomé")
            self.assertEqual(Project.objects.get(pk=campagne_a.pk).name, "Campagne")
            self.assertEqual(Project.objects.get(pk=campagne_b.pk).name, "Campagne (3)")
            self.assertEqual(Team.objects.count(), 4)
            self.assertEqual(Project.objects.count(), 3)
        finally:
            # Les autres tests attendent la base au dernier état.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
