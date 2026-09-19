"""Délais de la base — attendre, oui ; attendre sans fin, non.

Trouvé par l'audit de résilience, phase des pannes combinées. Rien ne
bornait le temps passé à attendre Postgres : ``statement_timeout``,
``lock_timeout`` et ``idle_in_transaction_session_timeout`` valaient tous
zéro — l'infini — et aucun délai n'était posé côté client. C'est le défaut
du stockage S3 (``test_delais_stockage.py``) à l'identique, sur la base
cette fois.

Mesuré :

=============================  ==========================  ====================
panne injectée                 avant                       après
=============================  ==========================  ====================
base muette (trou noir)        pendue > 90 s, sans fin     503 en 3,0 s
requête trop longue            attendue sans fin           503 en 0,35 s
verrou tenu par un voisin      attendu sans fin            refusé à 10,05 s
=============================  ==========================  ====================

**Une limite demeure, et ce test ne prétend pas la couvrir** : un processus
Postgres vivant au niveau TCP mais qui ne répond plus — figé par un
``SIGSTOP``, ou sur une machine dont le noyau acquitte encore alors que le
service est enlisé. Mesuré : la requête pend toujours au-delà de 95 s.
Aucun de ces réglages ne peut s'y appliquer — ``statement_timeout`` est
appliqué *par le serveur*, qui est justement ce qui manque, et les sondes
TCP reçoivent leurs acquittements du noyau distant, qui répond. Il n'y a
pas de correctif de configuration à cela ; c'est une limite connue, écrite
ici pour qu'elle ne se redécouvre pas.
"""

import importlib
import os
from unittest import mock

from django.test import SimpleTestCase


def _recharger_reglages():
    import config.settings

    return importlib.reload(config.settings)


class DelaisDeLaBaseTests(SimpleTestCase):
    def _options(self, **environnement):
        base = {
            "POSTGRES_PASSWORD": "peu-importe",
            "DJANGO_SECRET_KEY": "peu-importe-aussi-mais-assez-longue-pour-passer",
            "DATABASE_URL": "",
        }
        with mock.patch.dict(os.environ, {**base, **environnement}, clear=False):
            reglages = _recharger_reglages()
            return reglages.DATABASES["default"]["OPTIONS"]

    def test_la_connexion_ne_s_ouvre_pas_indefiniment(self):
        """Sans ``connect_timeout``, une base injoignable fait attendre le
        délai TCP du système — plus de deux minutes."""
        self.assertEqual(self._options()["connect_timeout"], 3)

    def test_une_base_devenue_muette_finit_par_se_voir(self):
        """Les sondes TCP : sans elles, une connexion déjà ouverte vers une
        base coupée n'est jamais déclarée morte."""
        options = self._options()

        self.assertEqual(options["keepalives"], 1)
        self.assertLessEqual(options["keepalives_idle"], 10)
        self.assertGreaterEqual(options["keepalives_count"], 1)

    def test_les_trois_delais_du_serveur_sont_poses(self):
        """Zéro, pour Postgres, veut dire « sans limite »."""
        options = self._options()["options"]

        for reglage in (
            "statement_timeout",
            "lock_timeout",
            "idle_in_transaction_session_timeout",
        ):
            self.assertIn(f"-c {reglage}=", options, f"{reglage} n'est plus posé")
            valeur = options.split(f"-c {reglage}=")[1].split()[0]
            self.assertNotEqual(valeur, "0", f"{reglage} est revenu à l'infini")

    def test_le_verrou_cede_avant_l_instruction(self):
        """Un verrou qui attendrait plus longtemps que l'instruction ne
        servirait à rien : c'est l'instruction qui serait coupée, et le
        message dirait « requête trop longue » au lieu de « verrou tenu »."""
        options = self._options()["options"]
        valeur = lambda nom: int(options.split(f"-c {nom}=")[1].split()[0])  # noqa: E731

        self.assertLess(valeur("lock_timeout"), valeur("statement_timeout"))

    def test_l_url_de_base_garde_les_delais(self):
        """``DATABASE_URL`` (base hébergée) suivait un autre chemin dans la
        configuration : il portait ses propres options, et les délais n'y
        seraient jamais arrivés."""
        options = self._options(
            DATABASE_URL="postgresql://u:p@hote.example.org:5432/base?sslmode=require"
        )

        self.assertEqual(options["sslmode"], "require")
        self.assertEqual(options["connect_timeout"], 3)
        self.assertIn("-c statement_timeout=", options["options"])

    def test_ce_que_l_url_dit_l_emporte(self):
        """Nos défauts ne doivent pas écraser un réglage écrit à la main."""
        options = self._options(
            DATABASE_URL="postgresql://u:p@hote.example.org:5432/base?connect_timeout=30"
        )

        self.assertEqual(options["connect_timeout"], "30")

    def test_les_migrations_ne_se_font_pas_couper(self):
        """Le délai d'instruction borne les requêtes du service ; un
        ``CREATE INDEX`` sur une grande table le dépasse légitimement.
        ``entrypoint.sh`` lève donc le délai pour les commandes de
        maintenance — et pour elles seulement."""
        from pathlib import Path

        entree = (Path(__file__).resolve().parents[2] / "entrypoint.sh").read_text()

        self.assertIn("POSTGRES_STATEMENT_TIMEOUT=0", entree)
        self.assertIn("en_tant_que_proprietaire python manage.py migrate", entree)
        self.assertNotIn(
            "POSTGRES_LOCK_TIMEOUT=0",
            entree,
            "une migration qui n'obtient pas son verrou doit échouer, pas attendre",
        )
