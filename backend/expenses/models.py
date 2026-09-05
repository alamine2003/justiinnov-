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
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

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

from .workflow import DECIDED_STATUSES, REOPEN_BLOCKING_STATUSES, Status

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
        PROSPECT = "prospect", _("Prospect")
        CLIENT = "client", _("Client")
        SUPPLIER = "supplier", _("Fournisseur")
        BENEFICIARY = "beneficiary", _("Bénéficiaire")
        OTHER = "other", _("Autre")

    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name="beneficiaries",
        verbose_name=_("Pays"),
    )
    name = models.CharField(_("Nom"), max_length=180)
    kind = models.CharField(
        _("Type"), max_length=32, choices=Kind.choices, default=Kind.BENEFICIARY
    )
    contact = models.CharField(_("Contact"), max_length=180, blank=True)
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Bénéficiaire")
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
                # Avancement du contrôle, pour dire quelles décisions le
                # dossier admet (``line_counts``) sans requête par dossier.
                pending=Count("id", filter=~Q(status__in=DECIDED_STATUSES)),
                unjustified=Count("id", filter=Q(status=Status.UNJUSTIFIED)),
                settled=Count("id", filter=Q(status__in=REOPEN_BLOCKING_STATUSES)),
            )
        )
        money = models.DecimalField(max_digits=16, decimal_places=2)
        entier = models.IntegerField()

        def compteur(nom):
            return Coalesce(
                Subquery(lines.values(nom)[:1], output_field=entier), Value(0)
            )

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
            total_lines=compteur("lines"),
            lines_pending=compteur("pending"),
            lines_unjustified=compteur("unjustified"),
            lines_settled=compteur("settled"),
            total_proofs=Count("proofs", distinct=True),
            # Une pièce rejetée ou archivée ne prouve rien.
            usable_proofs=Count(
                "proofs",
                filter=~Q(proofs__status__in=[
                    Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED,
                ]),
                distinct=True,
            ),
        )


