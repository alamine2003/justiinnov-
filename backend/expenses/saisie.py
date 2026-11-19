"""La saisie d'un brouillon (décisions 125 et 131, prolonge la décision 41).

Les verrous et les règles qu'une vue de saisie applique avant d'écrire, dans
l'ordre du circuit : le dossier d'abord, la ligne ensuite.
"""

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.regles import RegleViolee

from .circuit import _CIRCUITS, _verrouiller_le_dossier
from .exigences import (
    exiger_l_auteur_du_brouillon,
    exiger_un_brouillon,
    exiger_un_dossier_ouvert,
)


# --- Verrous pour les vues de saisie -------------------------------------------


def verrouiller(objet):
    """Relit un dossier ou une ligne sous verrou, avec ses relations.

    Pour les vues de modification : elles reçoivent une instance lue sans
    verrou par ``get_object`` ; c'est celle-ci qu'elles doivent remplacer
    avant de vérifier l'état et d'écrire. À appeler dans une transaction.
    """
    return _CIRCUITS[type(objet)][0](objet)


def verrouiller_le_dossier_vise(dossier, ligne):
    """Le dossier qu'une ligne rejoint (ou garde), relu sous verrou.

    ``dossier`` est celui de la charge utile, ``None`` si elle n'en donne
    pas : c'est alors celui de la ligne. Rend ``None`` sans dossier.
    """
    vise = dossier if dossier is not None else getattr(ligne, "dossier", None)
    if vise is None:
        return None
    return _verrouiller_le_dossier(vise)


# --- La saisie d'un brouillon (décision 125, prolonge la décision 41) -------
#
# Une vue de saisie ne porte que le HTTP : ces services prennent les verrous
# dans l'ordre du circuit — le dossier d'abord, la ligne ensuite, comme la
# soumission, l'ordre inverse pouvant s'interbloquer — et jugent les règles
# du brouillon. L'import et les commandes les trouvent au même endroit.

#: Rejoindre un dossier, c'est modifier ce brouillon-là : son auteur seul.
AJOUT_PAR_L_AUTEUR = gettext_lazy("Seul l'auteur d'un brouillon peut y ajouter une ligne.")


def preparer_l_ajout(dossier_vise, acteur):
    """Le dossier qui reçoit une ligne nouvelle, verrouillé le temps de
    l'insertion, s'il l'accepte encore.

    Sous verrou, une soumission ou un retrait du dossier au même instant
    attend, puis trouve la ligne — au lieu d'une ligne en brouillon dans un
    dossier déclaré que rien ne soumettrait plus (§3.7, §4.4). Le contrôle
    du dossier vient **après** celui du périmètre, que la vue a fait : dire
    « ce dossier est déjà soumis » à qui ne le voit pas révélerait son état.
    """
    dossier = verrouiller_le_dossier_vise(dossier_vise, None)
    exiger_un_dossier_ouvert(dossier)
    if dossier is not None:
        exiger_l_auteur_du_brouillon(dossier, acteur, str(AJOUT_PAR_L_AUTEUR))
    return dossier


def preparer_la_modification(ligne, dossier_vise, acteur):
    """La ligne relue sous verrou, si son auteur peut encore la modifier.

    L'instance validée a été lue sans verrou : une soumission a pu passer
    entre-temps, et écrire depuis l'objet périmé ramenait la ligne au
    brouillon, sans imputation ni trace. Déplacer un brouillon vers un
    dossier déjà déclaré l'y perdrait, exactement comme l'y créer ; une
    ligne qui porte des pièces ne change plus de dossier (décision 107).
    """
    dossier_vise = verrouiller_le_dossier_vise(dossier_vise, ligne)
    ligne = verrouiller(ligne)
    exiger_un_brouillon(ligne)
    exiger_l_auteur_du_brouillon(ligne, acteur)
    exiger_un_dossier_ouvert(dossier_vise)
    if dossier_vise is not None and dossier_vise.pk != ligne.dossier_id:
        exiger_l_auteur_du_brouillon(dossier_vise, acteur, str(AJOUT_PAR_L_AUTEUR))
        if ligne.proofs.exists():
            raise RegleViolee(
                "dossier",
                _("Cette ligne porte des justificatifs : elle ne change plus de dossier."),
            )
    return ligne


def preparer_la_modification_du_dossier(dossier, acteur):
    """Le dossier relu sous verrou, s'il est encore un brouillon de
    l'acteur : une soumission passée entre la lecture et l'écriture le
    ramènerait sinon au brouillon, sans réouverture ni trace."""
    dossier = verrouiller(dossier)
    exiger_un_brouillon(dossier)
    exiger_l_auteur_du_brouillon(dossier, acteur)
    return dossier
