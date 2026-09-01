"""Vues des dossiers, dépenses, justificatifs et journal d'audit."""

from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import (
    AUDIT_READ_ROLES,
    EXPENSE_WRITE_ROLES,
    VALIDATION_ROLES,
    RolePermission,
    get_access,
)
from accounts.scoping import CountryScopedMixin
from budget.models import Budget
from core.mixins import NoDestroyModelViewSet
from notifications import triggers

from .audit import record
from .models import AuditLog, Beneficiary, Dossier, Expense, Proof
from .serializers import (
    AuditLogSerializer,
    BeneficiarySerializer,
    DossierDetailSerializer,
    DossierSerializer,
    ExpenseSerializer,
    ProofReviewSerializer,
    ProofSerializer,
    TransitionSerializer,
)
from .services import attach_budget, check_budget_capacity
from .workflow import TransitionError, next_status

#: Rôle habilité pour chaque action du workflow.
ACTION_ROLES = {
    "submit": EXPENSE_WRITE_ROLES,
    "review": VALIDATION_ROLES,
    "approve": VALIDATION_ROLES,
    "reject": VALIDATION_ROLES,
    "close": VALIDATION_ROLES,
}

#: Action de workflow → action d'audit.
AUDIT_ACTIONS = {
    "submit": AuditLog.Action.SUBMITTED,
    "review": AuditLog.Action.REVIEWED,
    "approve": AuditLog.Action.APPROVED,
    "reject": AuditLog.Action.REJECTED,
    "close": AuditLog.Action.CLOSED,
}


class WorkflowMixin:
    """Transitions d'état, journalisées et contrôlées côté serveur."""

    action_write_roles = ACTION_ROLES

    @transaction.atomic
    def perform_transition(self, request, name):
        instance = self.get_object()
        # Le rôle a déjà été vérifié par RolePermission via action_write_roles.
        access = get_access(request.user)

        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.get("note", "").strip()
        if name == "reject" and not note:
            raise ValidationError({"note": "Un rejet doit être motivé."})

        try:
            target = next_status(name, instance.status)
        except TransitionError as exc:
            raise ValidationError({"status": str(exc)}) from exc

        previous = instance.status
        warning = self.before_transition(instance, name, access)

        instance.status = target
        if note:
            instance.note = note
        instance.save()

        record(
            request,
            AUDIT_ACTIONS[name],
            instance,
            country=self.audit_country(instance),
            from_status=previous,
            to_status=target,
            note=note,
        )

        self.after_transition(request, instance, name, note)

        data = self.get_serializer(instance).data
        if warning:
            data = {**data, "warning": warning}
        return Response(data)

    def before_transition(self, instance, name, access):
        """Contrôles propres à la ressource. Renvoie un avertissement ou None."""
        return None

    def after_transition(self, request, instance, name, note):
        """Effets de bord une fois la transition acquise (notifications)."""

    def audit_country(self, instance):
        return instance.country

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self.perform_transition(request, "submit")

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        return self.perform_transition(request, "review")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.perform_transition(request, "approve")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.perform_transition(request, "reject")

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self.perform_transition(request, "close")


class BeneficiaryViewSet(NoDestroyModelViewSet):
    """Prospects et bénéficiaires — référentiel commun à tous les pays."""

    queryset = Beneficiary.objects.all()
    serializer_class = BeneficiarySerializer
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES
    filterset_fields = ["kind", "is_active"]
    search_fields = ["name", "contact"]
    ordering_fields = ["name", "created_at"]


