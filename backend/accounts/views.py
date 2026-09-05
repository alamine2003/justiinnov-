"""Vues des comptes : obtention du jeton, profil courant, préférences, mot de
passe, double authentification, session, utilisateurs, et back-office
(configuration). L'authentification et le back-office vivent ici, et non
dans ``core`` : ils reposent sur les rôles, que ``core`` ne connaît pas
(décision 40)."""

import json

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView

from core.journal import tracer
from core.mixins import NoDestroyModelViewSet
from core.models import ChangeLog, WorkflowConfiguration
from core.requetes import client_ip
from core.serializers import ConfigurationSerializer, WorkflowConfigurationSerializer

from . import totp
from .authentication import obtenir_jeton, revoquer_jeton
from .journal import etat_compte, journaliser_compte, journaliser_modification
from .models import ALWAYS_GLOBAL_ROLES, HEADQUARTERS_ROLES, Role, UserProfile
from .permissions import CAPABILITIES, USER_WRITE_ROLES, RolePermission, get_access
from .serializers import (
    ChangePasswordSerializer,
    MePreferencesSerializer,
    MeSerializer,
    PermissionMatrixSerializer,
    TokenAuthErrorSerializer,
    TokenAuthSerializer,
    TokenSerializer,
    TotpCodeSerializer,
    TotpConfirmedSerializer,
    TotpEnrolmentSerializer,
    UserSerializer,
)


class LoginRateThrottle(AnonRateThrottle):
    """Limite les tentatives d'authentification par adresse IP."""

    scope = "login"

    def get_ident(self, request):
        # Même lecture de l'adresse que le journal : derrière nginx, la
        # version DRF compterait toutes les tentatives sur l'adresse du
        # mandataire — ou sur ce que le client a écrit dans X-Forwarded-For.
        return client_ip(request) or super().get_ident(request)


class LoginUsernameThrottle(SimpleRateThrottle):
    """Limite les tentatives d'authentification par nom de compte.

    La limite par adresse ne protège pas un compte visé depuis plusieurs
    adresses ; celle-ci compte les essais sur le nom, quelle qu'en soit
    l'origine.
    """

    scope = "login_user"

    def get_cache_key(self, request, view):
        username = request.data.get("username") if hasattr(request.data, "get") else None
        if not username:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": str(username).strip().lower()[:150],
        }


