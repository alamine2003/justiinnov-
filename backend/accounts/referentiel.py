"""API du référentiel — pays, managers, équipes, projets… — et de son historique.

Les modèles sont dans ``core`` ; leur API est ici parce qu'elle s'appuie sur
les rôles et les périmètres (``RolePermission``, ``CountryScopedMixin``),
que ``core`` ne connaît pas : ``core`` est au bas de l'ordre des
dépendances, ``accounts`` juste au-dessus (décision 40).
"""

from django.utils.translation import gettext_lazy
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, serializers, viewsets
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

from .perimetre import ChampCloisonne
from .permissions import RolePermission, get_access, roles_pour
from .scoping import CountryScopedMixin


def _cloisonne(serializer_class, **champs):
    """Le sérialiseur de ``core``, ses clés étrangères limitées au périmètre.

    ``core`` ne connaît pas les périmètres (décision 40) : ses sérialiseurs
    exposent ``country`` comme une clé étrangère ordinaire, et leur
    validateur d'unicité ``(country, nom)`` s'exécutait **avant** le contrôle
    de périmètre de la vue. Un compte restreint doté de ``referentiel.create``
    lisait alors, dans la différence entre « existe déjà » (400) et « hors
    périmètre » (403), les équipes, projets et bénéficiaires de la filiale
    voisine (audit du 8 septembre 2026, §4.5). Ici, comme pour les dépenses
    et les enveloppes, un identifiant hors périmètre est un identifiant
    inconnu : même réponse, rien à lire. La classe garde son nom, donc son
    nom de composant dans le schéma d'API — à la condition, tenue plus bas,
    que la classe d'origine ne soit plus servie nulle part.

    ``__module__`` n'est pas recopié : la classe est bien définie ici, et
    c'est ce que doivent dire les messages qui la nomment. Recopié, il
    faisait dire à drf-spectacular « deux composants de même nom et
    d'identités différentes ``<class 'core.serializers.TeamSerializer'>`` et
    ``<class 'core.serializers.TeamSerializer'>`` » — deux fois le même
    texte pour deux classes distinctes, sans rien qui permette de les
    distinguer.
    """
    return type(serializer_class.__name__, (serializer_class,), {
        "__doc__": serializer_class.__doc__, **champs,
    })


def _pays_cloisonne():
    # Le libellé garde le titre du champ dans le schéma d'API, comme la clé
    # étrangère déduite du modèle qu'il remplace.
    return ChampCloisonne(
        queryset=Country.objects.all(), chemin_pays="pk", label=gettext_lazy("Pays")
    )


TeamSerializer = _cloisonne(TeamSerializer, country=_pays_cloisonne())
CostCenterSerializer = _cloisonne(CostCenterSerializer, country=_pays_cloisonne())
ProjectSerializer = _cloisonne(ProjectSerializer, country=_pays_cloisonne())
ExpenseTitleSerializer = _cloisonne(ExpenseTitleSerializer, country=_pays_cloisonne())
MarketingCategorySerializer = _cloisonne(MarketingCategorySerializer, country=_pays_cloisonne())


def _exiger_un_pays_du_perimetre(self, attrs):
    """Un compte pays n'inscrit pas un responsable hors de son pays, ni sans pays.

    Le champ ``countries`` ne lui propose déjà que les siens
    (``ChampCloisonne``) ; il reste à refuser l'absence. Sans rattachement,
    le responsable sortirait du périmètre à peine créé — ``ManagerViewSet``
    ne montre que ceux d'un pays du demandeur — et son auteur ne le
    reverrait plus. C'est la règle des dépenses sans équipe
    (``expenses.serializers._exiger_une_equipe_du_perimetre``), appliquée au
    rattachement d'un responsable. Les rôles globaux gardent le champ
    facultatif : le siège inscrit un responsable avant de savoir où il ira.
    """
    access = get_access(getattr(self.context.get("request"), "user", None))
    if access is not None and not access.has_global_scope:
        fourni = "countries" in attrs
        if (self.instance is None and not attrs.get("countries")) or (
            fourni and not attrs["countries"]
        ):
            raise serializers.ValidationError(
                {"countries": gettext_lazy("Indiquez le pays de ce responsable.")}
            )
    return attrs


