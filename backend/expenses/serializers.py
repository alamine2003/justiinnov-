"""Sérialiseurs des dossiers, dépenses et justificatifs."""

from pathlib import Path

from django.conf import settings
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import AuditLog, Beneficiary, Dossier, Expense, Proof, compute_sha256
from .workflow import LOCKED_STATUSES, PROOF_LOCKED_STATUSES


class BeneficiarySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )

    class Meta:
        model = Beneficiary
        fields = [
            "id", "country", "country_name", "name", "kind", "kind_display",
            "contact", "is_active", "created_at", "updated_at",
        ]
        # Le message par défaut de la contrainte d'unicité est illisible ;
        # celui-ci dit ce qu'il faut corriger.
        validators = [
            UniqueTogetherValidator(
                queryset=Beneficiary.objects.all(),
                fields=["country", "name"],
                message="Ce bénéficiaire existe déjà pour ce pays.",
            )
        ]


class ProofSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Proof
        fields = [
            "id", "dossier", "file", "original_name", "kind", "kind_display",
            "status", "status_display", "is_complete", "sha256", "size",
            "content_type", "version", "replaces", "uploaded_by",
            "rejection_reason", "download_url", "created_at", "updated_at",
        ]
        read_only_fields = [
            "original_name", "sha256", "size", "content_type", "version",
            "uploaded_by", "status", "rejection_reason",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def get_download_url(self, proof):
        """Le fichier n'est jamais servi directement : le téléchargement passe
        par une vue qui vérifie le périmètre de l'utilisateur."""
        return f"/api/proofs/{proof.pk}/download/"

    def validate_file(self, uploaded):
        if uploaded.size > settings.MAX_PROOF_SIZE:
            limit = settings.MAX_PROOF_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                f"Fichier trop volumineux (maximum {limit} Mo)."
            )
        extension = Path(uploaded.name).suffix.lower()
        if extension not in settings.ALLOWED_PROOF_EXTENSIONS:
            accepted = ", ".join(settings.ALLOWED_PROOF_EXTENSIONS)
            raise serializers.ValidationError(
                f"Format non accepté ({extension or 'sans extension'}). "
                f"Formats autorisés : {accepted}."
            )
        return uploaded

    def validate(self, attrs):
        dossier = attrs.get("dossier") or getattr(self.instance, "dossier", None)
        if dossier is not None and dossier.status in PROOF_LOCKED_STATUSES:
            raise serializers.ValidationError(
                "Le dossier est clôturé : plus aucun justificatif ne peut y "
                "être ajouté."
            )

        uploaded = attrs.get("file")
        if uploaded is not None:
            attrs["sha256"] = compute_sha256(uploaded)
            attrs["size"] = uploaded.size
            attrs["original_name"] = uploaded.name[:255]
            attrs["content_type"] = getattr(uploaded, "content_type", "") or ""
            self._check_duplicate(dossier, attrs["sha256"], attrs.get("replaces"))
        return attrs

    def _check_duplicate(self, dossier, digest, replaces):
        """Refuse un fichier identique déjà présent sur le même dossier (§5.4).

        Un remplacement explicite reste possible : c'est le seul cas où
        redéposer le même contenu a un sens.
        """
        if dossier is None or replaces is not None:
            return
        existing = Proof.objects.filter(dossier=dossier, sha256=digest)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                {"file": "Ce fichier est déjà rattaché à ce dossier (doublon)."}
            )


class ExpenseSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    currency = serializers.CharField(source="country.currency", read_only=True)
    # §6 : la date est conservée en UTC, mais doit se lire dans le fuseau du
    # pays où la dépense a eu lieu. Un contrôleur au siège verrait sinon
    # l'heure de son propre fuseau, ce qui fausse le « quand ».
    country_timezone = serializers.CharField(
        source="country.timezone", read_only=True
    )
    dossier_number = serializers.CharField(source="dossier.number", read_only=True)
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )
    owner_name = serializers.CharField(
        source="owner.name", read_only=True, allow_null=True
    )
    project_name = serializers.CharField(
        source="project.name", read_only=True, allow_null=True
    )
    beneficiary_name = serializers.CharField(
        source="beneficiary.name", read_only=True, allow_null=True
    )
    # Un `source="budget.__str__"` renverrait la représentation du
    # method-wrapper de None quand la dépense n'est pas encore imputée.
    budget_label = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    gap = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
        help_text="Toujours calculé : dépense − montant justifié.",
    )

    class Meta:
        model = Expense
        fields = [
            "id", "dossier", "dossier_number", "country", "country_name",
            "currency", "country_timezone", "team", "team_name",
            "owner", "owner_name",
            "date", "place", "title", "description",
            "project", "project_name", "expense_title", "marketing_category",
            "beneficiary", "beneficiary_name", "budget", "budget_label",
            "amount", "justified_amount", "gap",
            "payment_method", "payment_method_display",
            "status", "status_display", "note", "created_by",
            "created_at", "updated_at",
        ]
        # Le statut ne se modifie que par les actions de workflow, et
        # l'imputation budgétaire est résolue par le serveur.
        read_only_fields = ["status", "budget", "created_by"]

    def get_budget_label(self, expense):
        return str(expense.budget) if expense.budget_id else None

    def validate(self, attrs):
        if self.instance is not None and self.instance.status in LOCKED_STATUSES:
            raise serializers.ValidationError(
                "Cette dépense est déclarée : elle ne peut plus être modifiée. "
                "Seul un brouillon reste modifiable."
            )

        dossier = attrs.get("dossier") or getattr(self.instance, "dossier", None)
        country = attrs.get("country") or getattr(self.instance, "country", None)
        if dossier is not None and country is not None and dossier.country_id != country.pk:
            raise serializers.ValidationError(
                {"dossier": "Le dossier appartient à un autre pays."}
            )
        for field in ("team", "project", "expense_title", "marketing_category"):
            value = attrs.get(field)
            if value is not None and country is not None and value.country_id != country.pk:
                raise serializers.ValidationError(
                    {field: "Cette entité appartient à un autre pays."}
                )
        return attrs


