"""Ce que la surveillance des erreurs laisse sortir — et ce qu'elle retient.

JUSTI INNOV suit des dépenses de filiales : qui a déclaré quoi, pour quel
bénéficiaire, avec quelle pièce. Un rapport d'erreur ne doit pas en devenir
une seconde copie, hors périmètre et hors journal d'audit. Les réglages qui
l'empêchent ne sont pas des préférences : ce sont eux qui rendent l'outil
acceptable, et Sentry enverrait le contraire par défaut.

Ce fichier les tient. Si l'un d'eux disparaît un jour d'un ``init`` remanié,
c'est ici que cela se voit — pas dans un tableau de bord, six mois plus tard.
"""

import logging
from unittest import mock

from django.test import SimpleTestCase

from config import surveillance

ADRESSE = "https://cle-de-test@exemple.ingest.sentry.io/42"


class SurveillanceEteinteTests(SimpleTestCase):
    def test_sans_adresse_rien_ne_s_installe(self):
        """Le défaut : aucune requête ne sort, aucune dépendance de plus."""
        with mock.patch.dict("os.environ", {"SENTRY_DSN": ""}, clear=False):
            with mock.patch("sentry_sdk.init") as init:
                retenu = surveillance.configurer_la_surveillance()

        init.assert_not_called()
        self.assertFalse(retenu["actif"])

    def test_une_adresse_faite_d_espaces_ne_compte_pas(self):
        """Une variable ``.env`` mal recopiée ne doit pas allumer la moitié
        d'une intégration."""
        with mock.patch.dict("os.environ", {"SENTRY_DSN": "   "}, clear=False):
            with mock.patch("sentry_sdk.init") as init:
                retenu = surveillance.configurer_la_surveillance()

        init.assert_not_called()
        self.assertFalse(retenu["actif"])

    def test_pendant_les_tests_jamais(self):
        """Une suite qui lève exprès n'a pas à remplir un tableau de bord —
        ni à exiger un réseau pour tourner."""
        with mock.patch.dict("os.environ", {"SENTRY_DSN": ADRESSE}, clear=False):
            with mock.patch("sentry_sdk.init") as init:
                retenu = surveillance.configurer_la_surveillance(en_test=True)

        init.assert_not_called()
        self.assertFalse(retenu["actif"])
        self.assertEqual(retenu["raison"], "test")


class CeQuiNeSortPasTests(SimpleTestCase):
    def _reglages(self, **variables):
        variables.setdefault("SENTRY_DSN", ADRESSE)
        with mock.patch.dict("os.environ", variables, clear=False):
            with mock.patch("sentry_sdk.init") as init:
                retenu = surveillance.configurer_la_surveillance()
        init.assert_called_once()
        return init.call_args.kwargs, retenu

    def test_ni_compte_ni_adresse_ip_ni_jeton(self):
        """``send_default_pii`` est vrai par défaut chez Sentry : il enverrait
        le nom du compte, l'adresse du client, les témoins de connexion et
        l'en-tête ``Authorization``. Sur cette plateforme, l'adresse IP est
        une donnée du journal d'audit (décision 68) ; elle n'a pas à partir
        ailleurs."""
        reglages, _ = self._reglages()

        self.assertIs(reglages["send_default_pii"], False)

    def test_le_corps_des_requetes_ne_part_jamais(self):
        """Il porte les montants, les intitulés, les bénéficiaires — et, sur
        un dépôt, jusqu'à 20 Mo de justificatif."""
        reglages, _ = self._reglages()

        self.assertEqual(reglages["max_request_body_size"], "never")

    def test_les_fils_d_ariane_s_arretent_aux_avertissements(self):
        """Au niveau ``INFO``, ils emporteraient le détail des requêtes
        servies dans chaque événement."""
        reglages, _ = self._reglages()
        journal = next(
            i for i in reglages["integrations"] if type(i).__name__ == "LoggingIntegration"
        )

        # ``_handler`` est celui qui fabrique un événement, ``_breadcrumb_handler``
        # celui qui retient un fil d'Ariane. Les confondre inverserait les deux.
        self.assertEqual(journal._handler.level, surveillance.NIVEAU_EVENEMENT)
        self.assertEqual(journal._breadcrumb_handler.level, surveillance.NIVEAU_FIL)
        self.assertGreaterEqual(surveillance.NIVEAU_FIL, logging.WARNING)
        self.assertGreaterEqual(surveillance.NIVEAU_EVENEMENT, logging.ERROR)

    def test_la_mesure_des_performances_est_eteinte_par_defaut(self):
        """Un second flux, plus volumineux que les erreurs, pour une mesure
        que Prometheus fait déjà sans rien faire sortir de la machine."""
        reglages, _ = self._reglages()

        self.assertEqual(reglages["traces_sample_rate"], 0.0)

    def test_elle_s_ouvre_si_on_le_demande(self):
        """Éteinte par défaut ne veut pas dire impossible : c'est un réglage,
        pas un verrou."""
        reglages, _ = self._reglages(SENTRY_TRACES_SAMPLE_RATE="0.05")

        self.assertAlmostEqual(reglages["traces_sample_rate"], 0.05)


