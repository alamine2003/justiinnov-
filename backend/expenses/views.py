"""Vues des dossiers, dépenses, justificatifs et journal d'audit."""

from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
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
from .mixins import DraftDeletableViewSet
from .models import AuditLog, Beneficiary, Dossier, Expense, Proof
from .serializers import (
    AuditLogSerializer,
    BeneficiarySerializer,
    DossierDetailSerializer,
    DossierSerializer,
    ExpenseRegisterSerializer,
    ExpenseSerializer,
    ProofReviewSerializer,
    ProofSerializer,
    TransitionSerializer,
)
from .services import attach_budget, check_budget_capacity
from .workflow import LOCKED_STATUSES, Status, TransitionError, next_status

#: Rôle habilité pour chaque action du workflow.
ACTION_ROLES = {
    "submit": EXPENSE_WRITE_ROLES,
    "review": VALIDATION_ROLES,
    "justify": VALIDATION_ROLES,
    "reject": VALIDATION_ROLES,
    "close": VALIDATION_ROLES,
}

#: Signalé au pays quand il soumet sans pièce. La soumission passe quand même :
#: bloquer reviendrait à ce qu'une dépense sans reçu ne soit jamais déclarée,
#: donc à ce que l'argent sorte sans laisser de trace — pire que l'écart.
SANS_PREUVE = (
    "Aucun justificatif n'est joint : la dépense est déclarée sans preuve, "
    "elle creusera l'écart et sera signalée au siège."
)


def _sans_preuve(dossier):
    """Le dossier est-il dépourvu de pièce exploitable ?"""
    return not dossier.proofs.exclude(
        status__in=[Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED]
    ).exists()


