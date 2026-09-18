"""La forme des erreurs : l'API répond en JSON, y compris quand tout casse.

Deux constats de l'audit de résilience.

**Une erreur non prévue rendait une page HTML.** Django appelle son
``handler500``, qui produit ``<!doctype html><title>Server Error (500)</title>``.
Un client qui fait ``response.json()`` casse alors *en plus* de l'erreur
initiale, et l'interface affiche « erreur inattendue » au lieu du message.

**Une base injoignable rendait 500.** C'est-à-dire « l'application a un
défaut », quand il faut dire « le service est momentanément indisponible,
réessayez ». La nuance n'est pas cosmétique : un 500 se signale à un
développeur, un 503 avec ``Retry-After`` se retente tout seul.

Les deux se règlent ici :

- :func:`gestionnaire_d_exception` est branché sur DRF
  (``REST_FRAMEWORK["EXCEPTION_HANDLER"]``). Il s'exécute autour de *tout*
  le traitement d'une vue — authentification, droits, limitation de débit,
  corps de la vue —, donc y compris quand c'est le limiteur qui échoue
  parce que son cache vit dans PostgreSQL ;
- :func:`erreur_400` à :func:`erreur_500` remplacent les pages de Django
  pour ce qui lui échappe : une URL inconnue, un hôte refusé, une
  exception levée hors d'une vue DRF.

Hors ``/api/``, rien ne change : l'admin Django, monté en développement
seulement, garde ses pages HTML.
"""

import logging
import os
import threading
import time

from django.db import InterfaceError, OperationalError
from django.http import JsonResponse
from django.utils.translation import gettext_lazy
from django.views import defaults
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as gestionnaire_drf

logger = logging.getLogger(__name__)

#: Pannes d'infrastructure de la base : connexion perdue, serveur absent,
#: interblocage. Le demandeur n'y est pour rien et peut réessayer.
PANNES_DE_BASE = (OperationalError, InterfaceError)

#: Secondes suggérées au client avant de réessayer. Assez pour laisser un
#: redémarrage de PostgreSQL aboutir — mesuré sous la seconde sur le banc —
#: sans qu'une interface reste figée.
DELAI_DE_REESSAI = 15

INDISPONIBLE = gettext_lazy(
    "Service momentanément indisponible. Réessayez dans quelques instants."
)
MESSAGES = {
    400: gettext_lazy("Requête incorrecte."),
    403: gettext_lazy("Accès refusé."),
    404: gettext_lazy("Ressource introuvable."),
    500: gettext_lazy("Erreur interne du serveur."),
}


#: Une base coupée fait échouer *toutes* les requêtes, et les échecs sont
#: rapides : le débit monte au lieu de descendre. Mesuré sur le banc — 441
#: erreurs par seconde, 7,8 ko de trace chacune, soit 3,5 Mo par seconde.
#: Docker retient 100 Mo par service (``max-size`` × ``max-file``) : **une
#: demi-minute de panne effaçait tout l'historique**, y compris les lignes
#: qui diraient ce qui s'est passé avant elle. La trace complète ne se répète
#: donc qu'à cet intervalle ; entre deux, une ligne compacte au plus par
#: seconde dit combien d'appels ont échoué. Le volume passe de 3,5 Mo/s à
#: moins d'un kilo-octet.
INTERVALLE_DE_TRACE = int(os.environ.get("DJANGO_LOG_PANNE_TRACE", "60"))
INTERVALLE_DE_RESUME = float(os.environ.get("DJANGO_LOG_PANNE_RESUME", "1"))

_verrou = threading.Lock()
_derniere_trace = 0.0
_dernier_resume = 0.0
_depuis_la_trace = 0


def _journaliser(exc, ou):
    """Une seule formulation pour cette panne, où qu'elle soit attrapée.

    Journalisée ici parce que la réponse n'est plus une erreur 500 : elle ne
    passera donc pas par ``django.request``, et la trace manquerait.

    Le débit est borné (voir ci-dessus). Rien n'est perdu de ce qui compte :
    la trace est identique à chaque fois — c'est toujours « connexion
    impossible » —, et le nombre d'appels échoués est dit.
    """
    global _derniere_trace, _dernier_resume, _depuis_la_trace

    maintenant = time.monotonic()
    with _verrou:
        _depuis_la_trace += 1
        if maintenant - _derniere_trace >= INTERVALLE_DE_TRACE:
            _derniere_trace = _dernier_resume = maintenant
            etouffees, _depuis_la_trace = _depuis_la_trace - 1, 0
            quoi = "trace"
        elif maintenant - _dernier_resume >= INTERVALLE_DE_RESUME:
            _dernier_resume = maintenant
            etouffees, quoi = _depuis_la_trace, "resume"
        else:
            return

    if quoi == "trace":
        suite = f" — et {etouffees} autres depuis la trace précédente" if etouffees else ""
        logger.error(
            "Base de données injoignable (%s) : %s%s", ou, exc, suite, exc_info=exc
        )
    else:
        logger.error(
            "Base de données injoignable (%s) : %s — %d appels échoués, "
            "trace au plus une fois toutes les %ss",
            ou, exc, etouffees, INTERVALLE_DE_TRACE,
        )


def reinitialiser_le_debit_de_journal():
    """Remet les compteurs à zéro. Réservé aux tests."""
    global _derniere_trace, _dernier_resume, _depuis_la_trace
    with _verrou:
        _derniere_trace = _dernier_resume = 0.0
        _depuis_la_trace = 0


def reponse_indisponible(exc=None, ou="hors vue"):
    """Le 503 en JSON, pour ce qui s'exécute hors du champ de DRF.

    Un middleware ``process_view`` en est le cas type : Django transforme son
    exception en réponse avant qu'aucun middleware supérieur ne puisse la
    voir, et DRF n'est pas encore entré en scène.
    """
    if exc is not None:
        _journaliser(exc, ou)
    reponse = JsonResponse({"detail": str(INDISPONIBLE)}, status=503)
    reponse["Retry-After"] = str(DELAI_DE_REESSAI)
    return reponse


def gestionnaire_d_exception(exc, context):
    """Traduit une panne d'infrastructure en 503 ; délègue le reste à DRF.

    Rendre ``None`` laisse DRF relancer l'exception : elle remonte alors à
    Django, qui la journalise avec sa trace (``django.request``) avant
    d'appeler :func:`erreur_500`. On ne masque donc jamais un défaut.
    """
    if isinstance(exc, PANNES_DE_BASE):
        _journaliser(exc, "vue")
        reponse = Response(
            {"detail": str(INDISPONIBLE)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        reponse["Retry-After"] = str(DELAI_DE_REESSAI)
        return reponse
    return gestionnaire_drf(exc, context)


def _veut_du_json(request):
    """Vrai pour l'API, et pour qui demande explicitement du JSON."""
    try:
        if request.path.startswith("/api/"):
            return True
        return "application/json" in request.headers.get("Accept", "")
    except Exception:  # noqa: BLE001 — une page d'erreur ne tombe jamais
        return False


def _rendre(request, code, defaut, *args):
    if not _veut_du_json(request):
        return defaut(request, *args)
    return JsonResponse({"detail": str(MESSAGES[code])}, status=code)


def erreur_400(request, exception=None):
    return _rendre(request, 400, defaults.bad_request, exception)


def erreur_403(request, exception=None):
    return _rendre(request, 403, defaults.permission_denied, exception)


def erreur_404(request, exception=None):
    return _rendre(request, 404, defaults.page_not_found, exception)


def erreur_500(request):
    return _rendre(request, 500, defaults.server_error)
