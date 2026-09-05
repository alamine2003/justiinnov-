"""Schéma OpenAPI servi par l'API, et son interface de consultation.

Le document décrit chaque route, ses droits et la forme de ses réponses :
c'est une carte de la plateforme, qui ne se distribue pas à n'importe qui.
Un compte pays n'en a pas l'usage — il n'a que l'écran de saisie — et la
carte lui dirait ce que le siège fait de ses déclarations. Le schéma est donc
réservé aux rôles du siège ; l'interface Swagger, qui permet d'exécuter les
requêtes depuis le navigateur, aux administrateurs et en mode debug
seulement : en production, le frontend est le seul client attendu.

Le même document, généré hors ligne par ``manage.py spectacular``, est
versionné dans ``docs/api/schema.json`` ; le frontend en tire ses types.
"""

from django.conf import settings
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import BasePermission

from accounts.models import HEADQUARTERS_ROLES
from accounts.permissions import USER_WRITE_ROLES, get_access


#: Champs qu'une réponse peut omettre, seuls exceptés de la règle ci-dessous.
CHAMPS_FACULTATIFS_EN_REPONSE = frozenset({"warning"})


def reponses_completes(result, generator, request, public):
    """Marque obligatoires tous les champs des composants de réponse.

    drf-spectacular ne rend obligatoire, en réponse, que ce qui l'est en
    requête ou en lecture seule : ``amount`` (calculé quand la dépense est
    décaissée dans une autre devise) ou ``team`` (facultatif en brouillon)
    devenaient optionnels dans les types du frontend, qui aurait dû tester
    des champs que le serveur envoie toujours. DRF rend chaque champ d'un
    sérialiseur ; ceux qui pourraient manquer portent ``allow_null`` pour
    justement ne jamais manquer (voir les commentaires des sérialiseurs).
    Le contrat dit donc ce qui est : tout est là, sauf l'avertissement
    d'une transition, absent quand il n'y a rien à dire.

    Les composants de requête (``…Request``, ``Patched…``) gardent leurs
    champs facultatifs : c'est en écriture qu'ils le sont.
    """
    for name, schema in result.get("components", {}).get("schemas", {}).items():
        if name.endswith("Request") or name.startswith("Patched"):
            continue
        properties = schema.get("properties")
        if not properties:
            continue
        schema["required"] = [
            champ for champ in properties if champ not in CHAMPS_FACULTATIFS_EN_REPONSE
        ]
    return result


class SchemaPermission(BasePermission):
    """Le schéma se lit depuis le siège."""

    message = _("Le schéma de l'API est réservé au siège.")

    def has_permission(self, request, view):
        access = get_access(request.user)
        return access is not None and access.role in HEADQUARTERS_ROLES


class SchemaUiPermission(BasePermission):
    """L'interface d'exploration est réservée aux administrateurs."""

    message = _("L'interface du schéma est réservée aux administrateurs du siège.")

    def has_permission(self, request, view):
        access = get_access(request.user)
        return access is not None and access.role in USER_WRITE_ROLES


class SchemaView(SpectacularAPIView):
    """``GET /api/schema/`` : YAML par défaut, JSON avec ``?format=json``."""

    permission_classes = [SchemaPermission]


class SchemaUiView(SpectacularSwaggerView):
    """``GET /api/schema/ui/`` : Swagger UI, en mode debug seulement.

    La route existe toujours, pour que le refus hors debug soit un 404
    testable et non une absence de route qui dépendrait des réglages au
    chargement. Swagger UI lit le schéma avec la session du navigateur
    (``SessionAuthentication``) : il faut être connecté à ``/admin/``, ou
    saisir son jeton dans « Authorize ».
    """

    permission_classes = [SchemaUiPermission]
    url_name = "schema"

    @extend_schema(exclude=True)
    def get(self, request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404
        return super().get(request, *args, **kwargs)
