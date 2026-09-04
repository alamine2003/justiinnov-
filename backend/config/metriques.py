"""Point de collecte Prometheus, protégé par un jeton.

``django_prometheus`` expose ses compteurs sans authentification : le nombre
de requêtes par vue, les temps de réponse et les requêtes SQL décrivent
l'activité de la plateforme, ce qui ne regarde que la supervision. Le
collecteur Prometheus présente ``METRICS_TOKEN`` dans l'en-tête
``Authorization`` ; sans jeton configuré, le point n'existe pas.
"""

import hmac

from django.conf import settings
from django.http import HttpResponse
from django_prometheus.exports import ExportToDjangoView


def metriques(request):
    attendu = settings.METRICS_TOKEN
    if not attendu:
        return HttpResponse(status=404)
    fourni = request.META.get("HTTP_AUTHORIZATION", "")
    if not fourni.startswith("Bearer ") or not hmac.compare_digest(
        fourni[len("Bearer "):], attendu
    ):
        return HttpResponse(status=401)
    return ExportToDjangoView(request)
