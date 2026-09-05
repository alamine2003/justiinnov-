"""Restriction des rapports au périmètre de l'utilisateur.

Les vues de pilotage n'héritent pas des viewsets : elles doivent appliquer le
même cloisonnement explicitement, sans quoi un rapport laisserait fuir les
données d'un autre pays.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils.formats import date_format
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound

from accounts.perimetre import filtrer
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


#: Fuseau des bornes quand aucun pays ne les fixe : voir :func:`bornes_periode`.
UTC = ZoneInfo("UTC")


def fuseau_de(country):
    """Fuseau IANA d'un pays, UTC si le pays est inconnu ou son fuseau illisible.

    Le champ est validé à l'écriture, mais une base reprise d'ailleurs peut
    porter un identifiant que la machine ne connaît pas : mieux vaut un
    rapport en UTC qu'une erreur 500 sur le tableau de bord.
    """
    if country is None:
        return UTC
    try:
        return ZoneInfo(country.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def bornes_periode(year, month=None, tz=None):
    """Premier et dernier instants d'une période, pour un filtre ``range``.

    ``date__year`` obligeait la base à convertir chaque date dans le fuseau
    courant avant de la comparer : l'index sur la colonne devenait inutile et
    le filtre parcourait toute la table. Deux bornes explicites — du 1er
    janvier au 31 décembre, ou du premier au dernier jour du mois — laissent
    l'index travailler.

    Renvoie ``(jours, instants)`` : le premier couple sert aux champs
    ``DateField`` (dossiers), le second aux ``DateTimeField`` (dépenses),
    exprimé dans le fuseau ``tz`` — celui du pays dont on lit les lignes,
    pour qu'une dépense faite à Djibouti le 1er janvier à 01:00, encore au
    31 décembre en UTC, tombe bien dans le nouvel exercice. Sans fuseau,
    UTC : c'est la seule horloge qui ne dépende ni du serveur ni de qui
    regarde, et elle est documentée par :func:`fuseau_du_perimetre`.
    """
    tz = tz or UTC
    if month:
        jours = (date(year, month, 1), date(year, month, monthrange(year, month)[1]))
    else:
        jours = (date(year, 1, 1), date(year, 12, 31))
    instants = (
        datetime.combine(jours[0], time.min, tzinfo=tz),
        datetime.combine(jours[1], time.max, tzinfo=tz),
    )
    return jours, instants


def bornes_annee(year, tz=None):
    """Bornes de l'exercice entier ; voir :func:`bornes_periode`."""
    return bornes_periode(year, tz=tz)


def fuseau_du_perimetre(access, country_id=None):
    """Fuseau dans lequel un rapport borne ses dépenses.

    Un rapport ne porte qu'une horloge. Quand il vise un seul pays — nommé
    par ``country_id``, ou seul pays du périmètre du demandeur — c'est celle
    de ce pays : l'exercice d'une ligne est celui de son pays, comme pour
    son imputation (``expenses.services.exercice``). Quand plusieurs pays se
    lisent ensemble, aucun fuseau national ne s'impose : les bornes sont en
    UTC, et le rapport le dit dans sa documentation plutôt que de choisir
    en silence celui du serveur. Ce cas ne concerne que le siège, qui lit
    des consolidations ; le détail d'un pays se lit toujours à son heure.
    """
    if country_id is None:
        if access is None or access.has_global_scope or len(access.country_ids) != 1:
            return UTC
        country_id = access.country_ids[0]
    return fuseau_de(Country.objects.filter(pk=country_id).first())


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

    Les dépenses sont bornées dans le fuseau du pays visé — ou en UTC quand
    plusieurs pays se lisent ensemble, voir :func:`fuseau_du_perimetre`.
    """
    # Même règle que les vues (``accounts.perimetre``). Les enveloppes restent
    # lisibles par pays entier : un manager cloisonné doit savoir où en est
    # l'enveloppe de son pays, même s'il n'en voit qu'une partie des lignes.
    budgets = filtrer(
        # Une enveloppe désactivée est retirée du suivi : elle ne doit plus
        # ni peser dans les totaux ni déclencher d'alerte.
        Budget.objects.filter(is_active=True)
        .select_related("country", "project", "team", "manager")
        .with_consumption(),
        access,
    )
    # Les totaux sont annotés d'emblée : les exports lisent ceux de chaque
    # dossier, et une agrégation par dossier affiché coûtait une requête par
    # ligne du rapport.
    dossiers = filtrer(
        Dossier.objects.select_related("country").with_totals(), access, equipe="team"
    )
    expenses = filtrer(Expense.objects.select_related("country"), access, equipe="team")

    if country_id:
        # Vérifié avant les bornes : le fuseau vient du pays, et un pays
        # hors périmètre ne doit pas même livrer le sien.
        _verifier_pays(access, country_id)
    if year:
        jours, instants = bornes_periode(year, month, fuseau_du_perimetre(access, country_id))
        budgets = budgets.filter(year=year)
        dossiers = dossiers.filter(date__range=jours)
        expenses = expenses.filter(date__range=instants)
    if country_id:
        budgets = budgets.filter(country_id=country_id)
        dossiers = dossiers.filter(country_id=country_id)
        expenses = expenses.filter(country_id=country_id)

    return budgets, dossiers, expenses
