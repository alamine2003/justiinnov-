"""Déclencheurs métier des notifications (§8).

Appelés depuis les vues, après que l'action a réussi : une notification ne doit
jamais faire échouer l'opération qu'elle signale.

Titres et corps sont des chaînes **paresseuses** (``format_lazy`` sur un
``gettext_lazy``) : ``services.notify`` les rend destinataire par
destinataire, dans la langue de chaque profil. Une f-string les aurait figés
dans la langue du processus émetteur — celle de l'ordonnanceur, pour tout le
monde.
"""

import logging

from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from accounts.permissions import COUNTRY_ROLES, roles_pour

from .models import Notification
from .services import notify, recipients_for

logger = logging.getLogger(__name__)

def controleurs():
    """Qui contrôle les dépenses — le siège, jamais le pays qui les a engagées.

    Ceux qui peuvent mettre en contrôle, lus dans la matrice des droits au
    moment de l'envoi : le DM, le DF et les administrateurs par défaut.
    ``recipients_for`` cloisonne : un DM ou un DF restreint à des pays n'est
    prévenu que pour ceux-là.
    """
    return roles_pour("expenses.review")

#: Qui peut fournir une pièce manquante ou corriger un dossier : le manager,
#: seul rôle du pays.
PROVIDERS = COUNTRY_ROLES

def arbitres():
    """Qui arbitre le budget : ceux qui décident des réallocations."""
    return roles_pour("reallocations.decide")


def _safe(action):
    """Exécute un déclencheur sans jamais propager son échec."""
    try:
        return action()
    except Exception:
        logger.exception("Notification non émise")
        return []


def _sauf(destinataires, actor):
    """Écarte l'auteur de l'action : on ne se prévient pas soi-même.

    ``actor`` peut manquer quand l'action vient d'une commande sans compte ;
    tout le monde est alors prévenu.
    """
    if actor is None:
        return destinataires
    return destinataires.exclude(pk=actor.pk)


