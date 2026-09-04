"""Alertes du §5.6 : seuils, dépassements, justificatifs et anomalies.

Les alertes sont **calculées**, jamais stockées : elles reflètent l'état
courant. Ce sont les notifications (§8) qui, elles, sont persistées, pour
n'avertir qu'une fois d'un même franchissement.

Titres et détails sont des chaînes **paresseuses** (:func:`format_lazy`) :
une même alerte est lue dans la langue du tableau de bord par qui le
consulte, et dans la langue de chaque destinataire par les notifications.
Une chaîne rendue ici le serait dans la langue du processus qui calcule —
celle de l'ordonnanceur, pour tout le monde.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from budget.aggregates import budget_figures
from expenses.models import Proof
from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES, Status
from core.models import WorkflowConfiguration

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


def _pourcentage(part, total):
    return (part / total * 100).quantize(Decimal("0.1"))


def budget_alerts(budgets):
    """Seuils de consommation franchis et dépassements (§8)."""
    thresholds = sorted(WorkflowConfiguration.charger().alert_thresholds, reverse=True)
    alerts = []

    for budget in budgets:
        figures = budget_figures(budget)
        used = figures["consumed"] + figures["engaged"]
        if not used and not budget.amount:
            continue

        if used > budget.amount:
            # Une enveloppe à zéro sur laquelle des dépenses sont engagées est
            # un dépassement, pas un cas à ignorer : c'est même le plus net.
            # Le pourcentage n'a alors pas de sens et n'est pas affiché.
            overrun = used - budget.amount
            taux = (
                format_lazy(
                    _(" ({taux} % engagés)"), taux=_pourcentage(used, budget.amount)
                )
                if budget.amount else ""
            )
            alerts.append(
                _alert(
                    "budget_overrun",
                    Level.CRITICAL,
                    format_lazy(_("Dépassement — {budget}"), budget=budget),
                    format_lazy(
                        _("{overrun} {currency} au-delà de l'enveloppe{taux}."),
                        overrun=overrun, currency=budget.country.currency, taux=taux,
                    ),
                    country=budget.country,
                    link="/budgets",
                    key=f"budget_overrun:{budget.pk}",
                )
            )
            continue
        if not budget.amount:
            continue
        percentage = _pourcentage(used, budget.amount)

        # Seul le seuil le plus élevé atteint est signalé : trois alertes pour
        # la même enveloppe noieraient l'information.
        for threshold in thresholds:
            if percentage >= threshold:
                alerts.append(
                    _alert(
                        "budget_threshold",
                        Level.CRITICAL if threshold >= 100 else Level.WARNING,
                        format_lazy(
                            _("Seuil {threshold} % atteint — {budget}"),
                            threshold=threshold, budget=budget,
                        ),
                        format_lazy(
                            _("{percentage} % de l'enveloppe sont engagés ou consommés."),
                            percentage=percentage,
                        ),
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
    delay = WorkflowConfiguration.charger().unjustified_alert_days
    pending = dossiers.filter(
        status__in=list(ENGAGING_STATUSES) + list(CONSUMING_STATUSES)
    )
    if delay:
        # Le délai de grâce s'applique dans la requête : le tester en mémoire
        # obligeait à charger — et à annoter — tous les dossiers récents pour
        # les écarter ensuite un à un.
        pending = pending.filter(
            date__lte=timezone.now().date() - timedelta(days=delay)
        )
    pending = pending.annotate(
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
                    format_lazy(
                        _("Justificatif manquant — {number}"), number=dossier.number
                    ),
                    format_lazy(
                        _("Le dossier « {label} » est engagé sans aucune preuve."),
                        label=dossier.label,
                    ),
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
                    format_lazy(
                        _("Justificatif incomplet — {number}"), number=dossier.number
                    ),
                    format_lazy(
                        _("{count} pièce(s) signalée(s) incomplète(s)."),
                        count=dossier.incomplete_proofs,
                    ),
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

    Cette comparaison « sans soi » se ramène à un simple seuil par pays. En
    notant *T* le total consommé du pays, *n* son nombre de lignes et *f* le
    facteur, la condition ``montant > f × (T − montant) / (n − 1)`` équivaut à
    ``montant > f × T / (n − 1 + f)``. Le filtrage se fait donc en base, au
    lieu de parcourir toutes les dépenses du pays en mémoire.
    """
    factor = WorkflowConfiguration.charger().unusual_expense_factor
    consuming = list(CONSUMING_STATUSES)
    # La référence se calcule sur le queryset reçu — même exercice, même
    # périmètre — et non sur toute la table : une dépense énorme d'un exercice
    # passé relevait sinon la moyenne au point de masquer celles de l'année.
    # Le ``order_by()`` est nécessaire : le tri par défaut du modèle entrerait
    # sinon dans le GROUP BY et ferait éclater les totaux ligne par ligne.
    stats = {
        row["country"]: (row["total"], row["lines"])
        for row in expenses.filter(status__in=consuming)
        .order_by()
        .values("country")
        .annotate(total=Sum("amount"), lines=Count("id"))
    }

    conditions = Q()
    retenu = False
    for country_id, (total, lines) in stats.items():
        # Il faut au moins une autre dépense pour que « hors norme » ait un sens.
        if not total or lines < 2:
            continue
        seuil_consommee = factor * total / (lines - 1 + factor)
        # Une dépense encore engagée n'entre pas dans le total : elle se compare
        # à la moyenne entière.
        seuil_engagee = factor * total / lines
        conditions |= Q(
            country_id=country_id, status__in=consuming, amount__gt=seuil_consommee
        )
        conditions |= ~Q(status__in=consuming) & Q(
            country_id=country_id, amount__gt=seuil_engagee
        )
        retenu = True

    if not retenu:
        return []

    hors_norme = (
        expenses.exclude(status=Status.DRAFT)
        .filter(conditions)
        .select_related("country", "dossier")
    )
    return [
        _alert(
            "unusual_expense",
            Level.WARNING,
            format_lazy(_("Dépense inhabituelle — {title}"), title=expense.title),
            format_lazy(
                _(
                    "{amount} {currency}, soit plus de {factor} fois la moyenne "
                    "des autres dépenses du pays."
                ),
                amount=expense.amount, currency=expense.country.currency,
                factor=f"{factor:g}",
            ),
            country=expense.country,
            link=f"/dossiers/{expense.dossier_id}",
            key=f"unusual_expense:{expense.pk}",
        )
        for expense in hors_norme
    ]


def collect(budgets, dossiers, expenses):
    """Toutes les alertes d'un périmètre, les plus graves en tête."""
    alerts = (
        budget_alerts(budgets)
        + proof_alerts(dossiers)
        + unusual_expense_alerts(expenses)
    )
    severity = {Level.CRITICAL: 0, Level.WARNING: 1, Level.INFO: 2}
    # Le titre est rendu pour le tri : deux chaînes paresseuses se comparent
    # mal, et l'ordre doit être celui de la langue courante.
    alerts.sort(key=lambda alert: (severity[alert["level"]], str(alert["title"])))
    return alerts


def rendue(alert):
    """L'alerte avec ses textes rendus dans la langue courante.

    Le tableau de bord la sérialise en JSON : le rendu explicite évite de
    dépendre de la façon dont l'encodeur traite une chaîne paresseuse.
    """
    return {**alert, "title": str(alert["title"]), "detail": str(alert["detail"])}
