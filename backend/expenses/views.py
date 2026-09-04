"""Vues des dossiers, dépenses, justificatifs et journal d'audit."""

from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse
from django.utils import timezone
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
from core.models import WorkflowConfiguration
from notifications import triggers

from .audit import enregistrer, preparer, record
from .mixins import DraftDeletableViewSet
from .models import ZERO, AuditLog, Beneficiary, Dossier, Expense, Proof
from .serializers import (
    AuditLogSerializer,
    BeneficiarySerializer,
    DossierDetailSerializer,
    DossierSerializer,
    ExpenseRegisterSerializer,
    ExpenseSerializer,
    ExpenseTransitionSerializer,
    ProofReviewSerializer,
    ProofSerializer,
    TransitionSerializer,
)
from .services import (
    attach_budget,
    check_budget_capacity,
    cle_d_imputation,
    committed_total,
)
from .workflow import (
    LOCKED_STATUSES,
    Status,
    TransitionError,
    next_proof_status,
    next_status,
)

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

#: Relations chargées avec chaque ligne : tout ce que le sérialiseur affiche.
#: Sans elles, chaque ligne d'une liste rouvrait une requête par relation.
EXPENSE_RELATIONS = (
    "dossier", "country", "team", "owner", "project",
    "expense_title", "marketing_category", "beneficiary",
    "budget__country", "budget__project", "budget__team", "budget__manager",
)


def _sans_preuve(dossier):
    """Le dossier est-il dépourvu de pièce exploitable ?"""
    return not dossier.proofs.exclude(
        status__in=[Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED]
    ).exists()


def _refuser_un_dossier_declare(dossier):
    """Une ligne ne rejoint qu'un dossier encore en brouillon.

    Sans ce refus, la ligne arrivait en brouillon dans un dossier déjà
    passé : plus rien ne pouvait la soumettre, et la dépense restait
    indéfiniment en suspens dans un dossier clos.
    """
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


#: Action de workflow → action d'audit.
AUDIT_ACTIONS = {
    "submit": AuditLog.Action.SUBMITTED,
    "review": AuditLog.Action.REVIEWED,
    "justify": AuditLog.Action.JUSTIFIED,
    "reject": AuditLog.Action.UNJUSTIFIED,
    "close": AuditLog.Action.CLOSED,
}

#: État visé d'une pièce → action d'audit.
PROOF_AUDIT_ACTIONS = {
    Proof.ProofStatus.VALIDATED: AuditLog.Action.APPROVED,
    Proof.ProofStatus.REJECTED: AuditLog.Action.REJECTED,
    Proof.ProofStatus.INCOMPLETE: AuditLog.Action.PROOF_INCOMPLETE,
    Proof.ProofStatus.TO_REVIEW: AuditLog.Action.PROOF_TO_REVIEW,
}


