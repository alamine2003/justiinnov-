"""Ce qu'il faut savoir d'une requête quand elle échoue.

Un audit de résilience a mesuré le trou : en production (``DEBUG=0``), une
erreur 500 ne laissait **aucune trace**. Django s'appuyait sur sa
configuration par défaut, où le gestionnaire console porte le filtre
``RequireDebugTrue`` et celui par courriel n'avait aucun destinataire
(``ADMINS = []``). Six mille erreurs produites pendant une coupure de la
base n'ont pas écrit une ligne : restait le code d'état dans le journal
d'accès de gunicorn, et rien pour dire *pourquoi*.

Ce module apporte le contexte que ``config.settings`` injecte dans chaque
ligne : l'identifiant de la requête, le compte, l'adresse. L'identifiant
part aussi en en-tête de réponse (``X-Requete-Id``), pour qu'un utilisateur
qui signale un incident puisse le citer et qu'on retrouve sa trace.

**Rien ici ne doit lever d'exception ni toucher la base.** Un filtre de
journalisation qui échoue casse la journalisation elle-même, et il s'exécute
précisément quand tout va mal — la base coupée, par exemple. D'où les
``try`` larges, et la lecture du compte *déjà résolu* seulement : forcer
``request.user`` déclencherait une requête SQL au pire moment.
"""

import logging
import re
import uuid
from contextvars import ContextVar

from django.utils.functional import empty

from .requetes import client_ip, get_current_request

#: Identifiant de la requête en cours. Comme la requête elle-même, une
#: variable de contexte : elle suit la tâche, pas le fil d'exécution.
_identifiant = ContextVar("identifiant_de_requete", default=None)

#: Un identifiant venu de l'extérieur n'entre que s'il est inoffensif : ni
#: espace, ni saut de ligne, rien qui puisse forger une seconde ligne de
#: journal. Tout le reste est remplacé par un identifiant à nous.
MOTIF_ACCEPTABLE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")

#: En-tête lu à l'entrée (nginx sait poser son ``$request_id``) et rendu en
#: sortie.
ENTETE = "X-Requete-Id"
CLE_META = "HTTP_X_REQUETE_ID"

ABSENT = "-"


def nouvel_identifiant():
    """Douze caractères : assez pour être unique, assez court pour être dicté."""
    return uuid.uuid4().hex[:12]


def poser_identifiant(request):
    """Reprend celui du mandataire s'il est acceptable, en crée un sinon."""
    recu = request.META.get(CLE_META, "")
    identifiant = recu if MOTIF_ACCEPTABLE.match(recu or "") else nouvel_identifiant()
    return identifiant, _identifiant.set(identifiant)


def retirer_identifiant(jeton):
    _identifiant.reset(jeton)


def lire_identifiant():
    return _identifiant.get()


def _deja_resolu(compte):
    """Vrai si lire ce compte ne déclenchera aucune requête.

    ``AuthenticationMiddleware`` pose un objet paresseux ; DRF, lui, écrit le
    compte authentifié par jeton directement sur la requête. Le second est
    lisible sans risque, le premier seulement une fois résolu.
    """
    if compte is None:
        return False
    try:
        enveloppe = object.__getattribute__(compte, "_wrapped")
    except AttributeError:
        return True  # un vrai objet, pas une enveloppe paresseuse
    return enveloppe is not empty


def _compte(request):
    """Le nom du compte, sans jamais le résoudre.

    ``request.user`` est un objet paresseux : le lire déclencherait une
    requête en base. Ici on ne lit que ce qui est déjà connu — sinon
    journaliser une panne de base provoquerait une panne de base. Une erreur
    survenue avant l'entrée de la vue dit donc « anonyme » : c'est exact, le
    jeton n'a pas encore été vérifié à ce moment-là.
    """
    for porteur in (request, getattr(request, "_request", None)):
        if porteur is None:
            continue
        for candidat in (porteur.__dict__.get("user"),
                         getattr(porteur, "_cached_user", None)):
            if _deja_resolu(candidat):
                return getattr(candidat, "username", "") or "anonyme"
    return ABSENT


class FiltreContexte(logging.Filter):
    """Ajoute ``requete``, ``compte`` et ``ip`` à chaque ligne de journal.

    Un filtre plutôt qu'un formateur : les champs restent disponibles quel
    que soit le format, et une ligne émise hors requête (ordonnanceur,
    commande de gestion) porte simplement des tirets.
    """

    def filter(self, record):
        record.requete = lire_identifiant() or ABSENT
        record.compte = ABSENT
        record.ip = ABSENT
        try:
            request = get_current_request()
            if request is not None:
                record.compte = _compte(request)
                record.ip = client_ip(request) or ABSENT
        except Exception:  # noqa: BLE001 — un journal ne tombe jamais
            pass
        return True