def _acces_du_lecteur(self):
    return get_access(getattr(self.context.get("request"), "user", None))


def _rattacher_sans_detacher_le_voisin(self, instance, validated_data):
    """Un compte restreint ne touche qu'aux rattachements de son périmètre.

    ``countries`` ne lui propose que ses pays (``ChampCloisonne``) ; la
    liste qu'il soumet est donc la liste **de ce qu'il voit**. L'écrire
    telle quelle détachait le responsable des pays qu'il ne voit pas — un
    manager du Togo effaçait, sans le savoir ni le vouloir, le
    rattachement ivoirien. Les pays hors périmètre sont recopiés tels
    quels : ils ne sont ni proposés, ni retirés.
    """
    access = _acces_du_lecteur(self)
    if "countries" in validated_data and access is not None and not access.has_global_scope:
        hors_perimetre = instance.countries.exclude(pk__in=access.country_ids)
        validated_data["countries"] = [
            *validated_data["countries"], *hors_perimetre,
        ]
    return _ManagerSerializerDeCore.update(self, instance, validated_data)


def _ne_montrer_que_le_perimetre(self, instance):
    """En lecture, les pays du responsable se limitent à ceux du lecteur :
    un rattachement hors périmètre n'existe pas pour lui, comme le pays
    lui-même (``CountryViewSet``)."""
    data = _ManagerSerializerDeCore.to_representation(self, instance)
    access = _acces_du_lecteur(self)
    if access is not None and not access.has_global_scope:
        visibles = set(access.country_ids)
        data["countries"] = [pk for pk in data["countries"] if pk in visibles]
    return data


_ManagerSerializerDeCore = ManagerSerializer
ManagerSerializer = _cloisonne(
    ManagerSerializer,
    countries=ChampCloisonne(
        many=True, queryset=Country.objects.all(), chemin_pays="pk",
        label=gettext_lazy("Pays"), required=False,
    ),
    validate=_exiger_un_pays_du_perimetre,
    update=_rattacher_sans_detacher_le_voisin,
    to_representation=_ne_montrer_que_le_perimetre,
)
# Le détail d'un pays imbrique son référentiel. Tant qu'il le tirait de
# ``core``, deux classes distinctes portaient le même nom — l'originale par
# ``/api/countries/{id}/``, la cloisonnée par ``/api/teams/`` et ses
# voisines — et le schéma d'API en gardait une au hasard de l'ordre de
# parcours, en signalant cinq fois « Encountered 2 components with identical
# names » (drf_spectacular.W001). C'est ce qui a bloqué la livraison de
# fcbc991 : ces avertissements sont des contrôles Django, et
# ``check --deploy --fail-level WARNING`` les refuse — à raison, puisque le
# schéma en devenait faux.
#
# Une seule classe par nom, donc : le détail d'un pays sert les mêmes
# sérialiseurs que les vues du référentiel. Les champs imbriqués sont en
# lecture seule, le cloisonnement de leur clé ``country`` ne joue qu'à
# l'écriture : la réponse ne change pas, et le composant du schéma non plus
# (``ChampCloisonne`` porte le même libellé « Pays » que la clé étrangère
# déduite du modèle qu'elle remplace).
#
# La liste des pays imbrique ses responsables : elle est clonée pour la même
# raison, et ``CountryDetailSerializer`` redéclare ``managers`` plutôt que de
# l'hériter de l'originale de ``core``.
CountryListSerializer = _cloisonne(
    CountryListSerializer,
    managers=ManagerSerializer(many=True, read_only=True),
)
CountryDetailSerializer = _cloisonne(
    CountryDetailSerializer,
    managers=ManagerSerializer(many=True, read_only=True),
    teams=TeamSerializer(many=True, read_only=True),
    cost_centers=CostCenterSerializer(many=True, read_only=True),
    projects=ProjectSerializer(many=True, read_only=True),
    expense_titles=ExpenseTitleSerializer(many=True, read_only=True),
    marketing_categories=MarketingCategorySerializer(many=True, read_only=True),
)


class ScopedViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Base commune : cloisonnement par pays + droits liés au rôle."""

    permission_classes = [RolePermission]


class CountryViewSet(ScopedViewSet):
    """CRUD des pays + activation/désactivation + historique."""

    queryset = Country.objects.prefetch_related(
        # ``managers__countries`` : le responsable porte maintenant ses pays,
        # une requête par responsable sans ce préchargement.
        "managers", "managers__countries", "teams", "cost_centers", "projects",
        "expense_titles", "marketing_categories",
    ).all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active", "currency", "country_ref"]
    search_fields = ["name", "code", "country_ref", "timezone"]
    ordering_fields = ["name", "code", "created_at"]
    write_capability = "countries.update"
    action_write_capabilities = {"create": "countries.create"}
    # La liste des pays à créer n'intéresse que ceux qui peuvent en créer.
    action_read_capabilities = {"disponibles": "countries.create"}
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
    """Les responsables, et leur rattachement aux pays.

    Capacités propres (``managers.*``), et non celles du pays : inscrire un
    responsable dans sa filiale se délègue au pays, changer la devise de
    cette filiale ne se délègue pas.
    """

    queryset = Manager.objects.prefetch_related("countries").all().order_by("name")
    serializer_class = ManagerSerializer
    filterset_fields = ["is_active"]
    search_fields = ["name", "email", "title"]
    write_capability = "managers.update"
    action_write_capabilities = {"create": "managers.create"}
    # Un manager est rattaché à ses pays par une relation multiple.
    country_lookup = "countries"
    country_field = None


class TeamViewSet(ScopedViewSet):
    queryset = Team.objects.select_related("country").all().order_by("name")
    serializer_class = TeamSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["name"]
    write_capability = "referentiel.update"
    action_write_capabilities = {"create": "referentiel.create"}
    # Un manager rattaché à des équipes ne voit que les siennes : la liste
    # qu'il consulte est celle dans laquelle il choisit pour ses dépenses.
    team_lookup = "pk"


class CostCenterViewSet(ScopedViewSet):
    queryset = CostCenter.objects.select_related("country").all().order_by("code")
    serializer_class = CostCenterSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["code", "name"]
    write_capability = "referentiel.update"
    action_write_capabilities = {"create": "referentiel.create"}


class ProjectViewSet(ScopedViewSet):
    queryset = Project.objects.select_related("country").all().order_by("-created_at")
    serializer_class = ProjectSerializer
    filterset_fields = ["country", "status", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["created_at", "name"]
    write_capability = "referentiel.update"
    action_write_capabilities = {"create": "referentiel.create"}


class ExpenseTitleViewSet(ScopedViewSet):
    queryset = ExpenseTitle.objects.select_related("country").all().order_by("label")
    serializer_class = ExpenseTitleSerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["label"]
    write_capability = "referentiel.update"
    action_write_capabilities = {"create": "referentiel.create"}


class MarketingCategoryViewSet(ScopedViewSet):
    queryset = (
        MarketingCategory.objects.select_related("country").all().order_by("name")
    )
    serializer_class = MarketingCategorySerializer
    filterset_fields = ["country", "is_active"]
    search_fields = ["name"]
    write_capability = "referentiel.update"
    action_write_capabilities = {"create": "referentiel.create"}


class ChangeLogViewSet(CountryScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Historique des changements de rattachement et de configuration."""

    queryset = ChangeLog.objects.select_related("country").all()
    serializer_class = ChangeLogSerializer
    permission_classes = [RolePermission]
    read_capability = "history.read"
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["country", "model_name", "action"]
    ordering_fields = ["created_at"]

    #: Entrées qui relèvent de l'administration : la vie des comptes (rôles,
    #: périmètres, 2FA) et la politique du workflow. Qui ne gère ni l'un ni
    #: l'autre n'a pas à les lire — la liste des comptes lui est fermée, son
    #: historique aussi.
    ENTREES_D_ADMINISTRATION = (
        ChangeLog.Models.USER,
        ChangeLog.Models.WORKFLOW_CONFIGURATION,
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        access = get_access(self.request.user)
        if access is None:
            return queryset
        if access.role not in roles_pour("configuration.manage"):
            queryset = queryset.exclude(model_name__in=self.ENTREES_D_ADMINISTRATION)
        return queryset

