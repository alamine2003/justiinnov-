"""Le dépôt d'un justificatif : verrous, contrôles, remplacement, trace.

Décision 125, qui prolonge la décision 41 : la vue de dépôt ne porte que le
HTTP. Elle valide la charge utile, écrit le fichier par ``serializer.save()``
— ``FileField`` l'exige — et appelle, de part et d'autre, les deux temps du
service :

1. :func:`preparer_le_depot` prend les verrous — le dossier, puis la ligne,
   puis la pièce remplacée — et juge ce qui a pu changer depuis la
   validation ; il rend un :class:`Depot` ;
2. :func:`consigner_le_depot` archive la pièce remplacée et écrit la trace.

:func:`doublon_refuse` traduit le doublon que la base a tranché (décision 45).
Aucun de ces services ne connaît DRF : ils lèvent les refus de
``core.regles``, que la vue traduit.
"""

from contextlib import contextmanager
from dataclasses import dataclass

from django.db import IntegrityError
from django.utils.translation import gettext as _

from core.regles import RegleViolee

from . import transitions
from .audit import record
from .models import AuditLog, Expense, Proof


@dataclass
class Depot:
    """Ce que le dépôt a relu sous verrou."""

    dossier: object
    ligne: object
    remplacee: object = None

    @property
    def version(self):
        return self.remplacee.version + 1 if self.remplacee is not None else 1


def verifier_le_remplacement(remplacee, dossier, ligne=None):
    """La pièce remplacée appartient au même dossier, et à la même ligne.

    Sans ce contrôle, un pays pouvait archiver — via ``replaces`` — une
    pièce d'un dossier qu'il n'a pas le droit de voir : le remplacement
    change le statut de la pièce remplacée. Le message ne distingue pas
    « autre dossier » de « inexistante », pour ne rien révéler. Une pièce
    d'avant la 2.0, sans ligne, se remplace sur une ligne de son dossier :
    c'est ainsi qu'elle trouve sa ligne (décision 107).
    """
    autre_ligne = (
        ligne is not None
        and remplacee.expense_id is not None
        and remplacee.expense_id != ligne.pk
    )
    if remplacee.dossier_id != dossier.pk or autre_ligne:
        raise RegleViolee("replaces", _("Pièce invalide pour ce dossier."))
    if remplacee.status == Proof.ProofStatus.ARCHIVED:
        raise RegleViolee("replaces", _("Cette pièce a déjà été remplacée."))


def preparer_le_depot(dossier, ligne, remplacee=None):
    """Verrouille et relit ce que le dépôt touche ; refuse ce qui a changé.

    Le dossier sous verrou le temps du dépôt : un retrait du brouillon au
    même instant attend, puis la pièce ne trouve plus son dossier (404) au
    lieu d'une violation de clé étrangère ; une clôture au même instant est
    relue avant d'écrire. La ligne est relue sous ce verrou : une ligne qui
    en serait sortie entre-temps ne range pas sa pièce dans l'ancien
    (décision 107), et un retrait de la ligne au même instant est attendu.
    """
    dossier = transitions.verrouiller_le_dossier_vise(dossier, None)
    if dossier.status in transitions.PROOF_LOCKED_STATUSES:
        # Sans champ : la réponse est la liste nue des erreurs, comme avant.
        raise RegleViolee(
            None, _("Le dossier est clôturé : plus aucun justificatif ne peut y être ajouté.")
        )
    if Expense.objects.select_for_update().filter(pk=ligne.pk, dossier=dossier).first() is None:
        raise RegleViolee("expense", _("Cette ligne n'est plus dans ce dossier."))
    if remplacee is not None:
        # Revalidée ici, hors sérialiseur, et **sous verrou** : la pièce
        # remplacée change d'état, elle doit relever du même dossier — et de
        # la même ligne — que la nouvelle, et ne pas avoir été remplacée
        # entre-temps. Jugée telle que lue à la validation, un second
        # « Remplacer » simultané butait sur l'unicité de ``replaces`` et
        # recevait « doublon » au lieu de « déjà remplacée ».
        remplacee = Proof.objects.select_for_update().get(pk=remplacee.pk)
        verifier_le_remplacement(remplacee, dossier, ligne)
    return Depot(dossier=dossier, ligne=ligne, remplacee=remplacee)


@contextmanager
def doublon_refuse():
    """Deux dépôts simultanés du même fichier : la base a tranché."""
    try:
        yield
    except IntegrityError as exc:
        raise RegleViolee(
            "file", _("Ce fichier est déjà rattaché à cette ligne (doublon).")
        ) from exc


def consigner_le_depot(piece, depot, trace):
    """Archive la pièce remplacée et écrit la trace du dépôt.

    ``trace`` est la requête ou une :class:`core.journal.Trace`.
    """
    dossier, ligne, remplacee = depot.dossier, depot.ligne, depot.remplacee
    commun = {
        "country": dossier.country,
        "dossier": dossier.number,
        "expense": ligne.pk,
        "sha256": piece.sha256,
        "version": piece.version,
    }
    if remplacee is None:
        record(trace, AuditLog.Action.PROOF_UPLOADED, piece, **commun)
        return
    remplacee.status = Proof.ProofStatus.ARCHIVED
    remplacee.save(update_fields=["status", "updated_at"])
    record(
        trace,
        AuditLog.Action.PROOF_REPLACED,
        piece,
        **commun,
        before={"sha256": remplacee.sha256, "version": remplacee.version},
        after={"sha256": piece.sha256, "version": piece.version},
        replaces=remplacee.pk,
    )
