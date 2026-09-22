"""La purge du cache ne doit pas emporter la protection anti-bourrage.

Trouvé par l'audit de résilience. ``DatabaseCache`` purge sa table dès
qu'elle dépasse ``MAX_ENTRIES`` — **300 par défaut**, un plafond que
personne n'avait choisi — et elle supprime **par ordre alphabétique de
clé**, jamais par ancienneté (``_cull`` et ``cache_key_culling_sql`` de
Django). Or les compteurs de la limite de connexion s'appellent
``throttle_login_<adresse>`` : ils se classent parmi les plus bas, donc
partent les premiers.

Mesuré : à 250 comptes actifs dans l'heure le compteur survit, à **400 il
est effacé** — chaque compte actif laissant une clé pendant une heure,
il suffit que la plateforme grandisse. Aucun attaquant n'est nécessaire, et
ce qui disparaît est précisément ce qui protège contre le bourrage
d'identifiants.

Ce test monte la **vraie** table du cache : les tests tournent d'ordinaire
sur un cache en mémoire, dont la purge est écrite autrement (tirage au
hasard). Un test sur celui-là n'aurait rien dit du défaut.
"""

import time

from django.conf import settings
from django.core.cache.backends.db import DatabaseCache
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase

#: Clé de la limite par adresse, telle que DRF la forme.
COMPTEUR = "throttle_login_203.0.113.7"

#: Comptes actifs simulés. Au-delà du défaut de Django (300), en deçà de ce
#: que la configuration déclare : c'est exactement la zone où le défaut
#: effaçait le compteur.
COMPTES_ACTIFS = 400


class PurgeDuCacheTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Le nom explicite est nécessaire : sans lui, la commande lit
        # ``settings.CACHES``, qui pointe en test sur un cache en mémoire,
        # et ne crée aucune table.
        call_command("createcachetable", "django_cache", verbosity=0)

    def setUp(self):
        with connection.cursor() as curseur:
            curseur.execute("DELETE FROM django_cache")

    def _cache_reel(self):
        """La table, avec les options de la configuration livrée."""
        return DatabaseCache(
            "django_cache", {"OPTIONS": {"MAX_ENTRIES": settings.CACHE_MAX_ENTRIES}}
        )

    def test_la_croissance_de_la_plateforme_n_efface_pas_le_compteur(self):
        cache = self._cache_reel()
        cache.set(COMPTEUR, [time.time()] * 10, 60)

        # Usage ordinaire : un compte qui se sert de l'application laisse une
        # clé ``throttle_user_<pk>`` pendant une heure.
        for numero in range(COMPTES_ACTIFS):
            cache.set(f"throttle_user_{numero}", [time.time()], 3600)

        self.assertIsNotNone(
            cache.get(COMPTEUR),
            f"{COMPTES_ACTIFS} comptes actifs ont effacé le compteur "
            "anti-bourrage : la purge supprime les clés les plus basses, et "
            "celles de la limite de connexion en font partie",
        )

    def test_le_plafond_d_entrees_est_une_decision(self):
        """Le défaut de Django ne laisse pas la place à la plateforme."""
        self.assertGreater(
            settings.CACHE_MAX_ENTRIES,
            COMPTES_ACTIFS,
            "le cache purge avant d'avoir la place des comptes actifs",
        )
