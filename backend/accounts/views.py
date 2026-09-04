"""Vues des comptes : profil courant, préférences, mot de passe, double
authentification, session, utilisateurs."""

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.mixins import NoDestroyModelViewSet
from core.models import ChangeLog
from core.views import BackOfficePermission

from . import totp
from .authentication import obtenir_jeton, revoquer_jeton
from .journal import etat_compte, journaliser_compte, journaliser_modification
from .models import HEADQUARTERS_ROLES, Role, UserProfile
from .permissions import CAPABILITIES, USER_WRITE_ROLES, RolePermission, get_access
from .serializers import (
    ChangePasswordSerializer,
    MePreferencesSerializer,
    MeSerializer,
    TotpCodeSerializer,
    UserSerializer,
)


def _profil_requis(user):
    """Profil du compte courant, ou 403 : sans profil, rien à régler."""
    profile = getattr(user, "profile", None)
    if profile is None:
        raise PermissionDenied(_("Ce compte n'a pas de profil."))
    return profile


class MeView(APIView):
    """Rôle, périmètre, droits et préférences de l'utilisateur connecté.

    ``PATCH`` ne règle que ce qui appartient au titulaire (sa langue) ; le
    reste du profil relève du siège, via ``/api/users/``.
    """

    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        profile = _profil_requis(request.user)
        serializer = MePreferencesSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "language" in serializer.validated_data:
            serializer.save()
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


class TotpEnrolView(APIView):
    """Enrôlement de l'application d'authentification du titulaire.

    Le secret n'est engagé qu'à la confirmation : rappeler l'enrôlement en
    remplace un secret jamais confirmé, pour qui a fermé la page avant de
    scanner le QR. Un compte déjà confirmé ne se réenrôle pas ici — le
    secret actif ne doit pas se remplacer sans trace ; c'est le siège qui
    réinitialise (``/api/users/{id}/reset-2fa/``), et l'entrée de journal
    dit qui l'a fait.
    """

    @transaction.atomic
    def post(self, request):
        profile = _profil_requis(request.user)
        if profile.totp_confirmed:
            raise ValidationError(
                {
                    "detail": _(
                        "La double authentification est déjà active sur ce compte. "
                        "Demandez sa réinitialisation à un administrateur."
                    )
                }
            )
        secret = totp.generer_secret()
        profile.totp_secret = secret
        profile.save(update_fields=["totp_secret", "updated_at"])
        # L'adresse e-mail nomme le compte dans l'application ; à défaut, le
        # nom de compte, pour un profil hérité d'avant l'obligation.
        libelle = request.user.email or request.user.username
        uri = totp.uri_d_enrolement(secret, libelle)
        return Response(
            {
                "otpauth_uri": uri,
                "qr_png_base64": totp.qr_png_base64(uri),
                "secret": secret,
            }
        )


