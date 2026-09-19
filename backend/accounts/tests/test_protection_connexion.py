"""La limite anti-bourrage ne se contourne pas avec un jeton, et le TOTP
mal formé ne provoque pas de 500.

Audit du 8 septembre 2026, §3.5 et §6 (TOTP non-ASCII).

**Les mots de passe écrits ici sont faux, et c'est le sujet du test.** Les
comptes de test reçoivent leur mot de passe de ``make_user``
(``accounts/tests/test_scoping.py``) ; « faux-mot-de-passe » et « faux »
n'ouvrent donc rien, nulle part, et sont là pour provoquer les 400 puis le
429 qu'on veut voir. « jeton-inexistant » n'est le jeton d'aucun compte.
Un détecteur de secrets qui signale ces littéraux voit un mot de passe en
dur — il a raison sur la forme, et il n'y a pourtant aucun identifiant à
révoquer : la qualification se règle dans le tableau de bord du détecteur,
pas en réécrivant le test.
"""

import threading
import time
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from accounts import totp
from accounts.models import Role
from accounts.tests.test_scoping import make_user

# Limites resserrées : deux tentatives par adresse et par compte suffisent à
# prouver le comptage sans lancer des dizaines de requêtes.
#
# **Pas par ``override_settings(REST_FRAMEWORK=…)``.** DRF lie les cadences
# à l'import — ``SimpleRateThrottle.THROTTLE_RATES =
# api_settings.DEFAULT_THROTTLE_RATES``, un attribut de classe (throttling.py,
# 3.17.2) — et ``get_rate()`` lit cet attribut, jamais les réglages courants.
# Surcharger ``REST_FRAMEWORK`` recharge ``api_settings`` mais ne rebranche
# pas l'attribut : les quatre tests de ce fichier tournaient avec les
# cadences réelles (10/min, 5/min) et la troisième tentative n'était jamais
# refusée — « 400 != 429 », première exécution, CI #25. On remplace donc
# l'attribut lui-même, sur la classe de base dont héritent les deux limites.
def cadences(**taux):
    return mock.patch.object(
        SimpleRateThrottle, "THROTTLE_RATES",
        {"user": "2000/hour", "password": "10/min", "health": "60/min", **taux},
    )


