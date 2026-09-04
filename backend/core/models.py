"""Modèles de la section 5.1 : gestion des pays et organisations."""

from decimal import Decimal

from django.core.cache import cache
from django.db import models
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext_lazy as _

from .africa import validate_african_country
from .validators import validate_timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Créé le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Modifié le"))

    class Meta:
        abstract = True


class Manager(TimeStampedModel):
    """Un responsable commercial / de pays."""

    name = models.CharField(_("Nom"), max_length=180)
    email = models.EmailField(_("Email"), blank=True)
    title = models.CharField(_("Fonction"), max_length=180, blank=True)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Country(TimeStampedModel):
    """Pays : devise, fuseau horaire, managers, équipes et centres de coûts."""

    name = models.CharField(_("Nom"), max_length=120, unique=True)
    code = models.CharField(
        "Code ISO",
        max_length=2,
        unique=True,
        help_text=_("ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains."),
        validators=[validate_african_country],
    )
    country_ref = models.CharField(
        "Identifiant pays",
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        help_text=_("Identifiant fonctionnel utilisé par le siège, ex. CT-01."),
    )
    currency = models.CharField(_("Devise"), max_length=3, help_text=_("ISO 4217"))
    currency_symbol = models.CharField(_("Symbole devise"), max_length=4, blank=True)
    timezone = models.CharField(
        "Fuseau horaire",
        max_length=64,
        default="UTC",
        help_text=_("Identifiant IANA, ex. Africa/Abidjan."),
        validators=[validate_timezone],
    )
    is_active = models.BooleanField(_("Actif"), default=True)
    managers = models.ManyToManyField(
        Manager, blank=True, related_name="countries", verbose_name=_("Manager(s)")
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("Pays")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # « ci » et « CI » désignent le même pays. Le sérialiseur normalise
        # déjà, mais l'admin Django, le shell et ``seed_users`` passent par
        # ici sans lui : la contrainte d'unicité laisserait sinon passer un
        # doublon de casse, et le validateur du périmètre africain refuserait
        # un code correct écrit en minuscules.
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class Team(TimeStampedModel):
    """Équipe rattachée à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="teams", verbose_name=_("Pays")
    )
    name = models.CharField(_("Nom"), max_length=180)
    description = models.TextField(_("Description"), blank=True)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Équipe")
        # Deux « Équipe Lomé » dans le même pays ne se distinguent ni à
        # l'écran ni dans un classeur importé : la ligne irait à l'une ou à
        # l'autre au hasard. Le même nom reste possible dans deux pays.
        constraints = [
            models.UniqueConstraint(
                fields=["country", "name"], name="unique_equipe_par_pays"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.country.name})"


class CostCenter(TimeStampedModel):
    """Centre de coûts rattaché à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="cost_centers", verbose_name=_("Pays")
    )
    code = models.CharField(_("Code"), max_length=20)
    name = models.CharField(_("Libellé"), max_length=180)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = _("Centre de coûts")
        unique_together = ("country", "code")

    def __str__(self):
        return f"{self.code} — {self.name}"


class Project(TimeStampedModel):
    STATUS_CHOICES = [
        ("planned", _("Planifié")),
        ("active", _("En cours")),
        ("on_hold", _("En pause")),
        ("completed", _("Terminé")),
    ]

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="projects", verbose_name=_("Pays")
    )
    name = models.CharField(_("Nom"), max_length=180)
    description = models.TextField(_("Description"), blank=True)
    status = models.CharField(_("Statut"), max_length=20, choices=STATUS_CHOICES, default="planned")
    budget = models.DecimalField(
        "Budget", max_digits=14, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Projet")
        # Même raison que pour l'équipe : une sous-enveloppe se rattache à
        # un projet par son nom, il doit désigner un seul projet du pays.
        constraints = [
            models.UniqueConstraint(
                fields=["country", "name"], name="unique_projet_par_pays"
            )
        ]

    def __str__(self):
        return self.name


class ExpenseTitle(TimeStampedModel):
    """Intitulé de dépenses rattaché à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="expense_titles", verbose_name=_("Pays")
    )
    label = models.CharField(_("Intitulé"), max_length=180)
    description = models.TextField(_("Description"), blank=True)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["label"]
        verbose_name = _("Intitulé de dépenses")
        unique_together = ("country", "label")

    def __str__(self):
        return self.label


class MarketingCategory(TimeStampedModel):
    """Catégorie marketing rattachée à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="marketing_categories",
        verbose_name=_("Pays"),
    )
    name = models.CharField(_("Nom"), max_length=180)
    description = models.TextField(_("Description"), blank=True)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Catégorie marketing")
        unique_together = ("country", "name")

    def __str__(self):
        return self.name


