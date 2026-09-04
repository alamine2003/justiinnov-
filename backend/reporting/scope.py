"""Restriction des rapports au périmètre de l'utilisateur.

Les vues de pilotage n'héritent pas des viewsets : elles doivent appliquer le
même cloisonnement explicitement, sans quoi un rapport laisserait fuir les
données d'un autre pays.
"""

from datetime import date, datetime, time

from django.utils import timezone
from rest_framework.exceptions import NotFound

from accounts.permissions import get_access
from budget.models import Budget
from core.models import Country
from expenses.models import Dossier, Expense


def bornes_annee(year):
    """Premier et dernier instants d'un exercice, pour un filtre ``range``.

    ``date__year`` obligeait la base à convertir chaque date dans le fuseau
    courant avant de la comparer : l'index sur la colonne devenait inutile et
    le filtre parcourait toute la table. Deux bornes explicites, du 1er
    janvier au 31 décembre, laissent l'index travailler.

    Renvoie ``(jours, instants)`` : le premier couple sert aux champs
    ``DateField`` (dossiers), le second aux ``DateTimeField`` (dépenses),
    exprimé dans le fuseau courant pour que le 31 décembre à 23 h 59 reste
    dans l'exercice.
    """
    jours = (date(year, 1, 1), date(year, 12, 31))
    instants = (
        timezone.make_aware(datetime.combine(jours[0], time.min)),
        timezone.make_aware(datetime.combine(jours[1], time.max)),
    )
    return jours, instants


def _restrict(queryset, access, lookup):
    if access is None:
        return queryset.none()
    if access.has_global_scope:
        return queryset
    return queryset.filter(**{f"{lookup}__in": access.country_ids})


def _verifier_pays(access, country_id):
    """Refuse un pays inexistant ou hors périmètre, sans distinguer les deux.

    Sans cette vérification, le filtre renvoyait un rapport vide pour un pays
    du voisin — ce qui confirmait son existence — et l'audit de l'export
    échouait ensuite sur une clé étrangère inexistante, en erreur 500.
    """
    visible = access is not None and (
        access.has_global_scope or country_id in access.country_ids
    )
    if not visible or not Country.objects.filter(pk=country_id).exists():
        raise NotFound("Pays introuvable.")


def scoped_querysets(request, year=None, country_id=None):
    """Budgets, dossiers et dépenses visibles, filtrés par année et pays."""
    return querysets_pour(get_access(request.user), year, country_id)


def querysets_pour(access, year=None, country_id=None):
    """Même cloisonnement, à partir des droits plutôt que de la requête.

    Les commandes planifiées n'ont pas de requête HTTP, mais envoient des
    rapports à des comptes dont le périmètre peut être restreint : elles
    doivent filtrer exactement comme les vues.
    """
    budgets = _restrict(
        # Une enveloppe désactivée est retirée du suivi : elle ne doit plus
        # ni peser dans les totaux ni déclencher d'alerte.
        Budget.objects.filter(is_active=True)
        .select_related("country", "project", "team", "manager")
        .with_consumption(),
        access,
        "country",
    )
    # Les totaux sont annotés d'emblée : les exports lisent ceux de chaque
    # dossier, et une agrégation par dossier affiché coûtait une requête par
    # ligne du rapport.
    dossiers = _restrict(
        Dossier.objects.select_related("country").with_totals(), access, "country"
    )
    expenses = _restrict(
        Expense.objects.select_related("country"), access, "country"
    )

    if year:
        jours, instants = bornes_annee(year)
        budgets = budgets.filter(year=year)
        dossiers = dossiers.filter(date__range=jours)
        expenses = expenses.filter(date__range=instants)
    if country_id:
        _verifier_pays(access, country_id)
        budgets = budgets.filter(country_id=country_id)
        dossiers = dossiers.filter(country_id=country_id)
        expenses = expenses.filter(country_id=country_id)

    return budgets, dossiers, expenses
