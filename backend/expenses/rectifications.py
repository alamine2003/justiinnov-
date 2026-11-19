"""La rectification, seconde exception à l'irréversibilité (décision 131).

Un constat se demande à rectifier, motif à l'appui ; un administrateur qui
n'est pas le demandeur approuve — la ligne revient en contrôle par le tronc
commun du circuit — ou refuse.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.perimetre import exiger_dans_le_perimetre
from accounts.permissions import exiger_la_capacite, roles_pour
from core.regles import PermissionRefusee, RegleViolee
from notifications import triggers

from .audit import record
from .circuit import _transition, _verrouiller_la_ligne, _verrouiller_le_dossier
from .exigences import MOTIF_MANQUANT, Resultat, relire_sous_verrou
from .models import (
    AuditLog,
    Dossier,
    Rectification,
)
from .workflow import (
    DECIDED_STATUSES,
    RECTIFIABLE_STATUSES,
)


# --- La rectification (seconde exception) ---------------------------------------


def _exiger_le_perimetre(acteur, expense):
    """La ligne est dans le périmètre de l'acteur, sinon elle n'existe pas
    pour lui — pays, et équipes pour un manager qui y est restreint."""
    exiger_dans_le_perimetre(acteur, expense.country_id, expense.team_id)


def verifier_la_decision_de_rectification(rectification, acteur):
    """La demande se décide-t-elle, et par cet acteur ?

    Deux refus, deux codes : déjà traitée (400), demandée par l'acteur
    lui-même (403 — demander et trancher sont deux regards, comme pour une
    réallocation).
    """
    if rectification.status != Rectification.Status.PENDING:
        raise RegleViolee(
            "status", _("Cette demande de rectification a déjà été traitée.")
        )
    if rectification.requested_by and rectification.requested_by == acteur.username:
        raise PermissionRefusee(
            _("Vous ne pouvez pas décider d'une rectification que vous avez demandée.")
        )


def peut_decider_rectification(rectification, acteur, configuration=None):
    """``can_decide`` : les mêmes conditions que la décision, en booléen.

    ``configuration`` évite à une liste de relire la matrice ligne par ligne.
    """
    if acteur is None or acteur.role not in roles_pour(
        "rectifications.decide", configuration
    ):
        return False
    try:
        verifier_la_decision_de_rectification(rectification, acteur)
    except (RegleViolee, PermissionRefusee):
        return False
    return True


def _verrouiller_la_demande(rectification, acteur):
    """Relit la demande sous verrou et vérifie qu'elle se décide.

    Le statut est contrôlé **après** la prise du verrou : lu avant, deux
    approbations simultanées le verraient toutes deux « en attente » et
    défaisaient le constat deux fois.

    Le dossier d'abord, puis la demande : c'est l'ordre des autres services
    (``controler_piece``) et de la corbeille, qui verrouille le dossier
    avant de retirer la ligne et ses demandes (décision 120). Dans l'ordre
    inverse, les deux s'interbloquaient.
    """
    dossier_id = (
        Rectification.objects.filter(pk=rectification.pk)
        .values_list("expense__dossier_id", flat=True)
        .first()
    )
    # Sans objet en base, aucun dossier à verrouiller : la relecture sous
    # verrou qui suit répond introuvable.
    if dossier_id is not None:
        Dossier.objects.select_for_update().filter(pk=dossier_id).first()
    verrouillee = relire_sous_verrou(
        Rectification.objects.select_related(
            "expense__country", "expense__dossier", "expense__team"
        ).select_for_update(of=("self",)),
        rectification.pk,
    )
    verifier_la_decision_de_rectification(verrouillee, acteur)
    return verrouillee


def _journaliser_la_demande(trace, action, rectification, **detail):
    return record(
        trace, action, rectification,
        country=rectification.expense.country,
        expense=rectification.expense_id,
        dossier=rectification.expense.dossier.number,
        **detail,
    )


def _decider_la_demande(rectification, acteur, note, trace, statut):
    """Tronc commun d'une décision : statut, motif, signature, journal."""
    rectification.status = statut
    rectification.decision_note = note
    rectification.decided_by = acteur.username
    rectification.decided_at = timezone.now()
    rectification.save()
    return _journaliser_la_demande(
        trace, AuditLog.Action.RECTIFICATION_DECIDED, rectification,
        from_status=Rectification.Status.PENDING, to_status=statut, note=note,
    )


