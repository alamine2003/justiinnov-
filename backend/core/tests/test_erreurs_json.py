"""L'API répond en JSON, y compris quand l'infrastructure lâche.

Deux régressions trouvées par l'audit de résilience :

- une erreur non prévue rendait ``<!doctype html><title>Server Error
  (500)</title>`` à un client qui attend du JSON — il cassait donc *en plus*
  de l'erreur initiale ;
- une base injoignable rendait 500, c'est-à-dire « l'application a un
  défaut », quand il faut dire « indisponible, réessayez ».

Mesuré sur le banc, base coupée : ``/api/health/`` rendait 503 pendant que
``/api/dossiers/`` rendait 500 — deux codes pour une même panne, parce que
le verrou d'accès interroge la base dans un ``process_view``, hors du champ
de DRF. Ces tests figent le contrat : même panne, même réponse, partout.
"""

import json
from unittest import mock

from django.db import OperationalError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import path
from rest_framework.exceptions import ValidationError

from core.exceptions import (
    DELAI_DE_REESSAI,
    INDISPONIBLE,
    gestionnaire_d_exception,
    reinitialiser_le_debit_de_journal,
    reponse_indisponible,
)


class GestionnaireDrfTests(SimpleTestCase):
    """Ce que DRF fait des exceptions qu'on lui donne."""

    def test_une_base_injoignable_devient_503(self):
        reponse = gestionnaire_d_exception(OperationalError("serveur absent"), {})

        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse["Retry-After"], str(DELAI_DE_REESSAI))
        self.assertEqual(reponse.data["detail"], str(INDISPONIBLE))

    def test_le_reste_garde_le_comportement_de_drf(self):
        reponse = gestionnaire_d_exception(ValidationError({"montant": ["trop"]}), {})

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("montant", reponse.data)

    def test_une_exception_inconnue_n_est_pas_masquee(self):
        """Rendre ``None`` laisse DRF relancer : la trace reste journalisée."""
        self.assertIsNone(gestionnaire_d_exception(ValueError("un vrai défaut"), {}))


class ReponseIndisponibleTests(SimpleTestCase):
    # Le débit de journal est un compteur de module : sans remise à zéro, un
    # test consomme la trace du suivant.
    def setUp(self):
        reinitialiser_le_debit_de_journal()

    def tearDown(self):
        reinitialiser_le_debit_de_journal()

    def test_elle_porte_le_code_le_delai_et_le_motif(self):
        reponse = reponse_indisponible()

        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse["Retry-After"], str(DELAI_DE_REESSAI))
        self.assertEqual(reponse["Content-Type"], "application/json")
        self.assertEqual(json.loads(reponse.content)["detail"], str(INDISPONIBLE))

    def test_elle_journalise_quand_on_lui_donne_la_panne(self):
        with self.assertLogs("core.exceptions", level="ERROR") as journal:
            reponse_indisponible(OperationalError("coupée"), ou="essai")

        self.assertIn("Base de données injoignable (essai)", journal.output[0])


class PagesDErreurTests(TestCase):
    """Ce que rend Django pour ce qui échappe à DRF."""

    def test_une_url_inconnue_sous_api_rend_du_json(self):
        reponse = self.client.get("/api/cette-route-n-existe-pas/")

        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse["Content-Type"], "application/json")
        self.assertIn("detail", json.loads(reponse.content))

    def test_une_url_inconnue_hors_api_garde_le_html(self):
        """L'admin Django, monté en développement, garde ses pages."""
        reponse = self.client.get("/quelque-chose/")

        self.assertEqual(reponse.status_code, 404)
        self.assertNotIn("application/json", reponse["Content-Type"])

    def test_un_client_qui_demande_du_json_en_reçoit(self):
        reponse = self.client.get("/quelque-chose/", HTTP_ACCEPT="application/json")

        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse["Content-Type"], "application/json")


