"""Sérialiseurs des dossiers, dépenses et justificatifs."""

from django.conf import settings
from rest_framework import serializers

from .models import AuditLog, Beneficiary, Dossier, Expense, Proof, compute_sha256
from .workflow import LOCKED_STATUSES


class BeneficiarySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            "id", "name", "kind", "kind_display", "contact", "is_active",
            "created_at", "updated_at",
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
        return uploaded

    def validate(self, attrs):
        dossier = attrs.get("dossier") or getattr(self.instance, "dossier", None)
        if dossier is not None and dossier.status in LOCKED_STATUSES:
            raise serializers.ValidationError(
                "Le dossier est verrouillé : aucun justificatif ne peut y être "
                "ajouté ou modifié."
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
            "currency", "team", "team_name", "owner", "owner_name",
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
                "Cette dépense est validée : elle ne peut plus être modifiée "
                "en place, seulement corrigée par une opération auditée."
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


class DossierSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    country_ref = serializers.CharField(
        source="country.country_ref", read_only=True, allow_null=True
    )
    currency = serializers.CharField(source="country.currency", read_only=True)
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )
    owner_name = serializers.CharField(
        source="owner.name", read_only=True, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    totals = serializers.SerializerMethodField()
    expense_count = serializers.IntegerField(source="expenses.count", read_only=True)
    proof_count = serializers.IntegerField(source="proofs.count", read_only=True)

    class Meta:
        model = Dossier
        fields = [
            "id", "number", "label", "country", "country_name", "country_ref",
            "currency", "team", "team_name", "owner", "owner_name", "date",
            "status", "status_display", "note", "totals",
            "expense_count", "proof_count", "created_at", "updated_at",
        ]
        read_only_fields = ["status"]

    def get_totals(self, dossier):
        return {key: str(value) for key, value in dossier.totals().items()}

    def validate(self, attrs):
        if self.instance is not None and self.instance.status in LOCKED_STATUSES:
            raise serializers.ValidationError(
                "Ce dossier est validé : il ne peut plus être modifié en place."
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