class ChangeLog(models.Model):
    """Journal des changements : référentiel, configuration et comptes.

    Chaque entrée dit qui, quoi, quand, depuis quelle adresse, et ce qui a
    changé (``diff``). Les connexions y sont aussi consignées : un échec de
    connexion n'a pas d'objet, d'où un ``object_id`` facultatif.
    """

    class Actions(models.TextChoices):
        CREATED = "created", _("Création")
        UPDATED = "updated", _("Mise à jour")
        REASSIGNED = "reassigned", _("Changement de rattachement")
        DEACTIVATED = "deactivated", _("Désactivation")
        REACTIVATED = "reactivated", _("Réactivation")
        DELETED = "deleted", _("Suppression")
        PASSWORD_RESET = "password_reset", _("Réinitialisation du mot de passe")
        PASSWORD_CHANGED = "password_changed", _("Changement de mot de passe")
        LOGIN = "login", _("Connexion")
        LOGIN_FAILED = "login_failed", _("Échec de connexion")
        LOGOUT = "logout", _("Déconnexion")
        # Second facteur : son activation et sa levée sont des actions
        # sensibles, à relire comme une réinitialisation de mot de passe.
        TOTP_CONFIRMED = "totp_confirmed", _("Double authentification activée")
        TOTP_RESET = "totp_reset", _("Double authentification réinitialisée")

    class Models(models.TextChoices):
        COUNTRY = "country", _("Pays")
        MANAGER = "manager", _("Manager")
        TEAM = "team", _("Équipe")
        COST_CENTER = "cost_center", _("Centre de coûts")
        PROJECT = "project", _("Projet")
        EXPENSE_TITLE = "expense_title", _("Intitulé de dépenses")
        MARKETING_CATEGORY = "marketing_category", _("Catégorie marketing")
        BUDGET = "budget", _("Enveloppe budgétaire")
        REALLOCATION = "reallocation", _("Réallocation budgétaire")
        EXCHANGE_RATE = "exchange_rate", _("Taux de change")
        WORKFLOW_CONFIGURATION = "workflow_configuration", _("Configuration du workflow")
        USER = "user", _("Compte utilisateur")

    model_name = models.CharField(
        "Entité", max_length=32, choices=Models.choices
    )
    object_id = models.PositiveBigIntegerField(
        "Identifiant d'entité", null=True, blank=True
    )
    label = models.CharField(_("Libellé"), max_length=250)
    action = models.CharField(_("Action"), max_length=20, choices=Actions.choices)
    # PROTECT, et non SET_NULL : l'historique est immuable en base (un
    # déclencheur refuse toute mise à jour), et un pays qui a laissé des
    # traces ne se supprime pas — il se désactive.
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.PROTECT,
        related_name="history", verbose_name=_("Pays"),
    )
    from_value = models.TextField(_("Valeur précédente"), blank=True)
    to_value = models.TextField(_("Nouvelle valeur"), blank=True)
    changed_fields = models.JSONField(_("Champs modifiés"), default=list, blank=True)
    #: ``{champ: [ancienne valeur, nouvelle valeur]}``, valeurs sérialisables
    #: en JSON : ``from_value``/``to_value`` ne portent qu'un libellé.
    diff = models.JSONField(_("Différences"), default=dict, blank=True)
    performed_by = models.CharField(_("Par"), max_length=180, blank=True)
    ip_address = models.GenericIPAddressField(_("Adresse IP"), null=True, blank=True)
    created_at = models.DateTimeField(_("Le"), auto_now_add=True)

    class Meta:
        # ``-pk`` départage deux entrées écrites dans la même transaction (un
        # rattachement puis une mise à jour) : sans lui, leur ordre relatif
        # dépendrait du plan d'exécution.
        ordering = ["-created_at", "-pk"]
        verbose_name = _("Historique")
        verbose_name_plural = _("Historiques")
        indexes = [
            models.Index(fields=["created_at"], name="core_changelog_cree_idx"),
            models.Index(
                fields=["country", "created_at"], name="core_changelog_pays_cree_idx"
            ),
            models.Index(
                fields=["model_name", "object_id"], name="core_changelog_entite_idx"
            ),
        ]

    def __str__(self):
        return f"[{self.get_action_display()}] {self.label}"


