"""Déclencheurs métier des notifications (§8).

Appelés depuis les vues, après que l'action a réussi : une notification ne doit
jamais faire échouer l'opération qu'elle signale.
"""

import logging

from accounts.models import Role

from .models import Notification
from .services import notify, recipients_for

logger = logging.getLogger(__name__)

#: Qui contrôle les dépenses d'un pays.
CONTROLLERS = [Role.CONTROLLER, Role.COUNTRY_MANAGER, Role.DOO, Role.SUPER_ADMIN]
#: Qui arbitre le budget.
BUDGET_OWNERS = [Role.DOO, Role.SUPER_ADMIN]


def _safe(action):
    """Exécute un déclencheur sans jamais propager son échec."""
    try:
        return action()
    except Exception:
        logger.exception("Notification non émise")
        return []


def expense_submitted(expense, actor):
    """Prévient les contrôleurs qu'une dépense attend leur examen."""
    return _safe(
        lambda: notify(
            recipients_for(CONTROLLERS, expense.country).exclude(pk=actor.pk),
            kind=Notification.Kind.EXPENSE_SUBMITTED,
            level=Notification.Level.INFO,
            title=f"Dépense à contrôler — {expense.title}",
            body=(
                f"{expense.amount} {expense.country.currency} "
                f"sur le dossier {expense.dossier.number}."
            ),
            link=f"/dossiers/{expense.dossier_id}",
            country=expense.country,
            # Une resoumission après correction doit re-notifier : la clé
            # inclut donc la date de mise à jour.
            dedup_key=f"expense_submitted:{expense.pk}:{expense.updated_at.isoformat()}",
        )
    )


def expense_rejected(expense, actor, motive):
    """Prévient le saisisseur du rejet et de son motif."""
    from django.contrib.auth.models import User

    if not expense.created_by:
        return []
    author = User.objects.filter(username=expense.created_by, is_active=True)
    return _safe(
        lambda: notify(
            author.exclude(pk=actor.pk),
            kind=Notification.Kind.EXPENSE_REJECTED,
            level=Notification.Level.WARNING,
            title=f"Dépense refusée — {expense.title}",
            body=f"Motif : {motive}",
            link=f"/dossiers/{expense.dossier_id}",
            country=expense.country,
            dedup_key=f"expense_rejected:{expense.pk}:{expense.updated_at.isoformat()}",
        )
    )


def budget_alert(alert, country):
    """Relaie une alerte budgétaire calculée par le tableau de bord.

    La clé de l'alerte sert de clé d'unicité : un seuil franchi n'est signalé
    qu'une fois, même si le tableau de bord est rouvert vingt fois.
    """
    critical = alert["level"] == "critical"
    return _safe(
        lambda: notify(
            recipients_for(BUDGET_OWNERS + [Role.COUNTRY_MANAGER], country),
            kind=(
                Notification.Kind.BUDGET_OVERRUN
                if alert["kind"] == "budget_overrun"
                else Notification.Kind.BUDGET_THRESHOLD
            ),
            level=(
                Notification.Level.CRITICAL if critical else Notification.Level.WARNING
            ),
            title=alert["title"],
            body=alert["detail"],
            link=alert["link"],
            country=country,
            dedup_key=alert["key"],
        )
    )


def reallocation_requested(reallocation, actor):
    """Prévient les arbitres qu'un transfert attend leur décision."""
    country = reallocation.source.country
    return _safe(
        lambda: notify(
            recipients_for(BUDGET_OWNERS, country).exclude(pk=actor.pk),
            kind=Notification.Kind.REALLOCATION_REQUESTED,
            level=Notification.Level.INFO,
            title="Demande de réallocation budgétaire",
            body=(
                f"{reallocation.amount} {country.currency} : "
                f"{reallocation.source} → {reallocation.target}. "
                f"Motif : {reallocation.reason}"
            ),
            link="/budgets",
            country=country,
            dedup_key=f"reallocation:{reallocation.pk}",
        )
    )
