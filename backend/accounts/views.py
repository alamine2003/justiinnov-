"""Vues des comptes : profil courant, mot de passe, gestion des utilisateurs."""

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from budget.models import CONSOLIDATION_CURRENCY
from core.mixins import NoDestroyModelViewSet

from .models import HEADQUARTERS_ROLES, Role
from .permissions import (
    CAPABILITIES,
    USER_WRITE_ROLES,
    RolePermission,
    get_access,
)
from .serializers import ChangePasswordSerializer, MeSerializer, UserSerializer


class MeView(APIView):
    """Rôle, périmètre et droits de l'utilisateur connecté."""

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Changement de mot de passe par l'utilisateur lui-même."""

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()

        profile = getattr(user, "profile", None)
        if profile is not None and profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=["must_change_password"])

        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(NoDestroyModelViewSet):
    """Gestion des comptes. Réservée au siège ; désactivation plutôt que
    suppression, pour préserver l'imputabilité des actions passées."""

    queryset = (
        User.objects.select_related("profile")
        .prefetch_related("profile__countries")
        .order_by("username")
    )
    serializer_class = UserSerializer
    permission_classes = [RolePermission]
    read_roles = USER_WRITE_ROLES
    write_roles = USER_WRITE_ROLES
    filterset_fields = ["is_active", "profile__role"]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["username", "date_joined"]

    def perform_update(self, serializer):
        """Interdit de se désactiver ou de se déclasser soi-même.

        Rien ne rattraperait l'erreur depuis l'application : le compte qui vient
        de se retirer ses droits n'a plus le droit de se les rendre. Le geste
        reste possible, mais il doit venir d'un autre administrateur.
        """
        if serializer.instance == self.request.user:
            if serializer.validated_data.get("is_active") is False:
                raise ValidationError(
                    {"is_active": "Vous ne pouvez pas désactiver votre propre compte."}
                )
            role = serializer.validated_data.get("profile", {}).get("role")
            if role is not None and role not in USER_WRITE_ROLES:
                raise ValidationError(
                    {"role": "Vous ne pouvez pas retirer vos propres droits d'administration."}
                )
        serializer.save()


class BackOfficePermission(RolePermission):
    """Le back-office est réservé au siège."""

    message = "Le back-office est réservé aux administrateurs du siège."

    def has_permission(self, request, view):
        access = get_access(request.user)
        return access is not None and access.role in USER_WRITE_ROLES


class ConfigurationView(APIView):
    """Paramètres système du back-office.

    Ils sont fixés par l'environnement au démarrage : les exposer en lecture
    permet de vérifier ce qui tourne réellement, sans se fier au fichier de
    configuration qu'on croit déployé.
    """

    permission_classes = [BackOfficePermission]

    def get(self, request):
        return Response(
            {
                "alertes": {
                    "seuils": settings.ALERT_THRESHOLDS,
                    "facteur_depense_inhabituelle": settings.UNUSUAL_EXPENSE_FACTOR,
                },
                "justificatifs": {
                    "taille_max_mo": settings.MAX_PROOF_SIZE // (1024 * 1024),
                    "formats_acceptes": settings.ALLOWED_PROOF_EXTENSIONS,
                    "stockage": (
                        "Object storage (S3/MinIO)"
                        if settings.AWS_S3_ENDPOINT_URL
                        else "Disque local"
                    ),
                },
                "budget": {
                    "devise_de_consolidation": CONSOLIDATION_CURRENCY,
                },
                "notifications": {
                    "email_configure": bool(settings.EMAIL_HOST),
                    "expediteur": settings.DEFAULT_FROM_EMAIL,
                },
                "systeme": {
                    "fuseau": settings.TIME_ZONE,
                    "mode_debug": settings.DEBUG,
                },
            }
        )


class PermissionMatrixView(APIView):
    """Matrice des rôles et de ce qu'ils autorisent.

    Lue dans les mêmes constantes que celles appliquées par ``RolePermission``.
    La matrice est **volontairement non modifiable** : la rendre éditable
    permettrait de rendre à un pays le droit de justifier ses propres dépenses,
    précisément ce que la séparation des tâches interdit.
    """

    permission_classes = [BackOfficePermission]

    def get(self, request):
        return Response(
            {
                "roles": [
                    {
                        "value": role.value,
                        "label": role.label,
                        "siege": role in HEADQUARTERS_ROLES,
                    }
                    for role in Role
                ],
                "capabilities": [
                    {
                        "key": capability["key"],
                        "label": capability["label"],
                        "description": capability["description"],
                        "roles": sorted(str(r) for r in capability["roles"]),
                    }
                    for capability in CAPABILITIES
                ],
                "editable": False,
                "note": (
                    "Les droits sont fixés dans le code et appliqués à chaque "
                    "requête. Les rendre modifiables permettrait de redonner à "
                    "un pays le droit de justifier ses propres dépenses."
                ),
            }
        )