def _seuils_par_defaut():
    return [80, 90, 100]


class WorkflowConfiguration(models.Model):
    """Politique du circuit, unique pour toute l'instance.

    Les défauts sont ceux du modèle, pas ceux de ``settings`` : une valeur
    d'environnement ne doit pas se glisser dans une migration, ni changer
    silencieusement ce que produit ``objects.create()``. L'environnement
    n'intervient qu'une fois, dans le ``RunPython`` d'amorçage.
    """

    CACHE_KEY = "justi_innov:workflow_configuration"
    OVERRUN_POLICY_CHOICES = (
        ("block", _("Bloquer")),
        ("warn", _("Alerter")),
        ("approval", _("Soumettre à approbation")),
    )

    require_review_step = models.BooleanField(
        "Étape de contrôle obligatoire", default=False
    )
    unjustified_alert_days = models.PositiveIntegerField(
        "Délai d'alerte sans justification", default=0
    )
    alert_thresholds = models.JSONField(_("Seuils d'alerte"), default=_seuils_par_defaut)
    unusual_expense_factor = models.DecimalField(
        "Facteur de dépense inhabituelle",
        max_digits=8,
        decimal_places=2,
        default=Decimal("5"),
    )
    default_overrun_policy = models.CharField(
        "Politique de dépassement par défaut",
        max_length=20,
        choices=OVERRUN_POLICY_CHOICES,
        default="block",
    )
    warn_without_proof_submission = models.BooleanField(
        "Avertir à la soumission sans pièce", default=True
    )
    updated_at = models.DateTimeField(_("Modifié le"), auto_now=True)

    class Meta:
        verbose_name = _("Configuration du workflow")
        constraints = [
            # La base elle-même refuse une seconde ligne, quel que soit le
            # chemin d'écriture (ORM brut, SQL, migration de données).
            models.CheckConstraint(
                condition=models.Q(id=1), name="core_workflowconfiguration_unique"
            ),
        ]

    def save(self, *args, **kwargs):
        self.pk = 1
        # ``objects.create()`` demande une insertion forcée ; sur la ligne 1
        # déjà présente, elle échouerait. On laisse Django tenter la mise à
        # jour avant d'insérer : créer « une seconde » configuration revient
        # à modifier l'unique.
        kwargs.pop("force_insert", None)
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    def delete(self, *args, **kwargs):
        raise ProtectedError(
            _("La configuration du workflow est un singleton et ne peut pas être supprimée."),
            self,
        )

    @classmethod
    def charger(cls):
        """Configuration courante, via le cache partagé.

        Le cache est celui de la base (``DatabaseCache``) : l'objet en est
        dépicklé, donc jamais identique (``is``) à celui qui y a été posé.
        """
        configuration = cache.get(cls.CACHE_KEY)
        if configuration is not None:
            return configuration
        configuration, _ = cls.objects.get_or_create(pk=1)
        cache.set(cls.CACHE_KEY, configuration, None)
        return configuration
