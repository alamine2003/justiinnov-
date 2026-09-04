"""Notifications in-app, doublées d'un e-mail (§8)."""

from django.contrib.auth.models import User
from django.db import models

from core.models import Country


class Notification(models.Model):
    class Kind(models.TextChoices):
        BUDGET_THRESHOLD = "budget_threshold", "Seuil budgétaire atteint"
        BUDGET_OVERRUN = "budget_overrun", "Dépassement budgétaire"
        EXPENSE_SUBMITTED = "expense_submitted", "Dépense à contrôler"
        EXPENSE_REJECTED = "expense_rejected", "Dépense rejetée"
        PROOF_MISSING = "proof_missing", "Justificatif manquant"
        PROOF_INCOMPLETE = "proof_incomplete", "Justificatif incomplet"
        REALLOCATION_REQUESTED = "reallocation_requested", "Demande de réallocation"
        STORAGE_ERROR = "storage_error", "Anomalie de stockage"

    class Level(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Avertissement"
        CRITICAL = "critical", "Critique"

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications",
        verbose_name="Destinataire",
    )
    kind = models.CharField("Type", max_length=32, choices=Kind.choices)
    level = models.CharField(
        "Niveau", max_length=16, choices=Level.choices, default=Level.INFO
    )
    title = models.CharField("Titre", max_length=200)
    body = models.TextField("Message", blank=True)
    link = models.CharField(
        "Lien", max_length=250, blank=True,
        help_text="Chemin relatif dans l'application, ex. /dossiers/12.",
    )
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="notifications", verbose_name="Pays",
    )
    dedup_key = models.CharField(
        "Clé d'unicité", max_length=180,
        help_text="Empêche de notifier deux fois le même événement.",
    )
    read_at = models.DateTimeField("Lu le", null=True, blank=True)
    emailed_at = models.DateTimeField("E-mail envoyé le", null=True, blank=True)
    created_at = models.DateTimeField("Le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedup_key"], name="unique_notification_par_evenement"
            )
        ]
        indexes = [
            models.Index(fields=["recipient", "read_at"]),
            # ``notify`` cherche d'abord qui a déjà été averti d'un événement,
            # par sa clé seule : sans index dédié, chaque alerte parcourait
            # la table entière.
            models.Index(fields=["dedup_key"], name="notification_dedup_key_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.recipient.username}"
