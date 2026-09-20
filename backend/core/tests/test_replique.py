"""La seconde machine doit suivre la première, sans pouvoir la mettre à terre.

Une réplique en attente chaude ajoute une machine, donc des façons de se
tromper. Trois d'entre elles sont graves et silencieuses, et ce test garde
le câblage qui les empêche :

1. **La primaire meurt de sa réplique.** Un emplacement de réplication lui
   demande de garder tout ce que la réplique n'a pas lu ; si la seconde
   machine s'absente, cela ne s'arrête jamais. Mesuré : sans borne, `pg_wal`
   grandit jusqu'à remplir le disque et la base s'arrête. Avec
   `max_slot_wal_keep_size`, l'emplacement est déclaré perdu, la primaire
   continue de servir, et c'est la réplique qu'on refait — 0,5 s pour 15 Mo.
   Perdre la réplique vaut mieux que perdre la base.

2. **Les deux machines sauvegardent au même endroit.** Elles écriraient
   l'une par-dessus l'autre dans le coffre distant. Les services de
   sauvegarde restent donc à l'arrêt sur la réplique, dans le profil
   `bascule`.

3. **On promeut alors que la primaire vivait encore.** Deux bases qui
   acceptent des écritures produisent deux histoires que rien ne réconcilie.

Mesuré sur banc, deux grappes locales : retard 0 octet / 0,69 ms, promotion
en 0,11 s, aucune perte après un SIGKILL de la primaire.
"""

import os
import stat
from pathlib import Path

import yaml
from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[3]
PRIMAIRE = RACINE / "deploy" / "docker-compose.prod.yml"
REPLIQUE = RACINE / "deploy" / "docker-compose.replique.yml"
PREPARATION = RACINE / "deploy" / "preparer_replique.sh"
PROMOTION = RACINE / "deploy" / "promouvoir_replique.sh"
ROLE = RACINE / "deploy" / "creer_role_replication.sql"
EXEMPLE = RACINE / "deploy" / ".env.example"

#: Services qui ne doivent jamais tourner sur la réplique tant qu'elle en est
#: une. Les sauvegardes d'abord : c'est la seule de la liste dont la présence
#: abîmerait quelque chose d'irremplaçable.
A_L_ARRET = (
    "sauvegarde", "sauvegarde-pieces", "sauvegarde-distante",
    "backend", "scheduler", "frontend", "caddy",
)


class RepliqueEnAttenteChaudeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.primaire = yaml.safe_load(PRIMAIRE.read_text())["services"]
        cls.replique = yaml.safe_load(REPLIQUE.read_text())["services"]

    def test_la_primaire_borne_ce_qu_elle_garde_pour_une_replique_absente(self):
        """Sans cette borne, une seconde machine éteinte remplit le disque de
        la première. C'est la ligne la plus importante de tout ce dispositif."""
        commande = " ".join(self.primaire["db"]["command"])

        self.assertIn("max_slot_wal_keep_size=", commande)

    def test_la_borne_n_est_pas_illimitee(self):
        """``-1`` est le défaut de Postgres, et il veut dire « sans limite »."""
        commande = " ".join(self.primaire["db"]["command"])
        valeur = commande.split("max_slot_wal_keep_size=")[1].split()[0]

        self.assertNotIn("-1", valeur, "la borne est revenue à l'illimité")

    def test_les_sauvegardes_ne_tournent_pas_sur_la_replique(self):
        """Deux machines qui sauvegardent vers le même coffre distant
        s'écrasent l'une l'autre. C'est la seule erreur de cette liste qui
        détruise quelque chose d'irremplaçable."""
        for service in ("sauvegarde", "sauvegarde-pieces", "sauvegarde-distante"):
            with self.subTest(service=service):
                self.assertIn(
                    "bascule", self.replique[service].get("profiles", []),
                    f"{service} tournerait sur la réplique et écraserait les "
                    "sauvegardes de la primaire",
                )

    def test_l_application_attend_la_bascule(self):
        """Démarrée pendant que la primaire vit, elle écrirait dans une base
        en lecture seule, et l'ordonnanceur notifierait en double."""
        for service in A_L_ARRET:
            with self.subTest(service=service):
                self.assertIn("bascule", self.replique[service].get("profiles", []))

    def test_la_replique_ne_redefinit_pas_les_services(self):
        """Une seconde définition de l'application dériverait de la première
        sans que rien ne le dise. La surcharge ne décide que de ce qui
        tourne."""
        for nom, service in self.replique.items():
            with self.subTest(service=nom):
                self.assertEqual(
                    set(service.keys()), {"profiles"},
                    f"{nom} redéfinit autre chose que son profil",
                )

    def test_la_promotion_refuse_une_primaire_vivante(self):
        """Deux primaires produisent deux histoires que rien ne réconcilie."""
        source = PROMOTION.read_text()

        self.assertIn("pg_isready", source)
        self.assertIn("bascule refusée tant que l'ancienne primaire vit", source)

    def test_la_promotion_rappelle_ce_qu_aucun_script_ne_fait(self):
        """Le domaine et l'ancienne machine : c'est là que les bascules
        ratent, pas dans la réplication."""
        source = PROMOTION.read_text()

        self.assertIn("LE DOMAINE POINTE ENCORE", source)
        self.assertIn("NE REDÉMARREZ JAMAIS", source)

    def test_la_promotion_dit_comment_empecher_le_retour_de_la_perdue(self):
        """Le retour d'une ancienne primaire est le seul point du dispositif
        qu'aucun programme ne tient, et c'est mesuré : redémarrée telle
        quelle, elle n'est pas en récupération, ``/api/health/`` y répond 200,
        et l'aiguillage — qui préfère toujours la première machine — lui a
        rendu le trafic **5,1 s** après son retour, sur une base arrêtée à
        l'instant de sa perte (docs/audit-resilience.md §9).

        Le rappel « ne la redémarrez jamais » ne suffit pas : avec
        ``restart: unless-stopped``, l'hôte la rallume sans demander l'avis de
        personne. Le script doit donner la commande qui l'en empêche, et la
        donner avant. Une consigne est ici la seule protection ; si elle
        disparaît d'un nettoyage, plus rien ne couvre le cas."""
        source = PROMOTION.read_text()

        self.assertIn("docker compose -f docker-compose.prod.yml down", source)
        self.assertIn("restart: unless-stopped", source)
        self.assertIn("AUCUN PROGRAMME", source)

    def test_la_bascule_se_repete_sans_rien_casser(self):
        """Une répétition qui promeut pour de bon ne se répète qu'une fois."""
        source = PROMOTION.read_text()

        self.assertIn("--repetition", source)
        self.assertIn("rien n'est irréversible", source)

    def test_la_preparation_refuse_d_ecraser_une_base(self):
        """Le répertoire visé contient peut-être la dernière copie qui
        reste."""
        source = PREPARATION.read_text()

        self.assertIn("contient déjà une base", source)

    def test_le_role_de_replication_ne_lit_pas_les_tables(self):
        """Il lit le journal, pas la base : lui refuser la connexion réduit
        ce qu'un mot de passe volé permet."""
        source = ROLE.read_text()

        self.assertIn("NOSUPERUSER", source)
        self.assertIn("REVOKE CONNECT", source)

    def test_les_scripts_sont_executables(self):
        for script in (PREPARATION, PROMOTION):
            with self.subTest(script=script.name):
                self.assertTrue(
                    os.stat(script).st_mode & stat.S_IXUSR,
                    f"{script.name} n'est pas exécutable",
                )

    def test_le_fichier_d_exemple_dit_qu_une_replique_n_est_pas_une_sauvegarde(self):
        """La confusion est fréquente et coûteuse : elle fait renoncer aux
        sauvegardes parce qu'« on a une réplique »."""
        exemple = EXEMPLE.read_text()

        self.assertIn("POSTGRES_SLOT_WAL_MAX", exemple)
        self.assertIn("N'EST PAS UNE SAUVEGARDE", exemple)
