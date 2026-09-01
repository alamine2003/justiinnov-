"""Dossiers de justification (N°ORDRE), dépenses et pièces justificatives.

Modèle figé par `docs/model-de-donnees.md` : le N°ORDRE devient un *dossier*
regroupant les preuves d'une même opération, et les lignes du fichier Excel
deviennent des dépenses rattachées à ce dossier. Le contexte (pays, équipe,
propriétaire, date) est **dupliqué sur chaque ligne**, pour une traçabilité
ligne à ligne indépendante.
"""

import hashlib
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from budget.models import Budget
from core.models import (
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
    TimeStampedModel,
)

from .workflow import Status

ZERO = Decimal("0.00")


def proof_upload_path(instance, filename):
    """Range les preuves par pays et par dossier."""
    dossier = instance.dossier
    return f"justificatifs/{dossier.country_id}/{dossier.number}/{filename}"


class Beneficiary(TimeStampedModel):
    """Prospect, client, fournisseur ou bénéficiaire d'une dépense."""

    class Kind(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        CLIENT = "client", "Client"
        SUPPLIER = "supplier", "Fournisseur"
        BENEFICIARY = "beneficiary", "Bénéficiaire"
        OTHER = "other", "Autre"

    name = models.CharField("Nom", max_length=180, unique=True)
    kind = models.CharField(
        "Type", max_length=32, choices=Kind.choices, default=Kind.BENEFICIARY
    )
    contact = models.CharField("Contact", max_length=180, blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Bénéficiaire"

    def __str__(self):
        return self.name


class Dossier(TimeStampedModel):
    """Le **N°ORDRE** : ensemble documentaire d'une opération."""

    number = models.CharField("N° d'ordre", max_length=50, unique=True)
    label = models.CharField("Libellé", max_length=250)
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="dossiers", verbose_name="Pays"
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dossiers", verbose_name="Équipe",
    )
    owner = models.ForeignKey(
        Manager, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dossiers", verbose_name="Propriétaire",
    )
    date = models.DateField("Date")
    status = models.CharField(
        "Statut", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField("Remarque de contrôle", blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Dossier de justification"
        verbose_name_plural = "Dossiers de justification"

    def __str__(self):
        return f"{self.number} — {self.label}"

    def totals(self):
        """Totaux du dossier, calculés sur ses lignes."""
        aggregate = self.expenses.aggregate(
            amount=models.Sum("amount"), justified=models.Sum("justified_amount")
        )
        amount = aggregate["amount"] or ZERO
        justified = aggregate["justified"] or ZERO
        return {"amount": amount, "justified": justified, "gap": amount - justified}


class Expense(TimeStampedModel):
    """Une ligne de dépense, rattachée à un dossier."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Espèces"
        TRANSFER = "transfer", "Virement"
        MOBILE = "mobile", "Mobile money"
        CARD = "card", "Carte"
        CHECK = "check", "Chèque"
        OTHER = "other", "Autre"

    dossier = models.ForeignKey(
        Dossier, on_delete=models.CASCADE, related_name="expenses",
        verbose_name="Dossier",
    )
    # Contexte dupliqué sur chaque ligne (décision de modélisation n°1).
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="expenses", verbose_name="Pays"
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses", verbose_name="Équipe",
    )
    owner = models.ForeignKey(
        Manager, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses", verbose_name="Propriétaire",
    )
    date = models.DateTimeField("Date et heure")
    place = models.CharField("Lieu", max_length=180, blank=True)
    title = models.CharField("Libellé de la transaction", max_length=250)
    description = models.TextField("Description", blank=True)

    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses", verbose_name="Projet",
    )
    expense_title = models.ForeignKey(
        ExpenseTitle, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses", verbose_name="Intitulé de dépenses",
    )
    marketing_category = models.ForeignKey(
        MarketingCategory, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses", verbose_name="Catégorie marketing",
    )
    beneficiary = models.ForeignKey(
        Beneficiary, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses", verbose_name="Prospect / bénéficiaire",
    )
    budget = models.ForeignKey(
        Budget, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name="Enveloppe imputée",
        help_text="Résolue automatiquement ; obligatoire avant validation.",
    )

    amount = models.DecimalField(
        "Dépense", max_digits=16, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    justified_amount = models.DecimalField(
        "Montant justifié", max_digits=16, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
    )
    payment_method = models.CharField(
        "Mode de paiement", max_length=20,
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    status = models.CharField(
        "Statut", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField("Remarque", blank=True)
    created_by = models.CharField("Saisie par", max_length=180, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Dépense"

    def __str__(self):
        return f"{self.title} ({self.amount})"

    @property
    def gap(self):
        """Écart entre la dépense et ce qui est prouvé — jamais saisi."""
        return self.amount - self.justified_amount

    @property
    def currency(self):
        return self.country.currency


class Proof(TimeStampedModel):
    """Pièce justificative, rattachée au **dossier** (§5.4)."""

    class Kind(models.TextChoices):
        RECEIPT = "receipt", "Reçu"
        INVOICE = "invoice", "Facture"
        DISCHARGE = "discharge", "Décharge"
        DELIVERABLE = "deliverable", "Livrable"
        OTHER = "other", "Autre"

    class ProofStatus(models.TextChoices):
        RECEIVED = "received", "Reçu"
        INCOMPLETE = "incomplete", "Incomplet"
        TO_REVIEW = "to_review", "À contrôler"
        VALIDATED = "validated", "Validé"
        REJECTED = "rejected", "Rejeté"
        ARCHIVED = "archived", "Archivé"

    dossier = models.ForeignKey(
        Dossier, on_delete=models.CASCADE, related_name="proofs",
        verbose_name="Dossier",
    )
    file = models.FileField("Fichier", upload_to=proof_upload_path)
    original_name = models.CharField("Nom d'origine", max_length=255, blank=True)
    kind = models.CharField(
        "Type", max_length=32, choices=Kind.choices, default=Kind.RECEIPT
    )
    status = models.CharField(
        "Statut", max_length=20, choices=ProofStatus.choices,
        default=ProofStatus.RECEIVED,
    )
    is_complete = models.BooleanField(
        "Justificatif complet", default=True,
        help_text="Reprend la nuance « reçu (justif incomplet) » du fichier source.",
    )
    sha256 = models.CharField(
        "Empreinte SHA-256", max_length=64, db_index=True,
        help_text="Détecte toute modification ultérieure et les doublons.",
    )
    size = models.PositiveBigIntegerField("Taille (octets)", default=0)
    content_type = models.CharField("Type MIME", max_length=120, blank=True)
    version = models.PositiveIntegerField("Version", default=1)
    replaces = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="replaced_by", verbose_name="Remplace",
    )
    uploaded_by = models.CharField("Déposé par", max_length=180, blank=True)
    rejection_reason = models.TextField("Motif de rejet", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pièce justificative"
        verbose_name_plural = "Pièces justificatives"

    def __str__(self):
        return f"{self.get_kind_display()} — {self.original_name or self.file.name}"


def compute_sha256(uploaded_file):
    """Empreinte d'un fichier, lu par blocs pour ne pas le charger en mémoire."""
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


class AuditLog(models.Model):
    """Journal des actions sensibles (§6) : qui, quoi, quand, depuis où."""

    class Action(models.TextChoices):
        CREATED = "created", "Création"
        UPDATED = "updated", "Modification"
        SUBMITTED = "submitted", "Soumission"
        REVIEWED = "reviewed", "Mise en contrôle"
        APPROVED = "approved", "Validation"
        REJECTED = "rejected", "Rejet"
        CLOSED = "closed", "Clôture"
        PROOF_UPLOADED = "proof_uploaded", "Dépôt de justificatif"
        PROOF_REPLACED = "proof_replaced", "Remplacement de justificatif"
        DOWNLOADED = "downloaded", "Téléchargement"

    user = models.CharField("Utilisateur", max_length=180, blank=True)
    action = models.CharField("Action", max_length=32, choices=Action.choices)
    object_type = models.CharField("Type d'objet", max_length=64)
    object_id = models.PositiveIntegerField("Identifiant")
    label = models.CharField("Libellé", max_length=250, blank=True)
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries", verbose_name="Pays",
    )
    detail = models.JSONField("Détail", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("Adresse IP", null=True, blank=True)
    user_agent = models.CharField("Appareil / session", max_length=250, blank=True)
    created_at = models.DateTimeField("Le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journal d'audit"
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def __str__(self):
        return f"[{self.get_action_display()}] {self.object_type} #{self.object_id}"
