"""Compter les tentatives sans en perdre une seule.

``SimpleRateThrottle`` de DRF compte ainsi : il lit l'historique dans le
cache, y ajoute l'instant courant, réécrit le tout. Trois opérations, aucun
verrou. Deux requêtes simultanées lisent le même historique, chacune y
ajoute son horodatage, et la dernière écriture efface l'autre — une
tentative comptée pour deux.

Sans conséquence quand les requêtes se suivent ; la limite est alors
exacte. Sous concurrence, elle fuit. Mesuré pendant l'audit de résilience,
sur la limite qui protège l'obtention du jeton — cinq essais par minute et
par compte :

====================================  ===================
tentatives                            essais non bloqués
====================================  ===================
douze, une par une                    5 — exact
quarante simultanées, 4 fils          7
quarante simultanées, 8 fils          11
quarante simultanées, 16 fils         13
====================================  ===================

La fuite suit le nombre de requêtes que le serveur mène de front : plus on
lui donne de fils, plus la limite s'affaiblit. Quelqu'un qui relève
``GUNICORN_THREADS`` affaiblit donc la protection contre le bourrage
d'identifiants sans le savoir.

Ce module rétablit l'exactitude là où elle protège quelque chose : la
connexion et la vérification du mot de passe. **Pas la limite générale**
(``user``, 2000/heure) : elle ne défend rien, elle borne un client
emballé, et la sérialiser ferait attendre chaque requête d'un même compte
derrière la précédente — un coût réel pour aucun gain.
"""

from django.db import connection, transaction


class ComptageSansPerte:
    """Sérialise le lire-modifier-écrire du compteur, par clé.

    Le verrou est un verrou consultatif Postgres, pris sur le nom de la
    clé et relâché à la fin de la transaction — donc toujours, y compris si
    la vue lève. Il ne porte que sur les requêtes qui partagent la même
    clé : la même adresse, ou le même nom de compte. Deux personnes qui se
    connectent en même temps ne s'attendent jamais ; un attaquant ne
    sérialise que lui-même.

    ``hashtext`` peut donner le même entier à deux clés distinctes. La
    conséquence serait que deux compteurs s'attendent l'un l'autre
    quelques millisecondes — jamais qu'un comptage soit faux.

    À placer **avant** la classe de DRF dans les bases : c'est
    ``allow_request`` qu'on entoure.
    """

    def allow_request(self, request, view):
        cle = self.get_cache_key(request, view)
        if cle is None or self.rate is None:
            # Pas de clé : DRF laisse passer, et il n'y a rien à compter.
            return super().allow_request(request, view)

        with transaction.atomic():
            with connection.cursor() as curseur:
                curseur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [cle])
            return super().allow_request(request, view)
