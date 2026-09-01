"""Vues des budgets, réallocations et taux de change."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import (
    BUDGET_WRITE_ROLES,
    REFERENTIAL_WRITE_ROLES,
    RolePermission,
)
from accounts.scoping import CountryScopedMixin
from core.mixins import NoDestroyModelViewSet

from .aggregates import budget_figures, to_xof
from .models import Budget, BudgetReallocation, ExchangeRate
from .serializers import (
    BudgetReallocationSerializer,
    BudgetSerializer,
    ExchangeRateSerializer,
    ReallocationDecisionSerializer,
)

ZERO = Decimal("0.00")


class BudgetViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Enveloppes annuelles et sous-enveloppes par projet."""

    queryset = (
        Budget.objects.select_related("country", "project").with_consumption()
    )
    serializer_class = BudgetSerializer
    permission_classes = [RolePermission]
    write_roles = BUDGET_WRITE_ROLES
    filterset_fields = ["country", "year", "project", "is_active"]
    search_fields = ["country__name", "country__country_ref", "project__name"]
    ordering_fields = ["year", "amount", "created_at"]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Consolidation par pays, avec total en FCFA (§5.6).

        Seules les enveloppes de pays (sans projet) composent le total : les
        sous-enveloppes en sont un découpage et seraient comptées deux fois.
        """
        budgets = self.filter_queryset(self.get_queryset())

        per_country = defaultdict(
            lambda: {"allocated": ZERO, "sub_allocated": ZERO, "engaged": ZERO,
                     "consumed": ZERO, "justified": ZERO}
        )
        countries = {}
        for budget in budgets:
            entry = per_country[budget.country_id]
            countries[budget.country_id] = budget.country
            if budget.project_id is None:
                entry["allocated"] += budget.amount
            else:
                entry["sub_allocated"] += budget.amount
            figures = budget_figures(budget)
            entry["engaged"] += figures["engaged"]
            entry["consumed"] += figures["consumed"]
            entry["justified"] += figures["justified"]

        rows = []
        total_xof = ZERO
        unconverted = set()
        for country_id, entry in per_country.items():
            country = countries[country_id]
            remaining = entry["allocated"] - entry["consumed"] - entry["engaged"]
            remaining_xof = to_xof(remaining, country.currency)
            if remaining_xof is None:
                unconverted.add(country.currency)
            else:
                total_xof += remaining_xof
            rows.append({
                "country": country_id,
                "country_name": country.name,
                "country_ref": country.country_ref,
                "currency": country.currency,
                "allocated": str(entry["allocated"]),
                "sub_allocated": str(entry["sub_allocated"]),
                "engaged": str(entry["engaged"]),
                "consumed": str(entry["consumed"]),
                "justified": str(entry["justified"]),
                "remaining": str(remaining),
                "remaining_xof": str(remaining_xof) if remaining_xof is not None else None,
            })

        rows.sort(key=lambda row: row["country_name"])
        return Response({
            "countries": rows,
            "total_remaining_xof": str(total_xof),
            # Devises sans taux connu : leur montant n'entre pas dans le total,
            # plutôt que d'y être absorbé silencieusement.
            "unconverted_currencies": sorted(unconverted),
        })


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

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approuve et exécute le transfert."""
        reallocation = self.get_object()
        self._check_pending(reallocation)

        serializer = ReallocationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Verrou : deux approbations simultanées ne doivent pas vider la
            # même enveloppe source deux fois.
            source = Budget.objects.select_for_update().get(pk=reallocation.source_id)
            target = Budget.objects.select_for_update().get(pk=reallocation.target_id)
            if reallocation.amount > source.amount:
                raise ValidationError(
                    {"amount": "L'enveloppe source ne couvre plus ce montant."}
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
        reallocation = self.get_object()
        self._check_pending(reallocation)

        serializer = ReallocationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "").strip()
        if not note:
            raise ValidationError({"note": "Un refus doit être motivé."})

        reallocation.status = BudgetReallocation.Status.REJECTED
        reallocation.decision_note = note
        self._stamp_decision(reallocation, request)

        return Response(self.get_serializer(reallocation).data)

    def _check_pending(self, reallocation):
        if reallocation.status != BudgetReallocation.Status.PENDING:
            raise ValidationError(
                {"status": "Cette réallocation a déjà été traitée."}
            )

    def _stamp_decision(self, reallocation, request):
        reallocation.decided_by = request.user.username
        reallocation.decided_at = timezone.now()
        reallocation.save()


class ExchangeRateViewSet(NoDestroyModelViewSet):
    """Taux de conversion vers le FCFA, saisis par le siège."""

    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    permission_classes = [RolePermission]
    write_roles = REFERENTIAL_WRITE_ROLES | BUDGET_WRITE_ROLES
    filterset_fields = ["currency"]
    ordering_fields = ["currency", "valid_from"]
