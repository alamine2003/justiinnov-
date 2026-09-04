"""Trace des actions sur les comptes : création, modification, mots de passe.

Un compte est une entité sensible au même titre qu'un pays : qui a donné un
rôle à qui, quand, depuis où, doit se relire des mois plus tard. Les entrées
vont dans ``ChangeLog`` (entité ``user``), sans pays : elles ne relèvent
d'aucun périmètre.
"""

from core.models import ChangeLog
from core.signals import journaliser, serialisable

#: Champs du compte et du profil dont l'évolution est journalisée.
CHAMPS_SUIVIS = (
    "username", "first_name", "last_name", "email", "is_active",
    "is_staff", "is_superuser", "role", "must_change_password",
)


def etat_compte(user):
    """Photographie sérialisable d'un compte, profil compris.

    Le périmètre (``countries``) n'y figure pas : sa modification est
    journalisée à part par ``accounts.signals``, avant/après compris.
    """
    profile = getattr(user, "profile", None)
    etat = {
        champ: serialisable(getattr(user, champ))
        for champ in CHAMPS_SUIVIS
        if hasattr(user, champ)
    }
    etat["role"] = profile.role if profile is not None else None
    etat["must_change_password"] = (
        profile.must_change_password if profile is not None else None
    )
    return etat


def journaliser_compte(request, user, action, *, avant=None, apres=None,
                       changed_fields=None):
    """Écrit une entrée pour ``user``, signée par l'auteur de ``request``."""
    diff = {}
    if avant is not None and apres is not None:
        diff = {
            champ: [avant.get(champ), apres.get(champ)]
            for champ in CHAMPS_SUIVIS
            if avant.get(champ) != apres.get(champ)
        }
        changed_fields = changed_fields or list(diff)
    return journaliser(
        user,
        action,
        ChangeLog.Models.USER,
        label=user.username,
        to_value=user.username,
        from_value=user.username if avant is not None else "",
        changed_fields=changed_fields,
        diff=diff,
        request=request,
    )


def journaliser_modification(request, user, avant, apres):
    """Découpe une mise à jour en événements qualifiés.

    L'activation est journalisée à part, comme pour un pays, pour qu'une
    désactivation ne se cache pas dans une liste de champs ; le reste part
    en « mise à jour ». Le mot de passe n'apparaît jamais, ni avant ni
    après : seule sa réinitialisation est consignée, par l'appelant.
    """
    avant, apres = dict(avant), dict(apres)
    if avant.get("is_active") != apres.get("is_active"):
        action = (
            ChangeLog.Actions.REACTIVATED
            if apres["is_active"]
            else ChangeLog.Actions.DEACTIVATED
        )
        journaliser_compte(
            request, user, action,
            avant={"is_active": avant["is_active"]},
            apres={"is_active": apres["is_active"]},
        )
        avant.pop("is_active")
        apres.pop("is_active")
    if avant != apres:
        journaliser_compte(
            request, user, ChangeLog.Actions.UPDATED, avant=avant, apres=apres
        )
