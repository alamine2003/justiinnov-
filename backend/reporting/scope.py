"""Restriction des rapports au périmètre de l'utilisateur.

Les vues de pilotage n'héritent pas des viewsets : elles doivent appliquer le
même cloisonnement explicitement, sans quoi un rapport laisserait fuir les
données d'un autre pays.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound

from accounts.permissions import get_access
from budget.models import Budget
from core.models import Country
from expenses.models import Dossier, Expense


@dataclass(frozen=True)
class Periode:
    """Exercice entier, ou un seul mois de l'exercice.

    Les exports se classent par année ou par mois : l'objet porte les deux
    et sait se nommer, dans le nom du fichier comme dans l'en-tête du
    document, pour que les vues n'aient pas chacune leur formatage.
    """

    year: int
    month: int | None = None

    @property
    def suffixe(self):
        """« 2026 » ou « 2026-03 », pour le nom du fichier."""
        if self.month:
            return f"{self.year}-{self.month:02d}"
        return str(self.year)

    @property
    def libelle(self):
        """« mars 2026 » ou « exercice 2026 », dans la langue courante."""
        if self.month:
            return date_format(date(self.year, self.month, 1), "F Y")
        return _("exercice %(year)s") % {"year": self.year}


def bornes_periode(year, month=None):
    """Premier et dernier instants d'une période, pour un filtre ``range``.

    ``date__year`` obligeait la base à convertir chaque date dans le fuseau
    courant avant de la comparer : l'index sur la colonne devenait inutile et
    le filtre parcourait toute la table. Deux bornes explicites — du 1er
    janvier au 31 décembre, ou du premier au dernier jour du mois — laissent
    l'index travailler.

    Renvoie ``(jours, instants)`` : le premier couple sert aux champs
    ``DateField`` (dossiers), le second aux ``DateTimeField`` (dépenses),
    exprimé dans le fuseau courant pour que le dernier jour à 23 h 59 reste
    dans la période.
    """
    if month:
        jours = (date(year, month, 1), date(year, month, monthrange(year, month)[1]))
    else:
        jours = (date(year, 1, 1), date(year, 12, 31))
    instants = (
        timezone.make_aware(datetime.combine(jours[0], time.min)),
        timezone.make_aware(datetime.combine(jours[1], time.max)),
    )
    return jours, instants


def bornes_annee(year):
    """Bornes de l'exercice entier ; voir :func:`bornes_periode`."""
    return bornes_periode(year)


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
        raise NotFound(_("Pays introuvable."))


def scoped_querysets(request, year=None, country_id=None, month=None):
    """Budgets, dossiers et dépenses visibles, filtrés par période et pays."""
    return querysets_pour(get_access(request.user), year, country_id, month)


def querysets_pour(access, year=None, country_id=None, month=None):
    """Même cloisonnement, à partir des droits plutôt que de la requête.

    Les commandes planifiées n'ont pas de requête HTTP, mais envoient des
    rapports à des comptes dont le périmètre peut être restreint : elles
    doivent filtrer exactement comme les vues.

    Le mois ne restreint que les dossiers et les dépenses : une enveloppe
    est annuelle, et son état — consommé, disponible — n'a de sens que sur
    l'exercice entier.
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
        jours, instants = bornes_periode(year, month)
        budgets = budgets.filter(year=year)
        dossiers = dossiers.filter(date__range=jours)
        expenses = expenses.filter(date__range=instants)
    if country_id:
        _verifier_pays(access, country_id)
        budgets = budgets.filter(country_id=country_id)
        dossiers = dossiers.filter(country_id=country_id)
        expenses = expenses.filter(country_id=country_id)

    return budgets, dossiers, expenses
