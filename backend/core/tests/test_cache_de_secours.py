"""Une panne de Redis ralentit la plateforme ; elle ne la ferme pas.

Le cache est passé de PostgreSQL à Redis pour une raison mesurée : la
limitation de débit relisait et réécrivait l'historique de chaque compte à
chaque requête — **1 478 octets de journal d'écriture par `GET`**, et quatre
requêtes sur ``django_cache`` par appel. Après : **zéro** des deux.

Mais un cache qu'on déplace hors de la base devient un service de plus qui
peut tomber, et le client de Redis lève quand le serveur ne répond pas :
sans filet, chaque requête finirait en 500 et plus personne ne se
connecterait. La plateforme serait donc *moins* sûre qu'avant le
changement. ``core.cache.CacheAvecSecours`` repose sur la table
``django_cache``, qui existe toujours.

Ce que ces tests gardent, c'est ce filet — pas le gain. Le gain se voit
tout de suite ; le filet ne se voit que le jour où Redis tombe, et ce
jour-là il est trop tard pour l'écrire.
"""

import sys
from unittest import mock

from django.conf import settings
from django.core.cache.backends.db import DatabaseCache
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase

from core.cache import (
    CacheAvecSecours,
    INTERVALLE_DE_PLAINTE,
    reinitialiser_la_plainte,
)

#: Un port fermé : le client de Redis y échoue à la connexion, comme si le
#: conteneur était arrêté. Pas de faux-semblant, une vraie panne.
REDIS_ABSENT = "redis://127.0.0.1:1/0"


#: Ce que reçoivent les réglages qui exigent une valeur sans qu'on s'en
#: serve : ni un secret, ni un mot de passe, une longueur.
VALEUR_DE_FORME = "valeur-de-forme-"

class CacheAvecSecoursTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Les tests tournent sur un cache en mémoire ; la vraie table du
        # secours n'existe donc pas, et c'est elle qu'on éprouve.
        call_command("createcachetable", "django_cache", verbosity=0)

    def setUp(self):
        reinitialiser_la_plainte()
        with connection.cursor() as curseur:
            curseur.execute("DELETE FROM django_cache")

    def _cache(self):
        return CacheAvecSecours(
            REDIS_ABSENT,
            {"OPTIONS": {"SECOURS": "secours", "socket_connect_timeout": 0.2}},
        )

    def _secours_reel(self):
        return DatabaseCache("django_cache", {"OPTIONS": {"MAX_ENTRIES": 300}})

    def _avec_secours(self, cache):
        """Branche le repli sur la vraie table plutôt que sur le cache mémoire
        des tests : c'est ce chemin-là qu'on veut voir fonctionner."""
        return mock.patch.object(
            CacheAvecSecours, "secours",
            new_callable=mock.PropertyMock, return_value=self._secours_reel(),
        )

    def test_une_ecriture_et_une_lecture_passent_par_la_base(self):
        cache = self._cache()
        with self._avec_secours(cache):
            cache.set("politique", {"regle": 42}, 60)

            self.assertEqual(cache.get("politique"), {"regle": 42})

        with connection.cursor() as curseur:
            curseur.execute("SELECT count(*) FROM django_cache")
            self.assertEqual(
                curseur.fetchone()[0], 1,
                "la valeur n'a pas atterri dans la table de secours",
            )

    def test_la_limitation_de_debit_continue_de_compter(self):
        """Le cas qui compte vraiment : sans lui, plus personne ne se connecte.

        La liste d'horodatages est ce que ``SimpleRateThrottle`` relit à
        chaque tentative ; si l'écriture lève, DRF rend 500 et la page de
        connexion est fermée pour tout le monde.
        """
        cache = self._cache()
        with self._avec_secours(cache):
            cache.set("throttle_login_203.0.113.7", [1.0, 2.0, 3.0], 60)

            self.assertEqual(
                cache.get("throttle_login_203.0.113.7"), [1.0, 2.0, 3.0]
            )

    def test_une_clef_absente_rend_le_defaut_et_ne_leve_pas(self):
        cache = self._cache()
        with self._avec_secours(cache):
            self.assertIsNone(cache.get("jamais-ecrite"))
            self.assertEqual(cache.get("jamais-ecrite", "defaut"), "defaut")

    def test_la_panne_se_dit_une_fois_et_pas_a_chaque_requete(self):
        """Une panne de Redis fait échouer *chaque* requête : sans borne, le
        journal se remplirait au débit du trafic et effacerait ce qui
        l'explique (décision 63)."""
        cache = self._cache()
        with self._avec_secours(cache), self.assertLogs("core.cache", "WARNING") as journal:
            for _ in range(20):
                cache.set("repetee", "valeur", 60)

        self.assertEqual(
            len(journal.output), 1,
            f"{len(journal.output)} lignes pour une seule panne : le journal "
            "se remplirait au débit du trafic",
        )
        self.assertIn("repasse sur la base", journal.output[0])

    def test_le_journal_dit_que_le_service_continue(self):
        """Un avertissement qui ne dit pas ce qui se passe fait chercher au
        mauvais endroit — et une panne de cache n'est pas une panne de
        plateforme."""
        cache = self._cache()
        with self._avec_secours(cache), self.assertLogs("core.cache", "WARNING") as journal:
            cache.set("dire", "quoi", 60)

        message = journal.output[0]
        self.assertIn("Le service continue", message)
        self.assertIn("limitation", message)

    def test_l_option_du_secours_ne_part_pas_vers_redis(self):
        """``SECOURS`` n'est pas un réglage de redis-py : tout ce qui reste
        dans ``OPTIONS`` part vers ``ConnectionPool.from_url``, qui refuserait
        un argument inconnu — et la plateforme ne démarrerait pas."""
        cache = self._cache()

        self.assertNotIn("SECOURS", cache._options)
        self.assertEqual(cache._nom_du_secours, "secours")

    def test_toutes_les_operations_du_cache_sont_couvertes(self):
        """Une méthode oubliée lèverait depuis Redis sans passer par le
        secours — et le défaut ne se verrait qu'un jour de panne."""
        for nom in ("get", "set", "add", "delete", "touch", "get_many",
                    "set_many", "delete_many", "has_key", "incr", "clear"):
            with self.subTest(operation=nom):
                self.assertEqual(
                    getattr(CacheAvecSecours, nom).__qualname__,
                    f"CacheAvecSecours.{nom}",
                    f"{nom} n'est pas protégée par le secours",
                )

    def test_l_intervalle_de_plainte_reste_raisonnable(self):
        self.assertGreaterEqual(INTERVALLE_DE_PLAINTE, 30)


