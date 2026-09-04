"""Sérialiseurs des dossiers, dépenses et justificatifs."""

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from accounts.permissions import get_access
from budget.aggregates import convert
from core.models import Country

from .models import AuditLog, Beneficiary, Dossier, Expense, Proof, compute_sha256
from .workflow import LOCKED_STATUSES, PROOF_LOCKED_STATUSES

#: États d'une pièce après lesquels plus rien ne se modifie.
PROOF_FINAL_STATUSES = frozenset(
    {
        Proof.ProofStatus.VALIDATED,
        Proof.ProofStatus.REJECTED,
        Proof.ProofStatus.ARCHIVED,
    }
)


class ChampCloisonne(serializers.PrimaryKeyRelatedField):
    """Clé étrangère limitée au périmètre du demandeur.

    Sans cela, un responsable pays pouvait sonder l'existence des dossiers du
    voisin : une clé inconnue répondait « invalide », une clé existante mais
    hors périmètre répondait « pays interdit » — et le dossier était trahi.
    Le queryset du champ est filtré comme celui des lectures : une clé hors
    périmètre est, pour le demandeur, une clé qui n'existe pas.

    ``chemin_pays`` mène du modèle visé au pays (``pk`` pour le pays
    lui-même).
    """

    def __init__(self, *, chemin_pays, **kwargs):
        self.chemin_pays = chemin_pays
        super().__init__(**kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        request = self.context.get("request")
        access = get_access(getattr(request, "user", None)) if request else None
        if access is None:
            return queryset.none()
        if access.has_global_scope:
            return queryset
        return queryset.filter(**{f"{self.chemin_pays}__in": access.country_ids})


def _verifier_le_manager(owner, country):
    """Un manager ne porte une dépense que dans un pays où il est rattaché."""
    if owner is None or country is None:
        return
    if not owner.countries.filter(pk=country.pk).exists():
        raise serializers.ValidationError(
            {"owner": "Ce manager n'est pas rattaché à ce pays."}
        )


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
    dossier = ChampCloisonne(queryset=Dossier.objects.all(), chemin_pays="country")
    replaces = ChampCloisonne(
        queryset=Proof.objects.all(), chemin_pays="dossier__country",
        required=False, allow_null=True,
    )
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()

    #: Fixés au dépôt. Une pièce est une preuve : on n'en change ni le
    #: contenu, ni le dossier, ni la filiation — on en dépose une nouvelle
    #: version, qui archive l'ancienne.
    IMMUABLES = ("file", "dossier", "replaces")

    class Meta:
        model = Proof
        fields = [
            "id", "dossier", "file", "original_name", "kind", "kind_display",
            "status", "status_display", "is_complete", "sha256", "size",
            "content_type", "version", "replaces", "uploaded_by",
            "rejection_reason", "download_url", "created_at", "updated_at",
        ]
        # ``is_complete`` ne se modifie que par ``review`` : c'est un constat
        # du contrôleur, pas une case que le déposant coche.
        read_only_fields = [
            "original_name", "sha256", "size", "content_type", "version",
            "uploaded_by", "status", "rejection_reason", "is_complete",
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
        if self.instance is not None:
            self._verifier_la_mise_a_jour()

        dossier = attrs.get("dossier") or getattr(self.instance, "dossier", None)
        if dossier is not None and dossier.status in PROOF_LOCKED_STATUSES:
            raise serializers.ValidationError(
                "Le dossier est clôturé : plus aucun justificatif ne peut y "
                "être ajouté."
            )

        replaces = attrs.get("replaces")
        if replaces is not None and dossier is not None:
            self.verifier_le_remplacement(replaces, dossier)

        uploaded = attrs.get("file")
        if uploaded is not None:
            attrs["sha256"] = compute_sha256(uploaded)
            attrs["size"] = uploaded.size
            attrs["original_name"] = uploaded.name[:255]
            attrs["content_type"] = getattr(uploaded, "content_type", "") or ""
            self._check_duplicate(dossier, attrs["sha256"], replaces)
        return attrs

    def _verifier_la_mise_a_jour(self):
        """Ce qui reste modifiable sur une pièce déposée : presque rien."""
        if self.instance.status in PROOF_FINAL_STATUSES:
            raise serializers.ValidationError(
                f"Ce justificatif est {self.instance.get_status_display().lower()} : "
                "il ne se modifie plus. Déposez une nouvelle version s'il "
                "doit être corrigé."
            )
        figes = [champ for champ in self.IMMUABLES if champ in self.initial_data]
        if figes:
            raise serializers.ValidationError(
                {
                    champ: "Ce champ est fixé au dépôt : déposez une nouvelle "
                    "version plutôt que de modifier celle-ci."
                    for champ in figes
                }
            )

    @staticmethod
    def verifier_le_remplacement(replaces, dossier):
        """La pièce remplacée doit appartenir au même dossier.

        Sans ce contrôle, un pays pouvait archiver — via ``replaces`` — une
        pièce d'un dossier qu'il n'a pas le droit de voir : le remplacement
        change le statut de la pièce remplacée. Le message ne distingue pas
        « autre dossier » de « inexistante », pour ne rien révéler.
        """
        if replaces.dossier_id != dossier.pk:
            raise serializers.ValidationError(
                {"replaces": "Pièce invalide pour ce dossier."}
            )
        if replaces.status == Proof.ProofStatus.ARCHIVED:
            raise serializers.ValidationError(
                {"replaces": "Cette pièce a déjà été remplacée."}
            )

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
    dossier = ChampCloisonne(queryset=Dossier.objects.all(), chemin_pays="country")
    country = ChampCloisonne(queryset=Country.objects.all(), chemin_pays="pk")
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
            "original_currency", "original_amount", "original_rate",
            "payment_method", "payment_method_display",
            "status", "status_display", "note", "control_note", "created_by",
            "created_at", "updated_at",
        ]
        # Le statut ne se modifie que par les actions de workflow ;
        # l'imputation budgétaire et le taux appliqué sont résolus par le
        # serveur — un taux fourni par le client serait un taux choisi.
        # Le montant justifié appartient au siège : le pays déclare ce qu'il
        # a dépensé, le contrôleur constate ce qui est prouvé (``justify``).
        # Le laisser saisir revenait à laisser le déclarant se donner quitus.
        read_only_fields = [
            "status", "budget", "created_by", "original_rate",
            "justified_amount", "control_note",
        ]
        extra_kwargs = {
            # Calculé lorsque la dépense est décaissée dans une autre devise.
            "amount": {"required": False},
        }

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
        for field in (
            "team", "project", "expense_title", "marketing_category", "beneficiary",
        ):
            value = attrs.get(field)
            if value is not None and country is not None and value.country_id != country.pk:
                raise serializers.ValidationError(
                    {field: "Cette entité appartient à un autre pays."}
                )
        _verifier_le_manager(attrs.get("owner"), country)

        self._resoudre_la_devise(attrs, country)
        return attrs

    def _resoudre_la_devise(self, attrs, country):
        """Convertit un décaissement fait dans une autre devise (§5.3).

        Une mission au Togo peut payer un hôtel en euros : la pièce porte
        120 EUR. Le montant d'origine est conservé pour que le contrôleur
        retrouve le chiffre du justificatif, et ``amount`` reçoit sa
        conversion dans la devise du pays — c'est elle qui pèse sur
        l'enveloppe, et c'est elle qui garde les agrégats monodevise.

        Le taux est celui du jour de la dépense, figé à la saisie : un
        rapport tiré l'an prochain doit donner le même chiffre
        qu'aujourd'hui.
        """
        if self.partial and not (
            "original_currency" in self.initial_data
            or "original_amount" in self.initial_data
        ):
            # Une modification qui ne touche pas au décaissement d'origine le
            # laisse intact : un PATCH du libellé effaçait la devise.
            if getattr(self.instance, "original_currency", "") and "amount" in attrs:
                raise serializers.ValidationError(
                    {
                        "amount": (
                            "Cette dépense a été décaissée en "
                            f"{self.instance.original_currency} : son montant "
                            "se calcule à partir du montant décaissé. "
                            "Modifiez celui-ci plutôt que la conversion."
                        )
                    }
                )
            return

        # En modification partielle, le champ absent garde sa valeur : ne
        # corriger que le montant décaissé ne doit pas faire perdre la devise.
        courant = self.instance if self.partial else None
        devise = attrs.get(
            "original_currency", getattr(courant, "original_currency", None)
        )
        montant = attrs.get(
            "original_amount", getattr(courant, "original_amount", None)
        )
        if devise is not None:
            devise = devise.strip().upper()
            attrs["original_currency"] = devise

        if not devise or montant is None:
            # Dépense dans la devise du pays : rien à convertir, et rien à
            # conserver qui ferait croire à un décaissement étranger.
            if not devise and montant is None:
                attrs["original_currency"] = ""
                attrs["original_amount"] = None
                attrs["original_rate"] = None
            if attrs.get("amount") is None and self.instance is None:
                raise serializers.ValidationError(
                    {"amount": "Le montant de la dépense est requis."}
                )
            if devise or montant is not None:
                raise serializers.ValidationError(
                    {
                        "original_currency": (
                            "Indiquez à la fois la devise et le montant "
                            "décaissés, ou aucun des deux."
                        )
                    }
                )
            return

        if country is None:
            return

        if devise == country.currency:
            # Même devise : la conversion serait l'identité, et conserver un
            # « montant d'origine » laisserait croire à un décaissement
            # étranger.
            attrs["amount"] = montant
            attrs["original_currency"] = ""
            attrs["original_amount"] = None
            attrs["original_rate"] = None
            return

        date = attrs.get("date") or getattr(self.instance, "date", None)
        converti, taux = convert(
            montant, devise, country.currency, date.date() if date else None
        )
        if converti is None:
            raise serializers.ValidationError(
                {
                    "original_currency": (
                        f"Aucun taux connu pour convertir {devise} en "
                        f"{country.currency} à cette date. Publiez-le dans "
                        "Configuration › Taux de change."
                    )
                }
            )
        attrs["amount"] = converti
        attrs["original_rate"] = taux


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
    country = ChampCloisonne(queryset=Country.objects.all(), chemin_pays="pk")
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
            "expense_count", "proof_count", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["status", "created_by"]

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
        _verifier_le_manager(attrs.get("owner"), country)
        return attrs


class DossierDetailSerializer(DossierSerializer):
    expenses = ExpenseSerializer(many=True, read_only=True)
    proofs = ProofSerializer(many=True, read_only=True)

    class Meta(DossierSerializer.Meta):
        fields = DossierSerializer.Meta.fields + ["expenses", "proofs"]


class TransitionSerializer(serializers.Serializer):
    """Motif accompagnant une transition ; obligatoire pour un rejet (§5.5)."""

    note = serializers.CharField(required=False, allow_blank=True)


class ExpenseTransitionSerializer(TransitionSerializer):
    """Transition d'une ligne : le contrôleur peut fixer ce qui est prouvé.

    Par défaut, justifier couvre toute la dépense ; une pièce partielle
    permet d'en constater une partie seulement. La borne haute (le montant
    de la dépense) se vérifie dans la vue, qui connaît la ligne.
    """

    justified_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False,
        min_value=Decimal("0"),
    )


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
