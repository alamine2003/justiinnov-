"""La pile doit archiver ses journaux de transaction, et pouvoir les rejouer.

Trouvé par l'audit de résilience, section « infrastructure de la base ». La
chaîne de sauvegarde était sérieuse — dump quotidien chiffré, copie mensuelle
gardée sans limite, miroir hors machine vérifié — mais elle avait un trou :
**aucun archivage des journaux de transaction**. La seule granularité de
reprise était le dump de 02:00.

En clair : une panne de disque à 01:59 perdait toute la journée de travail.
Toutes les dépenses saisies, toutes les pièces rattachées, toutes les
décisions du siège. Pour une application dont la raison d'être est de savoir
**où est la preuve**, c'était le risque le plus sérieux de l'infrastructure.

Mesuré sur un banc de 72 Mo, l'ensemble en place : sauvegarde physique en
3,0 s, reprise à un instant précis en 0,6 s, les lignes effacées par erreur
retrouvées et la bêtise absente.

Ce test garde le câblage, parce qu'il tient à quatre choses qui doivent
toutes être vraies en même temps, et dont aucune ne se voit à l'usage
quotidien. Un archivage débranché ne se remarque **que** le jour où l'on en
a besoin.
"""

import os
import stat
from pathlib import Path

import yaml
from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[3]
PILE = RACINE / "deploy" / "docker-compose.prod.yml"
ARCHIVEUR = RACINE / "deploy" / "archiver_wal.sh"
REPRISE = RACINE / "deploy" / "restaurer_a_la_date.sh"
EXEMPLE = RACINE / "deploy" / ".env.example"


class ArchivageDesJournauxTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db = yaml.safe_load(PILE.read_text())["services"]["db"]

    def _commande(self):
        """La commande de la base, en une chaîne.

        Elle est passée en **liste** dans la pile, et ce n'est pas un détail
        de style : ``archive_command`` vaut ``/archiver_wal.sh %p %f``, avec
        des espaces. En chaîne, sa découpe dépendrait des guillemets, et une
        erreur ne se verrait qu'au premier segment perdu.
        """
        commande = self.db.get("command", "")
        self.assertIsInstance(
            commande, list,
            "la commande de la base est repassée en chaîne : la découpe de "
            "archive_command dépend alors d'un shell",
        )
        return commande

    def test_l_archivage_est_active(self):
        commande = " ".join(self._commande())

        self.assertIn("archive_mode=${POSTGRES_ARCHIVE_MODE:-on}", commande)

    def test_l_archivage_appelle_le_script_du_depot(self):
        commande = self._commande()

        self.assertIn("archive_command=/archiver_wal.sh %p %f", commande)

    def test_un_segment_a_moitie_rempli_finit_par_partir(self):
        """Sans ``archive_timeout``, un segment attend d'être plein : le
        travail d'une soirée calme resterait hors de l'archive, et la reprise
        s'arrêterait au dernier segment complet."""
        commande = " ".join(self._commande())

        self.assertIn("archive_timeout=", commande)

    def test_la_base_peut_ecrire_dans_l_archive(self):
        """C'est Postgres lui-même qui appelle le script : sans le volume et
        sans le script montés, l'archivage échoue à chaque segment — et les
        segments s'accumulent dans pg_wal jusqu'à remplir le disque."""
        volumes = self.db.get("volumes", [])

        self.assertIn("./archiver_wal.sh:/archiver_wal.sh:ro", volumes)
        self.assertIn("sauvegardes:/sauvegardes", volumes)

    def test_les_segments_sont_chiffres_comme_les_dumps(self):
        """Un segment contient les mêmes données qu'un dump : lignes, jetons,
        secrets TOTP. Chiffrer les uns et pas les autres laisserait la porte
        ouverte à côté de la serrure."""
        environnement = self.db.get("environment", {})

        self.assertIn("SAUVEGARDE_CLE_PUBLIQUE", environnement)

    def test_les_deux_scripts_sont_executables(self):
        """Montés en lecture seule dans un conteneur, ils gardent les droits
        du dépôt : sans le bit d'exécution, Postgres ne peut pas les lancer."""
        for script in (ARCHIVEUR, REPRISE):
            with self.subTest(script=script.name):
                self.assertTrue(script.exists(), f"{script.name} a disparu")
                self.assertTrue(
                    os.stat(script).st_mode & stat.S_IXUSR,
                    f"{script.name} n'est pas exécutable",
                )

    def test_le_fichier_d_exemple_explique_le_danger(self):
        """L'archivage a un mode de panne que l'exploitant doit connaître
        avant de le rencontrer : tant qu'il échoue, Postgres garde ses
        segments, et finit par remplir le disque de la base."""
        exemple = EXEMPLE.read_text()

        self.assertIn("POSTGRES_ARCHIVE_MODE", exemple)
        self.assertIn("SAUVEGARDE_BASE_PHYSIQUE_JOURS", exemple)
        self.assertIn("pg_wal", exemple)

    def test_l_archiveur_refuse_un_nom_de_segment_douteux(self):
        """``%f`` vient de Postgres, mais le script écrit dans un chemin
        construit avec : un nom contenant « / » ou « .. » écrirait ailleurs
        que dans l'archive."""
        source = ARCHIVEUR.read_text()

        self.assertIn("nom de segment refusé", source)

    def test_la_reprise_ne_touche_rien_par_defaut(self):
        """Une reprise se répète, et une répétition qui détruit la production
        ne se répète qu'une fois. Le mode destructeur se demande."""
        source = REPRISE.read_text()

        self.assertIn('MODE="essai"', source)
        self.assertIn("--en-production", source)
        self.assertIn("La pile n'a pas été touchée", source)