#: Action de workflow → action d'audit.
AUDIT_ACTIONS = {
    "submit": AuditLog.Action.SUBMITTED,
    "review": AuditLog.Action.REVIEWED,
    "justify": AuditLog.Action.JUSTIFIED,
    "reject": AuditLog.Action.UNJUSTIFIED,
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
    def justify(self, request, pk=None):
        return self.perform_transition(request, "justify")

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


class DossierViewSet(WorkflowMixin, CountryScopedMixin, DraftDeletableViewSet):
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

    # Un dossier ne porte pas d'auteur : le périmètre pays fait foi.
    author_field = None

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

    def perform_destroy(self, instance):
        record(
            self.request,
            AuditLog.Action.DELETED,
            instance,
            label=f"Brouillon supprimé — {instance}",
        )
        super().perform_destroy(instance)

    def before_transition(self, dossier, name, access):
        if name == "submit":
            return self._soumettre_les_lignes(dossier, access)

        if name == "close":
            self._refuser_les_lignes_en_suspens(dossier)

        if name == "justify" and not dossier.proofs.exclude(
            status=Proof.ProofStatus.REJECTED
        ).exists():
            # Justifier un dossier sans preuve viderait de son sens l'ensemble
            # documentaire que le N°ORDRE représente.
            raise ValidationError(
                {"proofs": "Un dossier ne peut être justifié sans justificatif."}
            )
        return None

    def _refuser_les_lignes_en_suspens(self, dossier):
        """Un dossier ne se clôture pas sur une ligne non tranchée.

        Clôturer, c'est déclarer l'affaire terminée. Une ligne encore en
        brouillon, soumise ou en contrôle n'a pas été tranchée : la classer
        avec le dossier reviendrait à perdre la dépense de vue sans jamais
        dire si elle est justifiée.
        """
        en_suspens = dossier.expenses.exclude(
            status__in=[Status.JUSTIFIED, Status.UNJUSTIFIED, Status.CLOSED]
        )
        if not en_suspens.exists():
            return
        detail = ", ".join(
            f"{e.title} ({e.get_status_display().lower()})" for e in en_suspens[:5]
        )
        raise ValidationError(
            {
                "expenses": (
                    f"{en_suspens.count()} ligne(s) ne sont pas tranchées : "
                    f"{detail}. Justifiez-les ou marquez-les non justifiées "
                    "avant de clôturer."
                )
            }
        )

    def _soumettre_les_lignes(self, dossier, access):
        """Le dossier et ses lignes partent ensemble.

        Côté pays, déclarer une dépense doit tenir en une action : remplir les
        lignes, joindre la pièce, soumettre. Soumettre chaque ligne puis le
        dossier serait une cérémonie sans objet.
        """
        lignes = list(dossier.expenses.all())
        if not lignes:
            raise ValidationError(
                {
                    "expenses": (
                        "Un dossier se soumet avec ses lignes de dépenses : "
                        "ajoutez-en au moins une."
                    )
                }
            )

        avertissements = []
        for expense in lignes:
            if expense.status != Status.DRAFT:
                continue
            budget = attach_budget(expense)
            # Verrou : deux soumissions simultanées ne doivent pas franchir la
            # même enveloppe chacune de leur côté.
            budget = Budget.objects.select_for_update().get(pk=budget.pk)
            expense.budget = budget
            avertissement = check_budget_capacity(expense, budget, access.role)
            if avertissement:
                avertissements.append(avertissement)

            expense.status = Status.SUBMITTED
            expense.save()
            record(
                self.request,
                AuditLog.Action.SUBMITTED,
                expense,
                from_status=Status.DRAFT,
                to_status=Status.SUBMITTED,
                note="soumise avec son dossier",
            )

        if _sans_preuve(dossier):
            avertissements.append(SANS_PREUVE)
        return " ".join(avertissements) or None

    def after_transition(self, request, dossier, name, note):
        if name == "submit":
            triggers.dossier_submitted(dossier, request.user)


class ExpenseViewSet(WorkflowMixin, CountryScopedMixin, DraftDeletableViewSet):
    """Lignes de dépenses."""

    queryset = Expense.objects.select_related(
        "dossier", "country", "team", "owner", "project", "beneficiary", "budget"
    ).all()
    serializer_class = ExpenseSerializer
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES
    # Forme étendue : le §5.6 demande de filtrer par période et par état
    # multiple, ce qu'une simple liste de champs ne permet pas.
    filterset_fields = {
        "country": ["exact"],
        "country__country_ref": ["exact"],
        "dossier": ["exact"],
        "dossier__number": ["exact"],
        "status": ["exact", "in"],
        "team": ["exact"],
        "owner": ["exact"],
        "project": ["exact"],
        "beneficiary": ["exact"],
        "expense_title": ["exact"],
        "marketing_category": ["exact"],
        "payment_method": ["exact"],
        "date": ["gte", "lte"],
    }
    search_fields = ["title", "place", "description", "dossier__number"]
    ordering_fields = ["date", "amount", "created_at"]

    @action(detail=False, methods=["get"])
    def register(self, request):
        """Registre de justification : chaque dépense avec ses preuves.

        Le journal d'audit dit qui a fait quoi ; ce registre dit où est passé
        l'argent et ce qui l'atteste.
        """
        queryset = self.filter_queryset(
            self.get_queryset().prefetch_related("dossier__proofs")
        )
        page = self.paginate_queryset(queryset)
        serializer = ExpenseRegisterSerializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Enregistre une ligne, si son dossier l'accepte encore.

        Le contrôle du dossier vient après celui du périmètre, et non dans le
        sérialiseur : dire « ce dossier est déjà soumis » à quelqu'un qui n'a
        pas le droit de le voir révélerait son existence et son état.

        Sans ce refus, la ligne arrivait en brouillon dans un dossier déjà
        passé : plus rien ne pouvait la soumettre, et la dépense restait
        indéfiniment en suspens dans un dossier clos.
        """
        self._check_country_scope(serializer)
        dossier = serializer.validated_data.get("dossier")
        if dossier is not None and dossier.status in LOCKED_STATUSES:
            raise ValidationError(
                {
                    "dossier": (
                        f"Le dossier {dossier.number} est déjà déclaré "
                        f"({dossier.get_status_display().lower()}) : il "
                        "n'accepte plus de nouvelle ligne. Ouvrez un nouveau "
                        "dossier pour cette dépense."
                    )
                }
            )
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

    def perform_destroy(self, instance):
        record(
            self.request,
            AuditLog.Action.DELETED,
            instance,
            label=f"Brouillon supprimé — {instance}",
            amount=str(instance.amount),
        )
        super().perform_destroy(instance)

    def before_transition(self, expense, name, access):
        """Sépare la déclaration du contrôle, impute l'enveloppe et applique la
        politique de dépassement."""
        if name == "submit" and expense.dossier.status == Status.DRAFT:
            # Une ligne ne devance pas son dossier. Sans ce garde-fou, une
            # dépense pouvait être soumise puis justifiée alors que le pays
            # n'avait jamais rien déclaré : le dossier restait un brouillon
            # portant des lignes tranchées.
            raise ValidationError(
                {
                    "dossier": (
                        f"Le dossier {expense.dossier.number} est encore un "
                        "brouillon. Soumettez le dossier : ses lignes partent "
                        "avec lui."
                    )
                }
            )

        if name in ("justify", "reject") and expense.created_by:
            # Quatre yeux : décaisser puis se donner quitus soi-même n'est pas
            # un contrôle.
            if expense.created_by == self.request.user.username:
                raise PermissionDenied(
                    "Vous avez saisi cette dépense : son contrôle revient à "
                    "quelqu'un d'autre."
                )

        if name not in ("submit", "justify"):
            return None

        avertissements = []
        if name == "submit" and _sans_preuve(expense.dossier):
            avertissements.append(SANS_PREUVE)

        budget = attach_budget(expense)
        # Verrou sur l'enveloppe : sans lui, deux soumissions simultanées
        # liraient le même total engagé et franchiraient toutes deux une
        # enveloppe qu'une seule pouvait absorber.
        budget = Budget.objects.select_for_update().get(pk=budget.pk)
        expense.budget = budget
        # L'imputation est persistée par la sauvegarde de la transition.
        depassement = check_budget_capacity(
            expense, budget, access.role, at_approval=(name == "justify")
        )
        if depassement:
            avertissements.append(depassement)
        return " ".join(avertissements) or None

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
