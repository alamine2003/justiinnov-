"""Vues des budgets, réallocations et taux de change.

Le circuit d'une réallocation — demande, approbation, refus — est dans
``budget.transitions`` (décision 41) ; la vue trouve l'objet dans le
périmètre, lit la charge utile, appelle le service et répond.
"""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import BUDGET_WRITE_ROLES, RolePermission, get_access
from accounts.scoping import CountryScopedMixin
from core.journal import Trace
from core.mixins import NoDestroyModelViewSet
from core.regles import traduire_les_regles

from . import transitions
from .aggregates import consolidation_par_pays, current_rates
from .models import Budget, BudgetReallocation, ExchangeRate
from .serializers import (
    BudgetReallocationSerializer,
    BudgetSerializer,
    BudgetSummarySerializer,
    ExchangeRateSerializer,
    ReallocationDecisionSerializer,
)


class BudgetViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Enveloppes annuelles et sous-enveloppes par projet."""

    queryset = (
        Budget.objects.select_related(
            "country", "project", "team", "manager"
        ).with_consumption()
    )
    serializer_class = BudgetSerializer
    permission_classes = [RolePermission]
    write_roles = BUDGET_WRITE_ROLES
    filterset_fields = [
        "country", "country__country_ref", "year", "project", "team",
        "manager", "is_active",
    ]
    search_fields = ["country__name", "country__country_ref", "project__name"]
    ordering_fields = ["year", "amount", "created_at"]

    def get_queryset(self):
        # Pas le ``distinct()`` de ``CountryScopedMixin`` : le pays est porté
        # par l'enveloppe, le filtre ne multiplie rien, et un DISTINCT sur
        # les agrégats de ``with_consumption`` coûterait un tri pour rien.
        return self.queryset.visible_par(self.request.user)

    def get_serializer_context(self):
        # Les taux de change sont lus une fois par requête, pas une fois par
        # enveloppe affichée.
        return {**super().get_serializer_context(), "rates": current_rates()}

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "year", int, description="Exercice consolidé ; l'année en cours par défaut."
            )
        ],
        responses=BudgetSummarySerializer,
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Consolidation par pays, avec total en FCFA (§5.6).

        Porte sur **une** année : celle de ``?year=``, sinon l'année en cours.
        Sans ce garde-fou, l'absence de paramètre additionnait toutes les
        années d'un même pays comme s'il s'agissait d'une seule enveloppe.
        """
        budgets = self.filter_queryset(self.get_queryset())
        if "year" not in request.query_params:
            budgets = budgets.filter(year=timezone.now().year)

        rows, consolidated = consolidation_par_pays(budgets, rates=current_rates())
        return Response({
            "countries": [
                {
                    "country": row["country"],
                    "country_name": row["country_name"],
                    "country_ref": row["country_ref"],
                    "currency": row["currency"],
                    "allocated": str(row["allocated"]),
                    "sub_allocated": str(row["sub_allocated"]),
                    "engaged": str(row["engaged"]),
                    "consumed": str(row["consumed"]),
                    "justified": str(row["justified"]),
                    "remaining": str(row["remaining"]),
                    "remaining_xof": _as_str(row["remaining_xof"]),
                }
                for row in rows
            ],
            "total_remaining_xof": str(consolidated["remaining"]),
            # Devises sans taux connu : leur montant n'entre pas dans le total,
            # plutôt que d'y être absorbé silencieusement.
            "unconverted_currencies": consolidated["unconverted_currencies"],
        })


def _as_str(value):
    return str(value) if value is not None else None


class BudgetReallocationViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Transferts entre enveloppes, soumis à approbation."""

    queryset = BudgetReallocation.objects.select_related(
        "source__country", "target__country"
    ).all()
    serializer_class = BudgetReallocationSerializer
    permission_classes = [RolePermission]
    write_roles = BUDGET_WRITE_ROLES
    filterset_fields = ["status", "source__country", "target__country"]
    ordering_fields = ["created_at", "amount"]
    country_lookup = "source__country"
    country_field = None

    def perform_create(self, serializer):
        donnees = serializer.validated_data
        with traduire_les_regles():
            resultat = transitions.demander(
                donnees["source"], donnees["target"], donnees["amount"],
                donnees["reason"], get_access(self.request.user),
                Trace.depuis_requete(self.request),
            )
        serializer.instance = resultat.instance

    def _decider(self, request, service):
        """Approbation ou refus : périmètre, motif, service, réponse."""
        visible = self.get_object()
        serializer = ReallocationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with traduire_les_regles():
            resultat = service(
                visible, get_access(request.user),
                serializer.validated_data.get("note", ""),
                Trace.depuis_requete(request),
            )
        return Response(self.get_serializer(resultat.instance).data)

    @extend_schema(request=ReallocationDecisionSerializer, responses=BudgetReallocationSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approuve et exécute le transfert."""
        return self._decider(request, transitions.approuver)

    @extend_schema(request=ReallocationDecisionSerializer, responses=BudgetReallocationSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Refuse le transfert. Le motif est obligatoire (§5.5)."""
        return self._decider(request, transitions.refuser)


class ExchangeRateViewSet(NoDestroyModelViewSet):
    """Taux de conversion vers le FCFA, tenus par la direction.

    Un taux change la valeur consolidée de toutes les enveloppes : il relève
    de ceux qui les attribuent, pas de la RH ni du contrôle.
    """

    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    permission_classes = [RolePermission]
    write_roles = BUDGET_WRITE_ROLES
    filterset_fields = ["currency"]
    ordering_fields = ["currency", "valid_from"]
