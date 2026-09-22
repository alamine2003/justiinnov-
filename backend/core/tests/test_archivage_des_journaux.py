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
SAUVEGARDEUR = RACINE / "deploy" / "sauvegarder.sh"
EXEMPLE = RACINE / "deploy" / ".env.example"
README = RACINE / "deploy" / "README.md"


class ArchivageDesJournauxTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.services = yaml.safe_load(PILE.read_text())["services"]
        cls.db = cls.services["db"]

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


class LaRepriseEstCableeTests(SimpleTestCase):
    """Ce que l'audit avait documenté comme prêt, et qui ne l'était pas.

    Le banc n'avait pas Docker. Trois choses ne se voyaient donc qu'en
    lisant la pile, et personne ne l'avait fait : le script de reprise
    n'était monté dans aucun conteneur ; le service qui devait le lancer ne
    voyait pas le répertoire de données et tournait en root, que `pg_ctl`
    refuse ; et le volume des sauvegardes, créé par Docker en root, n'était
    pas inscriptible par Postgres — chaque archivage échouait, et les
    segments s'accumulaient dans `pg_wal`. Ce test relit la pile pour que
    cela ne se reproduise pas ; la CI, elle, la joue.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.services = yaml.safe_load(PILE.read_text())["services"]

    def test_le_volume_des_sauvegardes_est_donne_a_postgres_avant_la_base(self):
        """Docker crée un volume vide en root ; Postgres archive sous
        `postgres`. Sans ce passage, `mkdir base/wal` échoue au premier
        segment, et le disque se remplit en silence."""
        init = self.services["sauvegardes-init"]
        commande = " ".join(init["command"])

        self.assertIn("chown", commande)
        self.assertIn("postgres:postgres", commande)
        self.assertIn("/sauvegardes/base", commande)
        self.assertIn("/sauvegardes/.distant", commande)
        self.assertIn("sauvegardes:/sauvegardes", init["volumes"])
        self.assertEqual(
            self.services["db"]["depends_on"]["sauvegardes-init"]["condition"],
            "service_completed_successfully",
        )

    def test_la_sauvegarde_ecrit_sous_le_meme_compte_que_l_archivage(self):
        self.assertEqual(self.services["sauvegarde"].get("user"), "postgres")

    def test_la_reprise_a_son_service_et_lui_seul_voit_les_donnees(self):
        """`--en-production` remplace le répertoire de données : il faut
        le voir. Mais un service de sauvegarde qui le verrait en permanence
        pourrait, sur un bug, y écrire ; seul `reprise` l'a, et `up` ne le
        lance jamais."""
        reprise = self.services["reprise"]

        self.assertEqual(reprise["profiles"], ["reprise"])
        self.assertEqual(reprise["user"], "postgres")
        self.assertEqual(reprise["entrypoint"], ["/restaurer_a_la_date.sh"])
        self.assertIn("./restaurer_a_la_date.sh:/restaurer_a_la_date.sh:ro", reprise["volumes"])
        self.assertIn("sauvegardes:/sauvegardes", reprise["volumes"])
        self.assertIn("pgdata:/var/lib/postgresql/data", reprise["volumes"])
        for nom, service in self.services.items():
            if nom in ("db", "reprise"):
                continue
            with self.subTest(service=nom):
                self.assertFalse(
                    any(v.startswith("pgdata:") for v in service.get("volumes", [])),
                    f"{nom} voit le répertoire de données de la base",
                )

    def test_la_reprise_refuse_root_et_sait_que_les_donnees_sont_un_point_de_montage(self):
        source = REPRISE.read_text()

        self.assertIn('[ "$(id -u)" -ne 0 ]', source)
        # Un point de montage ne se renomme pas : le contenu est mis de côté,
        # élément par élément, dans le volume des sauvegardes.
        self.assertIn("avant-reprise-", source)
        self.assertNotIn('mv "$cible" "$sauvegarde_du_repertoire"', source)
        # L'essai se suffit à lui-même : le conteneur disparaît avec la
        # commande, il n'y aurait personne pour « regarder » après.
        self.assertIn("--requete", source)
        self.assertIn("recovery stopping", source)

    def test_le_readme_lance_la_reprise_par_son_service(self):
        readme = README.read_text()

        self.assertIn("run --rm reprise", readme)
        self.assertNotIn("--entrypoint /restaurer_a_la_date.sh sauvegarde", readme)

    def test_les_segments_et_les_sauvegardes_physiques_partent_hors_machine(self):
        """Sans eux là-bas, la reprise à un instant donné ne survit qu'à la
        perte d'un disque, pas à celle du serveur — et trois documents
        disaient le contraire."""
        source = SAUVEGARDEUR.read_text()

        self.assertIn("copier_wal_distant()", source)
        self.assertIn("copier_base_physique_distant()", source)
        self.assertIn("for d in $FAMILLES", source)
        self.assertRegex(source, r'(?m)^FAMILLES=".*base-physique.*wal.*"', "les familles copiées")
        # Chaque famille pose son marqueur : c'est ce que verifier_sauvegardes lit.
        self.assertIn('marquer_reussite "$(marqueur_distant_de "$d")"', source)