class DernierFiltreTests(SimpleTestCase):
    """``before_send`` ferme ce que les réglages ne couvrent pas.

    Chacun de ces trois cas a été trouvé en lisant un événement réel capté
    sur un banc, pas en relisant la documentation de Sentry."""

    def test_les_en_tetes_qui_portent_une_adresse_sont_retires(self):
        """``send_default_pii=False`` ne retire que l'adresse vue de la
        socket. Derrière Caddy et nginx, la vraie adresse du client est dans
        l'en-tête — et elle partait."""
        evenement = {
            "request": {
                "headers": {
                    "Host": "justi-innov.innovpharma.net",
                    "User-Agent": "Firefox",
                    "X-Forwarded-For": "41.82.13.7",
                    "X-Real-Ip": "41.82.13.7",
                    "X-Forwarded-Host": "justi-innov.innovpharma.net",
                    "Cookie": "sessionid=…",
                }
            }
        }

        rendu = surveillance._retirer_ce_qui_identifie(evenement, {})

        restants = set(rendu["request"]["headers"])
        self.assertEqual(restants, {"Host", "User-Agent"})
        self.assertNotIn("41.82.13.7", str(rendu))

    def test_le_compte_et_l_adresse_du_journal_sont_retires(self):
        """``core.journalisation`` attache le compte et l'adresse à chaque
        ligne ; Sentry recopie ces attributs dans ``extra``. Mesuré :
        ``extra.compte`` valait le nom du déposant."""
        evenement = {
            "extra": {
                "compte": "k.mensah",
                "ip": "41.82.13.7",
                "requete": "c0954021b17f",
                "asctime": "2026-09-20T16:31:31+0000",
            }
        }

        rendu = surveillance._retirer_ce_qui_identifie(evenement, {})

        self.assertNotIn("compte", rendu["extra"])
        self.assertNotIn("ip", rendu["extra"])
        # L'identifiant de requête reste : c'est celui que l'utilisateur cite
        # quand il signale un incident, et il n'identifie personne.
        self.assertEqual(rendu["extra"]["requete"], "c0954021b17f")

    def test_les_arguments_de_la_ligne_de_commande_sont_coupes(self):
        """``revoquer_sessions --compte <nom>`` mettrait un nom de compte
        dans ``sys.argv``, que Sentry joint de lui-même. On garde de quoi
        savoir quelle commande a échoué, rien de plus."""
        evenement = {
            "extra": {"sys.argv": ["manage.py", "revoquer_sessions", "--compte", "k.mensah"]}
        }

        rendu = surveillance._retirer_ce_qui_identifie(evenement, {})

        self.assertEqual(rendu["extra"]["sys.argv"], ["manage.py", "revoquer_sessions", "…"])
        self.assertNotIn("k.mensah", str(rendu))

    def test_un_evenement_sans_requete_ni_contexte_passe_sans_casser(self):
        """Une erreur de l'ordonnanceur n'a ni requête ni en-têtes. Un filtre
        qui lève empêcherait l'envoi de l'événement — donc de savoir."""
        self.assertEqual(surveillance._retirer_ce_qui_identifie({}, {}), {})
        self.assertIsNotNone(
            surveillance._retirer_ce_qui_identifie({"request": None, "extra": None}, {})
        )

    def test_le_filtre_est_bien_installe(self):
        """Sans cela, tout ce qui précède ne serait qu'un commentaire."""
        with mock.patch.dict("os.environ", {"SENTRY_DSN": ADRESSE}, clear=False):
            with mock.patch("sentry_sdk.init") as init:
                surveillance.configurer_la_surveillance()

        reglages = init.call_args.kwargs
        self.assertIs(reglages["before_send"], surveillance._retirer_ce_qui_identifie)
        # Les variables locales de chaque cadre de pile portaient le compte et
        # les données validées du sérialiseur : mesuré sur un banc.
        self.assertIs(reglages["include_local_variables"], False)


