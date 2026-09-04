"""Authentification par jeton : durée de vie bornée, profil chargé d'emblée."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed

#: Attribut de la requête HTTP où le middleware dépose ``(user, token)``.
ATTRIBUT_MEMO = "_authentification_par_jeton"


def est_expire(token):
    """Un jeton plus vieux que ``TOKEN_MAX_AGE_DAYS`` ne vaut plus rien.

    Un jeton DRF n'expire jamais de lui-même : celui d'un poste oublié
    resterait valable des années. Zéro désactive la limite.
    """
    max_age = int(settings.TOKEN_MAX_AGE_DAYS or 0)
    if not max_age:
        return False
    return token.created < timezone.now() - timedelta(days=max_age)


def obtenir_jeton(user):
    """Jeton en cours de validité du compte, renouvelé s'il a expiré."""
    token = Token.objects.filter(user=user).first()
    if token is not None and est_expire(token):
        token.delete()
        token = None
    return token or Token.objects.create(user=user)


def revoquer_jeton(user):
    """Supprime le jeton du compte : la prochaine requête devra se reconnecter."""
    Token.objects.filter(user=user).delete()


class JetonAuthentication(TokenAuthentication):
    """``TokenAuthentication`` de DRF, en deux points près.

    - Le jeton a une durée de vie (``TOKEN_MAX_AGE_DAYS``).
    - Si ``ProvisionalPasswordMiddleware`` a déjà authentifié la requête, le
      résultat est repris tel quel : le compte et son profil ne sont chargés
      qu'une fois par requête, pas une fois par le middleware et une fois par
      DRF.
    """

    def authenticate(self, request):
        http_request = getattr(request, "_request", request)
        memo = getattr(http_request, ATTRIBUT_MEMO, None)
        if memo is not None:
            return memo
        return super().authenticate(request)

    def authenticate_credentials(self, key):
        try:
            # Le profil est joint d'emblée : rôle et périmètre en dépendent,
            # et chaque vue y touche.
            token = Token.objects.select_related("user", "user__profile").get(key=key)
        except Token.DoesNotExist:
            raise AuthenticationFailed(_("Jeton invalide."))
        if not token.user.is_active:
            raise AuthenticationFailed(_("Compte désactivé."))
        if est_expire(token):
            raise AuthenticationFailed(_("Jeton expiré : reconnectez-vous."))
        return token.user, token
