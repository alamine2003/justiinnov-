"""Agrégats du pilotage : tableau de bord et répartition d'un pays.

Les vues (``reporting.views.DashboardView``, ``BreakdownView``) lisent la
requête, bornent les querysets au périmètre (``reporting.scope``) et
répondent ; les chiffres se calculent ici, sur des querysets déjà
cloisonnés ou sur des lignes déjà rendues, sans requête HTTP ni droit à
vérifier (décision 124). Les montants sortent en texte — ``"0.00"`` plutôt
que ``None`` —, les taux en texte ou ``None`` : c'est le contrat de
``/api/dashboard/`` et ``/api/dashboard/breakdown/``.
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext as _

from budget.aggregates import (
    consolidation_par_pays,
    niveau_d_execution,
    seuil_d_alerte,
    to_xof,
)
from budget.models import CONSOLIDATION_CURRENCY
from core.models import ProjectType
from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES, Status

ZERO = Decimal("0.00")

#: Chiffres d'une ligne de pays qui se consolident en FCFA.
MONTANTS = ("allocated", "engaged", "consumed", "justified", "remaining")


def _money(value):
    return str(value if value is not None else ZERO)


def _taux(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def _ratio(numerator, denominator):
    return _as_str(_taux(numerator, denominator))


def _as_str(value):
    return str(value) if value is not None else None


# -- Tableau de bord ---------------------------------------------------------


def par_pays(budgets, rates):
    """Lignes par pays et consolidé en FCFA, rendus pour la réponse.

    Agrège via :func:`budget.aggregates.consolidation_par_pays`, seul point
    de calcul partagé avec ``/api/budgets/summary/``.
    """
    rows, consolidated = consolidation_par_pays(budgets, rates=rates)
    return (
        [
            {
                "country": row["country"],
                "country_name": row["country_name"],
                "country_ref": row["country_ref"],
                "currency": row["currency"],
                "allocated": _money(row["allocated"]),
                "sub_allocated": _money(row["sub_allocated"]),
                "engaged": _money(row["engaged"]),
                "consumed": _money(row["consumed"]),
                "justified": _money(row["justified"]),
                "gap": _money(row["gap"]),
                "remaining": _money(row["remaining"]),
                "execution_rate": _as_str(row["execution_rate"]),
                "execution_level": row["execution_level"],
                "justification_rate": _as_str(row["justification_rate"]),
                "remaining_xof": _as_str(row["remaining_xof"]),
            }
            for row in rows
        ],
        {
            "allocated": str(consolidated["allocated"]),
            "remaining": str(consolidated["remaining"]),
            # Une devise sans taux connu est exclue du total et signalée,
            # jamais absorbée silencieusement.
            "unconverted_currencies": consolidated["unconverted_currencies"],
        },
    )


def totaux_consolides(rows, rates):
    """Totaux globaux, en FCFA uniquement, à partir des lignes de :func:`par_pays`.

    Additionner « allocated » du Togo (XOF) et du Guinée (GNF) donnait un
    chiffre sans unité, présenté comme un total. Chaque montant est
    converti aux taux de la date de référence de l'exercice ; un pays
    dont la devise n'a pas de taux est écarté et nommé, jamais absorbé.
    """
    totaux = {key: ZERO for key in MONTANTS}
    non_converties = set()
    for row in rows:
        montants = {
            key: to_xof(Decimal(row[key]), row["currency"], rates=rates)
            for key in MONTANTS
        }
        if any(value is None for value in montants.values()):
            non_converties.add(row["currency"])
            continue
        for key, value in montants.items():
            totaux[key] += value

    used = totaux["consumed"] + totaux["engaged"]
    execution_rate = _taux(used, totaux["allocated"])
    return {
        "currency": CONSOLIDATION_CURRENCY,
        **{key: _money(value) for key, value in totaux.items()},
        # Ce qui est sorti sans preuve à l'appui.
        "gap": _money(totaux["consumed"] - totaux["justified"]),
        "execution_rate": _as_str(execution_rate),
        # Jugé par la même règle que chaque ligne de pays et chaque
        # enveloppe (``budget.aggregates.niveau_d_execution``).
        "execution_level": niveau_d_execution(execution_rate, seuil_d_alerte()),
        "justification_rate": _ratio(totaux["justified"], totaux["consumed"]),
        "unconverted_currencies": sorted(non_converties),
    }


def charge_de_travail(dossiers, expenses):
    """Ce qui attend une action, pour orienter le contrôle."""
    by_status = dict(
        expenses.values_list("status").annotate(total=Count("id"))
    )
    return {
        "expenses_to_review": by_status.get(Status.SUBMITTED, 0)
        + by_status.get(Status.IN_REVIEW, 0),
        "expenses_draft": by_status.get(Status.DRAFT, 0),
        # Décaissements sans preuve : le chiffre que l'application existe
        # pour faire diminuer.
        "expenses_unjustified": by_status.get(Status.UNJUSTIFIED, 0),
        # La définition de la liste (`?ouverts=true`) : la tuile ouvre
        # une liste au même chiffre (décision 117).
        "dossiers_open": dossiers.ouverts().count(),
    }


# -- Répartition d'un pays ---------------------------------------------------


def depenses_comptees(expenses):
    """Les lignes qui pèsent : brouillons et refus ne représentent aucune
    consommation réelle."""
    return expenses.filter(
        status__in=list(ENGAGING_STATUSES) + list(CONSUMING_STATUSES)
    )


def _ligne_de_repartition(label, row):
    return {
        "label": label,
        "amount": _money(row["amount"]),
        "justified": _money(row["justified"]),
        "gap": _money((row["amount"] or ZERO) - (row["justified"] or ZERO)),
        "lines": row["lines"],
    }


def regrouper(expenses, field, fallback, libelles=None):
    """Montant, justifié, écart et nombre de lignes par valeur de ``field``,
    du plus gros montant au plus petit."""
    rows = (
        expenses.values(field)
        .annotate(
            amount=Sum("amount"),
            justified=Sum("justified_amount"),
            lines=Count("id"),
        )
        .order_by("-amount")
    )
    return [
        _ligne_de_repartition((libelles or {}).get(row[field], row[field]) or fallback, row)
        for row in rows
    ]


def par_mois(expenses, fuseau):
    """Les mêmes chiffres par mois, comptés à l'heure du pays (``fuseau``)."""
    rows = (
        expenses.annotate(month=TruncMonth("date", tzinfo=fuseau))
        .values("month")
        .annotate(
            amount=Sum("amount"),
            justified=Sum("justified_amount"),
            lines=Count("id"),
        )
        .order_by("month")
    )
    return [
        _ligne_de_repartition(row["month"].strftime("%Y-%m") if row["month"] else "—", row)
        for row in rows
    ]


def repartition(counted, fuseau):
    """Toutes les répartitions d'un pays, sur ses lignes comptées
    (:func:`depenses_comptees`), dans l'ordre de la réponse."""
    return {
        "by_team": regrouper(counted, "team__name", _("Sans équipe")),
        "by_owner": regrouper(counted, "owner__name", _("Sans propriétaire")),
        # Le projet de la ligne : celui de son dossier depuis la 2.0
        # (décision 102), celui qu'elle portait pour un dossier rangé
        # sous « Historique » (décision 103) — comme la consommation
        # des sous-enveloppes par projet.
        "by_project": regrouper(counted, "project__name", _("Hors projet")),
        "by_project_kind": regrouper(
            counted, "dossier__project__kind", _("Sans type de projet"),
            libelles={t.code: t.libelle for t in ProjectType.objects.all()},
        ),
        "by_dossier_kind": regrouper(
            counted, "dossier__kind__name", _("Sans type de dossier")
        ),
        "by_category": regrouper(
            counted, "marketing_category__name", _("Sans catégorie")
        ),
        "by_expense_title": regrouper(
            counted, "expense_title__label", _("Sans intitulé")
        ),
        "by_month": par_mois(counted, fuseau),
    }
