"""Références calculées des projets (décision 100, ``core.numerotation``)."""

import threading
import time
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest import mock

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase

from core import types_de_projets
from core.models import Country, Project
from core.numerotation import annee_locale, creer_projet


def _pays(code="TG", nom="Togo", fuseau="Africa/Lome"):
    return Country.objects.create(
        name=nom, code=code, currency="XOF", timezone=fuseau,
    )


class NumerotationDesProjetsTests(TestCase):
    def setUp(self):
        self.togo = _pays()
        self.annee = annee_locale(self.togo)

    def nouveau(self, nom, country=None):
        return creer_projet(Project(
            country=country or self.togo, name=nom, kind_id=types_de_projets.CONGRES,
        ))

    def test_les_projets_d_un_pays_se_suivent_dans_l_annee(self):
        premier = self.nouveau("Congrès de pédiatrie")
        second = self.nouveau("Congrès de cardiologie")
        self.assertEqual(premier.reference, f"TG-P-{self.annee}-001")
        self.assertEqual(second.reference, f"TG-P-{self.annee}-002")
        self.assertEqual((second.year, second.sequence), (self.annee, 2))

    def test_chaque_pays_a_son_compteur(self):
        self.nouveau("Congrès de Lomé")
        benin = _pays("BJ", "Bénin", "Africa/Porto-Novo")
        projet = self.nouveau("Congrès de Cotonou", country=benin)
        self.assertEqual(projet.reference, f"BJ-P-{self.annee}-001")

    def test_le_rang_repart_de_un_chaque_annee(self):
        self.nouveau("Congrès de l'an passé")
        with mock.patch("core.numerotation.annee_locale", return_value=self.annee + 1):
            projet = self.nouveau("Congrès de l'an prochain")
        self.assertEqual(projet.reference, f"TG-P-{self.annee + 1}-001")

    def test_l_annee_est_celle_du_pays(self):
        """Le 1er janvier 2027 à 00:30 UTC, Lomé (UTC) est en 2027 ; un pays
        à UTC-3 est encore le 31 décembre 2026."""
        instant = datetime(2027, 1, 1, 0, 30, tzinfo=dt_timezone.utc)
        with mock.patch("core.numerotation.timezone.now", return_value=instant):
            self.assertEqual(annee_locale(self.togo), 2027)
            self.togo.timezone = "America/Sao_Paulo"
            self.assertEqual(annee_locale(self.togo), 2026)

    def test_un_projet_deja_enregistre_ne_se_renumerote_pas(self):
        projet = self.nouveau("Congrès")
        with self.assertRaises(ValueError):
            creer_projet(projet)


class CourseSurLaNumerotation(TransactionTestCase):
    """Deux projets créés au même instant dans le même pays : deux rangs."""

    def test_deux_creations_simultanees_ne_tirent_pas_le_meme_rang(self):
        # Ce cas de test vide la base, types d'origine compris (core.0018).
        types_de_projets.assurer_les_types_d_origine()
        togo = _pays()
        resultats = {}

        def concurrent():
            try:
                resultats["second"] = creer_projet(Project(
                    country_id=togo.pk, name="Second", kind_id=types_de_projets.VOYAGE,
                ))
            finally:
                connection.close()

        fil = threading.Thread(target=concurrent)
        with transaction.atomic():
            premier = creer_projet(Project(
                country=togo, name="Premier", kind_id=types_de_projets.CONGRES,
            ))
            fil.start()
            self.assertTrue(self._attendre_une_session_bloquee())
        fil.join(timeout=10)
        self.assertFalse(fil.is_alive())
        self.assertEqual(premier.sequence, 1)
        self.assertEqual(resultats["second"].sequence, 2)

    def _attendre_une_session_bloquee(self, delai=10):
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_stat_clear_snapshot()")
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
                if cursor.fetchone()[0]:
                    return True
            time.sleep(0.05)
        return False
