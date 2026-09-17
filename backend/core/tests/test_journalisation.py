"""Une erreur laisse une trace, et cette trace dit de quelle requête il s'agit.

Régression trouvée par l'audit de résilience. En production (``DEBUG=0``),
Django s'appuyait sur sa configuration par défaut : gestionnaire console
filtré par ``RequireDebugTrue``, gestionnaire par courriel sans ``ADMINS``.
Six mille erreurs 500 produites pendant une coupure de la base n'avaient
écrit **aucune ligne**.

Ces tests vérifient les trois choses qui manquaient : la configuration
existe, le contexte est joint à chaque ligne, et l'identifiant rendu au
client est celui du journal.
"""

import logging
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils.functional import SimpleLazyObject
from rest_framework.authtoken.models import Token

from core.journalisation import (
    ABSENT,
    ENTETE,
    MOTIF_ACCEPTABLE,
    FiltreContexte,
    lire_identifiant,
    poser_identifiant,
    retirer_identifiant,
)


class ConfigurationDesJournauxTests(SimpleTestCase):
    """Ce que Django ne fait pas tout seul hors mode debug."""

    def test_une_configuration_existe(self):
        self.assertTrue(
            getattr(settings, "LOGGING", None),
            "sans LOGGING, la console de Django est filtrée par RequireDebugTrue",
        )

    def test_la_sortie_n_est_pas_conditionnee_au_mode_debug(self):
        for nom, handler in settings.LOGGING["handlers"].items():
            self.assertNotIn(
                "require_debug_true", handler.get("filters", []),
                f"le gestionnaire {nom} se tairait en production",
            )

    def test_les_erreurs_de_requete_sont_journalisees(self):
        niveau = settings.LOGGING["loggers"]["django.request"]["level"]

        self.assertIn(niveau, {"ERROR", "WARNING", "INFO", "DEBUG"})

    def test_le_sql_ne_part_pas_dans_les_journaux(self):
        """Un journal qui recopie chaque requête SQL est illisible, et bavard."""
        self.assertEqual(
            settings.LOGGING["loggers"]["django.db.backends"]["level"], "WARNING"
        )

    def test_le_format_porte_le_contexte(self):
        format_ = settings.LOGGING["formatters"]["standard"]["format"]

        for champ in ("requete", "compte", "ip"):
            self.assertIn(f"{champ}=%({champ})s", format_)


class FiltreContexteTests(SimpleTestCase):
    """Le filtre ne lève jamais, et ne touche jamais la base."""

    def setUp(self):
        self.filtre = FiltreContexte()
        self.fabrique = RequestFactory()

    def _ligne(self):
        return logging.LogRecord("essai", logging.ERROR, __file__, 1, "bonjour", (), None)

    def test_hors_requete_les_champs_sont_des_tirets(self):
        ligne = self._ligne()

        self.assertTrue(self.filtre.filter(ligne))
        self.assertEqual((ligne.requete, ligne.compte, ligne.ip),
                         (ABSENT, ABSENT, ABSENT))

    def test_sous_requete_le_contexte_est_joint(self):
        requete = self.fabrique.get("/api/dossiers/", REMOTE_ADDR="10.1.2.3")
        requete.user = AnonymousUser()
        identifiant, jeton = poser_identifiant(requete)
        try:
            with mock.patch("core.journalisation.get_current_request", return_value=requete):
                ligne = self._ligne()
                self.filtre.filter(ligne)
        finally:
            retirer_identifiant(jeton)

        self.assertEqual(ligne.requete, identifiant)
        self.assertEqual(ligne.ip, "10.1.2.3")
        self.assertEqual(ligne.compte, "anonyme")

    def test_un_compte_paresseux_non_resolu_n_est_jamais_force(self):
        """Forcer ``request.user`` interrogerait la base — au pire moment."""
        requete = self.fabrique.get("/api/dossiers/")
        appels = []

        def resoudre():
            appels.append(1)
            raise AssertionError("le filtre a résolu le compte")

        requete.user = SimpleLazyObject(resoudre)
        with mock.patch("core.journalisation.get_current_request", return_value=requete):
            ligne = self._ligne()
            self.filtre.filter(ligne)

        self.assertEqual(appels, [])
        self.assertEqual(ligne.compte, ABSENT)

    def test_le_filtre_ne_leve_jamais(self):
        """Un filtre qui échoue casse la journalisation, quand tout va déjà mal."""
        with mock.patch("core.journalisation.get_current_request",
                        side_effect=RuntimeError("base coupée")):
            ligne = self._ligne()

            self.assertTrue(self.filtre.filter(ligne))
            self.assertEqual(ligne.compte, ABSENT)


class IdentifiantDeRequeteTests(SimpleTestCase):
    def test_un_identifiant_venu_du_mandataire_est_repris(self):
        requete = RequestFactory().get("/", HTTP_X_REQUETE_ID="abc-123_XYZ")

        identifiant, jeton = poser_identifiant(requete)
        try:
            self.assertEqual(identifiant, "abc-123_XYZ")
            self.assertEqual(lire_identifiant(), "abc-123_XYZ")
        finally:
            retirer_identifiant(jeton)

    def test_un_identifiant_forge_est_ecarte(self):
        """Un saut de ligne fabriquerait une seconde ligne de journal."""
        for forge in ("ligne1\nERROR faux", "a" * 65, "avec espace", ""):
            requete = RequestFactory().get("/", HTTP_X_REQUETE_ID=forge)
            identifiant, jeton = poser_identifiant(requete)
            try:
                self.assertNotEqual(identifiant, forge)
                self.assertTrue(MOTIF_ACCEPTABLE.match(identifiant))
            finally:
                retirer_identifiant(jeton)


class EnTeteDeReponseTests(TestCase):
    def test_chaque_reponse_porte_son_identifiant(self):
        reponse = self.client.get("/api/health/")

        self.assertIn(ENTETE, reponse.headers)
        self.assertTrue(MOTIF_ACCEPTABLE.match(reponse[ENTETE]))

    def test_deux_requetes_ont_deux_identifiants(self):
        premier = self.client.get("/api/health/")[ENTETE]
        second = self.client.get("/api/health/")[ENTETE]

        self.assertNotEqual(premier, second)

    def test_le_compte_pose_par_drf_apparait_dans_la_ligne(self):
        """DRF écrit le compte du jeton sur la requête : il doit être lu.

        C'est le cas courant — une erreur survenue *dans* la vue, une fois le
        jeton vérifié. Sans cela, chaque trace dirait « anonyme » et le
        journal ne servirait plus à identifier qui a subi l'incident.
        """
        compte = User.objects.create_user("agent.journal", password="x" * 14)
        requete = RequestFactory().get("/api/dossiers/", REMOTE_ADDR="10.0.0.9")
        requete.user = compte  # exactement ce que fait ``Request.user`` de DRF
        identifiant, jeton = poser_identifiant(requete)
        try:
            with mock.patch("core.journalisation.get_current_request", return_value=requete):
                ligne = logging.LogRecord("essai", logging.ERROR, __file__, 1, "x", (), None)
                FiltreContexte().filter(ligne)
        finally:
            retirer_identifiant(jeton)

        self.assertEqual(ligne.compte, "agent.journal")
        self.assertEqual(ligne.ip, "10.0.0.9")
        self.assertEqual(ligne.requete, identifiant)
