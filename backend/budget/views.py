"""Vues des budgets, réallocations et taux de change."""

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.permissions import (
    BUDGET_WRITE_ROLES,
    REFERENTIAL_WRITE_ROLES,
    RolePermission,
    get_access,
)
from accounts.scoping import CountryScopedMixin
from core.mixins import NoDestroyModelViewSet
from notifications import triggers

from .aggregates import consolidation_par_pays, consumption, current_rates
from .models import Budget, BudgetReallocation, ExchangeRate
from .serializers import (
    BudgetReallocationSerializer,
    BudgetSerializer,
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
        serializer.save(requested_by=self.request.user.username)
        triggers.reallocation_requested(serializer.instance, self.request.user)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approuve et exécute le transfert."""
        serializer = ReallocationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            reallocation = self._verrouiller(request)
            # Les deux enveloppes sont verrouillées dans l'ordre de leurs
            # identifiants : deux réallocations croisées (A→B et B→A)
            # approuvées en même temps prendraient sinon les verrous en sens
            # inverse et s'interbloqueraient.
            budgets = {
                budget.pk: budget
                for budget in Budget.objects.select_for_update()
                .filter(pk__in=[reallocation.source_id, reallocation.target_id])
                .order_by("pk")
            }
            source = budgets[reallocation.source_id]
            target = budgets[reallocation.target_id]
            if reallocation.amount > disponible(source):
                # L'argent déjà sorti ou engagé n'est plus transférable : la
                # source doit pouvoir couvrir ses dépenses après le transfert.
                raise ValidationError(
                    {"amount": "Le disponible de l'enveloppe source ne couvre plus ce montant."}
                )
            source.amount -= reallocation.amount
            target.amount += reallocation.amount
            source.save(update_fields=["amount", "updated_at"])
            target.save(update_fields=["amount", "updated_at"])

            reallocation.status = BudgetReallocation.Status.APPROVED
            reallocation.decision_note = serializer.validated_data.get("note", "")
            self._stamp_decision(reallocation, request)

        return Response(self.get_serializer(reallocation).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Refuse le transfert. Le motif est obligatoire (§5.5)."""
        serializer = ReallocationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "").strip()
        if not note:
            raise ValidationError({"note": "Un refus doit être motivé."})

        with transaction.atomic():
            reallocation = self._verrouiller(request)
            reallocation.status = BudgetReallocation.Status.REJECTED
            reallocation.decision_note = note
            self._stamp_decision(reallocation, request)

        return Response(self.get_serializer(reallocation).data)

    def _verrouiller(self, request):
        """Relit la réallocation sous verrou et vérifie qu'elle se décide.

        Le statut est contrôlé **après** la prise du verrou : lu avant, deux
        approbations simultanées le verraient toutes deux « en attente » et
        exécuteraient le transfert deux fois. ``get_object`` reste appelé en
        premier pour le cloisonnement (404 hors périmètre).
        """
        visible = self.get_object()
        reallocation = BudgetReallocation.objects.select_for_update().get(
            pk=visible.pk
        )
        if reallocation.status != BudgetReallocation.Status.PENDING:
            raise ValidationError(
                {"status": "Cette réallocation a déjà été traitée."}
            )
        if reallocation.requested_by == request.user.username:
            # Demander et approuver sont deux regards : celui qui arbitre
            # n'est pas celui qui sollicite.
            raise PermissionDenied(
                "Vous ne pouvez pas décider d'une réallocation que vous avez "
                "demandée."
            )
        access = get_access(request.user)
        if access is not None and not access.has_global_scope:
            # Le queryset ne filtre que par le pays de la source ; la
            # destination doit être dans le périmètre elle aussi, et une
            # enveloppe hors périmètre n'existe pas pour le demandeur.
            if reallocation.target.country_id not in access.country_ids:
                raise NotFound()
        return reallocation

    def _stamp_decision(self, reallocation, request):
        reallocation.decided_by = request.user.username
        reallocation.decided_at = timezone.now()
        reallocation.save()


def disponible(budget):
    """Ce qu'une enveloppe peut encore céder : l'alloué moins le consommé
    et l'engagé. Recalculé sur l'instance verrouillée, hors annotations."""
    totals = consumption(budget)
    return budget.amount - totals["consumed"] - totals["engaged"]


class ExchangeRateViewSet(NoDestroyModelViewSet):
    """Taux de conversion vers le FCFA, saisis par le siège."""

    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    permission_classes = [RolePermission]
    write_roles = REFERENTIAL_WRITE_ROLES | BUDGET_WRITE_ROLES
    filterset_fields = ["currency"]
    ordering_fields = ["currency", "valid_from"]
