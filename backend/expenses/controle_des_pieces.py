"""Le contrôle documentaire d'un justificatif par le siège (décisions 53,
115 et 131) : valider, rejeter, signaler incomplet, remettre à revoir.
"""

from django.db import transaction
from django.utils.translation import gettext as _

from accounts.permissions import exiger_la_capacite
from core.regles import RegleViolee

from .audit import record
from .exigences import Resultat, relire_sous_verrou
from .models import (
    AuditLog,
    Dossier,
    Proof,
)
from .workflow import (
    PROOF_LOCKED_STATUSES,
    next_proof_status,
)


#: État visé d'une pièce → action d'audit.
PROOF_AUDIT_ACTIONS = {
    Proof.ProofStatus.VALIDATED: AuditLog.Action.APPROVED,
    Proof.ProofStatus.REJECTED: AuditLog.Action.REJECTED,
    Proof.ProofStatus.INCOMPLETE: AuditLog.Action.PROOF_INCOMPLETE,
    Proof.ProofStatus.TO_REVIEW: AuditLog.Action.PROOF_TO_REVIEW,
}


@transaction.atomic
def controler_piece(proof, statut, acteur, *, motif="", trace):
    """Contrôle documentaire : valide, rejette ou signale un justificatif.

    Relève du siège (``proofs.review``), pas du déposant. Une pièce d'un
    dossier clôturé ne se contrôle plus, comme il ne s'en dépose plus ; les
    états atteignables sont ceux de ``PROOF_TRANSITIONS``.
    """
    exiger_la_capacite("proofs.review", acteur)
    motif = (motif or "").strip()
    # Le dossier, puis la pièce (décision 53) : sans le verrou du dossier,
    # une pièce se rejetait pendant que le dossier se clôturait, chacun
    # croyant l'autre inchangé — et le dossier se fermait sur une pièce
    # rejetée, ce que la décision 115 refuse.
    dossier_id = Proof.objects.filter(pk=proof.pk).values_list("dossier_id", flat=True).first()
    # Sans objet en base, aucun dossier à verrouiller : la relecture sous
    # verrou qui suit répond introuvable.
    if dossier_id is not None:
        Dossier.objects.select_for_update().filter(pk=dossier_id).first()
    piece = relire_sous_verrou(
        Proof.objects.select_related("dossier__country").select_for_update(of=("self",)),
        proof.pk,
    )
    if piece.dossier.status in PROOF_LOCKED_STATUSES:
        raise RegleViolee(
            "status",
            _("Le dossier est clôturé : ses justificatifs ne se contrôlent plus."),
        )
    next_proof_status(piece.status, statut, dict(Proof.ProofStatus.choices))

    previous = piece.status
    piece.status = statut
    piece.rejection_reason = motif if statut == Proof.ProofStatus.REJECTED else ""
    piece.is_complete = statut != Proof.ProofStatus.INCOMPLETE
    piece.save()

    entree = record(
        trace,
        PROOF_AUDIT_ACTIONS[statut],
        piece,
        country=piece.dossier.country,
        from_status=previous,
        to_status=statut,
        reason=motif,
    )
    return Resultat(piece, audit=[entree])
