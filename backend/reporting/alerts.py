"""Alertes du §5.6 : seuils, dépassements, justificatifs et anomalies.

Les alertes sont **calculées**, jamais stockées : elles reflètent l'état
courant. Ce sont les notifications (§8) qui, elles, sont persistées, pour
n'avertir qu'une fois d'un même franchissement.
"""

from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q, Sum

from budget.aggregates import budget_figures
from expenses.models import Expense, Proof
from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES, Status

ZERO = Decimal("0.00")


class Level:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


def _alert(kind, level, title, detail, country=None, link="", key=""):
    return {
        "kind": kind,
        "level": level,
        "title": title,
        "detail": detail,
        "country": country.pk if country else None,
        "country_name": country.name if country else None,
        "link": link,
        "key": key,
    }


def budget_alerts(budgets):
    """Seuils de consommation franchis et dépassements (§8)."""
    thresholds = sorted(settings.ALERT_THRESHOLDS, reverse=True)
    alerts = []

    for budget in budgets:
        if not budget.amount:
            continue
        figures = budget_figures(budget)
        used = figures["consumed"] + figures["engaged"]
        percentage = (used / budget.amount * 100).quantize(Decimal("0.1"))

        if used > budget.amount:
            overrun = used - budget.amount
            alerts.append(
                _alert(
                    "budget_overrun",
                    Level.CRITICAL,
                    f"Dépassement — {budget}",
                    f"{overrun} {budget.country.currency} au-delà de l'enveloppe "
                    f"({percentage} % engagés).",
                    country=budget.country,
                    link="/budgets",
                    key=f"budget_overrun:{budget.pk}",
                )
            )
            continue

        # Seul le seuil le plus élevé atteint est signalé : trois alertes pour
        # la même enveloppe noieraient l'information.
        for threshold in thresholds:
            if percentage >= threshold:
                alerts.append(
                    _alert(
                        "budget_threshold",
                        Level.CRITICAL if threshold >= 100 else Level.WARNING,
                        f"Seuil {threshold} % atteint — {budget}",
                        f"{percentage} % de l'enveloppe sont engagés ou consommés.",
                        country=budget.country,
                        link="/budgets",
                        key=f"budget_threshold:{budget.pk}:{threshold}",
                    )
                )
                break
    return alerts


def proof_alerts(dossiers):
    """Dossiers engagés sans preuve, ou dont une preuve est incomplète."""
    alerts = []
    pending = dossiers.filter(
        status__in=list(ENGAGING_STATUSES) + list(CONSUMING_STATUSES)
    ).annotate(
        usable_proofs=Count(
            "proofs",
            filter=~Q(proofs__status__in=[
                Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED
            ]),
            distinct=True,
        ),
        incomplete_proofs=Count(
            "proofs",
            filter=Q(proofs__status=Proof.ProofStatus.INCOMPLETE),
            distinct=True,
        ),
    )

    for dossier in pending.select_related("country"):
        if dossier.usable_proofs == 0:
            alerts.append(
                _alert(
                    "proof_missing",
                    Level.CRITICAL,
                    f"Justificatif manquant — {dossier.number}",
                    f"Le dossier « {dossier.label} » est engagé sans aucune preuve.",
                    country=dossier.country,
                    link=f"/dossiers/{dossier.pk}",
                    key=f"proof_missing:{dossier.pk}",
                )
            )
        elif dossier.incomplete_proofs:
            alerts.append(
                _alert(
                    "proof_incomplete",
                    Level.WARNING,
                    f"Justificatif incomplet — {dossier.number}",
                    f"{dossier.incomplete_proofs} pièce(s) signalée(s) incomplète(s).",
                    country=dossier.country,
                    link=f"/dossiers/{dossier.pk}",
                    key=f"proof_incomplete:{dossier.pk}",
                )
            )
    return alerts


def unusual_expense_alerts(expenses):
    """Dépenses hors norme, rapportées aux **autres** dépenses de leur pays.

    La référence est établie par pays : comparer des montants entre pays aux
    devises et aux ordres de grandeur différents n'aurait pas de sens. Elle
    exclut aussi la dépense examinée — une dépense assez grosse relèverait
    sinon sa propre moyenne au point de ne plus s'en détacher.
    """
    factor = Decimal(str(settings.UNUSUAL_EXPENSE_FACTOR))
    consuming = list(CONSUMING_STATUSES)
    stats = {
        row["country"]: (row["total"], row["lines"])
        for row in Expense.objects.filter(status__in=consuming)
        .values("country")
        .annotate(total=Sum("amount"), lines=Count("id"))
    }

    alerts = []
    # Un brouillon n'est pas encore une dépense ; tout le reste l'est, y
    # compris ce qui n'a pas trouvé sa preuve.
    candidates = expenses.exclude(status=Status.DRAFT)
    for expense in candidates.select_related("country", "dossier"):
        total, lines = stats.get(expense.country_id, (None, 0))
        if total is None:
            continue
        # Comparaison « sans soi » : la dépense examinée sort de la référence.
        if expense.status in CONSUMING_STATUSES:
            total -= expense.amount
            lines -= 1
        if lines < 1:
            continue
        average = total / lines
        if average <= 0 or expense.amount <= average * factor:
            continue
        alerts.append(
            _alert(
                "unusual_expense",
                Level.WARNING,
                f"Dépense inhabituelle — {expense.title}",
                f"{expense.amount} {expense.country.currency}, soit plus de "
                f"{factor:g} fois la moyenne des autres dépenses du pays.",
                country=expense.country,
                link=f"/dossiers/{expense.dossier_id}",
                key=f"unusual_expense:{expense.pk}",
            )
        )
    return alerts


def collect(budgets, dossiers, expenses):
    """Toutes les alertes d'un périmètre, les plus graves en tête."""
    alerts = (
        budget_alerts(budgets)
        + proof_alerts(dossiers)
        + unusual_expense_alerts(expenses)
    )
    severity = {Level.CRITICAL: 0, Level.WARNING: 1, Level.INFO: 2}
    alerts.sort(key=lambda alert: (severity[alert["level"]], alert["title"]))
    return alerts
