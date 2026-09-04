"""Verrous transverses, appliqués avant que la moindre vue ne s'exécute."""

from django.http import JsonResponse
from rest_framework.exceptions import AuthenticationFailed

from .authentication import ATTRIBUT_MEMO, JetonAuthentication

#: Vues joignables sans profil et malgré un mot de passe provisoire.
#:
#: L'obtention du jeton et la déconnexion, sans quoi on ne pourrait ni entrer
#: ni sortir ; et l'état de la plateforme, qui ne dépend pas du compte qui le
#: demande.
TOUJOURS_OUVERTES = frozenset({"token-auth", "health", "logout"})

#: Vues joignables malgré un mot de passe provisoire, par leur nom d'URL.
#:
#: Le profil courant, sans quoi l'interface ne saurait pas quoi afficher, et le
#: changement de mot de passe, sans quoi le blocage n'aurait pas de sortie.
EXEMPT_URL_NAMES = TOUJOURS_OUVERTES | {"me", "change-password"}


class ProvisionalPasswordMiddleware:
    """Ferme la plateforme aux comptes sans profil ou au mot de passe provisoire.

    Le mot de passe distribué à la création a circulé — par message, par
    téléphone, sur un papier. Tant qu'il n'a pas été remplacé, le compte n'est
    pas réellement personnel : ce qu'il signe ne prouve rien, et l'imputabilité
    de chaque action, qui est la raison d'être de cette application, tombe.

    Un compte sans profil n'a ni rôle ni périmètre : le superutilisateur
    d'amorçage n'est pas un acteur du cahier des charges, et un compte hérité
    ne doit pas se retrouver avec des droits par défaut.

    Le verrou est un middleware et non une permission DRF : ``permission_classes``
    déclaré sur une vue *remplace* les classes par défaut, si bien qu'un réglage
    global n'en couvrait qu'une partie — et qu'une vue écrite demain y
    échapperait sans que personne ne s'en aperçoive. Ici, rien ne passe à côté.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # ``process_view`` s'exécute une fois l'URL résolue, ce qui donne accès
        # au nom de la route ; l'authentification par jeton, elle, n'a pas
        # encore eu lieu. Elle est faite ici, et son résultat est laissé sur la
        # requête pour que DRF ne la refasse pas à l'entrée de la vue.
        match = request.resolver_match
        if match is None or not request.path.startswith("/api/"):
            return None
        if match.url_name in TOUJOURS_OUVERTES:
            return None

        user = _authenticated_user(request)
        if user is None:
            # Anonyme ou jeton refusé : DRF répondra 401 avec le bon motif.
            return None
        profile = getattr(user, "profile", None)
        if profile is None:
            return JsonResponse(
                {
                    "detail": (
                        "Ce compte n'a pas de profil : aucun rôle ni périmètre "
                        "ne lui est attribué."
                    ),
                    "no_profile": True,
                },
                status=403,
            )
        if match.url_name in EXEMPT_URL_NAMES or not profile.must_change_password:
            return None

        return JsonResponse(
            {
                "detail": (
                    "Votre mot de passe a été défini par le siège : "
                    "remplacez-le avant d'utiliser la plateforme."
                ),
                "must_change_password": True,
            },
            status=403,
        )


def _authenticated_user(request):
    """Utilisateur de la requête, jeton compris.

    ``request.user`` est encore anonyme à ce stade pour une requête par jeton :
    l'authentification DRF n'intervient qu'à l'entrée de la vue.
    """
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return request.user
    try:
        resolved = JetonAuthentication().authenticate(request)
    except AuthenticationFailed:
        return None
    if resolved is None:
        return None
    setattr(request, ATTRIBUT_MEMO, resolved)
    return resolved[0]
