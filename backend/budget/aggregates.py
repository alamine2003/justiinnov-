"""Calculs budgétaires — **toujours côté serveur** (§6).

Le solde ne doit jamais être reconstitué dans l'interface : c'est ici, et
uniquement ici, que consommation, écart et disponible sont établis.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from core.statuts import CONSUMING_STATUSES, ENGAGING_STATUSES

from .models import CONSOLIDATION_CURRENCY, ExchangeRate

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")
#: Précision d'un taux figé sur une opération (``Expense.original_rate``).
RATE_PRECISION = Decimal("0.000001")


def consumption(budget):
    """Montants engagés, consommés et justifiés sur une enveloppe.

    Une dépense soumise ou en contrôle **engage** l'enveloppe sans l'avoir
    encore consommée ; seule une dépense validée ou clôturée la consomme. Un
    brouillon ou une dépense refusée ne comptent pour rien.

    Réutilise les annotations de :meth:`BudgetQuerySet.with_consumption`
    lorsqu'elles sont présentes, pour éviter une agrégation par enveloppe
    affichée.
    """
    engaged = getattr(budget, "engaged_total", None)
    if engaged is not None:
        return {
            "engaged": engaged,
            "consumed": budget.consumed_total,
            "justified": budget.justified_total,
        }

    totals = budget.expenses.aggregate(
        engaged=Sum("amount", filter=Q(status__in=list(ENGAGING_STATUSES))),
        consumed=Sum("amount", filter=Q(status__in=list(CONSUMING_STATUSES))),
        justified=Sum(
            "justified_amount", filter=Q(status__in=list(CONSUMING_STATUSES))
        ),
    )
    return {
        "engaged": totals["engaged"] or ZERO,
        "consumed": totals["consumed"] or ZERO,
        "justified": totals["justified"] or ZERO,
    }


def budget_figures(budget, rates=None):
    """Indicateurs d'une enveloppe, dans la devise du pays.

    Avec ``rates`` (voir :func:`current_rates`), ajoute ``amount_xof`` et
    ``remaining_xof`` sans requête supplémentaire ; sans lui, les clés
    restent celles d'origine — les exports et les alertes n'en attendent pas
    d'autres.
    """
    totals = consumption(budget)
    engaged = totals["engaged"]
    consumed = totals["consumed"]
    justified = totals["justified"]
    remaining = budget.amount - consumed - engaged
    figures = {
        "engaged": engaged,
        "consumed": consumed,
        "justified": justified,
        # Écart entre ce qui est dépensé et ce qui est prouvé.
        "gap": consumed - justified,
        # Le disponible retranche aussi l'engagé : sans cela, une enveloppe
        # paraîtrait libre alors qu'elle est déjà mobilisée.
        "remaining": remaining,
        "execution_rate": _ratio(consumed, budget.amount),
        "justification_rate": _ratio(justified, consumed),
    }
    if rates is not None:
        currency = budget.country.currency
        figures["amount_xof"] = to_xof(budget.amount, currency, rates=rates)
        figures["remaining_xof"] = to_xof(remaining, currency, rates=rates)
    return figures


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


# --- Taux de change ---------------------------------------------------------


def _date_effective(on_date):
    """Date à laquelle chercher un taux : celle donnée, sinon aujourd'hui.

    Un taux daté de demain existe peut-être déjà en base (saisi par
    l'administration, ou avant que l'API ne le refuse) : il ne doit pas
    s'appliquer à la consolidation d'aujourd'hui. « Le plus récent » n'est
    donc jamais le critère ; « le dernier en vigueur à la date » l'est.
    """
    return on_date if on_date is not None else timezone.localdate()


def current_rates(on_date=None):
    """Taux en vigueur par devise, chargés en **une** requête.

    Le dernier taux en vigueur à la date (aujourd'hui par défaut) pour chaque
    devise. Le dictionnaire obtenu se passe ensuite à :func:`to_xof`,
    :func:`convert`, :func:`budget_figures` ou :func:`consolidation_par_pays`,
    pour qu'une liste de cinquante enveloppes ne relise pas cinquante fois la
    table des taux.

    Le FCFA n'y figure pas : il n'a pas de taux, :func:`rate_to_xof` le
    traite à part.
    """
    rates = ExchangeRate.objects.filter(valid_from__lte=_date_effective(on_date))
    # ``DISTINCT ON (currency)`` avec le tri sur ``-valid_from`` garde la
    # ligne la plus récente de chaque devise ; c'est propre à PostgreSQL,
    # seul moteur de la plateforme.
    latest = rates.order_by("currency", "-valid_from", "-pk").distinct("currency")
    return dict(latest.values_list("currency", "rate_to_xof"))


def rate_to_xof(currency, on_date=None, rates=None):
    """Taux en vigueur à une date (aujourd'hui par défaut), ou ``None``.

    ``rates`` (devise → taux) court-circuite la requête ; il fait alors foi,
    même pour une devise absente — c'est le sens d'un jeu de taux chargé une
    fois pour toute une consolidation.
    """
    if currency == CONSOLIDATION_CURRENCY:
        return Decimal("1")
    if rates is not None:
        return rates.get(currency)
    rate = (
        ExchangeRate.objects.filter(
            currency=currency, valid_from__lte=_date_effective(on_date)
        )
        .order_by("-valid_from", "-pk")
        .first()
    )
    return rate.rate_to_xof if rate else None


def to_xof(amount, currency, on_date=None, rates=None):
    """Convertit un montant en FCFA, ou ``None`` faute de taux connu.

    Renvoyer ``None`` plutôt que zéro est délibéré : un total consolidé ne doit
    jamais absorber silencieusement une devise non convertible.
    """
    if amount is None:
        return None
    rate = rate_to_xof(currency, on_date, rates)
    if rate is None:
        return None
    return (Decimal(amount) * rate).quantize(CENTS)


def convert(amount, from_currency, to_currency, on_date=None, rates=None):
    """Convertit entre deux devises, en passant par le FCFA.

    Tous les taux sont donnés vers le FCFA : une conversion croisée est donc
    le rapport des deux. Renvoie ``(montant, taux)``, ou ``(None, None)``
    faute de taux connu — jamais zéro, qui ferait disparaître la dépense d'un
    total sans que rien ne le signale.

    Le taux est arrondi **avant** la multiplication : c'est lui qui est figé
    sur la dépense, et rejouer « montant d'origine × taux figé » doit
    redonner exactement le montant enregistré.
    """
    if amount is None:
        return None, None
    if from_currency == to_currency:
        return Decimal(amount).quantize(CENTS), Decimal("1")

    source = rate_to_xof(from_currency, on_date, rates)
    cible = rate_to_xof(to_currency, on_date, rates)
    if source is None or cible is None or not cible:
        return None, None

    rate = (source / cible).quantize(RATE_PRECISION)
    return (Decimal(amount) * rate).quantize(CENTS), rate


# --- Consolidation ----------------------------------------------------------

#: Grandeurs consolidées en FCFA par :func:`consolidation_par_pays`.
CONSOLIDATED_KEYS = (
    "allocated", "sub_allocated", "engaged", "consumed", "justified", "gap",
    "remaining",
)


def consolidation_par_pays(budgets, rates=None):
    """Agrège les enveloppes par pays, puis consolide en FCFA.

    Seules les enveloppes de pays composent l'alloué : projet, équipe et
    manager n'en sont que des découpages (``sub_allocated``), les additionner
    compterait deux fois le même argent. Engagé, consommé et justifié, eux,
    se lisent sur chaque enveloppe, sous-enveloppes comprises : une dépense
    n'est imputée qu'à une seule.

    Renvoie ``(rows, consolidated)`` avec des ``Decimal`` (ou ``None`` pour
    un taux sans dénominateur ou une devise sans taux) ; les lignes sont
    triées par nom de pays et c'est aux vues de les mettre en forme.

    Les totaux ne s'additionnent qu'**en FCFA** : une ligne par pays reste
    dans sa devise, mais sommer des dirhams et des francs n'aurait aucun
    sens. Une devise sans taux connu est exclue du consolidé **et signalée**
    (``unconverted_currencies``), jamais absorbée.

    Unique point de calcul pour ``/api/budgets/summary/`` et le tableau de
    bord : deux implémentations avaient fini par diverger.
    """
    per_country = defaultdict(
        lambda: {
            "allocated": ZERO, "sub_allocated": ZERO, "engaged": ZERO,
            "consumed": ZERO, "justified": ZERO,
        }
    )
    countries = {}

    for budget in budgets:
        entry = per_country[budget.country_id]
        countries[budget.country_id] = budget.country
        if budget.scope_kind == "country":
            entry["allocated"] += budget.amount
        else:
            entry["sub_allocated"] += budget.amount
        figures = budget_figures(budget)
        entry["engaged"] += figures["engaged"]
        entry["consumed"] += figures["consumed"]
        entry["justified"] += figures["justified"]

    rows = []
    xof = defaultdict(lambda: ZERO)
    unconverted = set()

    for country_id, entry in per_country.items():
        country = countries[country_id]
        used = entry["consumed"] + entry["engaged"]
        remaining = entry["allocated"] - used
        row = {
            "country": country_id,
            "country_name": country.name,
            "country_ref": country.country_ref,
            "currency": country.currency,
            **entry,
            "gap": entry["consumed"] - entry["justified"],
            "remaining": remaining,
            "execution_rate": _ratio(used, entry["allocated"]),
            "justification_rate": _ratio(entry["justified"], entry["consumed"]),
        }

        rate = rate_to_xof(country.currency, rates=rates)
        for key in CONSOLIDATED_KEYS:
            row[f"{key}_xof"] = (
                (row[key] * rate).quantize(CENTS) if rate is not None else None
            )
            if rate is not None:
                xof[key] += row[f"{key}_xof"]
        if rate is None:
            unconverted.add(country.currency)
        rows.append(row)

    rows.sort(key=lambda row: row["country_name"])
    used_xof = xof["consumed"] + xof["engaged"]
    return (
        rows,
        {
            **{key: xof[key] for key in CONSOLIDATED_KEYS},
            "execution_rate": _ratio(used_xof, xof["allocated"]),
            "justification_rate": _ratio(xof["justified"], xof["consumed"]),
            "unconverted_currencies": sorted(unconverted),
        },
    )
