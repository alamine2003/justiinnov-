"""Modèles de la section 5.1 : gestion des pays et organisations."""

from decimal import Decimal

from django.core.cache import cache
from django.db import models
from django.db.models.deletion import ProtectedError

from .africa import validate_african_country
from .validators import validate_timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        abstract = True


class Manager(TimeStampedModel):
    """Un responsable commercial / de pays."""

    name = models.CharField("Nom", max_length=180)
    email = models.EmailField("Email", blank=True)
    title = models.CharField("Fonction", max_length=180, blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Country(TimeStampedModel):
    """Pays : devise, fuseau horaire, managers, équipes et centres de coûts."""

    name = models.CharField("Nom", max_length=120, unique=True)
    code = models.CharField(
        "Code ISO",
        max_length=2,
        unique=True,
        help_text="ISO 3166-1 alpha-2 ; la plateforme ne suit que des pays africains.",
        validators=[validate_african_country],
    )
    country_ref = models.CharField(
        "Identifiant pays",
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        help_text="Identifiant fonctionnel utilisé par le siège, ex. CT-01.",
    )
    currency = models.CharField("Devise", max_length=3, help_text="ISO 4217")
    currency_symbol = models.CharField("Symbole devise", max_length=4, blank=True)
    timezone = models.CharField(
        "Fuseau horaire",
        max_length=64,
        default="UTC",
        help_text="Identifiant IANA, ex. Africa/Abidjan.",
        validators=[validate_timezone],
    )
    is_active = models.BooleanField("Actif", default=True)
    managers = models.ManyToManyField(
        Manager, blank=True, related_name="countries", verbose_name="Manager(s)"
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Pays"

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
        Country, on_delete=models.CASCADE, related_name="teams", verbose_name="Pays"
    )
    name = models.CharField("Nom", max_length=180)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Équipe"

    def __str__(self):
        return f"{self.name} ({self.country.name})"


class CostCenter(TimeStampedModel):
    """Centre de coûts rattaché à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="cost_centers", verbose_name="Pays"
    )
    code = models.CharField("Code", max_length=20)
    name = models.CharField("Libellé", max_length=180)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Centre de coûts"
        unique_together = ("country", "code")

    def __str__(self):
        return f"{self.code} — {self.name}"


class Project(TimeStampedModel):
    STATUS_CHOICES = [
        ("planned", "Planifié"),
        ("active", "En cours"),
        ("on_hold", "En pause"),
        ("completed", "Terminé"),
    ]

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="projects", verbose_name="Pays"
    )
    name = models.CharField("Nom", max_length=180)
    description = models.TextField("Description", blank=True)
    status = models.CharField("Statut", max_length=20, choices=STATUS_CHOICES, default="planned")
    budget = models.DecimalField(
        "Budget", max_digits=14, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Projet"

    def __str__(self):
        return self.name


class ExpenseTitle(TimeStampedModel):
    """Intitulé de dépenses rattaché à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="expense_titles", verbose_name="Pays"
    )
    label = models.CharField("Intitulé", max_length=180)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["label"]
        verbose_name = "Intitulé de dépenses"
        unique_together = ("country", "label")

    def __str__(self):
        return self.label


class MarketingCategory(TimeStampedModel):
    """Catégorie marketing rattachée à un pays."""

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="marketing_categories",
        verbose_name="Pays",
    )
    name = models.CharField("Nom", max_length=180)
    description = models.TextField("Description", blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Catégorie marketing"
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
        CREATED = "created", "Création"
        UPDATED = "updated", "Mise à jour"
        REASSIGNED = "reassigned", "Changement de rattachement"
        DEACTIVATED = "deactivated", "Désactivation"
        REACTIVATED = "reactivated", "Réactivation"
        DELETED = "deleted", "Suppression"
        PASSWORD_RESET = "password_reset", "Réinitialisation du mot de passe"
        PASSWORD_CHANGED = "password_changed", "Changement de mot de passe"
        LOGIN = "login", "Connexion"
        LOGIN_FAILED = "login_failed", "Échec de connexion"
        LOGOUT = "logout", "Déconnexion"

    class Models(models.TextChoices):
        COUNTRY = "country", "Pays"
        MANAGER = "manager", "Manager"
        TEAM = "team", "Équipe"
        COST_CENTER = "cost_center", "Centre de coûts"
        PROJECT = "project", "Projet"
        EXPENSE_TITLE = "expense_title", "Intitulé de dépenses"
        MARKETING_CATEGORY = "marketing_category", "Catégorie marketing"
        BUDGET = "budget", "Enveloppe budgétaire"
        REALLOCATION = "reallocation", "Réallocation budgétaire"
        EXCHANGE_RATE = "exchange_rate", "Taux de change"
        WORKFLOW_CONFIGURATION = "workflow_configuration", "Configuration du workflow"
        USER = "user", "Compte utilisateur"

    model_name = models.CharField(
        "Entité", max_length=32, choices=Models.choices
    )
    object_id = models.PositiveBigIntegerField(
        "Identifiant d'entité", null=True, blank=True
    )
    label = models.CharField("Libellé", max_length=250)
    action = models.CharField("Action", max_length=20, choices=Actions.choices)
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="history", verbose_name="Pays",
    )
    from_value = models.TextField("Valeur précédente", blank=True)
    to_value = models.TextField("Nouvelle valeur", blank=True)
    changed_fields = models.JSONField("Champs modifiés", default=list, blank=True)
    #: ``{champ: [ancienne valeur, nouvelle valeur]}``, valeurs sérialisables
    #: en JSON : ``from_value``/``to_value`` ne portent qu'un libellé.
    diff = models.JSONField("Différences", default=dict, blank=True)
    performed_by = models.CharField("Par", max_length=180, blank=True)
    ip_address = models.GenericIPAddressField("Adresse IP", null=True, blank=True)
    created_at = models.DateTimeField("Le", auto_now_add=True)

    class Meta:
        # ``-pk`` départage deux entrées écrites dans la même transaction (un
        # rattachement puis une mise à jour) : sans lui, leur ordre relatif
        # dépendrait du plan d'exécution.
        ordering = ["-created_at", "-pk"]
        verbose_name = "Historique"
        verbose_name_plural = "Historiques"
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
        ("block", "Bloquer"),
        ("warn", "Alerter"),
        ("approval", "Soumettre à approbation"),
    )

    require_review_step = models.BooleanField(
        "Étape de contrôle obligatoire", default=False
    )
    unjustified_alert_days = models.PositiveIntegerField(
        "Délai d'alerte sans justification", default=0
    )
    alert_thresholds = models.JSONField("Seuils d'alerte", default=_seuils_par_defaut)
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
    updated_at = models.DateTimeField("Modifié le", auto_now=True)

    class Meta:
        verbose_name = "Configuration du workflow"
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
            "La configuration du workflow est un singleton et ne peut pas être supprimée.",
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
