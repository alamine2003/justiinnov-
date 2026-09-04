"""Droits dérivés du rôle du profil.

Les vues déclarent les rôles autorisés (``write_roles``, ``read_roles``) ; la
matrice reste ainsi lisible en un seul endroit par ressource, plutôt que
dispersée dans des tests conditionnels.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


@dataclass(frozen=True)
class Access:
    """Vue immuable des droits d'un utilisateur pour la requête en cours."""

    role: str
    country_ids: list | None  # ``None`` = tous les pays
    #: Équipes auxquelles un manager est restreint ; ``None`` = pas de
    #: restriction par équipe (autre rôle, ou manager sans équipe).
    team_ids: list | None = None

    @property
    def has_global_scope(self):
        return self.country_ids is None


#: Attribut posé sur l'instance utilisateur pour mémoriser ses droits.
_ATTRIBUT_MEMO = "_acces_memorise"
_ABSENT = object()


def get_access(user):
    """Droits de l'utilisateur, ou ``None`` s'il n'en a aucun.

    Un compte sans profil — le superutilisateur d'amorçage, un compte hérité —
    n'a **aucun** accès à l'API, fût-il superutilisateur Django : le rôle et
    le périmètre viennent du profil, jamais des drapeaux du compte.

    Le résultat est mémorisé sur l'instance utilisateur, donc pour la durée de
    la requête : permission, filtrage du queryset et revalidation de l'écriture
    y font chacun appel, et chaque appel coûtait deux requêtes SQL.
    """
    if user is None or not user.is_authenticated:
        return None
    memo = getattr(user, _ATTRIBUT_MEMO, _ABSENT)
    if memo is not _ABSENT:
        return memo
    # L'accesseur inverse d'un OneToOne lève une exception dérivant
    # d'AttributeError : ``getattr`` avec défaut est donc sûr.
    profile = getattr(user, "profile", None)
    access = (
        None
        if profile is None
        else Access(
            role=profile.role,
            country_ids=profile.country_ids(),
            team_ids=profile.team_ids(),
        )
    )
    setattr(user, _ATTRIBUT_MEMO, access)
    return access


# --- Matrice des droits d'écriture -----------------------------------------

#: Pays, managers : structure de l'organisation, réservée au siège.
REFERENTIAL_WRITE_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Équipes, centres de coûts, projets, intitulés, catégories, bénéficiaires :
#: la RH gère le référentiel de tous les pays. Le manager ne le modifie pas —
#: il déclare dans un cadre que le siège a posé, il ne le redessine pas.
SUBENTITY_WRITE_ROLES = REFERENTIAL_WRITE_ROLES

#: Budgets, réallocations et taux de change : attribution et arbitrage (§4),
#: par la direction seule — DG, DO, CEO, super administrateurs. Le DF n'y
#: est pas : il constate ce qui a été dépensé, il ne fixe pas ce qui peut
#: l'être. Décision du produit : DM et DF n'ont aucun droit d'administration.
BUDGET_WRITE_ROLES = frozenset({Role.SUPER_ADMIN})

#: Exports (Excel, CSV, Word, PDF) et import : réservés aux administrateurs.
#: Le reste de l'organisation travaille dans l'application, sans fichier.
EXPORT_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Réouverture d'un dossier déclaré : seule exception à l'irréversibilité,
#: réservée aux administrateurs, motivée et tracée. Elle sert à demander des
#: comptes, pas à corriger en silence.
REOPEN_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Comptes utilisateurs et rôles.
USER_WRITE_ROLES = REFERENTIAL_WRITE_ROLES

#: Saisie des dépenses, des dossiers et dépôt des justificatifs (§4) : le
#: manager, seul rôle du pays. Le DM est au siège et ne déclare plus : celui
#: qui met en contrôle ne peut pas être celui qui a soumis.
EXPENSE_WRITE_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.MANAGER})

#: Mise en contrôle d'un dossier ou d'une ligne : premier temps du contrôle,
#: par le DM. Le DF, son supérieur, et les administrateurs peuvent aussi
#: le faire, pour ne pas bloquer un dossier quand le DM est absent.
REVIEW_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.DF, Role.DM})

#: Justification, constat de non-justification, clôture : le DF tranche,
#: pas le DM — qui prépare le contrôle mais ne le conclut pas.
#:
#: **Le pays en est exclu, délibérément.** Un manager qui pourrait justifier
#: ses propres dépenses viderait l'application de sa raison d'être : c'est
#: le siège qui constate qu'une pièce couvre un décaissement, jamais celui
#: qui l'a engagé.
VALIDATION_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.DF})

