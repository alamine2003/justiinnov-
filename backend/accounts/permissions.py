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


class RolePermission(BasePermission):
    """Autorise la requête selon le rôle porté par le profil.

    - lecture : ``view.read_roles`` (tous les rôles si non déclaré) ;
    - écriture : ``view.write_roles``, qui doit être déclaré explicitement —
      une vue qui l'oublie est en lecture seule plutôt qu'ouverte à tous.
    """

    message = "Votre rôle ne permet pas cette action."

    def has_permission(self, request, view):
        access = get_access(request.user)
        if access is None:
            return False
        if request.method in SAFE_METHODS:
            read_roles = getattr(view, "read_roles", None)
            return read_roles is None or access.role in read_roles
        return access.role in getattr(view, "write_roles", frozenset())
