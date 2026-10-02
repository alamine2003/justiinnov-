"""La requête HTTP en cours et l'adresse fiable de son client.

Deux choses que les journaux demandent à chaque écriture : *qui* signe
(``get_current_request``) et *depuis où* (``client_ip``). Elles vivent ici,
sous ``core.signals``, pour que la façade ``core.journal`` puisse les lire
sans dépendre des signaux qui, eux, dépendent d'elle.

Trois endroits lisaient l'adresse de trois façons : le premier élément de
``X-Forwarded-For`` (forgeable par le client, puisque nginx *ajoute* à
l'en-tête au lieu de le remplacer), ou ``REMOTE_ADDR`` (toujours l'adresse
du conteneur nginx en production). Le journal d'audit disait donc rarement
« depuis quelle adresse ». Une seule fonction, alignée sur ``NUM_PROXIES`` de
DRF : le nombre de sauts de confiance entre le client et Django.
"""

import ipaddress
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings

#: Requête HTTP en cours de traitement, posée par ``CurrentRequestMiddleware``.
#:
#: Une variable de contexte plutôt qu'un ``threading.local`` : elle suit la
#: tâche, pas le fil d'exécution. Avec des workers gunicorn en threads, ou
#: du code asynchrone, un ``threading.local`` mal remis à zéro ferait signer
#: les écritures d'une requête par l'utilisateur d'une autre.
_requete_courante = ContextVar("requete_courante", default=None)


def get_current_request():
    """Requête en cours, ou ``None`` hors requête (commande, tâche, test)."""
    return _requete_courante.get()


def set_current_request(request):
    """Pose la requête courante et rend le jeton qui permet de la retirer."""
    return _requete_courante.set(request)


def reset_current_request(token):
    _requete_courante.reset(token)


#: Motif de l'écriture en cours, quand la règle en exige un (décision 109) :
#: les signaux du référentiel écrivent l'historique sans voir la requête, la
#: vue le pose ici le temps de l'enregistrement.
_motif_courant = ContextVar("motif_courant", default="")


@contextmanager
def motif_du_journal(motif):
    """Le motif que portera chaque entrée d'historique écrite dans le bloc."""
    jeton = _motif_courant.set(motif or "")
    try:
        yield
    finally:
        _motif_courant.reset(jeton)


def motif_courant():
    return _motif_courant.get()


def _nombre_de_mandataires():
    return int(settings.REST_FRAMEWORK.get("NUM_PROXIES") or 0)


def _valide(adresse):
    try:
        return str(ipaddress.ip_address(adresse.strip()))
    except (ValueError, AttributeError):
        return None


def client_ip(request):
    """Adresse du client, ou ``None`` si elle n'est pas déterminable.

    Avec ``n`` mandataires de confiance, l'adresse réelle est le ``n``-ième
    élément en partant de la fin de ``X-Forwarded-For`` : tout ce qui précède
    a pu être écrit par le client lui-même. Sans mandataire déclaré, seule
    ``REMOTE_ADDR`` fait foi.
    """
    n = _nombre_de_mandataires()
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if n and forwarded:
        elements = [e for e in forwarded.split(",") if e.strip()]
        if len(elements) >= n:
            adresse = _valide(elements[-n])
            if adresse:
                return adresse
    return _valide(request.META.get("REMOTE_ADDR", "")) or None
