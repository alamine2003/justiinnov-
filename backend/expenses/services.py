"""Règles métier des dépenses : imputation budgétaire et dépassements.

Ces contrôles vivent côté serveur exclusivement (§6) : l'interface ne fait que
présenter leurs résultats.
"""

from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Sum
from django.utils.translation import gettext as _

from accounts.permissions import roles_pour
from budget.models import Budget, OverrunPolicy
from core.regles import RegleViolee

from .workflow import CONSUMING_STATUSES, ENGAGING_STATUSES

ZERO = Decimal("0.00")

def approuve_les_depassements(role):
    """Le rôle peut-il valider une dépense qui dépasse son enveloppe ?

    Ceux qui modifient les enveloppes (``budgets.update``) — la direction
    par défaut ; ni la RH ni la direction financière n'arbitrent un
    dépassement. La capacité est la même que pour l'attribution, pour ne
    pas dériver d'elle.
    """
    return role in roles_pour("budgets.update")


#: Ordre de priorité des sous-enveloppes, du plus précis au plus large.
#: Le projet l'emporte sur l'équipe, qui l'emporte sur le manager : une
#: dépense de projet doit peser sur le budget de ce projet, même si son auteur
#: dispose par ailleurs d'une enveloppe personnelle.
SUB_ENVELOPE_ORDER = [
    ("project_id", "project_id"),
    ("team_id", "team_id"),
    ("owner_id", "manager_id"),
]


def exercice(expense):
    """Année budgétaire d'une dépense, lue dans le fuseau de son pays.

    La date est conservée en UTC. Une dépense faite à Djibouti le 1er janvier
    à 01:00 est encore au 31 décembre en UTC : l'imputer sur l'exercice
    précédent, c'est la faire peser sur une enveloppe déjà close.
    """
    try:
        fuseau = ZoneInfo(expense.country.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        fuseau = ZoneInfo("UTC")
    return expense.date.astimezone(fuseau).year


def cle_d_imputation(expense):
    """Ce qui détermine l'enveloppe d'une dépense.

    Deux lignes de même clé s'imputent sur la même enveloppe : la soumission
    d'un dossier ne la résout qu'une fois par clé.
    """
    return (
        expense.country_id, exercice(expense),
        expense.project_id, expense.team_id, expense.owner_id,
    )


def resolve_budget(expense):
    """Enveloppe imputable à une dépense.

    La sous-enveloppe la plus précise l'emporte ; à défaut, l'enveloppe du pays
    pour l'année de la dépense.
    """
    base = Budget.objects.filter(
        country_id=expense.country_id, year=exercice(expense), is_active=True
    )

    for expense_field, budget_field in SUB_ENVELOPE_ORDER:
        value = getattr(expense, expense_field, None)
        if not value:
            continue
        sub_envelope = base.filter(**{budget_field: value}).first()
        if sub_envelope is not None:
            return sub_envelope

    return base.filter(
        project__isnull=True, team__isnull=True, manager__isnull=True
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
        raise RegleViolee(
            "budget",
            _("Aucune enveloppe active pour {country} en {year}.").format(
                country=expense.country.name, year=exercice(expense)
            ),
        )
    if not budget.is_active:
        raise RegleViolee("budget", _("L'enveloppe imputée est inactive."))
    if expense.budget_id != budget.pk:
        expense.budget = budget
    return budget


def check_budget_capacity(
    expense, budget, role, *, at_approval=False, committed=None
):
    """Applique la politique de dépassement de l'enveloppe (§5.2, §6).

    Renvoie un avertissement à afficher, ou ``None`` si l'enveloppe couvre la
    dépense. Lève :class:`~core.regles.RegleViolee` sur ``amount`` lorsque la
    politique interdit le dépassement.

    ``at_approval`` distingue les deux moments : sous la politique « soumettre
    à approbation », le manager doit pouvoir *demander* le dépassement — c'est
    la validation, et elle seule, qui est réservée à la direction. Bloquer dès
    la soumission rendrait la demande impossible.

    À l'inverse, la politique « bloquer » ne joue qu'à la soumission. Une
    dépense soumise a déjà engagé l'argent : si l'enveloppe est réduite
    entre-temps, refuser de la justifier la laisserait à jamais en suspens —
    sans faire revenir un franc.

    ``committed`` permet à l'appelant qui traite plusieurs lignes d'une même
    enveloppe de fournir le total déjà engagé, qu'il fait croître au fil des
    lignes, au lieu de le recalculer pour chacune.
    """
    if committed is None:
        committed = committed_total(budget, exclude_pk=expense.pk)
    projected = committed + expense.amount
    if projected <= budget.amount:
        return None

    overrun = projected - budget.amount
    # « Dépassement » ouvre le message dans les deux langues (« Overrun ») :
    # l'interface et les tests s'y repèrent.
    message = _(
        "Dépassement de {overrun} {currency} sur l'enveloppe {budget}."
    ).format(overrun=overrun, currency=budget.country.currency, budget=budget)

    if budget.overrun_policy == OverrunPolicy.BLOCK:
        if at_approval:
            return message
        raise RegleViolee(
            "amount", _("{message} Opération bloquée.").format(message=message)
        )

    if budget.overrun_policy == OverrunPolicy.APPROVAL:
        if at_approval and not approuve_les_depassements(role):
            raise RegleViolee(
                "amount",
                _(
                    "{message} La validation d'un dépassement relève de "
                    "la direction (super administrateur)."
                ).format(message=message),
            )
        if not at_approval:
            return _(
                "{message} Sa validation relèvera de la direction "
                "(super administrateur)."
            ).format(message=message)

    return message