class DegradationCoherenteTests(TestCase):
    """La même panne donne la même réponse, quelle que soit la route.

    C'est l'incohérence mesurée par l'audit : 503 sur le point de santé,
    500 sur toute route authentifiée, pour une seule et même base coupée.
    """

    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def _base_coupee(self):
        return mock.patch(
            "accounts.middleware._authenticated_user",
            side_effect=OperationalError("serveur absent"),
        )

    def test_le_verrou_d_acces_rend_503_et_non_500(self):
        with self._base_coupee():
            reponse = self.client.get("/api/dossiers/")

        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse["Retry-After"], str(DELAI_DE_REESSAI))
        self.assertEqual(reponse["Content-Type"], "application/json")

    def test_un_defaut_reel_reste_une_erreur_500_en_json(self):
        """Un bogue ne doit pas se déguiser en indisponibilité passagère."""
        with mock.patch(
            "accounts.middleware._authenticated_user", side_effect=ValueError("bogue")
        ):
            reponse = self.client.get("/api/dossiers/")

        self.assertEqual(reponse.status_code, 500)
        self.assertEqual(reponse["Content-Type"], "application/json")
        self.assertIn("detail", json.loads(reponse.content))


class DebitDuJournalTests(SimpleTestCase):
    """Une panne ne doit pas effacer l'historique des journaux.

    Une base coupée fait échouer toutes les requêtes, et vite : le débit
    monte au lieu de descendre. Mesuré sur le banc — 441 erreurs par
    seconde, 7,8 ko de trace chacune, soit **24 Mo en sept secondes**.
    Docker retient 100 Mo par service : une demi-minute de panne effaçait
    tout, y compris les lignes qui diraient ce qui s'est passé avant elle.

    Après bornage, le même test produit 17,8 ko.
    """

    def setUp(self):
        reinitialiser_le_debit_de_journal()

    def tearDown(self):
        reinitialiser_le_debit_de_journal()

    def test_la_premiere_panne_porte_sa_trace(self):
        with self.assertLogs("core.exceptions", level="ERROR") as journal:
            reponse_indisponible(OperationalError("coupée"), ou="essai")

        self.assertEqual(len(journal.records), 1)
        self.assertIsNotNone(journal.records[0].exc_info, "la trace manque")

    def test_les_suivantes_ne_repetent_pas_la_trace(self):
        with self.assertLogs("core.exceptions", level="ERROR") as journal:
            for _ in range(500):
                reponse_indisponible(OperationalError("coupée"), ou="essai")

        avec_trace = [r for r in journal.records if r.exc_info]
        self.assertEqual(len(avec_trace), 1, "la trace se répète")
        self.assertLess(
            len(journal.records), 10,
            f"{len(journal.records)} lignes pour 500 pannes : le débit n'est pas borné",
        )

    def test_le_nombre_d_appels_echoues_est_dit(self):
        """Rien de ce qui compte n'est perdu : la trace est la même à chaque
        fois, seul le volume change — et il est annoncé."""
        with self.assertLogs("core.exceptions", level="ERROR"):
            reponse_indisponible(OperationalError("coupée"), ou="essai")

        import core.exceptions as ce

        ce._dernier_resume = 0.0  # la seconde de résumé est écoulée
        with self.assertLogs("core.exceptions", level="ERROR") as journal:
            for _ in range(41):
                reponse_indisponible(OperationalError("coupée"), ou="essai")

        self.assertIn("appels échoués", journal.records[0].getMessage())

    def test_chaque_reponse_reste_un_503_meme_sans_ligne_de_journal(self):
        """Borner le journal ne borne pas les réponses : chacune est servie."""
        reponses = [
            reponse_indisponible(OperationalError("coupée"), ou="essai")
            for _ in range(50)
        ]

        self.assertTrue(all(r.status_code == 503 for r in reponses))
        self.assertTrue(all(r["Retry-After"] == str(DELAI_DE_REESSAI) for r in reponses))
