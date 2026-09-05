"""API du référentiel — pays, managers, équipes, projets… — et de son historique.

Les modèles sont dans ``core`` ; leur API est ici parce qu'elle s'appuie sur
les rôles et les périmètres (``RolePermission``, ``CountryScopedMixin``),
que ``core`` ne connaît pas : ``core`` est au bas de l'ordre des
dépendances, ``accounts`` juste au-dessus (décision 40).
"""

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.africa import AFRICAN_COUNTRIES
from core.mixins import NoDestroyModelViewSet
from core.models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
)
from core.serializers import (
    AvailableCountrySerializer,
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

from .models import HEADQUARTERS_ROLES
from .permissions import (
    HISTORY_READ_ROLES,
    REFERENTIAL_WRITE_ROLES,
    SUBENTITY_WRITE_ROLES,
    USER_WRITE_ROLES,
    RolePermission,
    get_access,
)
from .scoping import CountryScopedMixin


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

    @extend_schema(responses=AvailableCountrySerializer(many=True))
    @action(detail=False, methods=["get"], url_path="disponibles", pagination_class=None)
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

