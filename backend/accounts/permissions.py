"""Droits dérivés du rôle du profil.

Les vues déclarent les rôles autorisés (``write_roles``, ``read_roles``) ; la
matrice reste ainsi lisible en un seul endroit par ressource, plutôt que
dispersée dans des tests conditionnels.
"""

from dataclasses import dataclass

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


@dataclass(frozen=True)
class Access:
    """Vue immuable des droits d'un utilisateur pour la requête en cours."""

    role: str
    country_ids: list | None  # ``None`` = tous les pays

    @property
    def has_global_scope(self):
        return self.country_ids is None


def get_access(user):
    """Droits de l'utilisateur, ou ``None`` s'il n'en a aucun."""
    if user is None or not user.is_authenticated:
        return None
    # L'accesseur inverse d'un OneToOne lève une exception dérivant
    # d'AttributeError : ``getattr`` avec défaut est donc sûr.
    profile = getattr(user, "profile", None)
    if profile is None:
        # Superutilisateur Django sans profil : compte technique d'amorçage.
        if user.is_superuser:
            return Access(role=Role.SUPER_ADMIN, country_ids=None)
        return None
    return Access(role=profile.role, country_ids=profile.country_ids())


# --- Matrice des droits d'écriture -----------------------------------------

#: Pays, managers : structure de l'organisation, réservée au siège.
REFERENTIAL_WRITE_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Équipes, centres de coûts, projets, intitulés, catégories : le responsable
#: pays les gère pour son propre périmètre.
SUBENTITY_WRITE_ROLES = REFERENTIAL_WRITE_ROLES | {Role.COUNTRY_MANAGER}

#: Budgets et réallocations : attribution et arbitrage (§4).
BUDGET_WRITE_ROLES = frozenset({Role.SUPER_ADMIN, Role.DOO})

#: Comptes utilisateurs et rôles.
USER_WRITE_ROLES = REFERENTIAL_WRITE_ROLES

#: Saisie des dépenses, des dossiers et dépôt des justificatifs (§4).
EXPENSE_WRITE_ROLES = frozenset(
    {Role.SUPER_ADMIN, Role.ADMIN, Role.COUNTRY_MANAGER, Role.OWNER}
)

#: Contrôle documentaire, justification et constat de non-justification.
#:
#: **Le pays en est exclu, délibérément.** Un responsable pays qui pourrait
#: justifier ses propres dépenses viderait l'application de sa raison d'être :
#: c'est le siège qui constate qu'une pièce couvre un décaissement, jamais
#: celui qui l'a engagé.
VALIDATION_ROLES = frozenset(
    {Role.SUPER_ADMIN, Role.ADMIN, Role.DOO, Role.CONTROLLER}
)

#: Consultation du journal d'audit.
AUDIT_READ_ROLES = frozenset(
    {Role.SUPER_ADMIN, Role.ADMIN, Role.DOO, Role.CONTROLLER, Role.AUDITOR}
)


#: Matrice des capacités, source unique.
#:
#: Elle sert à la fois à décrire les droits (`/api/permissions/`) et à les
#: exposer au frontend (`/api/me/`). Décrire les rôles ailleurs qu'ici les
#: ferait diverger de ce qui est réellement appliqué.
CAPABILITIES = [
    {
        "key": "manage_users",
        "label": "Comptes et rôles",
        "description": "Créer, modifier, activer ou désactiver un compte.",
        "roles": USER_WRITE_ROLES,
    },
    {
        "key": "manage_countries",
        "label": "Pays et managers",
        "description": "Créer et modifier les pays, leurs devises et leurs managers.",
        "roles": REFERENTIAL_WRITE_ROLES,
    },
    {
        "key": "manage_subentities",
        "label": "Équipes, projets, intitulés",
        "description": "Gérer les sous-entités d'un pays.",
        "roles": SUBENTITY_WRITE_ROLES,
    },
    {
        "key": "manage_budgets",
        "label": "Enveloppes et réallocations",
        "description": "Attribuer les budgets et arbitrer les transferts.",
        "roles": BUDGET_WRITE_ROLES,
    },
    {
        "key": "record_expenses",
        "label": "Saisie et soumission",
        "description": "Saisir des dépenses, déposer des pièces, soumettre un dossier.",
        "roles": EXPENSE_WRITE_ROLES,
    },
    {
        "key": "validate_expenses",
        "label": "Justification",
        "description": (
            "Constater qu'une pièce couvre une dépense, ou l'absence de preuve. "
            "Le pays en est exclu : il déclare, le siège constate."
        ),
        "roles": VALIDATION_ROLES,
    },
    {
        "key": "view_audit",
        "label": "Journal d'audit",
        "description": "Consulter la trace des actions sensibles.",
        "roles": AUDIT_READ_ROLES,
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
    - ``view.action_write_roles`` surcharge par action. Indispensable : valider
      une dépense et la saisir relèvent de rôles différents, alors qu'il s'agit
      de la même vue.
    """

    message = "Votre rôle ne permet pas cette action."

    def has_permission(self, request, view):
        access = get_access(request.user)
        if access is None:
            return False
        if request.method in SAFE_METHODS:
            read_roles = getattr(view, "read_roles", None)
            return read_roles is None or access.role in read_roles

        per_action = getattr(view, "action_write_roles", {})
        action = getattr(view, "action", None)
        if action in per_action:
            return access.role in per_action[action]
        return access.role in getattr(view, "write_roles", frozenset())