@cadences(login="2/min", login_user="50/min")
class LimiteDeConnexionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_user("manager.togo", Role.MANAGER)
        cls.cible = make_user("dg.innov", Role.SUPER_ADMIN)

    def setUp(self):
        cache.clear()

    def _tenter(self, username, jeton=None):
        if jeton is not None:
            self.client.credentials(HTTP_AUTHORIZATION=f"Token {jeton}")
        else:
            self.client.credentials()
        return self.client.post(
            "/api/token-auth/", {"username": username, "password": "faux-mot-de-passe"}
        )

    def test_la_limite_par_adresse_finit_par_repondre_429(self):
        self.assertEqual(self._tenter("dg.innov").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._tenter("dg.innov").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._tenter("dg.innov").status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_un_jeton_valide_ne_leve_pas_la_limite(self):
        """Le contournement de l'audit : se connecter avec son compte, puis
        pulvériser un mot de passe sur d'autres comptes en présentant son
        jeton. La limite par adresse doit tenir quand même."""
        jeton = Token.objects.create(user=self.manager).key

        # Deux tentatives sur deux comptes différents épuisent la limite
        # *par adresse* (login 2/min) : la troisième est refusée, quel que
        # soit le compte visé — le jeton n'y change rien.
        self.assertEqual(self._tenter("dg.innov", jeton).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._tenter("dg.innov", jeton).status_code, status.HTTP_400_BAD_REQUEST)
        troisieme = self._tenter("rh.innov", jeton)
        self.assertEqual(troisieme.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_un_jeton_invalide_ne_change_rien(self):
        self._tenter("dg.innov", "jeton-inexistant")
        self._tenter("dg.innov", "jeton-inexistant")
        self.assertEqual(
            self._tenter("dg.innov", "jeton-inexistant").status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )


@cadences(login="50/min", login_user="2/min")
class LimiteParCompteTests(APITestCase):
    """``login_user`` (par nom de compte) protège un compte visé depuis
    plusieurs adresses : la limite par nom est serrée, l'adresse varie."""

    @classmethod
    def setUpTestData(cls):
        cls.cible = make_user("dg.innov", Role.SUPER_ADMIN)

    def setUp(self):
        cache.clear()

    def test_un_compte_vise_est_protege_toutes_adresses_confondues(self):
        adresses = iter(["10.0.0.1", "10.0.0.2", "10.0.0.3"])

        def adresse_variable(request):
            return next(adresses, "10.0.0.9")

        with mock.patch("accounts.views.client_ip", side_effect=adresse_variable):
            self.assertEqual(self._tenter().status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(self._tenter().status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(self._tenter().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def _tenter(self):
        self.client.credentials()
        return self.client.post(
            "/api/token-auth/", {"username": "dg.innov", "password": "faux"}
        )


class CodeTotpMalFormeTests(APITestCase):
    """``.isdigit()`` accepte des chiffres non-ASCII que ``compare_digest``
    refuse par une exception : un code arabo-indien renvoyait un 500."""

    SECRET = totp.generer_secret()

    def test_un_code_non_ascii_ne_leve_pas(self):
        # Chiffres arabo-indiens : isdigit() est vrai, ce ne sont pas des ASCII.
        self.assertIsNone(totp.compteur_du_code(self.SECRET, "١٢٣٤٥٦"))
        # Exposants : isdigit() est vrai aussi.
        self.assertIsNone(totp.compteur_du_code(self.SECRET, "¹²³⁴⁵⁶"))

    def test_un_code_ascii_valide_donne_un_compteur(self):
        import pyotp

        code = pyotp.TOTP(self.SECRET).now()
        self.assertIsNotNone(totp.compteur_du_code(self.SECRET, code))


@cadences(login="50/min", login_user="2/min")
class CourseSurLaLimiteTests(TransactionTestCase):
    """Deux tentatives simultanées ne doivent pas en valoir une.

    Trouvé par l'audit de résilience. ``SimpleRateThrottle`` lit
    l'historique, y ajoute l'instant courant, réécrit le tout — sans
    verrou. Deux requêtes lancées ensemble lisent le même historique et la
    dernière écriture efface l'autre : une tentative comptée pour deux.
    Mesuré sur le banc, limite de cinq par compte : cinq essais passaient
    en séquentiel, **treize** lancés ensemble sur seize fils. La fuite suit
    le parallélisme du serveur — relever ``GUNICORN_THREADS`` affaiblissait
    la protection contre le bourrage d'identifiants.

    **La course est forcée, pas espérée.** Attendre que les fils
    s'entrelacent d'eux-mêmes donnerait un test qui passe parfois sur du
    code fautif — le pire des tests. On allonge donc la fenêtre entre la
    lecture et l'écriture du compteur : sans le correctif, les fils la
    traversent tous ensemble ; avec lui, le verrou consultatif les fait
    passer l'un après l'autre.
    """

    #: Assez long pour que tous les fils soient dans la fenêtre, assez
    #: court pour que le test reste court même sérialisé.
    FENETRE = 0.15
    FILS = 6

    def setUp(self):
        cache.clear()
        make_user("dg.innov", Role.SUPER_ADMIN)

    @staticmethod
    def _ecriture_retardee(original, delai):
        """``throttle_success`` écrit le compteur : on retarde son écriture,
        pas sa lecture — c'est l'intervalle entre les deux qui est le
        défaut."""

        def remplacant(self):
            time.sleep(delai)
            return original(self)

        return remplacant

    def test_des_tentatives_simultanees_ne_depassent_pas_la_limite(self):
        codes, verrou = [], threading.Lock()
        depart = threading.Barrier(self.FILS)

        def tenter():
            try:
                depart.wait()
                reponse = APIClient().post(
                    "/api/token-auth/",
                    {"username": "dg.innov", "password": "faux-mot-de-passe"},
                )
                with verrou:
                    codes.append(reponse.status_code)
            finally:
                connection.close()

        retardee = self._ecriture_retardee(
            SimpleRateThrottle.throttle_success, self.FENETRE
        )
        with mock.patch.object(SimpleRateThrottle, "throttle_success", retardee):
            fils = [threading.Thread(target=tenter) for _ in range(self.FILS)]
            for fil in fils:
                fil.start()
            for fil in fils:
                fil.join(timeout=30)

        self.assertEqual(len(codes), self.FILS, "un fil n'a pas abouti")
        passees = [code for code in codes if code != status.HTTP_429_TOO_MANY_REQUESTS]
        self.assertEqual(
            len(passees), 2,
            f"la limite annonce 2 essais par compte, {len(passees)} sont passés : "
            "le compteur perd des tentatives sous concurrence",
        )
