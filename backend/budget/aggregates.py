"""Calculs budgétaires — **toujours côté serveur** (§6).

Le solde ne doit jamais être reconstitué dans l'interface : c'est ici, et
uniquement ici, que consommation, écart et disponible sont établis.
"""

from decimal import Decimal

from django.db.models import Sum

from .models import CONSOLIDATION_CURRENCY, ExchangeRate

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")


def consumption(budget):
    """Montants consommés et justifiés sur une enveloppe.

    Les lignes de dépenses sont introduites au lot 2 et se rattacheront à
    l'enveloppe via la relation inverse ``expenses``. Tant qu'elle n'existe
    pas, aucune dépense n'a pu être saisie : une consommation nulle est donc
    la valeur exacte, pas une valeur par défaut.
    """
    expenses = getattr(budget, "expenses", None)
    if expenses is None:
        return {"consumed": ZERO, "justified": ZERO}

    totals = expenses.aggregate(
        consumed=Sum("amount"), justified=Sum("justified_amount")
    )
    return {
        "consumed": totals["consumed"] or ZERO,
        "justified": totals["justified"] or ZERO,
    }


def budget_figures(budget):
    """Indicateurs d'une enveloppe, dans la devise du pays."""
    totals = consumption(budget)
    consumed = totals["consumed"]
    justified = totals["justified"]
    return {
        "consumed": consumed,
        "justified": justified,
        # Écart entre ce qui est dépensé et ce qui est prouvé.
        "gap": consumed - justified,
        "remaining": budget.amount - consumed,
        "execution_rate": _ratio(consumed, budget.amount),
        "justification_rate": _ratio(justified, consumed),
    }


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def rate_to_xof(currency, on_date=None):
    """Taux en vigueur à une date, ou ``None`` si aucun n'est connu."""
    if currency == CONSOLIDATION_CURRENCY:
        return Decimal("1")
    rates = ExchangeRate.objects.filter(currency=currency)
    if on_date is not None:
        rates = rates.filter(valid_from__lte=on_date)
    rate = rates.order_by("-valid_from").first()
    return rate.rate_to_xof if rate else None


def to_xof(amount, currency, on_date=None):
    """Convertit un montant en FCFA, ou ``None`` faute de taux connu.

    Renvoyer ``None`` plutôt que zéro est délibéré : un total consolidé ne doit
    jamais absorber silencieusement une devise non convertible.
    """
    if amount is None:
        return None
    rate = rate_to_xof(currency, on_date)
    if rate is None:
        return None
    return (Decimal(amount) * rate).quantize(CENTS)
