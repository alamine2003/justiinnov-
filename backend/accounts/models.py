"""Profils utilisateurs : rôle et périmètre pays.

Le cahier des charges (§4) définit six acteurs. Le rôle décide de *ce que* l'on
peut faire, le périmètre décide *sur quels pays*. Les deux sont portés par le
profil, jamais déduits du nom d'utilisateur.
"""

from django.contrib.auth.models import User
from django.db import models

from core.models import Country, Manager, Team, TimeStampedModel


class Role(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super administrateur"
    ADMIN = "admin", "Administrateur plateforme"
    DOO = "doo", "Direction des opérations"
    COUNTRY_MANAGER = "country_manager", "Responsable pays"
    OWNER = "owner", "Manager / Owner"
    CONTROLLER = "controller", "Contrôleur / Finance"
    AUDITOR = "auditor", "Auditeur"


#: Rôles exercés depuis le siège : ils portent sur l'ensemble des pays.
HEADQUARTERS_ROLES = frozenset(
    {Role.SUPER_ADMIN, Role.ADMIN, Role.DOO, Role.CONTROLLER, Role.AUDITOR}
)

#: Rôles dont le périmètre ne peut jamais être restreint.
ALWAYS_GLOBAL_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})


class UserProfile(TimeStampedModel):
    """Rôle et périmètre d'un compte."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", verbose_name="Compte"
    )
    role = models.CharField("Rôle", max_length=32, choices=Role.choices)
    countries = models.ManyToManyField(
        Country,
        blank=True,
        related_name="profiles",
        verbose_name="Pays du périmètre",
        help_text="Vide pour un rôle du siège : accès à tous les pays.",
    )
    teams = models.ManyToManyField(
        Team, blank=True, related_name="profiles", verbose_name="Équipes"
    )
    manager = models.ForeignKey(
        Manager,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
        verbose_name="Manager associé",
        help_text="Référentiel métier ; un manager peut exister sans compte.",
    )
    must_change_password = models.BooleanField(
        "Changement de mot de passe requis",
        default=True,
        help_text="Force le changement à la prochaine connexion.",
    )

    class Meta:
        ordering = ["user__username"]
        verbose_name = "Profil"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def has_global_scope(self):
        """Le profil voit-il tous les pays ?

        Un rôle du siège sans pays explicite couvre l'ensemble des pays ; s'il
        reçoit des pays, il y est restreint. À l'inverse, un rôle pays sans
        aucun pays ne voit **rien** : l'absence de périmètre ne doit jamais
        valoir autorisation générale.
        """
        if self.role in ALWAYS_GLOBAL_ROLES:
            return True
        return self.role in HEADQUARTERS_ROLES and not self.countries.exists()

    def country_ids(self):
        """Identifiants des pays visibles, ou ``None`` si tous le sont."""
        if self.has_global_scope:
            return None
        return list(self.countries.values_list("id", flat=True))

    def can_access_country(self, country_id):
        allowed = self.country_ids()
        return allowed is None or country_id in allowed