#: Consultation du journal d'audit : la RH, qui audite, et la direction.
#: Le DM et le DF en sont exclus : le journal relit *leurs* décisions autant
#: que celles des pays, et cette relecture est un acte d'administration.
AUDIT_READ_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Consultation de l'historique du référentiel (``/api/history/``) : le
#: siège entier, chacun sur son périmètre — c'est une lecture du référentiel
#: (qui a rattaché quoi, quel taux s'applique), pas un audit. Un manager
#: saisit des dépenses ; l'organisation du pays ne le regarde pas.
HISTORY_READ_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.DF, Role.DM})


#: Matrice des capacités, source unique.
#:
#: Elle sert à la fois à décrire les droits (`/api/permissions/`) et à les
#: exposer au frontend (`/api/me/`). Décrire les rôles ailleurs qu'ici les
#: ferait diverger de ce qui est réellement appliqué.
CAPABILITIES = [
    {
        "key": "manage_users",
        "label": _("Comptes et rôles"),
        "description": _("Créer, modifier, activer ou désactiver un compte."),
        "roles": USER_WRITE_ROLES,
    },
    {
        "key": "manage_countries",
        "label": _("Pays et managers"),
        "description": _("Créer et modifier les pays, leurs devises et leurs managers."),
        "roles": REFERENTIAL_WRITE_ROLES,
    },
    {
        "key": "manage_subentities",
        "label": _("Équipes, projets, intitulés"),
        "description": _(
            "Gérer le référentiel des pays : équipes, projets, intitulés, "
            "catégories, bénéficiaires. Le manager y déclare, la RH le tient."
        ),
        "roles": SUBENTITY_WRITE_ROLES,
    },
    {
        "key": "manage_budgets",
        "label": _("Enveloppes et réallocations"),
        "description": _(
            "Attribuer les budgets, arbitrer les transferts, tenir les taux "
            "de change : super administrateurs."
        ),
        "roles": BUDGET_WRITE_ROLES,
    },
    {
        "key": "record_expenses",
        "label": _("Saisie et soumission"),
        "description": _(
            "Saisir des dépenses, déposer des pièces, soumettre un dossier : "
            "le manager, pour son pays."
        ),
        "roles": EXPENSE_WRITE_ROLES,
    },
    {
        "key": "review_expenses",
        "label": _("Mise en contrôle"),
        "description": _(
            "Prendre un dossier soumis en contrôle : le DM prépare, le DF "
            "tranche. Le pays en est exclu."
        ),
        "roles": REVIEW_ROLES,
    },
    {
        "key": "validate_expenses",
        "label": _("Justification"),
        "description": _(
            "Constater qu'une pièce couvre une dépense, ou l'absence de preuve. "
            "Le DF tranche ; le pays en est exclu : il déclare, le siège constate."
        ),
        "roles": VALIDATION_ROLES,
    },
    {
        "key": "view_audit",
        "label": _("Journal d'audit"),
        "description": _(
            "Consulter la trace des actions sensibles : RH et direction."
        ),
        "roles": AUDIT_READ_ROLES,
    },
    {
        "key": "export_data",
        "label": _("Imports et exports"),
        "description": _(
            "Importer un classeur, exporter en Excel, CSV, Word ou PDF. "
            "Le reste de l'organisation travaille dans l'application."
        ),
        "roles": EXPORT_ROLES,
    },
    {
        "key": "reopen_dossiers",
        "label": _("Réouverture d'un dossier"),
        "description": _(
            "Rouvrir un dossier déclaré pour demander des comptes. "
            "Seule exception à l'irréversibilité, motivée et tracée."
        ),
        "roles": REOPEN_ROLES,
    },
]


def capabilities_for(role):
    """Droits d'un rôle, sous la forme attendue par le frontend."""
    return {
        capability["key"]: role in capability["roles"]
        for capability in CAPABILITIES
    }


class RolePermission(BasePermission):
    """Autorise la requête selon le rôle porté par le profil.

    - lecture : ``view.read_roles`` (tous les rôles si non déclaré) ;
    - écriture : ``view.write_roles``, qui doit être déclaré explicitement —
      une vue qui l'oublie est en lecture seule plutôt qu'ouverte à tous ;
    - ``view.action_write_roles`` et ``view.action_read_roles`` surchargent par
      action. Indispensable : valider une dépense et la saisir relèvent de
      rôles différents, alors qu'il s'agit de la même vue ; et une action de
      lecture peut n'intéresser que ceux qui peuvent agir dessus.
    """

    message = _("Votre rôle ne permet pas cette action.")

    def has_permission(self, request, view):
        access = get_access(request.user)
        if access is None:
            return False
        action = getattr(view, "action", None)

        if request.method in SAFE_METHODS:
            per_action = getattr(view, "action_read_roles", {})
            if action in per_action:
                return access.role in per_action[action]
            read_roles = getattr(view, "read_roles", None)
            return read_roles is None or access.role in read_roles

        per_action = getattr(view, "action_write_roles", {})
        if action in per_action:
            return access.role in per_action[action]
        return access.role in getattr(view, "write_roles", frozenset())
