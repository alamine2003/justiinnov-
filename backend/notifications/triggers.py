"""Déclencheurs métier des notifications (§8).

Appelés depuis les vues, après que l'action a réussi : une notification ne doit
jamais faire échouer l'opération qu'elle signale.
"""

import logging

from accounts.models import Role

from .models import Notification
from .services import notify, recipients_for

logger = logging.getLogger(__name__)

#: Qui contrôle les dépenses — le siège, jamais le pays qui les a engagées.
CONTROLLERS = [Role.CONTROLLER, Role.ADMIN, Role.DOO, Role.SUPER_ADMIN]

#: Qui peut fournir une pièce manquante : ceux qui ont saisi la dépense.
PROVIDERS = [Role.COUNTRY_MANAGER, Role.OWNER]

#: Qui arbitre le budget.
BUDGET_OWNERS = [Role.DOO, Role.SUPER_ADMIN]


def _safe(action):
    """Exécute un déclencheur sans jamais propager son échec."""
    try:
        return action()
    except Exception:
        logger.exception("Notification non émise")
        return []


def dossier_submitted(dossier, actor):
    """Prévient le contrôle qu'un dossier complet attend son examen.

    Une notification par dossier, et non par ligne : un dossier de vingt
    dépenses en produirait vingt, ce qui noierait l'information.
    """
    totaux = dossier.totals()
    return _safe(
        lambda: notify(
            recipients_for(CONTROLLERS, dossier.country).exclude(pk=actor.pk),
            kind=Notification.Kind.EXPENSE_SUBMITTED,
            level=Notification.Level.INFO,
            title=f"Dossier à contrôler — {dossier.number}",
            body=(
                f"{dossier.label} · {totaux['amount']} "
                f"{dossier.country.currency} sur {dossier.expenses.count()} ligne(s)."
            ),
            link=f"/dossiers/{dossier.pk}",
            country=dossier.country,
            dedup_key=f"dossier_submitted:{dossier.pk}:{dossier.updated_at.isoformat()}",
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


#: Correspondance entre le type d'alerte et le type de notification.
ALERT_KINDS = {
    "budget_overrun": Notification.Kind.BUDGET_OVERRUN,
    "budget_threshold": Notification.Kind.BUDGET_THRESHOLD,
    "proof_missing": Notification.Kind.PROOF_MISSING,
    "proof_incomplete": Notification.Kind.PROOF_INCOMPLETE,
}

#: Qui doit être averti, selon la nature de l'alerte.
ALERT_AUDIENCE = {
    # Le pays reste averti de l'état de son enveloppe, même s'il ne la
    # justifie pas lui-même.
    "budget_overrun": BUDGET_OWNERS + [Role.COUNTRY_MANAGER],
    "budget_threshold": BUDGET_OWNERS + [Role.COUNTRY_MANAGER],
    # Un justificatif manquant concerne d'abord ceux qui peuvent le fournir —
    # le pays — autant que ceux qui devront le contrôler.
    "proof_missing": CONTROLLERS + PROVIDERS,
    "proof_incomplete": CONTROLLERS + PROVIDERS,
}


def audience_for(alert_kind, country):
    """Destinataires d'un type d'alerte pour un pays.

    Exposé pour que l'appelant puisse résoudre une fois et réutiliser : cent
    dossiers sans preuve interrogeraient sinon cent fois la même liste. Un
    cache global serait pire encore — un compte créé ensuite ne recevrait
    plus jamais d'alerte.
    """
    return list(recipients_for(ALERT_AUDIENCE[alert_kind], country))


def alert_raised(alert, country, recipients=None):
    """Relaie une alerte calculée (§8).

    La clé de l'alerte sert de clé d'unicité : un même manquement n'est
    signalé qu'une fois, quel que soit le nombre de passages.
    """
    kind = ALERT_KINDS.get(alert["kind"])
    if kind is None:
        return []
    critical = alert["level"] == "critical"
    destinataires = (
        recipients if recipients is not None else audience_for(alert["kind"], country)
    )
    return _safe(
        lambda: notify(
            destinataires,
            kind=kind,
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
