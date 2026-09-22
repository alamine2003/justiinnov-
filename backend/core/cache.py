"""Cache principal : Redis, et la base de données en secours.

Le cache vivait dans PostgreSQL (`DatabaseCache`). Cela tenait, mais
l'audit de résilience en a mesuré le prix, et il est payé par **chaque
lecture** :

- la limitation de débit relit et réécrit l'historique du compte à chaque
  requête — **1,5 ko de journal d'écriture par `GET`**, 4,2 ko quand
  l'historique atteint mille entrées ;
- `DatabaseCache` compte toute la table (`SELECT COUNT(*)`) avant chaque
  écriture ;
- la table pesait **1 576 ko pour 57 ko de contenu utile** ;
- et sa purge supprime **par ordre alphabétique de clé**, si bien que
  quatre cents comptes actifs effaçaient les compteurs anti-bourrage
  (décision 69). Redis, lui, évince les clés les moins récemment utilisées :
  un compteur qu'on vient de toucher est le dernier à partir.

**Pourquoi un secours.** Ajouter Redis sans lui ferait de ce cache un
point de défaillance unique de plus — et un mauvais : le client de Redis
lève quand le serveur ne répond pas, chaque requête finirait en 500, et
plus personne ne se connecterait. La plateforme serait donc *moins* sûre
qu'avant. Le secours rend cette panne invisible : on retombe sur la table
`django_cache`, qui existe toujours, et le service continue — plus lent,
entier.

Ce que le secours ne rattrape pas, et c'est voulu : les compteurs de
limitation de débit tenus par Redis ne sont pas recopiés dans la base. Une
panne de Redis les remet donc à zéro, ce qui rouvre le quota de quelques
personnes. C'est le bon compromis : perdre un quota vaut mieux que fermer
la plateforme, et le verrou qui rend le comptage exact (décision 68) vit
dans PostgreSQL — il continue de protéger, où que soit le compteur.
"""

import logging
import time

from django.core.cache import caches
from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)

#: Opérations du cache que l'on protège. La liste est explicite : oublier
#: une méthode la laisserait lever depuis Redis sans passer par le secours,
#: et le défaut ne se verrait qu'un jour de panne.
OPERATIONS = (
    "add", "get", "set", "touch", "delete", "get_many", "get_or_set",
    "has_key", "incr", "decr", "set_many", "delete_many", "clear",
)

#: Une panne de Redis fait échouer *chaque* requête : sans borne, le journal
#: se remplirait au débit du trafic et effacerait ce qui l'explique
#: (décision 63). Une ligne par minute suffit à dire qu'il est tombé.
INTERVALLE_DE_PLAINTE = 60
_derniere_plainte = 0.0


def reinitialiser_la_plainte():
    """Remet le compteur de journal à zéro — pour les tests."""
    global _derniere_plainte
    _derniere_plainte = 0.0


def _se_plaindre(operation, panne):
    global _derniere_plainte
    maintenant = time.monotonic()
    if maintenant - _derniere_plainte < INTERVALLE_DE_PLAINTE:
        return
    _derniere_plainte = maintenant
    logger.warning(
        "Redis injoignable (%s) : le cache repasse sur la base de données. "
        "Le service continue, plus lentement ; les compteurs de limitation "
        "de débit repartent de zéro. %s: %s",
        operation, type(panne).__name__, panne,
    )


class CacheAvecSecours(RedisCache):
    """Redis d'abord ; la base de données dès qu'il ne répond plus.

    ``OPTIONS["SECOURS"]`` nomme le cache de repli (``secours`` par
    défaut), déclaré dans ``CACHES`` comme n'importe quel autre.
    """

    def __init__(self, server, params):
        # Tout ce qui reste dans ``OPTIONS`` part vers ``ConnectionPool.from_url``
        # de redis-py : ``SECOURS`` n'y a pas sa place et le ferait échouer.
        # On copie plutôt que de retirer la clé du réglage lui-même, partagé
        # avec le reste du processus.
        options = dict(params.get("OPTIONS", {}))
        self._nom_du_secours = options.pop("SECOURS", "secours")
        super().__init__(server, params)
        self._options = options

    @property
    def secours(self):
        return caches[self._nom_du_secours]


def _protegee(nom):
    """Enveloppe une opération du cache : Redis, puis la base s'il tombe.

    On n'attrape que les pannes du transport (`redis.exceptions.RedisError`
    et les erreurs de connexion du système). Une erreur de programmation —
    une valeur non sérialisable, par exemple — doit remonter : la masquer
    en la rejouant sur la base cacherait un défaut au lieu d'une panne.
    """

    def operation(self, *args, **kwargs):
        try:
            return getattr(RedisCache, nom)(self, *args, **kwargs)
        except Exception as panne:  # noqa: BLE001 — on trie juste après
            import redis.exceptions

            if not isinstance(
                panne, (redis.exceptions.RedisError, OSError)
            ):
                raise
            _se_plaindre(nom, panne)
            return getattr(self.secours, nom)(*args, **kwargs)

    operation.__name__ = nom
    operation.__qualname__ = f"CacheAvecSecours.{nom}"
    operation.__doc__ = getattr(RedisCache, nom).__doc__
    return operation


for _nom in OPERATIONS:
    setattr(CacheAvecSecours, _nom, _protegee(_nom))
