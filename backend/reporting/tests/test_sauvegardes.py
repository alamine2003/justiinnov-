"""Contrôle de fraîcheur des sauvegardes et révocation des sessions.

Audit du 8 septembre 2026, §3.2 et §3.3 : une sauvegarde qui manque ne
doit pas se lire seulement dans le journal d'un conteneur ; un jeton lu
dans une sauvegarde doit pouvoir être révoqué, et cela se relit.
"""

from datetime import timedelta
from unittest import mock
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token

from core.management.commands.run_scheduler import JOBS
from core.models import ChangeLog
from expenses.tests.base import ExpenseTestCase
from notifications.models import Notification
from reporting.management.commands.verifier_sauvegardes import (
    anomalies,
    archivage_en_panne,
)


def marquer(dossier, quoi, quand):
    (Path(dossier) / f".derniere-reussite-{quoi}").write_text(
        quand.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="utf-8"
    )


class FraicheurTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dossier_marqueurs = self.temp.name

    def verifier(self, **options):
        sortie = StringIO()
        with override_settings(SAUVEGARDES_MARQUEURS=self.dossier_marqueurs), \
                self.captureOnCommitCallbacks(execute=True):
            call_command("verifier_sauvegardes", stdout=sortie, **options)
        return sortie.getvalue()

    def test_des_marqueurs_frais_ne_notifient_personne(self):
        maintenant = timezone.now()
        for quoi in ("base", "pieces", "distant", "base-physique"):
            marquer(self.dossier_marqueurs, quoi, maintenant - timedelta(hours=6))

        sortie = self.verifier()

        self.assertIn("✔ Sauvegardes à jour", sortie)
        self.assertFalse(Notification.objects.exists())

    def test_une_copie_hors_machine_absente_est_notifiee_aux_administrateurs(self):
        maintenant = timezone.now()
        marquer(self.dossier_marqueurs, "base", maintenant - timedelta(hours=6))
        marquer(self.dossier_marqueurs, "pieces", maintenant - timedelta(hours=6))
        marquer(self.dossier_marqueurs, "base-physique", maintenant - timedelta(hours=6))

        sortie = self.verifier()

        self.assertIn("✘ distant", sortie)
        notification = Notification.objects.get(recipient=self.doo)
        self.assertEqual(notification.kind, Notification.Kind.STORAGE_ERROR)
        self.assertEqual(notification.level, Notification.Level.CRITICAL)
        self.assertIn("copie hors machine", notification.title)
        self.assertIn("Aucune réussite enregistrée", notification.body)
        self.assertEqual(len(mail.outbox), 1)
        # Le pays n'est pas prévenu : l'exploitation est l'affaire du siège.
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())

    def test_une_sauvegarde_trop_vieille_est_en_defaut(self):
        maintenant = timezone.now()
        marquer(self.dossier_marqueurs, "base", maintenant - timedelta(hours=40))
        marquer(self.dossier_marqueurs, "pieces", maintenant - timedelta(hours=6))
        marquer(self.dossier_marqueurs, "distant", maintenant - timedelta(hours=6))
        marquer(self.dossier_marqueurs, "base-physique", maintenant - timedelta(hours=6))

        self.verifier()

        notification = Notification.objects.get(recipient=self.doo)
        self.assertIn("sauvegarde de la base", notification.title)
        self.assertIn("plus de 26 h", notification.body)

    def test_un_manque_qui_dure_se_rappelle_une_fois_par_jour(self):
        self.verifier()
        self.verifier()

        self.assertEqual(Notification.objects.filter(recipient=self.doo).count(), 4)

    def test_avant_le_premier_marqueur_le_dump_le_plus_recent_fait_foi(self):
        """Les dumps existaient avant les marqueurs : le matin de la mise à
        jour, un volume avec un dump de la nuit n'est pas en défaut."""
        base = Path(self.dossier_marqueurs) / "base"
        base.mkdir()
        (base / "justi_innov-hier.dump").write_bytes(b"PGDMP")

        trouvees = anomalies(self.dossier_marqueurs, age_max=timedelta(hours=26))

        self.assertEqual(
            [quoi for quoi, _ in trouvees], ["pieces", "distant", "base-physique"]
        )

    def test_la_sauvegarde_physique_a_son_propre_seuil(self):
        """Elle est hebdomadaire : au seuil quotidien, elle serait déclarée
        en retard six jours sur sept, et l'alerte cesserait d'être lue."""
        maintenant = timezone.now()
        for quoi in ("base", "pieces", "distant"):
            marquer(self.dossier_marqueurs, quoi, maintenant - timedelta(hours=6))
        marquer(self.dossier_marqueurs, "base-physique", maintenant - timedelta(days=3))

        trouvees = anomalies(self.dossier_marqueurs, age_max=timedelta(hours=26))

        self.assertEqual(trouvees, [], "trois jours, c'est frais pour une hebdomadaire")

    def test_une_sauvegarde_physique_vieille_de_dix_jours_est_en_defaut(self):
        """Sans elle, les segments archivés ne servent à rien : une reprise
        à un instant donné part d'une sauvegarde physique, jamais d'un dump."""
        maintenant = timezone.now()
        for quoi in ("base", "pieces", "distant"):
            marquer(self.dossier_marqueurs, quoi, maintenant - timedelta(hours=6))
        marquer(self.dossier_marqueurs, "base-physique", maintenant - timedelta(days=10))

        trouvees = anomalies(self.dossier_marqueurs, age_max=timedelta(hours=26))

        self.assertEqual([quoi for quoi, _ in trouvees], ["base-physique"])

    def test_sans_dossier_de_marqueurs_rien_n_est_verifie(self):
        sortie = StringIO()
        with override_settings(SAUVEGARDES_MARQUEURS=""):
            call_command("verifier_sauvegardes", stdout=sortie)

        self.assertIn("aucun contrôle", sortie.getvalue())
        self.assertFalse(Notification.objects.exists())

    def test_la_simulation_ne_notifie_pas(self):
        self.verifier(dry_run=True)

        self.assertFalse(Notification.objects.exists())

    def test_le_controle_est_planifie(self):
        job = next(j for j in JOBS if j["command"][0] == "verifier_sauvegardes")
        self.assertEqual(job["cron"], "SCHEDULE_VERIF_SAUVEGARDES")


class RevocationDesSessionsTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)
        self.login(self.controller)
        self.assertEqual(Token.objects.count(), 2)

    def test_tous_les_jetons_sont_revoques_et_cela_se_relit(self):
        call_command("revoquer_sessions", tous=True, motif="fuite de sauvegarde", verbosity=0)

        self.assertEqual(Token.objects.count(), 0)
        entrees = ChangeLog.objects.filter(action=ChangeLog.Actions.LOGOUT)
        self.assertEqual(
            set(entrees.values_list("label", flat=True)), {"owner.togo", "rh.innov"}
        )
        self.assertEqual(entrees.first().diff["motif"], [None, "fuite de sauvegarde"])

    def test_un_jeton_revoque_ne_passe_plus(self):
        self.login(self.owner)
        self.assertEqual(self.client.get("/api/me/").status_code, status.HTTP_200_OK)

        call_command("revoquer_sessions", compte="owner.togo", motif="poste perdu", verbosity=0)

        self.assertEqual(self.client.get("/api/me/").status_code, status.HTTP_401_UNAUTHORIZED)
        # L'autre compte garde sa session.
        self.assertTrue(Token.objects.filter(user=self.controller).exists())

    def test_un_compte_inconnu_est_refuse(self):
        with self.assertRaises(CommandError):
            call_command("revoquer_sessions", compte="inconnu", motif="essai", verbosity=0)

    def test_la_simulation_ne_revoque_rien(self):
        call_command("revoquer_sessions", tous=True, motif="essai", dry_run=True, verbosity=0)

        self.assertEqual(Token.objects.count(), 2)


class ArchivageDesSegmentsTests(ExpenseTestCase):
    """Un archivage cassé doit se dire — et un archivage au repos, non.

    L'archivage des segments (``deploy/archiver_wal.sh``) est ce qui rend
    possible la reprise à un instant donné. Quand il échoue, deux choses se
    passent : la reprise s'arrête à la dernière réussite, et Postgres
    **conserve** ses segments dans ``pg_wal``, où ils s'accumulent jusqu'à
    remplir le disque de la base.

    Le signal juste n'est pas l'ancienneté du dernier segment archivé : une
    nuit sans écriture n'en produit aucun, et alerter là-dessus crierait au
    loup tous les week-ends. C'est la comparaison des deux horodatages.
    """

    @staticmethod
    def _postgres_repond(mode, dernier_echec, dernier_succes, segment="0000000100000000000000AA"):
        """Fait parler ``pg_stat_archiver`` sans dépendre de l'état réel de
        la base de test, où l'archivage n'est pas activé."""
        curseur = mock.MagicMock()
        curseur.__enter__.return_value = curseur
        reponses = iter([(mode,), (segment, dernier_echec, dernier_succes)])
        curseur.fetchone.side_effect = lambda: next(reponses)
        return mock.patch(
            "reporting.management.commands.verifier_sauvegardes.connection.cursor",
            return_value=curseur,
        )

    def test_un_archivage_desactive_ne_declenche_rien(self):
        """En développement et en intégration continue, l'archivage est
        éteint : ce n'est pas une panne."""
        with self._postgres_repond("off", None, None):
            self.assertIsNone(archivage_en_panne())

    def test_sans_echec_rien_ne_se_dit(self):
        with self._postgres_repond("on", None, timezone.now()):
            self.assertIsNone(archivage_en_panne())

    def test_un_echec_plus_ancien_que_le_dernier_succes_est_oublie(self):
        """L'archivage a trébuché puis s'est repris : le compteur d'échecs
        de Postgres ne redescend jamais, mais il n'y a plus rien à signaler."""
        maintenant = timezone.now()
        with self._postgres_repond("on", maintenant - timedelta(hours=3), maintenant):
            self.assertIsNone(archivage_en_panne())

    def test_un_echec_posterieur_au_dernier_succes_se_dit(self):
        maintenant = timezone.now()
        with self._postgres_repond("on", maintenant, maintenant - timedelta(hours=3)):
            panne = archivage_en_panne()

        self.assertIsNotNone(panne)
        self.assertEqual(panne[0], "0000000100000000000000AA")

    def test_un_archivage_qui_n_a_jamais_abouti_se_dit(self):
        """Le cas de la mise en service : l'archivage est activé, il échoue
        depuis le début, et aucun segment n'est jamais parti."""
        with self._postgres_repond("on", timezone.now(), None):
            self.assertIsNotNone(archivage_en_panne())
