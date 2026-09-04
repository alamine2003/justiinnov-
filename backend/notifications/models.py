"""Notifications in-app, doublées d'un e-mail (§8).

**Conservation illimitée.** Une notification lue reste en base : elle
atteste que quelqu'un a été prévenu d'un manquement, et à quelle date. Aucune
commande, aucun signal, aucune tâche planifiée ne purge cette table — pas
plus que les pièces, les dossiers, les dépenses ou le journal d'audit. La
seule suppression tolérée par l'application reste celle d'un brouillon
jamais soumis.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import Country


class Notification(models.Model):
    # Les libellés sont traduits à l'affichage (``kind_display`` suit la
    # langue de la requête) ; la valeur enregistrée, elle, ne change pas.
    class Kind(models.TextChoices):
        BUDGET_THRESHOLD = "budget_threshold", _("Seuil budgétaire atteint")
        BUDGET_OVERRUN = "budget_overrun", _("Dépassement budgétaire")
        EXPENSE_SUBMITTED = "expense_submitted", _("Dépense à contrôler")
        EXPENSE_REJECTED = "expense_rejected", _("Dépense rejetée")
        PROOF_MISSING = "proof_missing", _("Justificatif manquant")
        PROOF_INCOMPLETE = "proof_incomplete", _("Justificatif incomplet")
        REALLOCATION_REQUESTED = "reallocation_requested", _("Demande de réallocation")
        STORAGE_ERROR = "storage_error", _("Anomalie de stockage")
        #: Seule exception à l'irréversibilité : le siège rouvre un dossier
        #: déclaré pour demander des comptes, et le pays doit le savoir.
        DOSSIER_REOPENED = "dossier_reopened", _("Dossier rouvert")

    class Level(models.TextChoices):
        INFO = "info", _("Information")
        WARNING = "warning", _("Avertissement")
        CRITICAL = "critical", _("Critique")

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
