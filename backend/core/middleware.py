"""Middleware qui expose l'utilisateur courant pour l'historisation.

L'utilisateur authentifié est résolu de manière différée (callable) afin que,
au moment où un signal ``pre_save``/``post_save`` écrit l'historique, le
``request.user`` (forcé par Django REST Framework via le TokenAuthentication)
soit disponible.
"""

from .signals import set_current_user


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(
            lambda: getattr(request, "user", None),
        )
        try:
            response = self.get_response(request)
        finally:
            set_current_user(None)
        return response