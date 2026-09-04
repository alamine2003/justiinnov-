"""Vues de l'API de gestion des pays et organisations, et du back-office."""

import json

from django.conf import settings
from django.db import OperationalError, connection, transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView

from accounts import totp
from accounts.authentication import obtenir_jeton
from accounts.models import HEADQUARTERS_ROLES
from accounts.permissions import (
    HISTORY_READ_ROLES,
    REFERENTIAL_WRITE_ROLES,
    SUBENTITY_WRITE_ROLES,
    USER_WRITE_ROLES,
    RolePermission,
    get_access,
)
from accounts.scoping import CountryScopedMixin

from .africa import AFRICAN_COUNTRIES
from .mixins import NoDestroyModelViewSet
from .models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
    WorkflowConfiguration,
)
from .requetes import client_ip
from .serializers import (
    ChangeLogSerializer,
    CostCenterSerializer,
    CountryDetailSerializer,
    CountryListSerializer,
    CountryWriteSerializer,
    ExpenseTitleSerializer,
    ManagerSerializer,
    MarketingCategorySerializer,
    ProjectSerializer,
    TeamSerializer,
    WorkflowConfigurationSerializer,
)
from .signals import journaliser


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
        journaliser(
            user,
            ChangeLog.Actions.LOGIN_FAILED,
            ChangeLog.Models.USER,
            label=username,
            to_value="",
            changed_fields=[motif] if motif else None,
            performed_by=username,
            request=request,
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
            if not totp.verifier_code(profile.totp_secret, code):
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
        journaliser(
            user,
            ChangeLog.Actions.LOGIN,
            ChangeLog.Models.USER,
            label=user.username,
            to_value=user.username,
            performed_by=user.username,
            request=request,
        )
        return Response({"token": token.key})


class ScopedViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Base commune : cloisonnement par pays + droits liés au rôle."""

    permission_classes = [RolePermission]


class CountryViewSet(ScopedViewSet):
    """CRUD des pays + activation/désactivation + historique."""

    queryset = Country.objects.prefetch_related(
        "managers", "teams", "cost_centers", "projects",
        "expense_titles", "marketing_categories",
    ).all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active", "currency", "country_ref"]
    search_fields = ["name", "code", "country_ref", "timezone"]
    ordering_fields = ["name", "code", "created_at"]
    write_roles = REFERENTIAL_WRITE_ROLES
    # La liste des pays à créer n'intéresse que ceux qui peuvent en créer.
    action_read_roles = {"disponibles": REFERENTIAL_WRITE_ROLES}
    # Le pays est l'objet lui-même : il n'y a pas de champ « pays » à valider.
    country_lookup = "pk"
    country_field = None

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CountryWriteSerializer
        if self.action == "retrieve":
            return CountryDetailSerializer
        return CountryListSerializer

    @action(detail=False, methods=["get"], url_path="disponibles")
    def disponibles(self, request):
        """Pays africains que la plateforme ne suit pas encore.

        Le formulaire de création propose cette liste plutôt que de laisser
        deviner un code ISO : une faute de frappe se traduisait par un refus
        sans que rien n'indique quels codes sont acceptés. La liste vit côté
        serveur, là où la validation s'applique — la recopier dans le frontend
        la ferait diverger.
        """
        deja_suivis = set(
            Country.objects.values_list("code", flat=True)
        )
        return Response(
            [
                {"code": code, "name": nom}
                for code, nom in sorted(
                    AFRICAN_COUNTRIES.items(), key=lambda item: item[1]
                )
                if code not in deja_suivis
            ]
        )


class ManagerViewSet(ScopedViewSet):
    queryset = Manager.objects.all().order_by("name")
    serializer_class = ManagerSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name", "email", "title"]
    write_roles = REFERENTIAL_WRITE_ROLES
    # Un manager est rattaché à ses pays par une relation multiple.
    country_lookup = "countries"
    country_field = None


class TeamViewSet(ScopedViewSet):
    queryset = Team.objects.select_related("country").all().order_by("name")
    serializer_class = TeamSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["name"]
    write_roles = SUBENTITY_WRITE_ROLES
    # Un manager rattaché à des équipes ne voit que les siennes : la liste
    # qu'il consulte est celle dans laquelle il choisit pour ses dépenses.
    team_lookup = "pk"


class CostCenterViewSet(ScopedViewSet):
    queryset = CostCenter.objects.select_related("country").all().order_by("code")
    serializer_class = CostCenterSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["code", "name"]
    write_roles = SUBENTITY_WRITE_ROLES


class ProjectViewSet(ScopedViewSet):
    queryset = Project.objects.select_related("country").all().order_by("-created_at")
    serializer_class = ProjectSerializer
    filterset_fields = ["country", "status", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["created_at", "name"]
    write_roles = SUBENTITY_WRITE_ROLES


class ExpenseTitleViewSet(ScopedViewSet):
    queryset = ExpenseTitle.objects.select_related("country").all().order_by("label")
    serializer_class = ExpenseTitleSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["label"]
    write_roles = SUBENTITY_WRITE_ROLES


class MarketingCategoryViewSet(ScopedViewSet):
    queryset = (
        MarketingCategory.objects.select_related("country").all().order_by("name")
    )
    serializer_class = MarketingCategorySerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["name"]
    write_roles = SUBENTITY_WRITE_ROLES


class ChangeLogViewSet(CountryScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Historique des changements de rattachement et de configuration."""

    queryset = ChangeLog.objects.select_related("country").all()
    serializer_class = ChangeLogSerializer
    permission_classes = [RolePermission]
    read_roles = HISTORY_READ_ROLES
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["country", "model_name", "action"]
    ordering_fields = ["created_at"]

    #: Entrées qui relèvent de l'administration : la vie des comptes (rôles,
    #: périmètres, 2FA) et la politique du workflow. Le DM et le DF, qui ne
    #: gèrent ni l'un ni l'autre, n'ont pas à les lire — la liste des comptes
    #: leur est fermée, son historique aussi.
    ENTREES_D_ADMINISTRATION = (
        ChangeLog.Models.USER,
        ChangeLog.Models.WORKFLOW_CONFIGURATION,
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        access = get_access(self.request.user)
        if access is None:
            return queryset
        if not access.has_global_scope and access.role in HEADQUARTERS_ROLES:
            # Un rôle du siège restreint à quelques pays garde la vue sur ce
            # qui n'appartient à aucun : taux de change, par exemple. Le
            # filtre du mixin les lui cachait avec le reste.
            queryset = ChangeLog.objects.select_related("country").filter(
                Q(country__in=access.country_ids) | Q(country__isnull=True)
            )
        if access.role not in USER_WRITE_ROLES:
            queryset = queryset.exclude(model_name__in=self.ENTREES_D_ADMINISTRATION)
        return queryset


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

    def get(self, request):
        # ``budget`` dépend de ``core``, pas l'inverse : l'import reste local
        # pour ne pas inverser la dépendance au chargement du module.
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
            }
        )


class WorkflowConfigurationView(APIView):
    """Lecture et modification de la politique du workflow."""

    permission_classes = [BackOfficePermission]

    def get(self, request):
        return Response(
            WorkflowConfigurationSerializer(WorkflowConfiguration.charger()).data
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
            journaliser(
                configuration,
                ChangeLog.Actions.UPDATED,
                ChangeLog.Models.WORKFLOW_CONFIGURATION,
                label="Configuration du workflow",
                from_value=json.dumps(avant, ensure_ascii=False),
                to_value=json.dumps(apres, ensure_ascii=False),
                changed_fields=changes,
                diff={name: [avant[name], apres[name]] for name in changes},
                request=request,
            )
        return Response(serializer.data)


class HealthView(APIView):
    """État de la plateforme, pour Docker et la livraison continue.

    Ni compte, ni jeton, ni limitation de débit : le contrôle de santé du
    conteneur l'interroge toutes les trente secondes, et un déploiement n'est
    déclaré réussi que lorsqu'il répond. Il ne dit que deux choses — le
    serveur répond, la base est joignable — et rien sur ce qu'elle contient.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except OperationalError:
            return Response(
                {"status": "indisponible", "database": "ko"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})
