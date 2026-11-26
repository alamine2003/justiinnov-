"""Ce que partagent les services du circuit (décision 131).

Le résultat qu'ils rendent, les motifs exigés, les prédicats que la saisie,
le circuit, le retrait et l'import jugent de la même façon, et la relecture
sous verrou qui traduit un objet disparu en 404. Ce module n'importe aucun
de ses voisins : tous l'importent.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.regles import HorsPerimetre, PermissionRefusee, RegleViolee

from .models import (
    Dossier,
    Expense,
)
from .workflow import (
    FOUR_EYES_ACTIONS,
    LOCKED_STATUSES,
    a_ete_rectifiee,
    accepte_des_lignes,
    agit_en_auteur,
    breaks_four_eyes,
)


#: Message renvoyé quand une action qui exige un motif n'en reçoit pas.
MOTIF_MANQUANT = {
    "reject": gettext_lazy("Un rejet doit être motivé."),
    "reopen": gettext_lazy(
        "Une réouverture doit être motivée : le pays doit savoir ce qu'on "
        "lui demande."
    ),
    "rectify": gettext_lazy(
        "Une rectification doit être motivée : le siège doit savoir ce "
        "qu'il a constaté à tort."
    ),
}


@dataclass
class Resultat:
    """Ce qu'un service rend : l'objet après coup, l'avertissement, les traces."""

    instance: object
    warning: str | None = None
    audit: list = field(default_factory=list)


# --- Prédicats partagés -----------------------------------------------------


def exiger_l_auteur_du_brouillon(objet, acteur, message=None):
    """Un brouillon ne se modifie — ni ne se soumet — que par qui l'a saisi.

    Un collègue du même pays qui changerait le montant laisserait l'auteur
    soumettre une ligne qu'il n'a pas écrite, sous son nom ; un collègue qui
    soumettrait le dossier d'un autre déclarerait au nom de l'auteur ce que
    celui-ci n'a pas fini de saisir. Le siège ne corrige plus un brouillon :
    il ne déclare pas (décision 89). Sans auteur connu — compte disparu,
    brouillon rendu au pays — le pays le complète.
    """
    if not agit_en_auteur(objet, acteur.role, acteur.username):
        raise PermissionRefusee(
            message or _("Seul l'auteur d'un brouillon peut le modifier.")
        )


#: Ce que dit un refus de modifier une ligne ou un dossier déclaré — les
#: mêmes phrases que les sérialiseurs, pour que la relecture sous verrou
#: réponde exactement ce qu'aurait répondu la validation.
VERROUILLE = {
    Expense: gettext_lazy(
        "Cette dépense est déclarée : elle ne peut plus être "
        "modifiée. Seul un brouillon reste modifiable."
    ),
    Dossier: gettext_lazy("Ce dossier est déclaré : il ne peut plus être modifié."),
}


def exiger_un_brouillon(objet):
    """Un dossier ou une ligne déclarés ne se modifient plus.

    Le sérialiseur le vérifie sur l'instance qu'il a reçue, lue **sans
    verrou** ; entre cette lecture et l'écriture, une soumission a pu
    passer. Les vues relisent donc l'objet sous verrou et redemandent ici,
    juste avant d'écrire : l'état qui compte est celui du verrou, pas
    celui de la lecture (audit du 8 septembre 2026, §3.6).
    """
    if objet.status in LOCKED_STATUSES:
        raise RegleViolee("non_field_errors", str(VERROUILLE[type(objet)]))


def exiger_les_quatre_yeux(objet, action, acteur):
    """Celui qui a saisi ou ouvert ne contrôle pas ce qu'il a saisi.

    Sur une ligne, l'absence d'auteur est rédhibitoire : on ne tranche pas
    une ligne d'origine inconnue. Sur un dossier sans auteur (import, compte
    supprimé), la règle joue sur chaque ligne, qui refuse tout contrôle sans
    auteur.
    """
    if action not in FOUR_EYES_ACTIONS:
        return
    if isinstance(objet, Expense) and not objet.created_by:
        raise RegleViolee(
            "created_by",
            _("Cette dépense n'a pas d'auteur connu : elle ne peut pas être contrôlée."),
        )
    if breaks_four_eyes(action, objet.created_by, acteur.username):
        if isinstance(objet, Dossier):
            raise PermissionRefusee(
                _("Vous avez ouvert ce dossier : son contrôle revient à quelqu'un d'autre.")
            )
        raise PermissionRefusee(
            _("Vous avez saisi cette dépense : son contrôle revient à quelqu'un d'autre.")
        )


def exiger_une_ligne_jamais_rectifiee(ligne):
    """Une ligne qui a fait l'objet d'une rectification ne se retire plus.

    Revenue au brouillon par une réouverture, elle garde son histoire — un
    constat du siège, contesté, défait ou maintenu — et la demande la
    référence : l'effacer effacerait cette histoire, ou échouerait en base
    sur un message qui n'explique rien. Elle se corrige et se resoumet.
    """
    if a_ete_rectifiee(ligne):
        raise RegleViolee(
            "status",
            _(
                "Cette ligne a fait l'objet d'une demande de rectification : "
                "elle ne se supprime plus, elle se corrige et se resoumet."
            ),
        )


def sans_preuve(dossier):
    """Nombre de lignes du dossier qu'aucune pièce ne prouve (décision 107)."""
    return dossier.lignes_sans_preuve().count()


def exiger_un_dossier_ouvert(dossier):
    """Une ligne ne rejoint qu'un dossier encore en brouillon.

    Sans ce refus, la ligne arrivait en brouillon dans un dossier déjà
    passé : plus rien ne pouvait la soumettre, et la dépense restait
    indéfiniment en suspens dans un dossier clos.
    """
    if dossier is not None and not accepte_des_lignes(dossier):
        raise RegleViolee(
            "dossier",
            _(
                "Le dossier {number} est déjà déclaré ({status}) : il "
                "n'accepte plus de nouvelle ligne. Ouvrez un nouveau "
                "dossier pour cette dépense."
            ).format(
                number=dossier.number, status=dossier.get_status_display().lower()
            ),
        )


def _detail(lignes):
    return ", ".join(
        f"{e.title} ({e.get_status_display().lower()})" for e in lignes[:5]
    )


def relire_sous_verrou(queryset, pk):
    """L'objet ``pk`` du queryset (verrouillé), ou :class:`HorsPerimetre`.

    Lu avant le verrou, l'objet a pu disparaître pendant l'attente : retiré
    par son auteur (brouillon) ou mis à la corbeille par le super
    administrateur (décision 120). Il n'existe plus, ni pour cette écriture
    ni pour personne : 404. Seules ces relectures se traduisent ainsi —
    ailleurs, un objet introuvable reste un défaut, et répond 500.
    """
    try:
        return queryset.get(pk=pk)
    except queryset.model.DoesNotExist:
        raise HorsPerimetre() from None