class TotpConfirmView(APIView):
    """Confirmation de l'enrôlement par un premier code valide.

    Tant qu'aucun code n'a été présenté, rien ne prouve que le titulaire a
    bien enregistré le secret : confirmer sans code ouvrirait un compte que
    son titulaire ne pourrait plus jamais rejoindre.
    """

    # Pas de ``transaction.atomic`` : la trace d'un code faux doit survivre
    # à la réponse 400, qui annulerait la transaction avec elle.
    def post(self, request):
        profile = _profil_requis(request.user)
        serializer = TotpCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if profile.totp_confirmed:
            raise ValidationError(
                {"detail": _("La double authentification est déjà active sur ce compte.")}
            )
        if not profile.totp_secret:
            raise ValidationError(
                {"detail": _("Aucun enrôlement en cours : commencez par l'enrôlement.")}
            )
        if not totp.verifier_code(profile.totp_secret, serializer.validated_data["code"]):
            # Même trace qu'un mot de passe faux : un code deviné se tente
            # aussi en boucle.
            journaliser_compte(
                request, request.user, ChangeLog.Actions.LOGIN_FAILED,
                changed_fields=["totp"],
            )
            raise ValidationError({"code": [_("Code de double authentification invalide.")]})
        profile.totp_confirmed_at = timezone.now()
        profile.save(update_fields=["totp_confirmed_at", "updated_at"])
        journaliser_compte(
            request, request.user, ChangeLog.Actions.TOTP_CONFIRMED,
            changed_fields=["totp"],
            diff={"totp_confirmed": [False, True]},
        )
        return Response({"totp_confirmed": True})


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

    def _verifier_hierarchie(self, cible, role_vise=None):
        """Le rôle de super administrateur ne se touche qu'entre pairs.

        Un administrateur qui pourrait créer, modifier, réinitialiser le mot
        de passe ou la double authentification d'un super administrateur —
        ou s'attribuer le rôle — aurait de fait tous les droits. Seul un
        super administrateur agit sur un compte de ce niveau ou le confère.
        """
        access = get_access(self.request.user)
        if access is not None and access.role == Role.SUPER_ADMIN:
            return
        profile = getattr(cible, "profile", None) if cible is not None else None
        if role_vise == Role.SUPER_ADMIN or (
            profile is not None and profile.role == Role.SUPER_ADMIN
        ):
            raise PermissionDenied(
                _(
                    "Seul un super administrateur peut gérer un compte de super "
                    "administrateur ou attribuer ce rôle."
                )
            )

    def _verifier_hierarchie_serializer(self, serializer):
        self._verifier_hierarchie(
            serializer.instance,
            serializer.validated_data.get("profile", {}).get("role"),
        )

    @transaction.atomic
    def perform_create(self, serializer):
        self._verifier_hierarchie_serializer(serializer)
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
                    {"is_active": _("Vous ne pouvez pas désactiver votre propre compte.")}
                )
            role = serializer.validated_data.get("profile", {}).get("role")
            if role is not None and role not in USER_WRITE_ROLES:
                raise ValidationError(
                    {"role": _("Vous ne pouvez pas retirer vos propres droits d'administration.")}
                )
        self._verifier_hierarchie_serializer(serializer)

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

    @action(detail=True, methods=["post"], url_path="reset-2fa")
    @transaction.atomic
    def reset_2fa(self, request, pk=None):
        """Réinitialise la double authentification d'un compte.

        Téléphone perdu, application réinstallée : le titulaire ne peut plus
        produire de code, et lui seul pouvait enrôler. Le siège efface le
        secret ; le compte redevient « à enrôler », son jeton tombe — qui le
        détenait n'est plus forcément le titulaire — et l'opération est
        tracée : lever une protection est une action sensible.
        """
        user = self.get_object()
        self._verifier_hierarchie(user)
        profile = getattr(user, "profile", None)
        if profile is None:
            raise ValidationError({"detail": _("Ce compte n'a pas de profil.")})
        etait_confirme = profile.totp_confirmed
        profile.totp_secret = ""
        profile.totp_confirmed_at = None
        profile.save(update_fields=["totp_secret", "totp_confirmed_at", "updated_at"])
        revoquer_jeton(user)
        journaliser_compte(
            request, user, ChangeLog.Actions.TOTP_RESET,
            changed_fields=["totp"],
            diff={"totp_confirmed": [etait_confirme, False]},
        )
        return Response(UserSerializer(user).data)


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
                        "label": str(role.label),
                        "siege": role in HEADQUARTERS_ROLES,
                    }
                    for role in Role
                ],
                "capabilities": [
                    {
                        "key": capability["key"],
                        "label": str(capability["label"]),
                        "description": str(capability["description"]),
                        "roles": sorted(str(r) for r in capability["roles"]),
                    }
                    for capability in CAPABILITIES
                ],
                "editable": False,
                "note": _(
                    "Les droits sont fixés dans le code et appliqués à chaque "
                    "requête. Les rendre modifiables permettrait de redonner à "
                    "un pays le droit de justifier ses propres dépenses."
                ),
            }
        )