class DossierViewSet(WorkflowMixin, CountryScopedMixin, NoDestroyModelViewSet):
    """Dossiers de justification (N°ORDRE)."""

    queryset = (
        Dossier.objects.select_related("country", "team", "owner").with_totals()
    )
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES
    filterset_fields = [
        "country", "country__country_ref", "status", "team", "owner",
    ]
    search_fields = ["number", "label"]
    ordering_fields = ["date", "number", "created_at"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DossierDetailSerializer
        return DossierSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "retrieve":
            # Le détail sérialise chaque ligne avec son contexte : sans
            # `select_related` sur la sous-requête, chaque ligne rouvrirait
            # une requête par relation affichée.
            return queryset.prefetch_related(
                Prefetch(
                    "expenses",
                    queryset=Expense.objects.select_related(
                        "dossier", "country", "team", "owner", "project",
                        "beneficiary", "budget__country", "budget__project",
                    ),
                ),
                "proofs",
            )
        return queryset

    def perform_create(self, serializer):
        super().perform_create(serializer)
        record(self.request, AuditLog.Action.CREATED, serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        record(self.request, AuditLog.Action.UPDATED, serializer.instance)

    def before_transition(self, dossier, name, access):
        if name == "approve" and not dossier.proofs.exclude(
            status=Proof.ProofStatus.REJECTED
        ).exists():
            # Valider un dossier sans preuve viderait de son sens l'ensemble
            # documentaire que le N°ORDRE représente.
            raise ValidationError(
                {"proofs": "Un dossier ne peut être validé sans justificatif."}
            )
        return None


class ExpenseViewSet(WorkflowMixin, CountryScopedMixin, NoDestroyModelViewSet):
    """Lignes de dépenses."""

    queryset = Expense.objects.select_related(
        "dossier", "country", "team", "owner", "project", "beneficiary", "budget"
    ).all()
    serializer_class = ExpenseSerializer
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES
    filterset_fields = [
        "country", "country__country_ref", "dossier", "status", "team", "owner",
        "project", "beneficiary", "expense_title", "marketing_category",
        "payment_method",
    ]
    search_fields = ["title", "place", "description", "dossier__number"]
    ordering_fields = ["date", "amount", "created_at"]

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        serializer.save(created_by=self.request.user.username)
        record(self.request, AuditLog.Action.CREATED, serializer.instance)

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        stored = Expense.objects.get(pk=serializer.instance.pk)
        previous = {
            "amount": str(stored.amount),
            "justified_amount": str(stored.justified_amount),
        }
        serializer.save()
        record(
            self.request,
            AuditLog.Action.UPDATED,
            serializer.instance,
            before=previous,
            after={
                "amount": str(serializer.instance.amount),
                "justified_amount": str(serializer.instance.justified_amount),
            },
        )

    def before_transition(self, expense, name, access):
        """Impute l'enveloppe et applique la politique de dépassement."""
        if name not in ("submit", "approve"):
            return None
        budget = attach_budget(expense)
        # Verrou sur l'enveloppe : sans lui, deux soumissions simultanées
        # liraient le même total engagé et franchiraient toutes deux une
        # enveloppe qu'une seule pouvait absorber.
        budget = Budget.objects.select_for_update().get(pk=budget.pk)
        expense.budget = budget
        # L'imputation est persistée par la sauvegarde de la transition.
        return check_budget_capacity(
            expense, budget, access.role, at_approval=(name == "approve")
        )

    def after_transition(self, request, expense, name, note):
        if name == "submit":
            triggers.expense_submitted(expense, request.user)
        elif name == "reject":
            triggers.expense_rejected(expense, request.user, note)


class ProofViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Pièces justificatives, rattachées au dossier."""

    queryset = Proof.objects.select_related("dossier__country").all()
    serializer_class = ProofSerializer
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES
    filterset_fields = ["dossier", "kind", "status", "is_complete"]
    search_fields = ["original_name", "dossier__number"]
    ordering_fields = ["created_at", "version"]
    # La preuve n'a pas de pays propre : elle suit celui de son dossier.
    country_lookup = "dossier__country"
    country_field = None
    country_via = "dossier"
    # Le contrôle documentaire relève du contrôleur, pas du déposant.
    action_write_roles = {"review": VALIDATION_ROLES}

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        replaced = serializer.validated_data.get("replaces")
        serializer.save(
            uploaded_by=self.request.user.username,
            version=replaced.version + 1 if replaced else 1,
        )
        proof = serializer.instance
        if replaced is not None:
            replaced.status = Proof.ProofStatus.ARCHIVED
            replaced.save(update_fields=["status", "updated_at"])
        record(
            self.request,
            AuditLog.Action.PROOF_REPLACED if replaced else AuditLog.Action.PROOF_UPLOADED,
            proof,
            country=proof.dossier.country,
            dossier=proof.dossier.number,
            sha256=proof.sha256,
            version=proof.version,
        )

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        serializer.save()
        record(
            self.request,
            AuditLog.Action.UPDATED,
            serializer.instance,
            country=serializer.instance.dossier.country,
        )

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Contrôle documentaire : valide, rejette ou signale un justificatif."""
        proof = self.get_object()

        serializer = ProofReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "").strip()

        previous = proof.status
        proof.status = target
        proof.rejection_reason = reason if target == Proof.ProofStatus.REJECTED else ""
        proof.is_complete = target != Proof.ProofStatus.INCOMPLETE
        proof.save()

        record(
            request,
            AuditLog.Action.APPROVED
            if target == Proof.ProofStatus.VALIDATED
            else AuditLog.Action.REJECTED,
            proof,
            country=proof.dossier.country,
            from_status=previous,
            to_status=target,
            reason=reason,
        )
        return Response(self.get_serializer(proof).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Téléchargement contrôlé (§5.4).

        Le fichier transite par cette vue plutôt que par une URL signée : le
        périmètre est ainsi vérifié à chaque accès, et chaque téléchargement
        laisse une trace d'audit.
        """
        proof = self.get_object()
        record(
            request,
            AuditLog.Action.DOWNLOADED,
            proof,
            country=proof.dossier.country,
            sha256=proof.sha256,
        )
        return FileResponse(
            proof.file.open("rb"),
            as_attachment=True,
            filename=proof.original_name or proof.file.name.rsplit("/", 1)[-1],
        )


class AuditLogViewSet(CountryScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Journal d'audit — consultation par le siège et les auditeurs."""

    queryset = AuditLog.objects.select_related("country").all()
    serializer_class = AuditLogSerializer
    permission_classes = [RolePermission]
    read_roles = AUDIT_READ_ROLES
    filterset_fields = ["user", "action", "object_type", "country"]
    search_fields = ["label", "user"]
    ordering_fields = ["created_at"]
