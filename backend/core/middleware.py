"""Middleware qui expose la requête courante à l'historisation.

Les signaux d'historisation (``core.signals``) n'ont pas accès à la requête :
ce middleware la pose dans une variable de contexte (``core.requetes``), d'où
la façade ``core.journal`` lit l'auteur et son adresse. L'utilisateur n'est pas résolu ici mais au
moment de l'écriture : pour une requête par jeton, ``request.user`` n'est
forcé par DRF qu'à l'entrée de la vue, bien après ce middleware.
"""

from .requetes import reset_current_request, set_current_request


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        jeton = set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            reset_current_request(jeton)
