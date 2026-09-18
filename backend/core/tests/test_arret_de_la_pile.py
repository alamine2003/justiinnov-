"""La pile doit avoir le temps de se vider avant d'être abattue.

Trouvé par l'audit de résilience. Trois délais qui se contredisaient :

- ``GUNICORN_TIMEOUT`` vaut 120 s — et `deploy/.env.example` dit pourquoi :
  « un export Excel d'une année complète ou le dépôt d'une pièce de 20 Mo
  sur une liaison lente peuvent dépasser les 30 s par défaut » ;
- ``--graceful-timeout 30`` laisse trente secondes aux requêtes en vol pour
  finir quand gunicorn s'arrête ;
- Compose, lui, n'accordait rien : **dix secondes** par défaut entre son
  SIGTERM et son SIGKILL.

Mesuré : une pièce en cours de dépôt a mis **11,07 s** à finir après le
SIGTERM au maître gunicorn — une seconde de trop. À chaque livraison, le
déposant perdait donc son envoi. Aucune donnée n'était corrompue (les
transitions sont atomiques, c'est vérifié par ailleurs) ; le travail de la
personne, si.

Ce test lit la pile livrable telle qu'elle sera déployée.
"""

from pathlib import Path

import yaml
from django.test import SimpleTestCase

RACINE = Path(__file__).resolve().parents[3]
PILE = RACINE / "deploy" / "docker-compose.prod.yml"
ENTREE = RACINE / "backend" / "entrypoint.sh"

#: Défaut de Compose quand rien n'est déclaré.
GRACE_PAR_DEFAUT = 10


def _secondes(valeur):
    """``35s`` → 35. Compose accepte aussi ``1m30s``, non utilisé ici."""
    texte = str(valeur).strip()
    if texte.endswith("s") and texte[:-1].isdigit():
        return int(texte[:-1])
    if texte.isdigit():
        return int(texte)
    raise AssertionError(f"délai non reconnu : {valeur!r}")


class ArretDeLaPileTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pile = yaml.safe_load(PILE.read_text())["services"]
        cls.entree = ENTREE.read_text()

    def _grace(self, service):
        valeur = self.pile[service].get("stop_grace_period")
        self.assertIsNotNone(
            valeur,
            f"{service} n'accorde que {GRACE_PAR_DEFAUT} s : ses requêtes en vol "
            "sont abattues à chaque livraison",
        )
        return _secondes(valeur)

    def test_le_backend_a_le_temps_de_se_vider(self):
        """Sa grâce doit dépasser le ``--graceful-timeout`` de gunicorn.

        Sinon Docker l'abat pendant qu'il attend ses requêtes, et le réglage
        de gunicorn ne sert à rien.
        """
        grace_gunicorn = int(
            self.entree.split("--graceful-timeout")[1].split()[0].strip("\\ \n")
        )

        self.assertGreater(
            self._grace("backend"), grace_gunicorn,
            f"gunicorn attend {grace_gunicorn} s, Docker doit lui en laisser plus",
        )

    def test_la_base_a_le_temps_de_poser_son_point_de_reprise(self):
        self.assertGreaterEqual(self._grace("db"), 30)

    def test_le_delai_de_requete_reste_coherent_avec_la_vidange(self):
        """Autoriser 120 s puis n'en accorder que 10 se contredit.

        On ne demande pas l'égalité — attendre deux minutes à chaque
        livraison serait absurde —, mais que la vidange soit une décision
        écrite, pas le défaut de Compose.
        """
        environnement = self.pile["backend"].get("environment", {})
        declare = "GUNICORN_TIMEOUT" in str(environnement) or "GUNICORN_TIMEOUT" in str(
            yaml.safe_load(PILE.read_text())
        )

        self.assertTrue(declare, "GUNICORN_TIMEOUT n'est plus déclaré dans la pile")
        self.assertGreater(self._grace("backend"), GRACE_PAR_DEFAUT)