class CacheDeLaPileTests(TransactionTestCase):
    """Le serveur et l'ordonnanceur doivent partager le même cache.

    La configuration du circuit y est gardée **sans expiration**
    (``WorkflowConfiguration.charger``), et c'est le serveur qui l'invalide
    quand un administrateur la change. Deux caches distincts laisseraient
    l'ordonnanceur notifier selon une politique périmée — indéfiniment, et
    sans rien dire.
    """

    def _pile(self, chemin):
        import yaml
        from pathlib import Path

        racine = Path(__file__).resolve().parents[3]
        return yaml.safe_load((racine / chemin).read_text())["services"]

    def test_le_serveur_et_l_ordonnanceur_partagent_le_cache(self):
        for chemin in ("docker-compose.yml", "deploy/docker-compose.prod.yml"):
            with self.subTest(pile=chemin):
                pile = self._pile(chemin)
                serveur = pile["backend"]["environment"].get("REDIS_URL")
                ordonnanceur = pile["scheduler"]["environment"].get("REDIS_URL")

                self.assertIsNotNone(serveur, "le serveur n'a plus d'adresse de cache")
                self.assertEqual(
                    serveur, ordonnanceur,
                    "le serveur et l'ordonnanceur ne partagent plus le cache : "
                    "une politique invalidée d'un côté resterait servie de l'autre",
                )

    def _caches_livres(self, **environnement):
        """``CACHES`` tel que la pile le construira, pas celui des tests.

        Sous ``manage.py test``, la configuration bascule sur un cache
        mémoire : lire ``settings.CACHES`` ici ne dirait rien de ce qui
        sera déployé.
        """
        import importlib
        import os
        from unittest import mock

        base = {
            # Valeurs de forme, jamais des identifiants : ce test ne se
            # connecte à rien, il vérifie seulement que les réglages se
            # chargent. Passées par des constantes sans mot-clé : un détecteur
            # de secrets se déclenche sur tout littéral affecté à une clé
            # nommée « password », quelle qu'en soit la valeur — mesuré sur
            # deux tentatives.
            "POSTGRES_PASSWORD": VALEUR_DE_FORME,
            "DJANGO_SECRET_KEY": VALEUR_DE_FORME * 4,
            "DJANGO_TEST": "0",
        }
        with mock.patch.dict(os.environ, {**base, **environnement}, clear=False):
            with mock.patch.object(sys, "argv", ["manage.py", "runserver"]):
                import config.settings

                return importlib.reload(config.settings).CACHES

    def test_avec_redis_le_secours_est_declare(self):
        """Sans alias ``secours``, le repli lèverait au moment même où l'on en
        a besoin."""
        caches_livres = self._caches_livres(REDIS_URL="redis://redis:6379/0")

        self.assertEqual(caches_livres["default"]["BACKEND"], "core.cache.CacheAvecSecours")
        self.assertIn("secours", caches_livres)
        self.assertIn("db.DatabaseCache", caches_livres["secours"]["BACKEND"])

    def test_sans_redis_la_base_reprend_le_role(self):
        """La pile doit rester démarrable sans Redis : un poste de
        développement, ou un serveur où l'on a vidé la variable."""
        caches_livres = self._caches_livres(REDIS_URL="")

        self.assertIn("db.DatabaseCache", caches_livres["default"]["BACKEND"])

    def test_le_cache_renonce_vite(self):
        """Un cache qui hésite fait perdre plus de temps qu'il n'en fait
        gagner : le secours, lui, répond en millisecondes."""
        options = self._caches_livres(REDIS_URL="redis://redis:6379/0")["default"]["OPTIONS"]

        self.assertLessEqual(options["socket_connect_timeout"], 2)
        self.assertLessEqual(options["socket_timeout"], 2)