class ThrottledObtainAuthToken(ObtainAuthToken):
    """Obtention du jeton, protégée contre le bourrage d'identifiants.

    ``ObtainAuthToken`` force ``throttle_classes = ()`` : les limites globales
    de ``REST_FRAMEWORK`` ne s'y appliquent pas et il faut donc les réattacher
    explicitement. Chaque tentative, réussie ou non, est consignée avec le nom
    saisi et l'adresse : c'est la première trace d'une intrusion.

    Second facteur : quand la double authentification du compte est
    confirmée, la charge utile doit porter ``code``. Le mot de passe est
    vérifié d'abord — un code n'est jamais demandé pour un mot de passe faux,
    sinon la réponse dirait à l'attaquant qu'il a trouvé le bon. Un compte
    pas encore enrôlé se connecte sans code ; si la politique exige la
    double authentification (``settings.TOTP_REQUIRED``), c'est le
    middleware qui lui ferme tout sauf l'enrôlement. Un compte enrôlé, lui,
    fournit son code que la politique l'exige ou non : un second facteur
    qu'on a choisi d'activer ne se contourne pas.
    """

    throttle_classes = [LoginRateThrottle, LoginUsernameThrottle]

    def _journaliser_echec(self, request, username, user=None, motif=None):
        tracer(
            request,
            ChangeLog.Actions.LOGIN_FAILED,
            user,
            famille="session",
            label=username,
            to_value="",
            changed_fields=[motif] if motif else None,
            performed_by=username,
        )

    # Le sérialiseur de DRF ne connaît pas ``code`` et ne rend pas ``token``
    # seul : la forme documentée est celle réellement échangée.
    @extend_schema(
        request=TokenAuthSerializer,
        responses={200: TokenSerializer, 400: TokenAuthErrorSerializer},
        auth=[],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        username = str(request.data.get("username", "") or "")[:150]
        if not serializer.is_valid():
            self._journaliser_echec(request, username)
            serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        profile = getattr(user, "profile", None)
        if profile is not None and profile.totp_confirmed:
            code = request.data.get("code")
            if code in (None, ""):
                return Response(
                    {
                        "code": [_("Code de double authentification requis.")],
                        "totp_required": True,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Le code est consommé, pas seulement vérifié : présenté une
            # seconde fois, il est refusé (cf. ``accounts.totp``).
            if not totp.consommer_code(profile, code):
                # Journalisé comme un mot de passe faux, avec le motif : un
                # code se devine aussi en boucle, et la limite de débit
                # compte cette tentative comme les autres.
                self._journaliser_echec(request, username, user=user, motif="totp")
                return Response(
                    {
                        "code": [_("Code de double authentification invalide.")],
                        "totp_required": True,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        # Renouvelé s'il a dépassé ``TOKEN_MAX_AGE_DAYS`` : ``get_or_create``
        # rendrait indéfiniment le même jeton périmé.
        token = obtenir_jeton(user)
        tracer(
            request,
            ChangeLog.Actions.LOGIN,
            user,
            famille="session",
            label=user.username,
            to_value=user.username,
            performed_by=user.username,
        )
        return Response({"token": token.key})


class BackOfficePermission(RolePermission):
    """Le back-office est réservé au siège."""

    message = _("Le back-office est réservé aux administrateurs du siège.")

    def has_permission(self, request, view):
        access = get_access(request.user)
        return access is not None and access.role in USER_WRITE_ROLES


class ConfigurationView(APIView):
    """Paramètres du back-office.

    Deux origines : l'environnement, figé au démarrage (stockage, courriel,
    fuseau), et la politique du workflow, modifiable en base. Les exposer
    ensemble permet de vérifier ce qui tourne réellement, sans se fier au
    fichier de configuration qu'on croit déployé.
    """

    permission_classes = [BackOfficePermission]

    @extend_schema(responses=ConfigurationSerializer)
    def get(self, request):
        # ``budget`` dépend d'``accounts``, pas l'inverse : l'import reste
        # local pour ne pas inverser la dépendance au chargement du module.
        from budget.models import CONSOLIDATION_CURRENCY

        configuration = WorkflowConfiguration.charger()
        return Response(
            {
                "alertes": {
                    "seuils": configuration.alert_thresholds,
                    "facteur_depense_inhabituelle": float(
                        configuration.unusual_expense_factor
                    ),
                },
                "justificatifs": {
                    "taille_max_mo": settings.MAX_PROOF_SIZE // (1024 * 1024),
                    "formats_acceptes": settings.ALLOWED_PROOF_EXTENSIONS,
                    "stockage": (
                        _("Object storage (S3/MinIO)")
                        if settings.AWS_S3_ENDPOINT_URL
                        else _("Disque local")
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
                "workflow": WorkflowConfigurationSerializer(configuration).data,
                # Réglage de déploiement : la pile expose-t-elle Grafana ?
                "supervision": bool(settings.SUPERVISION),
            }
        )


class WorkflowConfigurationView(APIView):
    """Lecture et modification de la politique du workflow."""

    permission_classes = [BackOfficePermission]

    @extend_schema(responses=WorkflowConfigurationSerializer)
    def get(self, request):
        return Response(
            WorkflowConfigurationSerializer(WorkflowConfiguration.charger()).data
        )

    @extend_schema(
        request=WorkflowConfigurationSerializer(partial=True),
        responses=WorkflowConfigurationSerializer,
    )
    @transaction.atomic
    def patch(self, request):
        # Lue en base et verrouillée, pas depuis le cache : deux
        # modifications simultanées se succèdent au lieu de s'écraser, et le
        # journal décrit exactement l'état que chacune a trouvé.
        configuration, _ = (
            WorkflowConfiguration.objects.select_for_update().get_or_create(pk=1)
        )
        serializer = WorkflowConfigurationSerializer(
            configuration, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        modifiables = [
            name for name, field in serializer.fields.items() if not field.read_only
        ]
        avant = {
            name: value
            for name, value in WorkflowConfigurationSerializer(configuration).data.items()
            if name in modifiables
        }
        serializer.save()
        apres = {name: value for name, value in serializer.data.items() if name in modifiables}

        changes = [name for name in modifiables if avant[name] != apres[name]]
        if changes:
            tracer(
                request,
                ChangeLog.Actions.UPDATED,
                configuration,
                famille="configuration",
                label="Configuration du workflow",
                from_value=json.dumps(avant, ensure_ascii=False),
                to_value=json.dumps(apres, ensure_ascii=False),
                changed_fields=changes,
                diff={name: [avant[name], apres[name]] for name in changes},
            )
        return Response(serializer.data)



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

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(request=MePreferencesSerializer, responses=MeSerializer)
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

    @extend_schema(request=ChangePasswordSerializer, responses=TokenSerializer)
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

    @extend_schema(request=None, responses=TotpEnrolmentSerializer)
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
        # Nouveau secret, nouveaux compteurs : la mémoire anti-rejeu repart.
        profile.totp_last_counter = None
        profile.save(update_fields=["totp_secret", "totp_last_counter", "updated_at"])
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
    @extend_schema(request=TotpCodeSerializer, responses=TotpConfirmedSerializer)
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
        # Consommé et non seulement vérifié : le code de confirmation ne
        # doit pas pouvoir resservir à la connexion qui suit.
        if not totp.consommer_code(profile, serializer.validated_data["code"]):
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

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        journaliser_compte(request, request.user, ChangeLog.Actions.LOGOUT)
        revoquer_jeton(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(NoDestroyModelViewSet):
    """Gestion des comptes. Réservée au siège ; désactivation plutôt que
    suppression, pour préserver l'imputabilité des actions passées."""

    queryset = (
        User.objects.select_related("profile")
        .prefetch_related("profile__countries", "profile__teams")
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

    @extend_schema(request=None, responses=UserSerializer)
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
        profile.totp_last_counter = None
        profile.save(
            update_fields=[
                "totp_secret", "totp_confirmed_at", "totp_last_counter", "updated_at",
            ]
        )
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

    @extend_schema(responses=PermissionMatrixSerializer)
    def get(self, request):
        return Response(
            {
                "roles": [
                    {
                        "value": role.value,
                        "label": str(role.label),
                        "siege": role in HEADQUARTERS_ROLES,
                        # Un rôle du siège peut être restreint à des pays
                        # (DM, DF) ; la RH et les super administrateurs,
                        # jamais : ils administrent l'ensemble.
                        "always_global": role in ALWAYS_GLOBAL_ROLES,
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
