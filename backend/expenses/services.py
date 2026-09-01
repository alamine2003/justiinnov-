"""Règles métier des dépenses : imputation budgétaire et dépassements.

Ces contrôles vivent côté serveur exclusivement (§6) : l'interface ne fait que
présenter leurs résultats.
"""

from decimal import Decimal

from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from accounts.models import Role
from budget.models import Budget, OverrunPolicy

from .workflow import CONSUMING_STATUSES, ENGAGING_STATUSES

ZERO = Decimal("0.00")

#: Rôles habilités à valider une dépense qui dépasse son enveloppe lorsque la
#: politique du budget l'exige.
OVERRUN_APPROVERS = frozenset({Role.SUPER_ADMIN, Role.DOO})


def resolve_budget(expense):
    """Enveloppe imputable à une dépense.

    La sous-enveloppe du projet est prioritaire ; à défaut, l'enveloppe du pays
    pour l'année de la dépense.
    """
    year = expense.date.year
    if expense.project_id:
        sub_envelope = Budget.objects.filter(
            country_id=expense.country_id,
            year=year,
            project_id=expense.project_id,
            is_active=True,
        ).first()
        if sub_envelope is not None:
            return sub_envelope
    return Budget.objects.filter(
        country_id=expense.country_id,
        year=year,
        project__isnull=True,
        is_active=True,
    ).first()


def committed_total(budget, exclude_pk=None):
    """Montant déjà engagé ou consommé sur une enveloppe."""
    expenses = budget.expenses.filter(
        status__in=ENGAGING_STATUSES | CONSUMING_STATUSES
    )
    if exclude_pk is not None:
        expenses = expenses.exclude(pk=exclude_pk)
    return expenses.aggregate(total=Sum("amount"))["total"] or ZERO


def attach_budget(expense):
    """Impute la dépense à une enveloppe active, ou refuse.

    §6 : une dépense doit être associée à un budget actif avant validation.
    """
    budget = expense.budget or resolve_budget(expense)
    if budget is None:
        raise ValidationError(
            {
                "budget": (
                    f"Aucune enveloppe active pour {expense.country.name} "
                    f"en {expense.date.year}."
                )
            }
        )
    if not budget.is_active:
        raise ValidationError({"budget": "L'enveloppe imputée est inactive."})
    if expense.budget_id != budget.pk:
        expense.budget = budget
    return budget


def check_budget_capacity(expense, budget, role, *, at_approval=False):
    """Applique la politique de dépassement de l'enveloppe (§5.2, §6).

    Renvoie un avertissement à afficher, ou ``None`` si l'enveloppe couvre la
    dépense. Lève une erreur lorsque la politique interdit le dépassement.

    ``at_approval`` distingue les deux moments : sous la politique « soumettre
    à approbation », le manager doit pouvoir *demander* le dépassement — c'est
    la validation, et elle seule, qui est réservée à la direction. Bloquer dès
    la soumission rendrait la demande impossible.
    """
    projected = committed_total(budget, exclude_pk=expense.pk) + expense.amount
    if projected <= budget.amount:
        return None

    overrun = projected - budget.amount
    message = (
        f"Dépassement de {overrun} {budget.country.currency} "
        f"sur l'enveloppe {budget}."
    )

    if budget.overrun_policy == OverrunPolicy.BLOCK:
        raise ValidationError({"amount": f"{message} Opération bloquée."})

    if budget.overrun_policy == OverrunPolicy.APPROVAL:
        if at_approval and role not in OVERRUN_APPROVERS:
            raise ValidationError(
                {
                    "amount": (
                        f"{message} La validation d'un dépassement relève "
                        f"de la direction des opérations."
                    )
                }
            )
        if not at_approval:
            return f"{message} Sa validation relèvera de la direction des opérations."

    return message
