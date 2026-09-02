"""Journalisation des mouvements budgétaires (§5.7).

Réduire une enveloppe de huit millions à quatre cent mille ne laissait aucune
trace. Ces mouvements rejoignent donc l'historique des changements, consultable
au même endroit que le reste du référentiel.
"""

from core.models import ChangeLog
from core.signals import register

from .models import Budget, BudgetReallocation, ExchangeRate


def _reallocation_country(reallocation):
    """Une réallocation n'a pas de pays propre : celui de l'enveloppe source."""
    return reallocation.source.country


def _no_country(_instance):
    """Un taux de change vaut pour toutes les devises, sans pays rattaché."""
    return None


def connect():
    register(Budget, ChangeLog.Models.BUDGET)
    register(
        BudgetReallocation,
        ChangeLog.Models.REALLOCATION,
        country_resolver=_reallocation_country,
    )
    register(
        ExchangeRate, ChangeLog.Models.EXCHANGE_RATE, country_resolver=_no_country
    )
