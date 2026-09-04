"""Vues des comptes : profil courant, mot de passe, session, utilisateurs."""

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import NoDestroyModelViewSet
from core.models import ChangeLog
from core.views import BackOfficePermission

from .authentication import obtenir_jeton, revoquer_jeton
from .journal import etat_compte, journaliser_compte, journaliser_modification
from .models import HEADQUARTERS_ROLES, Role
from .permissions import CAPABILITIES, USER_WRITE_ROLES, RolePermission, get_access
from .serializers import ChangePasswordSerializer, MeSerializer, UserSerializer


class MeView(APIView):
    """Rôle, périmètre et droits de l'utilisateur connecté."""

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    """Changement de mot de passe par l'utilisateur lui-même.

    Le jeton en cours est remplacé : un jeton obtenu avec l'ancien mot de
    passe — sur un poste oublié, ou par qui l'a intercepté — ne doit pas
    survivre au nouveau. Le client reçoit le jeton de remplacement.
    """

    @transaction.atomic
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

        revoquer_jeton(user)
        token = obtenir_jeton(user)
        journaliser_compte(request, user, ChangeLog.Actions.PASSWORD_CHANGED)
        return Response({"token": token.key})


class LogoutView(APIView):
    """Déconnexion : le jeton est supprimé côté serveur.

    Oublier le jeton dans le navigateur ne suffit pas : tant qu'il existe en
    base, quiconque l'a copié agit au nom du compte.
    """

    def post(self, request):
        journaliser_compte(request, request.user, ChangeLog.Actions.LOGOUT)
        revoquer_jeton(request.user)
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

    def _verifier_hierarchie(self, serializer):
        """Le rôle de super administrateur ne se touche qu'entre pairs.

        Un administrateur qui pourrait créer, modifier ou réinitialiser le
        mot de passe d'un super administrateur — ou s'attribuer le rôle —
        aurait de fait tous les droits. Seul un super administrateur agit sur
        un compte de ce niveau ou le confère.
        """
        access = get_access(self.request.user)
        if access is not None and access.role == Role.SUPER_ADMIN:
            return
        cible = serializer.instance
        profile = getattr(cible, "profile", None) if cible is not None else None
        role_vise = serializer.validated_data.get("profile", {}).get("role")
        if role_vise == Role.SUPER_ADMIN or (
            profile is not None and profile.role == Role.SUPER_ADMIN
        ):
            raise PermissionDenied(
                "Seul un super administrateur peut gérer un compte de super "
                "administrateur ou attribuer ce rôle."
            )

    @transaction.atomic
    def perform_create(self, serializer):
        self._verifier_hierarchie(serializer)
        user = serializer.save()
        journaliser_compte(
            self.request, user, ChangeLog.Actions.CREATED,
            apres=etat_compte(user),
        )

    @transaction.atomic
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
        self._verifier_hierarchie(serializer)

        avant = etat_compte(serializer.instance)
        user = serializer.save()
        apres = etat_compte(user)
        journaliser_modification(self.request, user, avant, apres)

        if serializer.validated_data.get("password"):
            # Le mot de passe posé par le siège rend l'ancien jeton caduc :
            # qui le détenait n'est plus forcément le titulaire.
            revoquer_jeton(user)
            journaliser_compte(
                self.request, user, ChangeLog.Actions.PASSWORD_RESET,
                changed_fields=["password"],
            )
        if avant["is_active"] and not apres["is_active"]:
            revoquer_jeton(user)


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
