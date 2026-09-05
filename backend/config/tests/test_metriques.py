"""Le point de collecte Prometheus n'est ouvert qu'au porteur du jeton."""

import os
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings


class MetriquesTests(TestCase):
    @override_settings(METRICS_TOKEN="")
    def test_sans_jeton_configure_le_point_n_existe_pas(self):
        self.assertEqual(self.client.get("/metrics").status_code, 404)

    @override_settings(METRICS_TOKEN="collecte-2026")
    def test_un_jeton_faux_est_refuse(self):
        reponse = self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer autre")
        self.assertEqual(reponse.status_code, 401)

    @override_settings(METRICS_TOKEN="collecte-2026")
    def test_le_bon_jeton_livre_les_compteurs(self):
        reponse = self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer collecte-2026")
        self.assertEqual(reponse.status_code, 200)
        self.assertIn(b"django_http_requests", reponse.content)

    @override_settings(METRICS_TOKEN="collecte-2026")
    def test_en_multi_processus_le_point_repond_depuis_le_repertoire_partage(self):
        """Avec plusieurs workers gunicorn, les compteurs sont lus dans
        ``PROMETHEUS_MULTIPROC_DIR`` et non dans la mémoire du processus."""
        with tempfile.TemporaryDirectory() as repertoire, patch.dict(
            os.environ, {"PROMETHEUS_MULTIPROC_DIR": repertoire}
        ):
            reponse = self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer collecte-2026")

        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse["Content-Type"].startswith("text/plain"))