class Dossier(TimeStampedModel):
    """Le **N°ORDRE** : ensemble documentaire d'une opération."""

    objects = DossierQuerySet.as_manager()

    # Le N°ORDRE est numéroté **par pays** : le classeur du client repart de
    # 1 dans chaque pays. Une unicité globale refusait donc le « 12 » du
    # Togo dès que la Côte d'Ivoire avait le sien — et trahissait au passage
    # l'existence du dossier voisin. L'unicité vaut sur (pays, numéro).
    number = models.CharField(_("N° d'ordre"), max_length=50)
    label = models.CharField(_("Libellé"), max_length=250)
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="dossiers", verbose_name=_("Pays")
    )
    # Rien ne se supprime dans le référentiel : une équipe ou un manager se
    # désactive. ``PROTECT`` rend la règle inviolable même depuis l'admin ou
    # un script — un ``SET_NULL`` aurait effacé silencieusement le contexte
    # d'un dossier déclaré.
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT,
        related_name="dossiers", verbose_name=_("Équipe"),
    )
    owner = models.ForeignKey(
        Manager, null=True, blank=True, on_delete=models.PROTECT,
        related_name="dossiers", verbose_name=_("Propriétaire"),
    )
    date = models.DateField(_("Date"))
    status = models.CharField(
        _("Statut"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField(_("Remarque de contrôle"), blank=True)
    # Motif de la dernière réouverture par un administrateur (voir
    # ``workflow``). Il reste lisible sur la fiche, y compris après la
    # resoumission : le pays comme le siège doivent voir pourquoi ce dossier
    # est repassé par le brouillon. L'historique complet est dans le journal.
    reopen_note = models.TextField(_("Motif de la réouverture"), blank=True)
    # Permet la règle des quatre yeux au niveau du dossier : celui qui l'a
    # ouvert ne le tranche pas. Et seul son auteur peut retirer un brouillon.
    created_by = models.CharField(_("Ouvert par"), max_length=180, blank=True)

    class Meta:
        # ``-pk`` en dernier : deux dossiers créés dans la même seconde
        # n'auraient sinon pas d'ordre stable entre deux pages.
        ordering = ["-date", "-created_at", "-pk"]
        verbose_name = _("Dossier de justification")
        verbose_name_plural = _("Dossiers de justification")
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

    def line_counts(self):
        """Lignes par avancement du contrôle : ce que le dossier admet.

        ``pending`` : pas encore tranchées (brouillon, soumises, en
        contrôle) ; ``unjustified`` : constatées sans preuve ; ``settled`` :
        justifiées ou clôturées, ce qui interdit la réouverture. Lues dans
        les annotations de :meth:`DossierQuerySet.with_totals` quand elles
        sont là, sinon en une seule agrégation.
        """
        pending = getattr(self, "lines_pending", None)
        if pending is None:
            aggregate = self.expenses.aggregate(
                total=Count("id"),
                pending=Count("id", filter=~Q(status__in=DECIDED_STATUSES)),
                unjustified=Count("id", filter=Q(status=Status.UNJUSTIFIED)),
                settled=Count("id", filter=Q(status__in=REOPEN_BLOCKING_STATUSES)),
            )
            return aggregate
        return {
            "total": self.total_lines,
            "pending": pending,
            "unjustified": self.lines_unjustified,
            "settled": self.lines_settled,
        }

    def usable_proof_count(self):
        """Pièces qui prouvent encore quelque chose : ni rejetées ni archivées."""
        usable = getattr(self, "usable_proofs", None)
        if usable is None:
            return self.proofs.exclude(
                status__in=[Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED]
            ).count()
        return usable


#: Relations chargées avec chaque ligne : tout ce que le sérialiseur affiche.
#: Sans elles, chaque ligne d'une liste — ou relue après une transition —
#: rouvrirait une requête par relation.
EXPENSE_RELATIONS = (
    "dossier", "country", "team", "owner", "project",
    "expense_title", "marketing_category", "beneficiary",
    "budget__country", "budget__project", "budget__team", "budget__manager",
)


class Expense(TimeStampedModel):
    """Une ligne de dépense, rattachée à un dossier."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", _("Espèces")
        TRANSFER = "transfer", _("Virement")
        MOBILE = "mobile", _("Mobile money")
        CARD = "card", _("Carte")
        CHECK = "check", _("Chèque")
        OTHER = "other", _("Autre")

    # ``PROTECT`` partout : supprimer un dossier ne doit jamais emporter ses
    # lignes en cascade — l'argent a été dépensé, la trace reste. Le retrait
    # d'un brouillon passe par la vue, qui efface les lignes une à une en
    # les journalisant.
    dossier = models.ForeignKey(
        Dossier, on_delete=models.PROTECT, related_name="expenses",
        verbose_name=_("Dossier"),
    )
    # Contexte dupliqué sur chaque ligne (décision de modélisation n°1).
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="expenses", verbose_name=_("Pays")
    )
    team = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Équipe"),
    )
    owner = models.ForeignKey(
        Manager, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Propriétaire"),
    )
    date = models.DateTimeField(_("Date et heure"))
    place = models.CharField(_("Lieu"), max_length=180, blank=True)
    title = models.CharField(_("Libellé de la transaction"), max_length=250)
    description = models.TextField(_("Description"), blank=True)

    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Projet"),
    )
    expense_title = models.ForeignKey(
        ExpenseTitle, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Intitulé de dépenses"),
    )
    marketing_category = models.ForeignKey(
        MarketingCategory, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Catégorie marketing"),
    )
    beneficiary = models.ForeignKey(
        Beneficiary, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Prospect / bénéficiaire"),
    )
    budget = models.ForeignKey(
        Budget, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses", verbose_name=_("Enveloppe imputée"),
        help_text=_("Résolue automatiquement ; obligatoire avant validation."),
    )

    amount = models.DecimalField(
        _("Dépense"), max_digits=16, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe."),
    )
    justified_amount = models.DecimalField(
        _("Montant justifié"), max_digits=16, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
    )

    # --- Décaissement dans une autre devise (§5.3) -------------------------
    #
    # Une mission au Togo peut payer un hôtel en euros. Le reçu porte alors
    # 120 EUR, pas son équivalent en francs. Conserver le montant d'origine
    # est nécessaire pour rapprocher la dépense de sa pièce : le siège
    # qui ne lirait que la conversion ne retrouverait aucun des deux chiffres
    # sur le justificatif.
    #
    # L'enveloppe, elle, reste dans la devise du pays : ``amount`` porte la
    # conversion, figée au taux du jour de la dépense, de sorte que les
    # agrégats restent monodevise — et justes.
    original_currency = models.CharField(
        _("Devise du décaissement"), max_length=3, blank=True,
        help_text=_("Vide si la dépense a été faite dans la devise du pays."),
    )
    original_amount = models.DecimalField(
        _("Montant décaissé"), max_digits=16, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Tel qu'il figure sur la pièce, dans sa devise d'origine."),
    )
    original_rate = models.DecimalField(
        _("Taux appliqué"), max_digits=18, decimal_places=6, null=True, blank=True,
        help_text=_(
            "Figé à la saisie. Le conserver permet de refaire le calcul plus "
            "tard, même si la table des taux a depuis été corrigée."
        ),
    )
    payment_method = models.CharField(
        _("Mode de paiement"), max_length=20,
        choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    status = models.CharField(
        _("Statut"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    note = models.TextField(_("Remarque"), blank=True)
    # Le motif du siège (DF) a son propre champ : il écrasait ``note``, la
    # remarque du pays, si bien qu'un rejet effaçait ce que le déclarant
    # avait pris soin d'expliquer.
    control_note = models.TextField(_("Motif du contrôle"), blank=True)
    created_by = models.CharField(_("Saisie par"), max_length=180, blank=True)

    class Meta:
        ordering = ["-date", "-created_at", "-pk"]
        verbose_name = _("Dépense")
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
        """Écart entre la dépense et ce qui est prouvé — jamais saisi ; lu par les sérialiseurs."""
        return self.amount - self.justified_amount

    @property
    def currency(self):
        return self.country.currency


class Proof(TimeStampedModel):
    """Pièce justificative, rattachée au **dossier** (§5.4)."""

    class Kind(models.TextChoices):
        RECEIPT = "receipt", pgettext_lazy("type de pièce", "Reçu")
        INVOICE = "invoice", _("Facture")
        DISCHARGE = "discharge", _("Décharge")
        DELIVERABLE = "deliverable", _("Livrable")
        OTHER = "other", _("Autre")

    class ProofStatus(models.TextChoices):
        RECEIVED = "received", pgettext_lazy("état d'une pièce", "Reçu")
        INCOMPLETE = "incomplete", _("Incomplet")
        TO_REVIEW = "to_review", _("À contrôler")
        VALIDATED = "validated", _("Validé")
        REJECTED = "rejected", _("Rejeté")
        ARCHIVED = "archived", _("Archivé")

    dossier = models.ForeignKey(
        Dossier, on_delete=models.PROTECT, related_name="proofs",
        verbose_name=_("Dossier"),
    )
    file = models.FileField(_("Fichier"), upload_to=proof_upload_path)
    original_name = models.CharField(_("Nom d'origine"), max_length=255, blank=True)
    kind = models.CharField(
        _("Type"), max_length=32, choices=Kind.choices, default=Kind.RECEIPT
    )
    status = models.CharField(
        _("Statut"), max_length=20, choices=ProofStatus.choices,
        default=ProofStatus.RECEIVED,
    )
    is_complete = models.BooleanField(
        _("Justificatif complet"), default=True,
        help_text=_("Reprend la nuance « reçu (justif incomplet) » du fichier source."),
    )
    sha256 = models.CharField(
        _("Empreinte SHA-256"), max_length=64, db_index=True,
        help_text=_("Détecte toute modification ultérieure et les doublons."),
    )
    size = models.PositiveBigIntegerField(_("Taille (octets)"), default=0)
    content_type = models.CharField(_("Type MIME"), max_length=120, blank=True)
    version = models.PositiveIntegerField(_("Version"), default=1)
    # La chaîne des versions est une preuve en soi : on ne la rompt pas.
    replaces = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="replaced_by", verbose_name=_("Remplace"),
    )
    uploaded_by = models.CharField(_("Déposé par"), max_length=180, blank=True)
    rejection_reason = models.TextField(_("Motif de rejet"), blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("Pièce justificative")
        verbose_name_plural = _("Pièces justificatives")
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
        CREATED = "created", _("Création")
        UPDATED = "updated", _("Modification")
        SUBMITTED = "submitted", _("Soumission")
        REVIEWED = "reviewed", _("Mise en contrôle")
        JUSTIFIED = "justified", _("Justification")
        UNJUSTIFIED = "unjustified", _("Constat de non-justification")
        # Conservées pour le contrôle documentaire d'une pièce : celle-ci
        # est bien validée ou rejetée, à la différence de la dépense.
        APPROVED = "approved", _("Validation d'un justificatif")
        REJECTED = "rejected", _("Rejet d'un justificatif")
        # Un justificatif signalé incomplet ou remis à contrôler n'est pas
        # rejeté : le journal doit dire ce qui s'est réellement passé.
        PROOF_INCOMPLETE = "proof_incomplete", _("Justificatif signalé incomplet")
        PROOF_TO_REVIEW = "proof_to_review", _("Justificatif remis à contrôler")
        DELETED = "deleted", _("Suppression d'un brouillon")
        CLOSED = "closed", _("Clôture")
        # Seule exception à l'irréversibilité : un administrateur renvoie un
        # dossier déclaré au brouillon pour demander des comptes. L'entrée
        # porte le motif ; en la cherchant, on relit toute l'histoire.
        REOPENED = "reopened", _("Réouverture")
        PROOF_UPLOADED = "proof_uploaded", _("Dépôt de justificatif")
        PROOF_REPLACED = "proof_replaced", _("Remplacement de justificatif")
        DOWNLOADED = "downloaded", _("Téléchargement")
        IMPORTED = "imported", _("Import Excel")

    user = models.CharField(_("Utilisateur"), max_length=180, blank=True)
    action = models.CharField(_("Action"), max_length=32, choices=Action.choices)
    object_type = models.CharField(_("Type d'objet"), max_length=64)
    # Nul pour une action qui ne porte sur aucun objet précis (export,
    # import). Les modules qui écrivent encore ``0`` restent acceptés.
    object_id = models.PositiveBigIntegerField(_("Identifiant"), null=True, blank=True)
    label = models.CharField(_("Libellé"), max_length=250, blank=True)
    # PROTECT : le journal est immuable en base, une mise à NULL serait
    # refusée ; un pays tracé ne se supprime pas, il se désactive.
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.PROTECT,
        related_name="audit_entries", verbose_name=_("Pays"),
    )
    detail = models.JSONField(_("Détail"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("Adresse IP"), null=True, blank=True)
    user_agent = models.CharField(_("Appareil / session"), max_length=250, blank=True)
    created_at = models.DateTimeField(_("Le"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("Journal d'audit")
        verbose_name_plural = _("Journal d'audit")
        indexes = [
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["created_at"], name="audit_date"),
            models.Index(fields=["country", "created_at"], name="audit_pays_date"),
            models.Index(fields=["user"], name="audit_utilisateur"),
        ]

    def __str__(self):
        return f"[{self.get_action_display()}] {self.object_type} #{self.object_id}"
