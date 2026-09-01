"""Modèles de la section 5.1 : gestion des pays et organisations."""

from django.db import models


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
    code = models.CharField("Code ISO", max_length=2, unique=True, help_text="ISO 3166-1 alpha-2")
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
    timezone = models.CharField("Fuseau horaire", max_length=64, default="UTC")
    is_active = models.BooleanField("Actif", default=True)
    managers = models.ManyToManyField(
        Manager, blank=True, related_name="countries", verbose_name="Manager(s)"
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Pays"

    def __str__(self):
        return self.name


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
    """Journal des changements (y compris les rattachements de pays)."""

    class Actions(models.TextChoices):
        CREATED = "created", "Création"
        UPDATED = "updated", "Mise à jour"
        REASSIGNED = "reassigned", "Changement de rattachement"
        DEACTIVATED = "deactivated", "Désactivation"
        REACTIVATED = "reactivated", "Réactivation"
        DELETED = "deleted", "Suppression"

    class Models(models.TextChoices):
        COUNTRY = "country", "Pays"
        MANAGER = "manager", "Manager"
        TEAM = "team", "Équipe"
        COST_CENTER = "cost_center", "Centre de coûts"
        PROJECT = "project", "Projet"
        EXPENSE_TITLE = "expense_title", "Intitulé de dépenses"
        MARKETING_CATEGORY = "marketing_category", "Catégorie marketing"

    model_name = models.CharField(
        "Entité", max_length=32, choices=Models.choices
    )
    object_id = models.PositiveIntegerField("Identifiant d'entité")
    label = models.CharField("Libellé", max_length=250)
    action = models.CharField("Action", max_length=20, choices=Actions.choices)
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="history", verbose_name="Pays",
    )
    from_value = models.TextField("Valeur précédente", blank=True)
    to_value = models.TextField("Nouvelle valeur", blank=True)
    changed_fields = models.JSONField("Champs modifiés", default=list, blank=True)
    performed_by = models.CharField("Par", max_length=180, blank=True)
    created_at = models.DateTimeField("Le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Historique"
        verbose_name_plural = "Historiques"

    def __str__(self):
        return f"[{self.get_action_display()}] {self.label}"