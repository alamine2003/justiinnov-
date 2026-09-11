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

#: Longueur maximale d'un titre de notification, préfixe compris.
#:
#: Un titre se compose d'un préfixe traduit et d'un libellé venu d'ailleurs,
#: repris **tel quel** — jamais tronqué : « Dépense refusée — {title} » porte
#: les 250 caractères de ``Expense.title`` ; « Seuil 100 % atteint —
#: {budget} » porte ``Budget.__str__``, soit le nom du pays (120), l'année,
#: et le nom du projet, de l'équipe ou du manager (180), un peu plus de 330
#: caractères au pire. La colonne faisait 200 : un libellé importé un peu
#: long faisait lever la base au moment d'écrire la notification, et cette
#: erreur, avalée, annulait la transition qu'elle signalait
#: (``notifications.tests.test_reprise_des_emails``). La marge est large,
#: et un test compose le pire cas pour qu'elle le reste.
TITRE_MAX = 500


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
        #: Seconde exception : une demande de rectification d'un constat
        #: attend un administrateur ; puis sa décision revient au demandeur,
        #: au contrôle et au pays.
        RECTIFICATION_REQUESTED = "rectification_requested", _("Demande de rectification")
        RECTIFICATION_DECIDED = "rectification_decided", _("Décision sur une rectification")

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
    title = models.CharField("Titre", max_length=TITRE_MAX)
    body = models.TextField("Message", blank=True)
    link = models.CharField(
        "Lien", max_length=250, blank=True,
        help_text="Chemin relatif dans l'application, ex. /dossiers/12.",
    )
    # PROTECT : une notification atteste que quelqu'un a été prévenu, pour
    # quel pays ; un pays tracé ne se supprime pas, il se désactive.
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.PROTECT,
        related_name="notifications", verbose_name="Pays",
    )
    dedup_key = models.CharField(
        "Clé d'unicité", max_length=180,
        help_text="Empêche de notifier deux fois le même événement.",
    )
    read_at = models.DateTimeField("Lu le", null=True, blank=True)
    #: Posé quand l'e-mail est **parti** — après ``send()``, jamais avant.
    emailed_at = models.DateTimeField("E-mail envoyé le", null=True, blank=True)
    #: Reprise des envois (``services.envoyer_les_emails``) : l'e-mail part
    #: après la validation de la transaction, hors de tout verrou métier, et
    #: son échec ne fait échouer ni l'action ni sa réponse. Il faut donc
    #: pouvoir le reprendre plus tard : ``email_attempted_at`` réclame la
    #: ligne pour un envoi en cours (un second processus ne la reprend
    #: qu'après ``DELAI_DE_REPRISE``), ``email_attempts`` borne les essais.
    #: Une ligne avec ``emailed_at`` vide et une adresse est un envoi qui
    #: reste à faire — c'est l'enregistrement durable du travail restant,
    #: sans table de file d'attente.
    email_attempted_at = models.DateTimeField(
        "Dernier essai d'envoi le", null=True, blank=True
    )
    email_attempts = models.PositiveSmallIntegerField("Essais d'envoi", default=0)
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
            # La reprise cherche les envois restants par ``emailed_at`` vide :
            # un index partiel, petit, sur les seules lignes à reprendre.
            models.Index(
                fields=["email_attempted_at"],
                name="notification_email_a_faire_idx",
                condition=models.Q(emailed_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.recipient.username}"
