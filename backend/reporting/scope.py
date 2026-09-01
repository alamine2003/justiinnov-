"""Restriction des rapports au périmètre de l'utilisateur.

Les vues de pilotage n'héritent pas des viewsets : elles doivent appliquer le
même cloisonnement explicitement, sans quoi un rapport laisserait fuir les
données d'un autre pays.
"""

from accounts.permissions import get_access
from budget.models import Budget
from expenses.models import Dossier, Expense


def _restrict(queryset, access, lookup):
    if access is None:
        return queryset.none()
    if access.has_global_scope:
        return queryset
    return queryset.filter(**{f"{lookup}__in": access.country_ids})


def scoped_querysets(request, year=None, country_id=None):
    """Budgets, dossiers et dépenses visibles, filtrés par année et pays."""
    access = get_access(request.user)

    budgets = _restrict(
        Budget.objects.select_related("country", "project").with_consumption(),
        access,
        "country",
    )
    dossiers = _restrict(Dossier.objects.select_related("country"), access, "country")
    expenses = _restrict(
        Expense.objects.select_related("country"), access, "country"
    )

    if year:
        budgets = budgets.filter(year=year)
        dossiers = dossiers.filter(date__year=year)
        expenses = expenses.filter(date__year=year)
    if country_id:
        budgets = budgets.filter(country_id=country_id)
        dossiers = dossiers.filter(country_id=country_id)
        expenses = expenses.filter(country_id=country_id)

    return budgets, dossiers, expenses
