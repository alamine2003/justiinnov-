"""Vues des comptes : profil courant, mot de passe, gestion des utilisateurs."""

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import NoDestroyModelViewSet

from .permissions import USER_WRITE_ROLES, RolePermission
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
