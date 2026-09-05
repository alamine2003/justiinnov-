"""``seed_users`` : équipes, manager et langue du profil."""

import io
import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Manager, Team

from .test_scoping import ScopingTestCase


class SeedUsersProfilTests(ScopingTestCase):
    def setUp(self):
        super().setUp()
        self.team_kara = Team.objects.create(country=self.togo, name="Équipe Kara")
        # Le même nom d'équipe existe en Côte d'Ivoire : il ne doit pas
        # être pris pour celui du Togo.
        Team.objects.create(country=self.ivoire, name="Équipe Kara")
        self.manager = Manager.objects.create(name="Kossi Mensah")
        self.manager.countries.set([self.togo])

    def seed(self, **compte):
        payload = {
            "username": "kofi.innov", "password": "Provisoire-2026-Ghana",
            "email": "kofi@innovpharma.net", "role": "manager",
            "countries": ["TG-02"], **compte,
        }
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "seed.json"
            fichier.write_text(json.dumps({"users": [payload]}), encoding="utf-8")
            call_command("seed_users", file=str(fichier), stdout=io.StringIO())
        return User.objects.get(username="kofi.innov").profile

    def test_les_equipes_sont_cherchees_dans_les_pays_du_compte(self):
        profil = self.seed(teams=["Équipe Kara", "Équipe Lomé"])

        self.assertEqual(
            sorted(profil.teams.values_list("pk", flat=True)),
            sorted([self.team_kara.pk, self.team_togo.pk]),
        )

    def test_une_equipe_inconnue_est_refusee(self):
        with self.assertRaisesMessage(CommandError, "Équipe Abidjan"):
            self.seed(teams=["Équipe Abidjan"])

    def test_sans_la_cle_les_equipes_restent(self):
        """Relancer le fichier ne doit pas défaire ce que le siège a réglé
        depuis l'application."""
        self.seed(teams=["Équipe Lomé"])

        profil = self.seed()

        self.assertEqual(list(profil.teams.all()), [self.team_togo])

    def test_le_manager_et_la_langue(self):
        profil = self.seed(manager="Kossi Mensah", language="en")

        self.assertEqual(profil.manager, self.manager)
        self.assertEqual(profil.language, "en")

        profil = self.seed(manager=None)
        self.assertIsNone(profil.manager)

    def test_un_manager_inconnu_ou_ambigu_est_refuse(self):
        with self.assertRaisesMessage(CommandError, "Manager inconnu"):
            self.seed(manager="Personne")

        Manager.objects.create(name="Kossi Mensah").countries.set([self.togo])
        with self.assertRaisesMessage(CommandError, "Plusieurs managers"):
            self.seed(manager="Kossi Mensah")

    def test_une_langue_inconnue_est_refusee(self):
        with self.assertRaisesMessage(CommandError, "langue inconnue"):
            self.seed(language="de")
