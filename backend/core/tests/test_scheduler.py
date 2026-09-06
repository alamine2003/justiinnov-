"""Ordonnanceur des tâches périodiques.

Les tâches étaient documentées comme des lignes de crontab à poser sur
l'hôte : documentées, donc jamais posées.
"""

import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from apscheduler.triggers.cron import CronTrigger
from django.core.management import call_command
from django.test import TestCase

from core.management.commands.run_scheduler import JOBS, battre, run_job


class SchedulerTests(TestCase):
    def test_chaque_cadence_est_une_expression_cron_valide(self):
        """Une expression fautive ne se verrait qu'au démarrage du conteneur,
        et l'ordonnanceur refuserait de démarrer sans que personne ne
        s'en aperçoive avant l'alerte manquée."""
        for job in JOBS:
            with self.subTest(job=job["id"]):
                CronTrigger.from_crontab(job["default"])

    def test_les_identifiants_sont_uniques(self):
        """Deux tâches de même identifiant s'écrasent : la seconde ne
        tournerait jamais."""
        identifiants = [job["id"] for job in JOBS]
        self.assertEqual(len(identifiants), len(set(identifiants)))

    def test_le_calendrier_s_affiche_sans_rien_executer(self):
        sortie = StringIO()

        with mock.patch(
            "core.management.commands.run_scheduler.call_command"
        ) as appel:
            call_command("run_scheduler", "--list", stdout=sortie)

        appel.assert_not_called()
        self.assertIn("Notification des alertes", sortie.getvalue())

    def test_une_execution_immediate_lance_chaque_tache(self):
        with mock.patch(
            "core.management.commands.run_scheduler.call_command"
        ) as appel:
            call_command("run_scheduler", "--once", stdout=StringIO())

        lancees = [c.args[0] for c in appel.call_args_list]
        self.assertEqual(lancees, [job["command"][0] for job in JOBS])

    def test_une_tache_qui_echoue_n_emporte_pas_les_suivantes(self):
        """Un serveur SMTP injoignable ne doit pas arrêter l'ordonnanceur :
        les alertes suivantes doivent continuer de partir."""
        with mock.patch(
            "core.management.commands.run_scheduler.call_command",
            side_effect=OSError("SMTP injoignable"),
        ):
            with self.assertLogs("scheduler", level="ERROR"):
                run_job(JOBS[0])  # ne lève pas


class BattementTests(TestCase):
    """Le contrôle de santé du conteneur lit un fichier que l'ordonnanceur
    touche lui-même : sans lui, `docker compose up --wait` refusait le
    service et la livraison s'arrêtait avant les captures."""

    def setUp(self):
        self.dossier = TemporaryDirectory()
        self.fichier = Path(self.dossier.name) / "battement"
        patch = mock.patch(
            "core.management.commands.run_scheduler.BATTEMENT", self.fichier
        )
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.dossier.cleanup)

    def test_battre_cree_puis_rafraichit_le_fichier(self):
        self.assertFalse(self.fichier.exists())

        battre()
        self.assertTrue(self.fichier.exists())
        # Un fichier vieilli doit redevenir frais, pas seulement exister.
        dix_minutes = 600 * 10**9
        vieux = self.fichier.stat().st_mtime_ns - dix_minutes
        os.utime(self.fichier, ns=(vieux, vieux))

        battre()

        self.assertGreater(self.fichier.stat().st_mtime_ns, vieux)

    def test_l_ordonnanceur_bat_avant_de_demarrer_et_planifie_le_battement(self):
        """Le conteneur doit être sain dès son démarrage, pas une minute
        plus tard ; et la boucle doit continuer de battre ensuite."""
        with mock.patch(
            "core.management.commands.run_scheduler.BlockingScheduler"
        ) as fabrique:
            ordonnanceur = fabrique.return_value
            call_command("run_scheduler", stdout=StringIO())

        self.assertTrue(self.fichier.exists(), "aucun battement avant start()")
        identifiants = [c.kwargs.get("id") for c in ordonnanceur.add_job.call_args_list]
        self.assertIn("battement", identifiants)
        self.assertEqual(
            set(identifiants) - {"battement"}, {job["id"] for job in JOBS}
        )
        ordonnanceur.start.assert_called_once()
