"""Le nombre de connexions que la pile demande doit tenir dans ce que la
base en accorde.

Trouvé par l'audit de résilience. ``max_connections`` était laissé à son
défaut — 100 —, un plafond que personne n'avait choisi et que le
``mem_limit: 1g`` de la base ne peut pas honorer : une connexion coûte 1,9 à
2,4 Mo (mesuré), plus 4 Mo par tri.

Mesuré aussi : le serveur ouvre exactement ``GUNICORN_WORKERS ×
GUNICORN_THREADS`` connexions, jamais davantage — un fil en garde une
(``CONN_MAX_AGE = 60``). Il n'y a pas de réserve qui grossit ; la borne est
structurelle. Quand le budget est épuisé, ce n'est donc pas le serveur qui
tombe — il garde les connexions déjà ouvertes et répond —, c'est
**l'ordonnanceur** qui se voit refuser l'entrée, parce qu'il partage le rôle
applicatif ; les sauvegardes et une session de dépannage, elles, gardent les
trois places que Postgres réserve au propriétaire.

Ce test lit la pile livrable et le fichier d'exemple que l'exploitant
recopie : augmenter les processus ou les fils sans relever le plafond le
fait échouer ici, plutôt qu'en production un dimanche.
"""

import re
from pathlib import Path

import yaml
from django.test import SimpleTestCase

from core.management.commands.run_scheduler import JOBS

RACINE = Path(__file__).resolve().parents[3]
PILE = RACINE / "deploy" / "docker-compose.prod.yml"
EXEMPLE = RACINE / "deploy" / ".env.example"

#: Places que Postgres garde pour le propriétaire (défaut de
#: ``superuser_reserved_connections``) : la sauvegarde et le dépannage.
RESERVE_PROPRIETAIRE = 3

#: Ce que consomme le reste de la pile : exportateur Prometheus, pg_dump,
#: les migrations au déploiement, une session psql d'urgence. Une provision,
#: pas une mesure — d'où sa générosité.
PROVISION_EXPLOITATION = 8


def _valeur_env(nom):
    """Valeur de ``nom`` dans .env.example, commentée ou non.

    Une variable proposée en exemple est souvent commentée : c'est quand
    même la valeur que l'exploitant recopiera.
    """
    motif = re.compile(rf"^#?\s*{nom}=(\S+)\s*$", re.MULTILINE)
    trouve = motif.search(EXEMPLE.read_text())
    assert trouve, f"{nom} ne figure plus dans deploy/.env.example"
    return int(trouve.group(1))


class BudgetDeConnexionsTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db = yaml.safe_load(PILE.read_text())["services"]["db"]

    def _plafond_de_la_pile(self):
        """``max_connections`` tel que la pile le passe à Postgres."""
        commande = str(self.db.get("command", ""))
        trouve = re.search(
            r"-c\s+max_connections=\$\{POSTGRES_MAX_CONNECTIONS:-(\d+)\}", commande
        )
        self.assertIsNotNone(
            trouve,
            "la pile ne fixe plus max_connections : Postgres reprendrait son "
            "défaut de 100, que le gigaoctet de la base ne peut pas honorer",
        )
        return int(trouve.group(1))

    def test_le_plafond_est_une_decision_et_non_un_defaut(self):
        self.assertEqual(self._plafond_de_la_pile(), _valeur_env("POSTGRES_MAX_CONNECTIONS"))

    def test_la_pile_tient_dans_le_plafond(self):
        """Serveur + ordonnanceur + exploitation + réserve ≤ plafond.

        L'appétit du serveur est le produit mesuré ; celui de l'ordonnanceur
        se lit dans ses tâches — en ajouter une augmente le besoin, et ce
        test le dira.
        """
        serveur = _valeur_env("GUNICORN_WORKERS") * _valeur_env("GUNICORN_THREADS")
        ordonnanceur = len(JOBS)
        besoin = serveur + ordonnanceur + PROVISION_EXPLOITATION + RESERVE_PROPRIETAIRE

        self.assertLessEqual(
            besoin,
            self._plafond_de_la_pile(),
            f"la pile demande {besoin} connexions ({serveur} pour le serveur, "
            f"{ordonnanceur} pour l'ordonnanceur) : relevez "
            "POSTGRES_MAX_CONNECTIONS, ou l'ordonnanceur sera refusé",
        )

    def test_le_plafond_tient_dans_la_memoire_de_la_base(self):
        """Un plafond que la mémoire ne peut pas honorer est un piège.

        Le noyau tue la base bien avant que Postgres ne refuse une
        connexion : on compte les tampons partagés, puis le coût mesuré
        d'une connexion, et on exige qu'il reste de quoi trier.
        """
        limite_mo = int(re.fullmatch(r"(\d+)g", str(self.db["mem_limit"])).group(1)) * 1024
        tampons_mo = int(
            re.search(r"shared_buffers=(\d+)MB", str(self.db["command"])).group(1)
        )
        cout_connexion_mo = 2.4  # haut de la fourchette mesurée
        plafond = self._plafond_de_la_pile()

        consomme = tampons_mo + plafond * cout_connexion_mo

        self.assertLess(
            consomme,
            limite_mo * 0.7,
            f"à {plafond} connexions, la base réserve {consomme:.0f} Mo sur "
            f"{limite_mo} Mo : il ne reste pas de quoi trier",
        )
