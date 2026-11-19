"""Le retrait d'un brouillon par son auteur, avec ce qu'il contient
(décisions 46, 107 et 131).

Seul un brouillon jamais déclaré se retire : il n'a aucune valeur probante.
Chaque ligne et chaque pièce retirées laissent leur trace ; les fichiers ne
s'effacent qu'après le commit.
"""

from django.db import transaction
from django.utils.translation import gettext as _

from accounts.permissions import exiger_la_capacite
from core.regles import PermissionRefusee, RegleViolee

from . import stockage
from .audit import record
from .exigences import Resultat, exiger_une_ligne_jamais_rectifiee, relire_sous_verrou
from .models import (
    AuditLog,
    Expense,
    Rectification,
)
from .workflow import (
    DELETABLE_STATUSES,
    Status,
    a_ete_declare,
)


@transaction.atomic
def retirer_brouillon(objet, acteur, trace):
    """Retire un brouillon — dossier ou ligne — par son auteur.

    Une fois déclaré, l'effacer reviendrait à perdre la trace de l'argent :
    c'est précisément ce que l'application doit empêcher. Un brouillon
    jamais soumis n'a en revanche aucune valeur probante. Un dossier part
    avec ses lignes et ses pièces, chacune laissant sa trace ; il ne se
    retire pas s'il porte la ligne d'un autre auteur — ce serait effacer le
    travail de quelqu'un d'autre sous couvert de ranger le sien.
    """
    exiger_la_capacite("expenses.delete", acteur)
    instance = relire_sous_verrou(
        type(objet)._default_manager.select_related("country")
        .select_for_update(of=("self",)),
        objet.pk,
    )
    if instance.status not in DELETABLE_STATUSES:
        raise RegleViolee(
            "status",
            _(
                "Cet élément est déclaré : il ne peut plus être "
                "supprimé. Seul un brouillon peut l'être."
            ),
        )
    if a_ete_declare(instance):
        # Revenu au brouillon par une réouverture, il a été déclaré : il se
        # corrige et se soumet à nouveau, il ne disparaît pas.
        raise RegleViolee(
            "status",
            _(
                "Ce brouillon a déjà été déclaré, puis rouvert : il ne se "
                "supprime pas. Corrigez-le et soumettez-le à nouveau."
            ),
        )
    if instance.created_by and instance.created_by != acteur.username:
        raise PermissionRefusee(_("Seul l'auteur d'un brouillon peut le supprimer."))

    resultat = Resultat(instance)
    if isinstance(instance, Expense):
        exiger_une_ligne_jamais_rectifiee(instance)
        # Ses pièces d'abord : elles la protègent en base (décision 107).
        _retirer_les_pieces(
            instance.proofs, instance.dossier, trace, resultat,
            "Justificatif supprimé avec sa ligne",
        )
        resultat.audit.append(
            record(
                trace, AuditLog.Action.DELETED, instance,
                label=f"Brouillon supprimé — {instance}", amount=str(instance.amount),
                # La ligne disparaît : son dossier la retrouve dans
                # l'historique du projet (décision 110).
                dossier_id=instance.dossier_id,
            )
        )
        instance.delete()
        return resultat

    lignes = _retirer_le_contenu(instance, acteur, trace, resultat)
    resultat.audit.append(
        record(
            trace, AuditLog.Action.DELETED, instance,
            label=f"Brouillon supprimé — {instance}", lines=lignes,
        )
    )
    instance.delete()
    return resultat


def _retirer_le_contenu(dossier, acteur, trace, resultat):
    """Les lignes et les pièces d'un brouillon de dossier, une à une.

    Les lignes sont protégées en base contre la cascade : elles sont
    retirées une à une, chacune laissant sa trace. Rend le nombre de lignes.

    Lignes et pièces sont lues **sous verrou**, comme le dossier : une
    ligne lue sans verrou pouvait être soumise entre la lecture et le
    retrait. Les fichiers, eux, ne s'effacent pas ici — un stockage n'a
    pas de retour arrière — mais après le commit (``stockage``).
    """
    lignes = list(
        dossier.expenses.select_for_update(of=("self",)).select_related("country")
    )
    autrui = [
        ligne for ligne in lignes
        if ligne.created_by and ligne.created_by != acteur.username
    ]
    if autrui:
        raise PermissionRefusee(
            _(
                "Ce dossier contient des lignes saisies par quelqu'un "
                "d'autre ({author}) : il ne peut pas être supprimé."
            ).format(author=autrui[0].created_by)
        )
    if any(ligne.status != Status.DRAFT for ligne in lignes):
        raise RegleViolee(
            "expenses",
            _("Ce dossier contient une ligne déclarée : il ne peut plus être supprimé."),
        )
    # Une requête pour toutes les lignes, pas une par ligne.
    if Rectification.objects.filter(expense__in=lignes).exists():
        raise RegleViolee(
            "expenses",
            _(
                "Ce dossier contient une ligne qui a fait l'objet d'une demande "
                "de rectification : il ne se supprime plus."
            ),
        )

    # Les pièces d'abord : depuis la 2.0, elles protègent leur ligne en base
    # (décision 107).
    _retirer_les_pieces(
        dossier.proofs, dossier, trace, resultat,
        "Justificatif supprimé avec son dossier",
    )
    for ligne in lignes:
        resultat.audit.append(
            record(
                trace, AuditLog.Action.DELETED, ligne,
                label=f"Brouillon supprimé avec son dossier — {ligne}",
                amount=str(ligne.amount), dossier=dossier.number,
            )
        )
        ligne.delete()
    return len(lignes)


def _retirer_les_pieces(pieces, dossier, trace, resultat, libelle):
    """Retire des pièces d'un brouillon, chacune tracée, sous verrou.

    ``libelle`` est écrit tel quel au journal, en français comme ses
    autres libellés : il ne dépend pas de la langue du demandeur.

    La plus récente d'abord : une nouvelle version référence celle qu'elle
    remplace, et cette référence est protégée. Le fichier ne doit pas
    survivre à sa fiche — un stockage qui garde des pièces orphelines finit
    par en servir à tort —, mais il ne s'efface qu'une fois le retrait
    acquis, après le commit.
    """
    for piece in (
        pieces.select_for_update(of=("self",))
        .select_related("dossier__country")
        .order_by("-pk")
    ):
        resultat.audit.append(
            record(
                trace, AuditLog.Action.DELETED, piece,
                label=f"{libelle} — {piece}",
                country=dossier.country, sha256=piece.sha256, version=piece.version,
                dossier=dossier.number, dossier_id=dossier.pk,
            )
        )
        stockage.programmer_la_suppression(piece, trace=trace, dossier=dossier)
        piece.delete()