class WorkflowMixin:
    """Transitions d'état, journalisées et contrôlées côté serveur."""

    action_write_roles = ACTION_ROLES
    transition_serializer_class = TransitionSerializer

    def lock_queryset(self):
        """Queryset servant à relire l'objet sous verrou.

        Distinct de ``get_queryset`` : les annotations d'agrégat des listes
        ne se combinent pas avec ``FOR UPDATE``.
        """
        return self.queryset.model._default_manager.all()

    def verrouiller(self, pk):
        """Relit l'objet sous verrou, dans la transaction en cours.

        ``get_object`` a déjà vérifié le périmètre ; mais l'instance qu'il
        renvoie a été lue avant le verrou. Deux contrôleurs qui tranchent la
        même ligne au même instant liraient tous deux « soumise » et
        passeraient tous deux : le second écraserait le premier sans que le
        journal ne le dise.
        """
        return self.lock_queryset().select_for_update(of=("self",)).get(pk=pk)

    @transaction.atomic
    def perform_transition(self, request, name):
        visible = self.get_object()
        instance = self.verrouiller(visible.pk)
        # Le rôle a déjà été vérifié par RolePermission via action_write_roles.
        access = get_access(request.user)

        serializer = self.transition_serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        note = donnees.get("note", "").strip()
        if name == "reject" and not note:
            raise ValidationError({"note": "Un rejet doit être motivé."})

        try:
            target = next_status(
                name, instance.status, WorkflowConfiguration.charger()
            )
        except TransitionError as exc:
            raise ValidationError({"status": str(exc)}) from exc

        previous = instance.status
        avant = self.audit_snapshot(instance)
        warning = self.before_transition(instance, name, access, donnees)

        instance.status = target
        self.apply_decision(instance, name, note, donnees)
        instance.save()

        record(
            request,
            AUDIT_ACTIONS[name],
            instance,
            country=self.audit_country(instance),
            from_status=previous,
            to_status=target,
            note=note,
            before=avant,
            after=self.audit_snapshot(instance),
        )

        self.after_transition(request, instance, name, note)

        data = self.get_serializer(instance).data
        if warning:
            data = {**data, "warning": warning}
        return Response(data)

    def before_transition(self, instance, name, access, donnees):
        """Contrôles propres à la ressource. Renvoie un avertissement ou None."""
        return None

    def apply_decision(self, instance, name, note, donnees):
        """Reporte la décision du contrôleur sur l'instance, avant sauvegarde."""
        if note:
            instance.note = note

    def audit_snapshot(self, instance):
        """Valeurs dont le journal doit garder l'avant et l'après."""
        return {"status": instance.status}

    def after_transition(self, request, instance, name, note):
        """Effets de bord une fois la transition acquise (notifications)."""

    def audit_country(self, instance):
        return instance.country

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


class BeneficiaryViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Prospects, clients, fournisseurs et bénéficiaires d'un pays.

    Le référentiel était commun : un pays lisait les fournisseurs et les
    prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
    Il est cloisonné comme le reste.
    """

    queryset = Beneficiary.objects.select_related("country").all()
    serializer_class = BeneficiarySerializer
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES
    filterset_fields = ["kind", "is_active", "country"]
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

    # Seul celui qui a ouvert un dossier peut retirer son brouillon.
    author_field = "created_by"

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
                    queryset=Expense.objects.select_related(*EXPENSE_RELATIONS),
                ),
                "proofs",
            )
        return queryset

    def lock_queryset(self):
        return Dossier.objects.select_related("country", "team", "owner")

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Déclare le dossier : ses lignes partent avec lui."""
        return self.perform_transition(request, "submit")

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        serializer.save(created_by=self.request.user.username)
        record(self.request, AuditLog.Action.CREATED, serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        record(self.request, AuditLog.Action.UPDATED, serializer.instance)

    @transaction.atomic
    def perform_destroy(self, dossier):
        """Retire un brouillon de dossier avec ce qu'il contient.

        Les lignes sont protégées en base contre la cascade : elles sont
        retirées une à une, chacune laissant sa trace. Un brouillon ne se
        retire pas s'il porte la ligne d'un autre auteur — ce serait effacer
        le travail de quelqu'un d'autre sous couvert de ranger le sien.
        """
        utilisateur = self.request.user.username
        lignes = list(dossier.expenses.select_related("country"))
        autrui = [
            ligne for ligne in lignes
            if ligne.created_by and ligne.created_by != utilisateur
        ]
        if autrui:
            raise PermissionDenied(
                "Ce dossier contient des lignes saisies par quelqu'un "
                f"d'autre ({autrui[0].created_by}) : il ne peut pas être "
                "supprimé."
            )
        declarees = [ligne for ligne in lignes if ligne.status != Status.DRAFT]
        if declarees:
            raise ValidationError(
                {"expenses": "Ce dossier contient une ligne déclarée : il ne "
                 "peut plus être supprimé."}
            )

        for ligne in lignes:
            record(
                self.request,
                AuditLog.Action.DELETED,
                ligne,
                label=f"Brouillon supprimé avec son dossier — {ligne}",
                amount=str(ligne.amount),
                dossier=dossier.number,
            )
            ligne.delete()

        # La plus récente d'abord : une nouvelle version référence celle
        # qu'elle remplace, et cette référence est protégée.
        for piece in dossier.proofs.select_related("dossier__country").order_by("-pk"):
            record(
                self.request,
                AuditLog.Action.DELETED,
                piece,
                label=f"Justificatif supprimé avec son dossier — {piece}",
                country=dossier.country,
                sha256=piece.sha256,
                version=piece.version,
                dossier=dossier.number,
            )
            # Le fichier ne doit pas survivre à sa fiche : un stockage qui
            # garde des pièces orphelines finit par en servir à tort.
            piece.file.delete(save=False)
            piece.delete()

        record(
            self.request,
            AuditLog.Action.DELETED,
            dossier,
            label=f"Brouillon supprimé — {dossier}",
            lines=len(lignes),
        )
        super().perform_destroy(dossier)

    def audit_snapshot(self, dossier):
        return {"status": dossier.status, "note": dossier.note}

    def before_transition(self, dossier, name, access, donnees):
        if name == "submit":
            return self._soumettre_les_lignes(dossier, access)

        if name == "close":
            self._refuser_les_lignes_en_suspens(dossier)

        if name in ("justify", "reject"):
            self._quatre_yeux(dossier)

        if name == "justify":
            if _sans_preuve(dossier):
                # Justifier un dossier sans preuve viderait de son sens
                # l'ensemble documentaire que le N°ORDRE représente. Une
                # pièce rejetée ou archivée n'en est pas une.
                raise ValidationError(
                    {"proofs": "Un dossier ne peut être justifié sans justificatif."}
                )
            self._exiger_les_lignes(
                dossier,
                attendus=[Status.JUSTIFIED, Status.CLOSED],
                consigne="Justifiez chaque ligne avant le dossier.",
            )

        if name == "reject":
            self._exiger_les_lignes(
                dossier,
                attendus=[Status.JUSTIFIED, Status.UNJUSTIFIED, Status.CLOSED],
                consigne="Tranchez chaque ligne avant de constater la "
                "non-justification du dossier.",
            )
        return None

    def _quatre_yeux(self, dossier):
        """Celui qui a ouvert le dossier ne le tranche pas."""
        if dossier.created_by and dossier.created_by == self.request.user.username:
            raise PermissionDenied(
                "Vous avez ouvert ce dossier : son contrôle revient à "
                "quelqu'un d'autre."
            )

    def _exiger_les_lignes(self, dossier, *, attendus, consigne):
        """Le dossier ne dit pas autre chose que ses lignes.

        Un dossier « justifié » portant une ligne encore soumise mentirait :
        le total justifié, lui, n'aurait pas bougé.
        """
        en_suspens = dossier.expenses.exclude(status__in=attendus)
        if not en_suspens.exists():
            return
        detail = ", ".join(
            f"{e.title} ({e.get_status_display().lower()})" for e in en_suspens[:5]
        )
        raise ValidationError(
            {
                "expenses": (
                    f"{en_suspens.count()} ligne(s) ne sont pas dans l'état "
                    f"attendu : {detail}. {consigne}"
                )
            }
        )

    def _refuser_les_lignes_en_suspens(self, dossier):
        """Un dossier ne se clôture pas sur une ligne non tranchée.

        Clôturer, c'est déclarer l'affaire terminée. Une ligne encore en
        brouillon, soumise ou en contrôle n'a pas été tranchée : la classer
        avec le dossier reviendrait à perdre la dépense de vue sans jamais
        dire si elle est justifiée.
        """
        self._exiger_les_lignes(
            dossier,
            attendus=[Status.JUSTIFIED, Status.UNJUSTIFIED, Status.CLOSED],
            consigne="Justifiez-les ou marquez-les non justifiées avant de "
            "clôturer.",
        )

    def _soumettre_les_lignes(self, dossier, access):
        """Le dossier et ses lignes partent ensemble.

        Côté pays, déclarer une dépense doit tenir en une action : remplir les
        lignes, joindre la pièce, soumettre. Soumettre chaque ligne puis le
        dossier serait une cérémonie sans objet.

        Le coût ne suit pas le nombre de lignes : l'enveloppe est résolue une
        fois par clé d'imputation, verrouillée une fois, son total engagé
        calculé une fois puis accumulé ; lignes et traces sont écrites en
        bloc.
        """
        # Les lignes sont verrouillées avec le dossier : une ligne modifiée
        # entre la lecture et l'écriture partirait avec un montant périmé.
        lignes = list(
            dossier.expenses.select_for_update(of=("self",)).select_related(
                "country", "project", "team", "owner"
            )
        )
        if not lignes:
            raise ValidationError(
                {
                    "expenses": (
                        "Un dossier se soumet avec ses lignes de dépenses : "
                        "ajoutez-en au moins une."
                    )
                }
            )
        brouillons = [e for e in lignes if e.status == Status.DRAFT]

        # Une résolution par clé d'imputation, pas par ligne.
        par_cle = {}
        for expense in brouillons:
            cle = cle_d_imputation(expense)
            if cle in par_cle:
                expense.budget = par_cle[cle]
            else:
                par_cle[cle] = attach_budget(expense)

        # Verrou : deux soumissions simultanées ne doivent pas franchir la
        # même enveloppe chacune de leur côté. Une requête pour toutes.
        # ``of=("self",)`` : seule l'enveloppe est verrouillée, pas les
        # référentiels joints — Postgres refuse un verrou sur le côté
        # nullable d'une jointure externe.
        verrouillees = (
            Budget.objects.select_for_update(of=("self",))
            .select_related("country", "project", "team", "manager")
            .in_bulk({b.pk for b in par_cle.values()})
        )
        engage = {pk: None for pk in verrouillees}
        depassements = {}
        maintenant = timezone.now()
        for expense in brouillons:
            budget = verrouillees[expense.budget_id]
            if engage[budget.pk] is None:
                # Les brouillons n'y figurent pas : rien à exclure.
                engage[budget.pk] = committed_total(budget)
            expense.budget = budget
            avertissement = check_budget_capacity(
                expense, budget, access.role, committed=engage[budget.pk]
            )
            engage[budget.pk] += expense.amount
            if avertissement:
                # Le dernier message d'une enveloppe porte le dépassement
                # cumulé : un seul avertissement par enveloppe suffit.
                depassements[budget.pk] = avertissement
            expense.status = Status.SUBMITTED
            expense.updated_at = maintenant

        Expense.objects.bulk_update(brouillons, ["budget", "status", "updated_at"])
        enregistrer(
            preparer(
                self.request,
                AuditLog.Action.SUBMITTED,
                expense,
                from_status=Status.DRAFT,
                to_status=Status.SUBMITTED,
                note="soumise avec son dossier",
            )
            for expense in brouillons
        )

        avertissements = list(depassements.values())
        if _sans_preuve(dossier) and WorkflowConfiguration.charger().warn_without_proof_submission:
            avertissements.append(SANS_PREUVE)
        return " ".join(avertissements) or None

    def after_transition(self, request, dossier, name, note):
        if name == "submit":
            triggers.dossier_submitted(dossier, request.user)


class ExpenseViewSet(WorkflowMixin, CountryScopedMixin, DraftDeletableViewSet):
    """Lignes de dépenses.

    Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
    brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
    ne se déclare donc jamais seule.
    """

    queryset = Expense.objects.select_related(*EXPENSE_RELATIONS).all()
    serializer_class = ExpenseSerializer
    transition_serializer_class = ExpenseTransitionSerializer
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

    def lock_queryset(self):
        return Expense.objects.select_related(*EXPENSE_RELATIONS)

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
        """
        self._check_country_scope(serializer)
        _refuser_un_dossier_declare(serializer.validated_data.get("dossier"))
        serializer.save(created_by=self.request.user.username)
        record(self.request, AuditLog.Action.CREATED, serializer.instance)

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        # Déplacer un brouillon vers un dossier déjà déclaré l'y perdrait,
        # exactement comme l'y créer.
        _refuser_un_dossier_declare(serializer.validated_data.get("dossier"))
        stored = serializer.instance
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

    def audit_snapshot(self, expense):
        return {
            "status": expense.status,
            "justified_amount": str(expense.justified_amount),
            "control_note": expense.control_note,
        }

    def apply_decision(self, expense, name, note, donnees):
        """Le contrôleur fixe ce qui est prouvé, et pourquoi.

        Le motif va dans ``control_note`` : ``note`` est la remarque du
        déclarant, qu'un rejet ne doit pas effacer.
        """
        if note:
            expense.control_note = note
        if name == "justify":
            justifie = donnees.get("justified_amount")
            if justifie is None:
                justifie = expense.amount
            if justifie > expense.amount:
                raise ValidationError(
                    {
                        "justified_amount": (
                            "Le montant justifié ne peut pas dépasser la "
                            f"dépense ({expense.amount})."
                        )
                    }
                )
            expense.justified_amount = justifie
        elif name == "reject":
            # Non justifiée : rien n'est prouvé, l'écart est entier.
            expense.justified_amount = ZERO

    def before_transition(self, expense, name, access, donnees):
        """Sépare la déclaration du contrôle, impute l'enveloppe et applique la
        politique de dépassement."""
        if name in ("review", "justify", "reject"):
            # Quatre yeux : décaisser puis se donner quitus soi-même n'est pas
            # un contrôle. Sans auteur connu, la règle ne peut pas être
            # vérifiée — on ne tranche pas une ligne d'origine inconnue.
            if not expense.created_by:
                raise ValidationError(
                    {
                        "created_by": (
                            "Cette dépense n'a pas d'auteur connu : elle ne "
                            "peut pas être contrôlée."
                        )
                    }
                )
            if expense.created_by == self.request.user.username:
                raise PermissionDenied(
                    "Vous avez saisi cette dépense : son contrôle revient à "
                    "quelqu'un d'autre."
                )

        if name != "justify":
            return None

        budget = attach_budget(expense)
        # Verrou sur l'enveloppe : la politique « soumettre à approbation »
        # se juge ici, sur un total engagé qui ne bouge pas sous nos pieds.
        budget = Budget.objects.select_for_update().get(pk=budget.pk)
        expense.budget = budget
        # L'imputation est persistée par la sauvegarde de la transition.
        return check_budget_capacity(expense, budget, access.role, at_approval=True)

    def after_transition(self, request, expense, name, note):
        if name == "reject":
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

    @transaction.atomic
    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        dossier = serializer.validated_data["dossier"]
        replaced = serializer.validated_data.get("replaces")
        if replaced is not None:
            # Revalidé ici, hors sérialiseur : la pièce remplacée change
            # d'état, elle doit relever du même dossier que la nouvelle.
            ProofSerializer.verifier_le_remplacement(replaced, dossier)
            replaced = Proof.objects.select_for_update().get(pk=replaced.pk)
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
                AuditLog.Action.PROOF_REPLACED,
                proof,
                country=dossier.country,
                dossier=dossier.number,
                sha256=proof.sha256,
                version=proof.version,
                before={"sha256": replaced.sha256, "version": replaced.version},
                after={"sha256": proof.sha256, "version": proof.version},
                replaces=replaced.pk,
            )
            return
        record(
            self.request,
            AuditLog.Action.PROOF_UPLOADED,
            proof,
            country=dossier.country,
            dossier=dossier.number,
            sha256=proof.sha256,
            version=proof.version,
        )

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        avant = {"kind": serializer.instance.kind}
        serializer.save()
        record(
            self.request,
            AuditLog.Action.UPDATED,
            serializer.instance,
            country=serializer.instance.dossier.country,
            before=avant,
            after={"kind": serializer.instance.kind},
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def review(self, request, pk=None):
        """Contrôle documentaire : valide, rejette ou signale un justificatif."""
        visible = self.get_object()
        proof = (
            Proof.objects.select_related("dossier__country")
            .select_for_update(of=("self",))
            .get(pk=visible.pk)
        )

        serializer = ProofReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "").strip()

        try:
            next_proof_status(
                proof.status, target, dict(Proof.ProofStatus.choices)
            )
        except TransitionError as exc:
            raise ValidationError({"status": str(exc)}) from exc

        previous = proof.status
        proof.status = target
        proof.rejection_reason = reason if target == Proof.ProofStatus.REJECTED else ""
        proof.is_complete = target != Proof.ProofStatus.INCOMPLETE
        proof.save()

        record(
            request,
            PROOF_AUDIT_ACTIONS[target],
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
        laisse une trace d'audit. Il est servi en flux : ``FileResponse``
        lit le fichier ouvert par blocs, sans le charger en mémoire — une
        pièce de vingt mégaoctets ne doit pas en coûter vingt au serveur.
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
            content_type=proof.content_type or None,
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
