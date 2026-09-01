"""Vues de l'API de gestion des pays et organisations."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.throttling import AnonRateThrottle

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


class CountryViewSet(NoDestroyModelViewSet):
    """CRUD des pays + activation/désactivation + historique."""

    queryset = Country.objects.prefetch_related(
        "managers", "teams", "cost_centers", "projects",
        "expense_titles", "marketing_categories",
    ).all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active", "currency"]
    search_fields = ["name", "code", "timezone"]
    ordering_fields = ["name", "code", "created_at"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CountryWriteSerializer
        if self.action == "retrieve":
            return CountryDetailSerializer
        return CountryListSerializer


class ManagerViewSet(NoDestroyModelViewSet):
    queryset = Manager.objects.all().order_by("name")
    serializer_class = ManagerSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name", "email", "title"]


class TeamViewSet(NoDestroyModelViewSet):
    queryset = Team.objects.select_related("country").all().order_by("name")
    serializer_class = TeamSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["name"]


class CostCenterViewSet(NoDestroyModelViewSet):
    queryset = CostCenter.objects.select_related("country").all().order_by("code")
    serializer_class = CostCenterSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["code", "name"]


class ProjectViewSet(NoDestroyModelViewSet):
    queryset = Project.objects.select_related("country").all().order_by("-created_at")
    serializer_class = ProjectSerializer
    filterset_fields = ["country", "status", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["created_at", "name"]


class ExpenseTitleViewSet(NoDestroyModelViewSet):
    queryset = ExpenseTitle.objects.select_related("country").all().order_by("label")
    serializer_class = ExpenseTitleSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["label"]


class MarketingCategoryViewSet(NoDestroyModelViewSet):
    queryset = MarketingCategory.objects.select_related("country").all().order_by("name")
    serializer_class = MarketingCategorySerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["name"]


class ChangeLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Historique des changements de rattachement et de configuration."""

    serializer_class = ChangeLogSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["country", "model_name", "action"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = ChangeLog.objects.select_related("country").all()
        country_id = self.request.query_params.get("country")
        if country_id:
            queryset = queryset.filter(country_id=country_id)
        return queryset