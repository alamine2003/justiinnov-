"""Calculs budgétaires — **toujours côté serveur** (§6).

Le solde ne doit jamais être reconstitué dans l'interface : c'est ici, et
uniquement ici, que consommation, écart et disponible sont établis.
"""

from decimal import Decimal

from django.db.models import Q, Sum

from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES

from .models import CONSOLIDATION_CURRENCY, ExchangeRate

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")


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


def budget_figures(budget):
    """Indicateurs d'une enveloppe, dans la devise du pays."""
    totals = consumption(budget)
    engaged = totals["engaged"]
    consumed = totals["consumed"]
    justified = totals["justified"]
    return {
        "engaged": engaged,
        "consumed": consumed,
        "justified": justified,
        # Écart entre ce qui est dépensé et ce qui est prouvé.
        "gap": consumed - justified,
        # Le disponible retranche aussi l'engagé : sans cela, une enveloppe
        # paraîtrait libre alors qu'elle est déjà mobilisée.
        "remaining": budget.amount - consumed - engaged,
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