@transaction.atomic
def demander_rectification(expense, acteur, motif, trace):
    """Demande la rectification d'un constat : une ligne justifiée ou
    clôturée l'a été à tort, et voici pourquoi.

    Ouverte à tous par défaut (``rectifications.request``) : le pays voit
    l'erreur le premier. La ligne ne bouge pas — seule la décision la fera
    revenir en contrôle — mais la demande relève ce qu'elle remet en cause
    (état, montant justifié), pour que le journal et la fiche le disent
    encore quand la ligne aura été tranchée à nouveau. Une seule demande
    en attente par ligne : la contrainte en base y veille aussi.
    """
    exiger_la_capacite("rectifications.request", acteur)
    _exiger_le_perimetre(acteur, expense)
    motif = (motif or "").strip()
    if not motif:
        raise RegleViolee("motif", str(MOTIF_MANQUANT["rectify"]))
    ligne = _verrouiller_la_ligne(expense)
    if ligne.status not in RECTIFIABLE_STATUSES:
        raise RegleViolee(
            "status",
            _(
                "Seule une ligne justifiée ou clôturée se rectifie : "
                "celle-ci est « {status} »."
            ).format(status=ligne.get_status_display().lower()),
        )
    if ligne.rectifications.filter(status=Rectification.Status.PENDING).exists():
        raise RegleViolee(
            "expense",
            _("Une demande de rectification est déjà en attente sur cette ligne."),
        )
    demande = Rectification.objects.create(
        expense=ligne,
        motif=motif,
        requested_by=acteur.username,
        previous_status=ligne.status,
        previous_justified_amount=ligne.justified_amount,
    )
    entree = _journaliser_la_demande(
        trace, AuditLog.Action.RECTIFICATION_REQUESTED, demande,
        from_status=ligne.status, note=motif,
        justified_amount=str(ligne.justified_amount),
    )
    triggers.rectification_requested(demande, trace.compte)
    return Resultat(demande, audit=[entree])


@transaction.atomic
def approuver_rectification(rectification, acteur, note, trace):
    """Approuve la demande : la ligne revient en contrôle, le dossier la suit.

    Deux verrous dans l'ordre du circuit — le dossier, puis la ligne —
    comme à la soumission et à la réouverture : une clôture du dossier
    prise au même instant attend, et trouve la ligne revenue en contrôle
    au lieu de clore par-dessus. La transition ``rectify`` passe par le
    tronc commun (``_transition``) : état de départ vérifié, journal
    ``rectified`` avec avant et après, montant justifié remis à zéro. Le
    dossier ne suit que s'il avait été constaté (justifié, non justifié ou
    clôturé) : un dossier encore en contrôle n'a rien à défaire.
    """
    exiger_la_capacite("rectifications.decide", acteur)
    note = (note or "").strip()
    demande = _verrouiller_la_demande(rectification, acteur)
    _exiger_le_perimetre(acteur, demande.expense)
    dossier = _verrouiller_le_dossier(demande.expense.dossier)

    ligne = _transition(demande.expense, "rectify", acteur, trace, note=demande.motif)
    traces = list(ligne.audit)
    if dossier.status in DECIDED_STATUSES:
        suivi = _transition(dossier, "rectify", acteur, trace, note=demande.motif)
        traces.extend(suivi.audit)

    traces.append(
        _decider_la_demande(demande, acteur, note, trace, Rectification.Status.APPROVED)
    )
    triggers.rectification_decided(demande, trace.compte)
    return Resultat(demande, audit=traces)


@transaction.atomic
def refuser_rectification(rectification, acteur, note, trace):
    """Refuse la demande : le constat tient. Le refus est motivé — le
    demandeur doit savoir pourquoi on ne le suit pas."""
    exiger_la_capacite("rectifications.decide", acteur)
    note = (note or "").strip()
    if not note:
        raise RegleViolee("note", _("Un refus doit être motivé."))
    demande = _verrouiller_la_demande(rectification, acteur)
    _exiger_le_perimetre(acteur, demande.expense)
    entree = _decider_la_demande(
        demande, acteur, note, trace, Rectification.Status.REFUSED
    )
    triggers.rectification_decided(demande, trace.compte)
    return Resultat(demande, audit=[entree])