class CeQuiEstUtileTests(SimpleTestCase):
    def test_la_version_et_l_environnement_sont_transmis(self):
        """Sans eux, une trace ne dit pas quelle livraison l'a produite : on
        cherche dans un code qui a déjà changé."""
        with mock.patch.dict(
            "os.environ",
            {"SENTRY_DSN": ADRESSE, "SENTRY_ENVIRONMENT": "preproduction", "IMAGE_TAG": "v1.4.2"},
            clear=False,
        ):
            with mock.patch("sentry_sdk.init") as init:
                retenu = surveillance.configurer_la_surveillance()

        reglages = init.call_args.kwargs
        self.assertEqual(reglages["environment"], "preproduction")
        self.assertEqual(reglages["release"], "v1.4.2")
        self.assertTrue(retenu["actif"])

    def test_ce_qui_est_rendu_ne_contient_jamais_l_adresse(self):
        """Elle porte une clé : elle n'a sa place ni dans un journal, ni dans
        une page de diagnostic."""
        with mock.patch.dict("os.environ", {"SENTRY_DSN": ADRESSE}, clear=False):
            with mock.patch("sentry_sdk.init"):
                retenu = surveillance.configurer_la_surveillance()

        self.assertNotIn(ADRESSE, str(retenu))
        self.assertNotIn("cle-de-test", str(retenu))


class ChaineDeRequeteTests(SimpleTestCase):
    """La chaîne de requête porte ce que l'on cherche : elle ne part pas."""

    def test_la_chaine_de_requete_et_les_temoins_sont_retires(self):
        """``?search=…`` nomme un bénéficiaire ou un N°ORDRE, et Sentry la
        recopie dans l'URL de l'événement : seul le chemin reste."""
        evenement = {
            "request": {
                "url": "https://justi-innov.innovpharma.net/api/expenses/?search=Pharmacie%20Adjamé",
                "query_string": "search=Pharmacie%20Adjamé",
                "cookies": {"sessionid": "abc"},
                "method": "GET",
            }
        }

        rendu = surveillance._retirer_ce_qui_identifie(evenement, {})

        requete = rendu["request"]
        self.assertEqual(requete["url"], "https://justi-innov.innovpharma.net/api/expenses/")
        self.assertEqual(requete["query_string"], "")
        self.assertNotIn("cookies", requete)
        self.assertEqual(requete["method"], "GET")
        self.assertNotIn("Pharmacie", str(rendu))

    def test_une_requete_sans_chaine_reste_intacte(self):
        evenement = {"request": {"url": "https://justi-innov.innovpharma.net/api/me/"}}

        rendu = surveillance._retirer_ce_qui_identifie(evenement, {})

        self.assertEqual(rendu["request"]["url"], "https://justi-innov.innovpharma.net/api/me/")