class ExpenseProofSerializer(serializers.ModelSerializer):
    """Pièce vue depuis une dépense : de quoi juger sans ouvrir le dossier."""

    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Proof
        fields = [
            "id", "original_name", "kind", "kind_display",
            "status", "status_display", "is_complete", "sha256", "version",
        ]


class ExpenseRegisterSerializer(ExpenseSerializer):
    """Registre de justification : la dépense et ses preuves d'un seul tenant.

    Répond à la question que l'application existe pour trancher — on vous a
    confié un budget, qu'avez-vous dépensé, et qu'est-ce qui l'atteste ? Aucun
    détail de la dépense n'est écarté.
    """

    proofs = ExpenseProofSerializer(
        source="dossier.proofs", many=True, read_only=True
    )
    dossier_label = serializers.CharField(source="dossier.label", read_only=True)
    expense_title_label = serializers.CharField(
        source="expense_title.label", read_only=True, allow_null=True
    )
    marketing_category_name = serializers.CharField(
        source="marketing_category.name", read_only=True, allow_null=True
    )
    has_proof = serializers.SerializerMethodField()

    class Meta(ExpenseSerializer.Meta):
        fields = ExpenseSerializer.Meta.fields + [
            "dossier_label", "expense_title_label", "marketing_category_name",
            "proofs", "has_proof",
        ]

    def get_has_proof(self, expense):
        """Une pièce rejetée ou archivée ne prouve rien."""
        return any(
            proof.status
            not in (Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED)
            for proof in expense.dossier.proofs.all()
        )


class DossierSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    country_ref = serializers.CharField(
        source="country.country_ref", read_only=True, allow_null=True
    )
    currency = serializers.CharField(source="country.currency", read_only=True)
    country_timezone = serializers.CharField(
        source="country.timezone", read_only=True
    )
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )
    owner_name = serializers.CharField(
        source="owner.name", read_only=True, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    totals = serializers.SerializerMethodField()
    expense_count = serializers.SerializerMethodField()
    proof_count = serializers.SerializerMethodField()

    class Meta:
        model = Dossier
        fields = [
            "id", "number", "label", "country", "country_name", "country_ref",
            "currency", "country_timezone", "team", "team_name",
            "owner", "owner_name", "date",
            "status", "status_display", "note", "totals",
            "expense_count", "proof_count", "created_at", "updated_at",
        ]
        read_only_fields = ["status"]

    def get_totals(self, dossier):
        return {key: str(value) for key, value in dossier.totals().items()}

    def get_expense_count(self, dossier):
        return dossier.counts()["expenses"]

    def get_proof_count(self, dossier):
        return dossier.counts()["proofs"]

    def validate(self, attrs):
        if self.instance is not None and self.instance.status in LOCKED_STATUSES:
            raise serializers.ValidationError(
                "Ce dossier est déclaré : il ne peut plus être modifié."
            )
        country = attrs.get("country") or getattr(self.instance, "country", None)
        team = attrs.get("team")
        if team is not None and country is not None and team.country_id != country.pk:
            raise serializers.ValidationError(
                {"team": "Cette équipe appartient à un autre pays."}
            )
        return attrs


class DossierDetailSerializer(DossierSerializer):
    expenses = ExpenseSerializer(many=True, read_only=True)
    proofs = ProofSerializer(many=True, read_only=True)

    class Meta(DossierSerializer.Meta):
        fields = DossierSerializer.Meta.fields + ["expenses", "proofs"]


class TransitionSerializer(serializers.Serializer):
    """Motif accompagnant une transition ; obligatoire pour un rejet (§5.5)."""

    note = serializers.CharField(required=False, allow_blank=True)


class ProofReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Proof.ProofStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        rejected = attrs["status"] == Proof.ProofStatus.REJECTED
        if rejected and not attrs.get("reason", "").strip():
            raise serializers.ValidationError(
                {"reason": "Un rejet doit être motivé."}
            )
        return attrs


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )

    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "action", "action_display", "object_type", "object_id",
            "label", "country", "country_name", "detail", "ip_address",
            "user_agent", "created_at",
        ]
