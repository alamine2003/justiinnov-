"""Vues de l'API de gestion des pays et organisations."""

from django.db import OperationalError, connection
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounts.permissions import (
    REFERENTIAL_WRITE_ROLES,
    SUBENTITY_WRITE_ROLES,
    RolePermission,
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
)
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
)


class LoginRateThrottle(AnonRateThrottle):
    """Limite les tentatives d'authentification par adresse IP."""

    scope = "login"


class ThrottledObtainAuthToken(ObtainAuthToken):
    """Obtention du jeton, protégée contre le bourrage d'identifiants.

    ``ObtainAuthToken`` force ``throttle_classes = ()`` : les limites globales
    de ``REST_FRAMEWORK`` ne s'y appliquent pas et il faut donc les réattacher
    explicitement.
    """

    throttle_classes = [LoginRateThrottle]


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
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["country", "model_name", "action"]
    ordering_fields = ["created_at"]


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
