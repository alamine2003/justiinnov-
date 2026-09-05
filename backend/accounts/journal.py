"""Trace des actions sur les comptes : création, modification, mots de passe.

Un compte est une entité sensible au même titre qu'un pays : qui a donné un
rôle à qui, quand, depuis où, doit se relire des mois plus tard. Les entrées
vont dans ``ChangeLog`` (entité ``user``), sans pays : elles ne relèvent
d'aucun périmètre.
"""

from core.journal import serialisable, tracer
from core.models import ChangeLog

#: Champs du compte et du profil dont l'évolution est journalisée ici.
#:
#: ``username`` n'y est pas : le nom de compte est immuable (cf.
#: ``UserSerializer``), il sert de libellé à chaque entrée. ``role`` et
#: ``language`` non plus : ils sont journalisés par ``accounts.signals`` au
#: moment où le profil s'enregistre, quel que soit le chemin — API, admin
#: Django ou ``seed_users``.
ACTIONS_DE_SESSION = frozenset(
    {ChangeLog.Actions.LOGIN, ChangeLog.Actions.LOGIN_FAILED, ChangeLog.Actions.LOGOUT}
)

CHAMPS_SUIVIS = (
    "first_name", "last_name", "email", "is_active",
    "is_staff", "is_superuser", "must_change_password",
    "totp_confirmed",
)


def etat_compte(user):
    """Photographie sérialisable d'un compte, profil compris.

    Le périmètre (``countries``, ``teams``), le rôle et la langue n'y
    figurent pas : leur modification est journalisée à part par
    ``accounts.signals``, avant/après compris.
    """
    profile = getattr(user, "profile", None)
    etat = {
        champ: serialisable(getattr(user, champ))
        for champ in CHAMPS_SUIVIS
        if hasattr(user, champ)
    }
    etat["must_change_password"] = (
        profile.must_change_password if profile is not None else None
    )
    # L'état du second facteur, jamais le secret : il ne doit figurer nulle
    # part ailleurs que sur le profil et le téléphone du titulaire.
    etat["totp_confirmed"] = profile.totp_confirmed if profile is not None else None
    return etat


def journaliser_compte(request, user, action, *, avant=None, apres=None,
                       changed_fields=None, diff=None):
    """Écrit une entrée pour ``user``, signée par l'auteur de ``request``.

    Couche d'adaptation de :func:`core.journal.tracer` : ``diff`` se calcule
    d'``avant``/``apres`` quand ils sont fournis, restreint aux champs
    suivis ; sinon l'appelant peut le donner tel quel (un seul champ qui
    bascule).
    """
    if avant is not None and apres is not None:
        avant = {champ: avant.get(champ) for champ in CHAMPS_SUIVIS}
        apres = {champ: apres.get(champ) for champ in CHAMPS_SUIVIS}
    return tracer(
        request,
        action,
        user,
        famille="session" if action in ACTIONS_DE_SESSION else "compte",
        avant=avant,
        apres=apres,
        label=user.username,
        to_value=user.username,
        from_value=user.username if avant is not None else "",
        changed_fields=changed_fields,
        diff=diff or None,
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