def dossier_submitted(dossier, actor):
    """Prévient le contrôle qu'un dossier complet attend son examen.

    Une notification par dossier, et non par ligne : un dossier de vingt
    dépenses en produirait vingt, ce qui noierait l'information.
    """
    totaux = dossier.totals()
    return _safe(
        lambda: notify(
            _sauf(recipients_for(controleurs(), dossier.country, dossier.team), actor),
            kind=Notification.Kind.EXPENSE_SUBMITTED,
            level=Notification.Level.INFO,
            title=format_lazy(
                _("Dossier à contrôler — {number}"), number=dossier.number
            ),
            body=format_lazy(
                _("{label} · {amount} {currency} sur {lines} ligne(s)."),
                label=dossier.label,
                amount=totaux["amount"],
                currency=dossier.country.currency,
                lines=dossier.expenses.count(),
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
            _sauf(author, actor),
            kind=Notification.Kind.EXPENSE_REJECTED,
            level=Notification.Level.WARNING,
            title=format_lazy(_("Dépense refusée — {title}"), title=expense.title),
            body=format_lazy(_("Motif : {motive}"), motive=motive),
            link=f"/dossiers/{expense.dossier_id}",
            country=expense.country,
            dedup_key=f"expense_rejected:{expense.pk}:{expense.updated_at.isoformat()}",
        )
    )


def dossier_reopened(dossier, actor, motive):
    """Prévient le pays qu'un dossier déclaré lui revient, et pourquoi.

    Seule exception à l'irréversibilité (``expenses.workflow``) : un
    administrateur a renvoyé le dossier au brouillon pour demander des
    comptes. Ceux qui l'ont déclaré — les managers du pays — doivent le
    savoir sans attendre d'ouvrir la liste : il faut le corriger et le
    resoumettre. Le motif figure dans le message, pas seulement sur la fiche.

    La clé d'unicité porte le dossier et l'instant de sa dernière écriture —
    celle de la réouverture elle-même : chaque réouverture notifie, même
    deux le même jour. Une clé au jour taisait la seconde, alors que le
    pays avait resoumis entre-temps et devait apprendre le nouveau motif.
    """
    return _safe(
        lambda: notify(
            _sauf(recipients_for(PROVIDERS, dossier.country, dossier.team), actor),
            kind=Notification.Kind.DOSSIER_REOPENED,
            level=Notification.Level.WARNING,
            title=format_lazy(_("Dossier rouvert — {number}"), number=dossier.number),
            body=format_lazy(
                _(
                    "{label} : le dossier est revenu au brouillon, à corriger "
                    "puis à resoumettre. Motif : {motive}"
                ),
                label=dossier.label,
                motive=motive,
            ),
            link=f"/dossiers/{dossier.pk}",
            country=dossier.country,
            dedup_key=f"dossier_reopened:{dossier.pk}:{dossier.updated_at.isoformat()}",
        )
    )


#: Correspondance entre le type d'alerte et le type de notification.
ALERT_KINDS = {
    "budget_overrun": Notification.Kind.BUDGET_OVERRUN,
    "budget_threshold": Notification.Kind.BUDGET_THRESHOLD,
    "proof_missing": Notification.Kind.PROOF_MISSING,
    "proof_incomplete": Notification.Kind.PROOF_INCOMPLETE,
}

#: Qui doit être averti, selon la nature de l'alerte : le siège entier
#: (super administrateurs, RH, DF, DM), et le manager pour les alertes de
#: son pays.
#: L'enveloppe : la direction l'arbitre, le contrôle la surveille, et le
#: pays reste averti de son état même s'il ne la justifie pas lui-même. Un
#: justificatif manquant concerne d'abord ceux qui peuvent le fournir — le
#: pays — autant que ceux qui devront le contrôler.
ALERT_KINDS_NOTIFIED = frozenset(
    {"budget_overrun", "budget_threshold", "proof_missing", "proof_incomplete"}
)


def audience_roles(alert_kind):
    """Rôles avertis d'une alerte : le contrôle et le pays."""
    if alert_kind not in ALERT_KINDS_NOTIFIED:
        raise KeyError(alert_kind)
    return controleurs() | PROVIDERS


def audience_for(alert_kind, country, team=None):
    """Destinataires d'un type d'alerte pour un pays et, s'il y a lieu, une équipe.

    Exposé pour que l'appelant puisse résoudre une fois et réutiliser : cent
    dossiers sans preuve interrogeraient sinon cent fois la même liste. Un
    cache global serait pire encore — un compte créé ensuite ne recevrait
    plus jamais d'alerte.

    ``team`` est celle du dossier ou de la ligne en alerte (identifiant ou
    instance) ; une alerte d'enveloppe n'en a pas et s'adresse au pays.
    """
    return list(recipients_for(audience_roles(alert_kind), country, team))


def alert_raised(alert, country, recipients=None):
    """Relaie une alerte calculée (§8).

    La clé de l'alerte sert de clé d'unicité : un même manquement n'est
    signalé qu'une fois, quel que soit le nombre de passages. Titre et
    détail viennent de ``reporting.alerts``, déjà paresseux.
    """
    kind = ALERT_KINDS.get(alert["kind"])
    if kind is None:
        return []
    critical = alert["level"] == "critical"
    destinataires = (
        recipients
        if recipients is not None
        else audience_for(alert["kind"], country, alert.get("team"))
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
            _sauf(recipients_for(arbitres(), country), actor),
            kind=Notification.Kind.REALLOCATION_REQUESTED,
            level=Notification.Level.INFO,
            title=_("Demande de réallocation budgétaire"),
            body=format_lazy(
                _("{amount} {currency} : {source} → {target}. Motif : {reason}"),
                amount=reallocation.amount,
                currency=country.currency,
                source=reallocation.source,
                target=reallocation.target,
                reason=reallocation.reason,
            ),
            link="/budgets",
            country=country,
            dedup_key=f"reallocation:{reallocation.pk}",
        )
    )
