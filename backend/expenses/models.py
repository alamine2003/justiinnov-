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
from django.db.models import Count, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

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
    """Range les preuves par pays et par dossier.

    Le dossier est désigné par sa clé et non par son numéro : le numéro est
    saisi par un humain, il peut contenir un séparateur de chemin ou changer
    tant que le dossier est en brouillon, ce qui égarerait les fichiers déjà
    déposés.
    """
    dossier = instance.dossier
    return f"justificatifs/{dossier.country_id}/{dossier.pk}/{filename}"


class Beneficiary(TimeStampedModel):
    """Prospect, client, fournisseur ou bénéficiaire d'une dépense.

    Rattaché à un pays, comme le reste du référentiel. Il ne l'était pas :
    la liste était commune, si bien qu'un pays lisait les fournisseurs et les
    prospects d'un autre — de quoi reconstituer qui le voisin démarche et qui
    il paie. Le nom était unique globalement par-dessus le marché : deux pays
    ne pouvaient pas déclarer le même fournisseur.
    """

    class Kind(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        CLIENT = "client", "Client"
        SUPPLIER = "supplier", "Fournisseur"
        BENEFICIARY = "beneficiary", "Bénéficiaire"
        OTHER = "other", "Autre"

    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name="beneficiaries",
        verbose_name="Pays",
    )
    name = models.CharField("Nom", max_length=180)
    kind = models.CharField(
        "Type", max_length=32, choices=Kind.choices, default=Kind.BENEFICIARY
    )
    contact = models.CharField("Contact", max_length=180, blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Bénéficiaire"
        constraints = [
            models.UniqueConstraint(
                fields=["country", "name"], name="unique_beneficiaire_par_pays"
            )
        ]

    def __str__(self):
        return self.name


class DossierQuerySet(models.QuerySet):
    def with_totals(self):
        """Prépare totaux et compteurs en une seule requête.

        Les totaux passent par une sous-requête plutôt que par une jointure :
        joindre à la fois les dépenses et les preuves multiplierait chaque
        montant par le nombre de preuves du dossier.
        """
        lines = (
            Expense.objects.filter(dossier=OuterRef("pk"))
            .order_by()
            .values("dossier")
            .annotate(
                amount=Sum("amount"),
                justified=Sum("justified_amount"),
                lines=Count("id"),
            )
        )
        money = models.DecimalField(max_digits=16, decimal_places=2)
        # Le comptage des preuves introduit un GROUP BY, qui fait perdre à
        # Django l'ordre par défaut du modèle : sans tri explicite, deux pages
        # successives pourraient se recouvrir.
        return self.order_by(*Dossier._meta.ordering).annotate(
            total_amount=Coalesce(
                Subquery(lines.values("amount")[:1], output_field=money),
                Value(ZERO),
                output_field=money,
            ),
            total_justified=Coalesce(
                Subquery(lines.values("justified")[:1], output_field=money),
                Value(ZERO),
                output_field=money,
            ),
            total_lines=Coalesce(
                Subquery(
                    lines.values("lines")[:1],
                    output_field=models.IntegerField(),
                ),
                Value(0),
            ),
            total_proofs=Count("proofs", distinct=True),
        )


class Dossier(TimeStampedModel):
    """Le **N°ORDRE** : ensemble documentaire d'une opération."""

    objects = DossierQuerySet.as_manager()

    # Le N°ORDRE est numéroté **par pays** : le classeur du client repart de
    # 1 dans chaque pays. Une unicité globale refusait donc le « 12 » du
    # Togo dès que la Côte d'Ivoire avait le sien — et trahissait au passage
    # l'existence du dossier voisin. L'unicité vaut sur (pays, numéro).
    number = models.CharField("N° d'ordre", max_length=50)
    label = models.CharField("Libellé", max_length=250)
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="dossiers", verbose_name="Pays"
    )
    # Rien ne se supprime dans le référentiel : une équipe ou un manager se
    # désactive. ``PROTECT`` rend la règle inviolable même depuis l'admin ou
    # un script — un ``SET_NULL`` aurait effacé silencieusement le contexte
    # d'un dossier déclaré.
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT,
        related_name="dossiers", verbose_name="Équipe",
    )
    owner = models.ForeignKey(
        Manager, null=True, blank=True, on_delete=models.PROTECT,
        related_name="dossiers", verbose_name="Propriétaire",
    )
    date = models.DateField("Date")
    status = models.CharField(
        "Statut", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField("Remarque de contrôle", blank=True)
    # Permet la règle des quatre yeux au niveau du dossier : celui qui l'a
    # ouvert ne le tranche pas. Et seul son auteur peut retirer un brouillon.
    created_by = models.CharField("Ouvert par", max_length=180, blank=True)

    class Meta:
        # ``-pk`` en dernier : deux dossiers créés dans la même seconde
        # n'auraient sinon pas d'ordre stable entre deux pages.
        ordering = ["-date", "-created_at", "-pk"]
        verbose_name = "Dossier de justification"
        verbose_name_plural = "Dossiers de justification"
        constraints = [
            models.UniqueConstraint(
                fields=["country", "number"], name="unique_dossier_par_pays"
            )
        ]
        indexes = [
            models.Index(fields=["country", "status"], name="dossier_pays_statut"),
            models.Index(fields=["date"], name="dossier_date"),
        ]

    def __str__(self):
        return f"{self.number} — {self.label}"

    def totals(self):
        """Totaux du dossier, calculés sur ses lignes.

        Réutilise les annotations de :meth:`DossierQuerySet.with_totals`
        lorsqu'elles sont présentes, plutôt que de relancer une agrégation par
        dossier affiché.
        """
        amount = getattr(self, "total_amount", None)
        if amount is None:
            aggregate = self.expenses.aggregate(
                amount=Sum("amount"), justified=Sum("justified_amount")
            )
            amount = aggregate["amount"] or ZERO
            justified = aggregate["justified"] or ZERO
        else:
            justified = self.total_justified
        return {"amount": amount, "justified": justified, "gap": amount - justified}

    def counts(self):
        """Nombre de lignes et de preuves, annotés si disponibles."""
        lines = getattr(self, "total_lines", None)
        proofs = getattr(self, "total_proofs", None)
        return {
            "expenses": self.expenses.count() if lines is None else lines,
            "proofs": self.proofs.count() if proofs is None else proofs,
        }


class Expense(TimeStampedModel):
    """Une ligne de dépense, rattachée à un dossier."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Espèces"
        TRANSFER = "transfer", "Virement"
        MOBILE = "mobile", "Mobile money"
        CARD = "card", "Carte"
        CHECK = "check", "Chèque"
        OTHER = "other", "Autre"

    # ``PROTECT`` partout : supprimer un dossier ne doit jamais emporter ses
    # lignes en cascade — l'argent a été dépensé, la trace reste. Le retrait
    # d'un brouillon passe par la vue, qui efface les lignes une à une en
    # les journalisant.
    dossier = models.ForeignKey(
        Dossier, on_delete=models.PROTECT, related_name="expenses",
        verbose_name="Dossier",
    )
    # Contexte dupliqué sur chaque ligne (décision de modélisation n°1).
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="expenses", verbose_name="Pays"
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name="Équipe",
    )
    owner = models.ForeignKey(
        Manager, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name="Propriétaire",
    )
    date = models.DateTimeField("Date et heure")
    place = models.CharField("Lieu", max_length=180, blank=True)
    title = models.CharField("Libellé de la transaction", max_length=250)
    description = models.TextField("Description", blank=True)

    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name="Projet",
    )
    expense_title = models.ForeignKey(
        ExpenseTitle, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name="Intitulé de dépenses",
    )
    marketing_category = models.ForeignKey(
        MarketingCategory, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name="Catégorie marketing",
    )
    beneficiary = models.ForeignKey(
        Beneficiary, null=True, blank=True, on_delete=models.PROTECT,
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
        help_text="Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe.",
    )
    justified_amount = models.DecimalField(
        "Montant justifié", max_digits=16, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # --- Décaissement dans une autre devise (§5.3) -------------------------
    #
    # Une mission au Togo peut payer un hôtel en euros. Le reçu porte alors
    # 120 EUR, pas son équivalent en francs. Conserver le montant d'origine
    # est nécessaire pour rapprocher la dépense de sa pièce : un contrôleur
    # qui ne lirait que la conversion ne retrouverait aucun des deux chiffres
    # sur le justificatif.
    #
    # L'enveloppe, elle, reste dans la devise du pays : ``amount`` porte la
    # conversion, figée au taux du jour de la dépense, de sorte que les
    # agrégats restent monodevise — et justes.
    original_currency = models.CharField(
        "Devise du décaissement", max_length=3, blank=True,
        help_text="Vide si la dépense a été faite dans la devise du pays.",
    )
    original_amount = models.DecimalField(
        "Montant décaissé", max_digits=16, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Tel qu'il figure sur la pièce, dans sa devise d'origine.",
    )
    original_rate = models.DecimalField(
        "Taux appliqué", max_digits=18, decimal_places=6, null=True, blank=True,
        help_text=(
            "Figé à la saisie. Le conserver permet de refaire le calcul plus "
            "tard, même si la table des taux a depuis été corrigée."
        ),
    )
    payment_method = models.CharField(
        "Mode de paiement", max_length=20,
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    status = models.CharField(
        "Statut", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField("Remarque", blank=True)
    # Le motif du contrôleur a son propre champ : il écrasait ``note``, la
    # remarque du pays, si bien qu'un rejet effaçait ce que le déclarant
    # avait pris soin d'expliquer.
    control_note = models.TextField("Motif du contrôle", blank=True)
    created_by = models.CharField("Saisie par", max_length=180, blank=True)

    class Meta:
        ordering = ["-date", "-created_at", "-pk"]
        verbose_name = "Dépense"
        # Les invariants métier sont aussi posés en base : un script ou
        # l'admin ne passent pas par les sérialiseurs.
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0), name="depense_montant_positif"
            ),
            # Ce qui est prouvé ne dépasse jamais ce qui est dépensé.
            models.CheckConstraint(
                condition=Q(justified_amount__gte=0)
                & Q(justified_amount__lte=F("amount")),
                name="depense_justifie_borne",
            ),
            # Devise d'origine : tout ou rien. Un montant sans devise, ou une
            # conversion sans taux, ne se rapproche d'aucune pièce.
            models.CheckConstraint(
                condition=Q(
                    original_currency="",
                    original_amount__isnull=True,
                    original_rate__isnull=True,
                )
                | (
                    ~Q(original_currency="")
                    & Q(original_amount__isnull=False)
                    & Q(original_rate__isnull=False)
                ),
                name="depense_devise_origine_coherente",
            ),
            # Une dépense déclarée pèse sur une enveloppe, toujours.
            models.CheckConstraint(
                condition=Q(status=Status.DRAFT) | Q(budget__isnull=False),
                name="depense_declaree_imputee",
            ),
        ]
        indexes = [
            models.Index(fields=["budget", "status"], name="depense_enveloppe_statut"),
            models.Index(
                fields=["country", "status", "date"], name="depense_pays_statut_date"
            ),
            models.Index(fields=["date"], name="depense_date"),
        ]

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
        Dossier, on_delete=models.PROTECT, related_name="proofs",
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
    # La chaîne des versions est une preuve en soi : on ne la rompt pas.
    replaces = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="replaced_by", verbose_name="Remplace",
    )
    uploaded_by = models.CharField("Déposé par", max_length=180, blank=True)
    rejection_reason = models.TextField("Motif de rejet", blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Pièce justificative"
        verbose_name_plural = "Pièces justificatives"
        indexes = [
            models.Index(fields=["dossier", "status"], name="piece_dossier_statut"),
        ]

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
        JUSTIFIED = "justified", "Justification"
        UNJUSTIFIED = "unjustified", "Constat de non-justification"
        # Conservées pour le contrôle documentaire d'une pièce : celle-ci
        # est bien validée ou rejetée, à la différence de la dépense.
        APPROVED = "approved", "Validation d'un justificatif"
        REJECTED = "rejected", "Rejet d'un justificatif"
        # Un justificatif signalé incomplet ou remis à contrôler n'est pas
        # rejeté : le journal doit dire ce qui s'est réellement passé.
        PROOF_INCOMPLETE = "proof_incomplete", "Justificatif signalé incomplet"
        PROOF_TO_REVIEW = "proof_to_review", "Justificatif remis à contrôler"
        DELETED = "deleted", "Suppression d'un brouillon"
        CLOSED = "closed", "Clôture"
        PROOF_UPLOADED = "proof_uploaded", "Dépôt de justificatif"
        PROOF_REPLACED = "proof_replaced", "Remplacement de justificatif"
        DOWNLOADED = "downloaded", "Téléchargement"
        IMPORTED = "imported", "Import Excel"

    user = models.CharField("Utilisateur", max_length=180, blank=True)
    action = models.CharField("Action", max_length=32, choices=Action.choices)
    object_type = models.CharField("Type d'objet", max_length=64)
    # Nul pour une action qui ne porte sur aucun objet précis (export,
    # import). Les modules qui écrivent encore ``0`` restent acceptés.
    object_id = models.PositiveBigIntegerField("Identifiant", null=True, blank=True)
    label = models.CharField("Libellé", max_length=250, blank=True)
    # PROTECT : le journal est immuable en base, une mise à NULL serait
    # refusée ; un pays tracé ne se supprime pas, il se désactive.
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.PROTECT,
        related_name="audit_entries", verbose_name="Pays",
    )
    detail = models.JSONField("Détail", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("Adresse IP", null=True, blank=True)
    user_agent = models.CharField("Appareil / session", max_length=250, blank=True)
    created_at = models.DateTimeField("Le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Journal d'audit"
        verbose_name_plural = "Journal d'audit"
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["created_at"], name="audit_date"),
            models.Index(fields=["country", "created_at"], name="audit_pays_date"),
            models.Index(fields=["user"], name="audit_utilisateur"),
        ]

    def __str__(self):
        return f"[{self.get_action_display()}] {self.object_type} #{self.object_id}"
