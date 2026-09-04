"""Lecture fiable de l'adresse du client derrière les mandataires.

Trois endroits lisaient l'adresse de trois façons : le premier élément de
``X-Forwarded-For`` (forgeable par le client, puisque nginx *ajoute* à
l'en-tête au lieu de le remplacer), ou ``REMOTE_ADDR`` (toujours l'adresse
du conteneur nginx en production). Le journal d'audit disait donc rarement
« depuis quelle adresse ». Une seule fonction, alignée sur ``NUM_PROXIES`` de
DRF : le nombre de sauts de confiance entre le client et Django.
"""

import ipaddress

from django.conf import settings


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
