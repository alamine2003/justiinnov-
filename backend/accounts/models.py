"""Profils utilisateurs : rôle, périmètre pays, équipes, double authentification.

Trois rôles (décision 89). Le rôle décide de *ce que* l'on
peut faire, le périmètre décide *sur quels pays* — et, pour un manager, *sur
quelles équipes*. Les deux sont portés par le profil, jamais déduits du nom
d'utilisateur.

Le profil porte aussi l'enrôlement TOTP : le secret, la date à laquelle
son titulaire a prouvé qu'il le détenait (``totp_confirmed_at``) et le
dernier compteur accepté (``totp_last_counter``), qui interdit de rejouer
un code. Tant que cette date est vide, le compte n'est pas considéré comme
protégé ; quand la politique l'exige (``settings.TOTP_REQUIRED``), la
plateforme lui est fermée (cf. ``accounts.middleware``). Un compte enrôlé,
obligation ou non, fournit toujours son code à la connexion.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import Country, Manager, Team, TimeStampedModel


class Role(models.TextChoices):
    """Les trois rôles de la plateforme (décision 89).

    Côté pays, le **manager** : il ouvre les dossiers de son pays, y saisit
    les dépenses, dépose les justificatifs et soumet — lui seul, et
    seulement pour le pays auquel il est rattaché. Au siège,
    l'**administrateur** (RH) contrôle chaque dossier de bout en bout — mise
    en contrôle, justification ou refus, clôture, contrôle des pièces,
    réouverture, rectification — et tient les comptes, le référentiel et
    les enveloppes. Le **super administrateur** (DG, DO, CEO, développeurs)
    supervise : il voit tout, relit le journal d'audit et administre la
    plateforme, sans déclarer ni contrôler. Ni l'un ni l'autre ne crée de
    dossier ni ne dépose de pièce. Il n'y a plus de DM ni de DF : le
    contrôle qu'ils se partageaient revient à l'administrateur seul.
    """

    SUPER_ADMIN = "super_admin", _("Super administrateur (DG, DO, CEO, DEV)")
    ADMIN = "admin", _("Administrateur (RH)")
    MANAGER = "manager", _("Manager (pays)")


#: Rôles exercés depuis le siège : ils portent toujours sur l'ensemble des
#: pays et ne se restreignent pas.
HEADQUARTERS_ROLES = frozenset({Role.SUPER_ADMIN, Role.ADMIN})

#: Rôles dont le périmètre ne peut jamais être restreint : le siège entier
#: depuis que le DM et le DF, seuls restrictibles, ont disparu.
ALWAYS_GLOBAL_ROLES = HEADQUARTERS_ROLES

#: Langue par défaut d'un profil : celle de référence des messages.
DEFAULT_LANGUAGE = "fr"


def aligner_drapeaux(user, role):
    """Aligne l'accès à l'admin Django sur le rôle du profil.

    Le back-office Django est réservé au siège. Sans cet alignement, un super
    administrateur rétrogradé garderait ``is_superuser`` — et donc tous les
    droits sur l'admin — alors que l'API ne lui reconnaît plus rien. Rend
    vrai si un drapeau a changé, pour que l'appelant sache s'il doit
    enregistrer le compte.
    """
    is_staff = role in (Role.SUPER_ADMIN, Role.ADMIN)
    is_superuser = role == Role.SUPER_ADMIN
    change = (user.is_staff, user.is_superuser) != (is_staff, is_superuser)
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    return change


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
        help_text=_("Le pays du manager. Le siège voit tous les pays."),
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
    # Compteur de temps (RFC 6238) du dernier code accepté : un code ne vaut
    # qu'une fois. Sans cette mémoire, un code lu par-dessus l'épaule restait
    # valable une minute et demie, et pouvait ouvrir une seconde session.
    totp_last_counter = models.BigIntegerField(
        _("Dernier compteur TOTP accepté"),
        null=True,
        blank=True,
        help_text=_("Un code déjà présenté, ou plus ancien, est refusé."),
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

        Le siège, toujours. Le manager jamais : sans aucun pays, il ne voit
        **rien** — l'absence de périmètre ne doit jamais valoir
        autorisation générale.
        """
        return self.role in ALWAYS_GLOBAL_ROLES

    def country_ids(self):
        """Identifiants des pays visibles, ou ``None`` si tous le sont."""
        if self.has_global_scope:
            return None
        return list(self.countries.values_list("id", flat=True))

    def team_ids(self):
        """Identifiants des équipes auxquelles la vue est restreinte, ou ``None``.

        Seul le manager est cloisonné par équipe : le siège couvre le pays
        entier. Un manager **sans équipe rattachée voit tout
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
