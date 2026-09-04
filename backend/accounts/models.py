"""Profils utilisateurs : rôle, périmètre pays, équipes, double authentification.

Le cahier des charges (§4) définit six acteurs. Le rôle décide de *ce que* l'on
peut faire, le périmètre décide *sur quels pays* — et, pour un manager, *sur
quelles équipes*. Les deux sont portés par le profil, jamais déduits du nom
d'utilisateur.

Le profil porte aussi l'enrôlement TOTP : le secret, et la date à laquelle
son titulaire a prouvé qu'il le détenait (``totp_confirmed_at``). Tant que
cette date est vide, le compte n'est pas considéré comme protégé ; quand la
politique l'exige (``settings.TOTP_REQUIRED``), la plateforme lui est fermée
(cf. ``accounts.middleware``). Un compte enrôlé, obligation ou non, fournit
toujours son code à la connexion.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import Country, Manager, Team, TimeStampedModel


class Role(models.TextChoices):
    """Les cinq rôles de la plateforme.

    Côté pays, un seul rôle : le manager engage la dépense, la saisit et
    soumet le dossier de son pays (de ses équipes, s'il en a). Le contrôle
    est au siège, en deux temps : le DM (directeur manager) met le dossier
    en contrôle, le DF (directeur financier, supérieur du DM) justifie ou
    rejette. La RH administre les comptes, le référentiel de tous les pays,
    et audite ; la direction (DG, DO, CEO) et l'équipe de développement sont
    super administrateurs. RH et super administrateurs peuvent tout ce que
    font le DM et le DF ; l'inverse est faux : **le DM et le DF n'ont aucun
    droit d'administration** — ni comptes, ni référentiel, ni enveloppes,
    ni journal d'audit. Il n'y a ni « direction des opérations » ni
    « auditeur » distincts : la DO est super administratrice, l'audit
    revient à la RH.
    """

    SUPER_ADMIN = "super_admin", _("Super administrateur (DG, DO, CEO, DEV)")
    ADMIN = "admin", _("Administrateur (RH)")
    DF = "df", _("DF — directeur financier (siège)")
    DM = "dm", _("DM — directeur manager (siège)")
    MANAGER = "manager", _("Manager (pays)")


#: Rôles exercés depuis le siège : ils portent sur l'ensemble des pays.
#: Le DM et le DF contrôlent pour le siège ; chacun peut être restreint à
#: certains pays. Les administrateurs, eux, ne se restreignent jamais.
HEADQUARTERS_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN, Role.DF, Role.DM})

#: Rôles dont le périmètre ne peut jamais être restreint.
ALWAYS_GLOBAL_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Langue par défaut d'un profil : celle de référence des messages.
DEFAULT_LANGUAGE = "fr"


class UserProfile(TimeStampedModel):
    """Rôle, périmètre, équipes, langue et double authentification d'un compte."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", verbose_name=_("Compte")
    )
    role = models.CharField(_("Rôle"), max_length=32, choices=Role.choices)
    countries = models.ManyToManyField(
        Country,
        blank=True,
        related_name="profiles",
        verbose_name=_("Pays du périmètre"),
        help_text=_("Vide pour un rôle du siège : accès à tous les pays."),
    )
    teams = models.ManyToManyField(
        Team,
        blank=True,
        related_name="profiles",
        verbose_name=_("Équipes"),
        help_text=_(
            "Pour un manager : restreint sa vue à ces équipes. "
            "Vide, il voit tout son pays."
        ),
    )
    manager = models.ForeignKey(
        Manager,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
        verbose_name=_("Manager associé"),
        help_text=_("Référentiel métier ; un manager peut exister sans compte."),
    )
    must_change_password = models.BooleanField(
        _("Changement de mot de passe requis"),
        default=True,
        help_text=_("Force le changement à la prochaine connexion."),
    )
    # Le secret TOTP n'est jamais exposé par l'API après l'enrôlement : il ne
    # sort qu'une fois, dans le QR d'enrôlement, vers le titulaire.
    totp_secret = models.CharField(
        _("Secret TOTP"),
        max_length=64,
        blank=True,
        help_text=_("Vide tant que le compte n'est pas enrôlé."),
    )
    totp_confirmed_at = models.DateTimeField(
        _("Double authentification confirmée le"),
        null=True,
        blank=True,
        help_text=_(
            "Date à laquelle le titulaire a saisi un premier code valide. "
            "Vide : le compte n'est pas enrôlé, et la plateforme lui est "
            "fermée si la politique l'exige."
        ),
    )
    language = models.CharField(
        _("Langue"),
        max_length=8,
        choices=settings.LANGUAGES,
        default=DEFAULT_LANGUAGE,
        help_text=_(
            "Préférence d'affichage de l'interface. La langue d'une réponse "
            "de l'API suit l'en-tête Accept-Language de la requête."
        ),
    )

    class Meta:
        ordering = ["user__username"]
        verbose_name = _("Profil")
        verbose_name_plural = _("Profils")

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

    def team_ids(self):
        """Identifiants des équipes auxquelles la vue est restreinte, ou ``None``.

        Seul le manager est cloisonné par équipe : le siège (DM, DF)
        couvre le pays entier. Un manager **sans équipe rattachée voit tout
        son pays** : c'est le choix retenu, parce que l'équipe est une
        subdivision facultative du référentiel — un pays qui n'en a pas
        déclaré n'a pas à en inventer une pour que ses managers travaillent.
        La restriction s'active dès que l'administrateur rattache une équipe.
        """
        if self.role != Role.MANAGER:
            return None
        ids = list(self.teams.values_list("id", flat=True))
        return ids or None

    @property
    def totp_confirmed(self):
        """La double authentification est-elle active sur ce compte ?"""
        return self.totp_confirmed_at is not None
