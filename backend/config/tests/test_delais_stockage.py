"""Délais du client S3 — le thread qui sert un fichier ne s'éternise pas.

Régression trouvée par l'audit de résilience (scénario 10). Sans
``client_config``, botocore attend soixante secondes par tentative et
recommence jusqu'à cinq fois. Un stockage qui accepte la connexion sans
jamais répondre bloquait alors les huit threads de gunicorn, et **toute**
l'API devenait muette — y compris les écrans qui ne touchent aucun fichier.
Le ``--timeout`` de gunicorn ne rattrapait rien : en mode ``gthread`` il
surveille la boucle du worker, pas ses threads de requête.

Mesuré sur un stockage muet (un socket qui accepte et ne répond jamais),
huit téléchargements simultanés sur huit threads :

===============  ==========================  ==============================
                 avant correction            après correction
===============  ==========================  ==============================
téléchargement   bloqué > 140 s, sans fin    503 en 31 à 34 s
reste de l'API   muette, sans reprise        200 en 0,02 s dès t+13 s
journal          aucune ligne                503 rendu proprement
===============  ==========================  ==============================

Les 34 s dépassent la somme ``(connexion + lecture) × tentatives`` : le mode
``standard`` de botocore attend entre deux tentatives. C'est borné, c'est
l'essentiel. Ce test fige ces bornes.
"""

import importlib
import os
from unittest import mock

from django.test import SimpleTestCase


def _recharger_reglages():
    import config.settings

    return importlib.reload(config.settings)


class DelaisDuStockageS3Tests(SimpleTestCase):
    """Les bornes existent, sont finies, et restent raisonnables."""

    def _reglages_avec_s3(self, **surcharges):
        env = {
            "AWS_S3_ENDPOINT_URL": "http://minio:9000",
            "AWS_STORAGE_BUCKET_NAME": "justificatifs",
            **surcharges,
        }
        with mock.patch.dict(os.environ, env, clear=False):
            return _recharger_reglages()

    def tearDown(self):
        # Les réglages du processus de test reprennent leurs valeurs.
        _recharger_reglages()

    def test_le_client_s3_porte_des_delais_bornes(self):
        reglages = self._reglages_avec_s3()
        options = reglages.STORAGES["default"]["OPTIONS"]

        config = options.get("client_config")
        self.assertIsNotNone(config, "aucun délai posé sur le client S3")
        self.assertIsNotNone(config.connect_timeout)
        self.assertIsNotNone(config.read_timeout)
        self.assertLessEqual(config.connect_timeout, 10)
        self.assertLessEqual(config.read_timeout, 30)

    def _config(self, **surcharges):
        options = self._reglages_avec_s3(**surcharges).STORAGES["default"]["OPTIONS"]
        config = options.get("client_config")
        self.assertIsNotNone(config, "aucun délai posé sur le client S3")
        return config

    def test_le_nombre_de_tentatives_est_borne(self):
        config = self._config()

        self.assertIsNotNone(config.retries)
        self.assertLessEqual(config.retries["max_attempts"], 3)

    def test_le_pire_cas_tient_sous_le_timeout_de_gunicorn(self):
        """Un thread bloqué sur le stockage se libère avant que gunicorn n'abandonne.

        Sans cette borne, le thread ne se libérait jamais : c'est la panne
        totale et définitive mesurée par l'audit.
        """
        config = self._config()
        pire_cas = (config.connect_timeout + config.read_timeout) * config.retries["max_attempts"]

        # Mesuré à 34 s avec les valeurs par défaut, attentes entre tentatives
        # comprises. La marge couvre ces attentes sans laisser passer un
        # retour aux soixante secondes de botocore.
        self.assertLess(pire_cas, 60, f"pire cas {pire_cas}s : un thread peut rester pris")

    def test_les_delais_se_reglent_par_l_environnement(self):
        config = self._config(
            AWS_S3_CONNECT_TIMEOUT="2", AWS_S3_READ_TIMEOUT="7", AWS_S3_MAX_ATTEMPTS="1"
        )

        self.assertEqual(config.connect_timeout, 2)
        self.assertEqual(config.read_timeout, 7)
        self.assertEqual(config.retries["max_attempts"], 1)

    def test_sans_s3_le_stockage_reste_le_disque(self):
        with mock.patch.dict(os.environ, {"AWS_S3_ENDPOINT_URL": ""}, clear=False):
            reglages = _recharger_reglages()

        self.assertEqual(
            reglages.STORAGES["default"]["BACKEND"],
            "django.core.files.storage.FileSystemStorage",
        )
