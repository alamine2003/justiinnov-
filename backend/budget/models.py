"""Enveloppes budgétaires, réallocations et taux de change.

Une enveloppe est annuelle et rattachée à un pays. Elle peut être déclinée en
sous-enveloppes par projet (``project`` renseigné). Les montants sont stockés
dans la devise du pays ; la consolidation au siège se fait en FCFA (XOF).
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce

from core.models import Country, Project, TimeStampedModel

#: Devise de consolidation : le siège est au Sénégal.
CONSOLIDATION_CURRENCY = "XOF"


class OverrunPolicy(models.TextChoices):
    """Conduite à tenir lorsqu'une dépense ferait dépasser l'enveloppe (§6)."""

    BLOCK = "block", "Bloquer"
    WARN = "warn", "Alerter"
    APPROVAL = "approval", "Soumettre à approbation"


class BudgetQuerySet(models.QuerySet):
    def with_consumption(self):
        """Annote engagé, consommé et justifié en une seule requête.

        Les trois totaux passent par la même jointure sur les dépenses, avec
        des filtres conditionnels : pas de multiplication des lignes possible,
        `expenses` étant l'unique relation jointe.
        """
        # Import local : `expenses` dépend de `budget`, l'inverse ne doit pas
        # créer de cycle à l'import du module.
        from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES

        money = models.DecimalField(max_digits=16, decimal_places=2)
        engaging = list(ENGAGING_STATUSES)
        consuming = list(CONSUMING_STATUSES)
        zero = Value(Decimal("0.00"))
        # L'agrégation introduit un GROUP BY, qui fait perdre à Django
        # l'ordre par défaut du modèle : sans tri explicite, deux pages
        # successives pourraient se recouvrir.
        return self.order_by(*Budget._meta.ordering).annotate(
            engaged_total=Coalesce(
                Sum("expenses__amount", filter=Q(expenses__status__in=engaging)),
                zero,
                output_field=money,
            ),
            consumed_total=Coalesce(
                Sum("expenses__amount", filter=Q(expenses__status__in=consuming)),
                zero,
                output_field=money,
            ),
            justified_total=Coalesce(
                Sum(
                    "expenses__justified_amount",
                    filter=Q(expenses__status__in=consuming),
                ),
                zero,
                output_field=money,
            ),
        )


class Budget(TimeStampedModel):
    """Enveloppe annuelle d'un pays, ou sous-enveloppe d'un projet."""

    objects = BudgetQuerySet.as_manager()

    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name="budgets", verbose_name="Pays"
    )
    year = models.PositiveIntegerField("Année")
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="budgets",
        verbose_name="Projet",
        help_text="Renseigné pour une sous-enveloppe ; vide pour l'enveloppe du pays.",
    )
    amount = models.DecimalField(
        "Montant",
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    overrun_policy = models.CharField(
        "Politique de dépassement",
        max_length=20,
        choices=OverrunPolicy.choices,
        default=OverrunPolicy.BLOCK,
    )
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["-year", "country__name"]
        verbose_name = "Budget"
        constraints = [
            models.UniqueConstraint(
                fields=["country", "year"],
                condition=Q(project__isnull=True),
                name="unique_enveloppe_pays_annee",
            ),
            models.UniqueConstraint(
                fields=["country", "project", "year"],
                name="unique_sous_enveloppe_projet_annee",
            ),
        ]

    def __str__(self):
        if self.project_id:
            return f"{self.country.name} {self.year} — {self.project.name}"
        return f"{self.country.name} {self.year}"

    @property
    def currency(self):
        return self.country.currency


class BudgetReallocation(TimeStampedModel):
    """Transfert entre enveloppes, avec justification et approbation (§5.2)."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        APPROVED = "approved", "Approuvée"
        REJECTED = "rejected", "Refusée"

    source = models.ForeignKey(
        Budget, on_delete=models.PROTECT, related_name="reallocations_out",
        verbose_name="Enveloppe source",
    )
    target = models.ForeignKey(
        Budget, on_delete=models.PROTECT, related_name="reallocations_in",
        verbose_name="Enveloppe destinataire",
    )
    amount = models.DecimalField(
        "Montant",
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.TextField("Justification")
    status = models.CharField(
        "Statut", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    requested_by = models.CharField("Demandée par", max_length=180, blank=True)
    decided_by = models.CharField("Décidée par", max_length=180, blank=True)
    decided_at = models.DateTimeField("Décidée le", null=True, blank=True)
    decision_note = models.TextField("Motif de la décision", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Réallocation budgétaire"
        verbose_name_plural = "Réallocations budgétaires"

    def __str__(self):
        return f"{self.amount} : {self.source} → {self.target}"


class ExchangeRate(models.Model):
    """Taux de conversion d'une devise vers le FCFA, daté.

    La conversion d'une opération est figée au taux en vigueur à sa date, afin
    que les rapports historiques restent stables.
    """

    currency = models.CharField("Devise", max_length=3, help_text="ISO 4217")
    rate_to_xof = models.DecimalField(
        "Taux vers le FCFA",
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text="Nombre de FCFA pour une unité de la devise.",
    )
    valid_from = models.DateField("En vigueur depuis")
    created_at = models.DateTimeField("Créé le", auto_now_add=True)

    class Meta:
        ordering = ["currency", "-valid_from"]
        verbose_name = "Taux de change"
        verbose_name_plural = "Taux de change"
        constraints = [
            models.UniqueConstraint(
                fields=["currency", "valid_from"], name="unique_taux_devise_date"
            )
        ]

    def __str__(self):
        return f"1 {self.currency} = {self.rate_to_xof} XOF ({self.valid_from})"
