"""Sérialiseurs de l'API de gestion des pays et organisations."""

from decimal import Decimal

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
    WorkflowConfiguration,
)


class ManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manager
        fields = ["id", "name", "email", "title", "is_active", "created_at", "updated_at"]


class TeamSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = Team
        fields = [
            "id", "country", "country_name", "name", "description",
            "is_active", "created_at", "updated_at",
        ]
        # Le message par défaut de la contrainte d'unicité est illisible ;
        # celui-ci dit ce qu'il faut corriger.
        validators = [
            UniqueTogetherValidator(
                queryset=Team.objects.all(),
                fields=["country", "name"],
                message="Cette équipe existe déjà pour ce pays.",
            )
        ]


class CostCenterSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = CostCenter
        fields = [
            "id", "country", "country_name", "code", "name",
            "is_active", "created_at", "updated_at",
        ]


class ProjectSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "country", "country_name", "name", "description",
            "status", "status_display", "budget",
            "is_active", "created_at", "updated_at",
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=Project.objects.all(),
                fields=["country", "name"],
                message="Ce projet existe déjà pour ce pays.",
            )
        ]


class ExpenseTitleSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = ExpenseTitle
        fields = [
            "id", "country", "country_name", "label", "description",
            "is_active", "created_at", "updated_at",
        ]


class MarketingCategorySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = MarketingCategory
        fields = [
            "id", "country", "country_name", "name", "description",
            "is_active", "created_at", "updated_at",
        ]


class CountryListSerializer(serializers.ModelSerializer):
    """Représentation compacte pour la liste des pays."""

    managers = ManagerSerializer(many=True, read_only=True)
    team_count = serializers.IntegerField(source="teams.count", read_only=True)
    cost_center_count = serializers.IntegerField(source="cost_centers.count", read_only=True)
    project_count = serializers.IntegerField(source="projects.count", read_only=True)

    class Meta:
        model = Country
        fields = [
            "id", "name", "code", "country_ref", "currency", "currency_symbol",
            "timezone", "is_active", "managers", "team_count",
            "cost_center_count", "project_count", "created_at", "updated_at",
        ]


class CountryDetailSerializer(CountryListSerializer):
    teams = TeamSerializer(many=True, read_only=True)
    cost_centers = CostCenterSerializer(many=True, read_only=True)
    projects = ProjectSerializer(many=True, read_only=True)
    expense_titles = ExpenseTitleSerializer(many=True, read_only=True)
    marketing_categories = MarketingCategorySerializer(many=True, read_only=True)
    expense_title_count = serializers.IntegerField(
        source="expense_titles.count", read_only=True
    )
    marketing_category_count = serializers.IntegerField(
        source="marketing_categories.count", read_only=True
    )

    class Meta(CountryListSerializer.Meta):
        fields = CountryListSerializer.Meta.fields + [
            "teams", "cost_centers", "projects",
            "expense_titles", "marketing_categories",
            "expense_title_count", "marketing_category_count",
        ]


class CountryWriteSerializer(serializers.ModelSerializer):
    managers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Manager.objects.all(), required=False
    )
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Country
        fields = [
            "id", "name", "code", "country_ref", "currency", "currency_symbol",
            "timezone", "is_active", "managers",
        ]

    def validate_code(self, value):
        """Normalise le code avant de l'enregistrer.

        « ci » et « CI » désignent le même pays ; sans cela, la contrainte
        d'unicité laisserait passer un doublon de casse.
        """
        return value.strip().upper()


class ChangeLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    model_name_display = serializers.CharField(
        source="get_model_name_display", read_only=True
    )
    # Le pays peut être nul (entité sans pays, ou pays supprimé) : sans
    # `allow_null`, DRF omettrait purement et simplement la clé.
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )

    class Meta:
        model = ChangeLog
        fields = [
            "id", "model_name", "model_name_display", "object_id", "label",
            "action", "action_display", "country", "country_name",
            "from_value", "to_value", "changed_fields", "diff",
            "performed_by", "ip_address", "created_at",
        ]


class StrictBooleanField(serializers.BooleanField):
    """N'accepte que ``true``/``false`` JSON.

    Le champ standard de DRF prend aussi ``"yes"``, ``1`` ou ``"faux"`` ;
    pour une politique de contrôle, un réglage doit être ce qu'il paraît.
    """

    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


class SeuilField(serializers.IntegerField):
    """Entier positif ou nul, jamais un booléen.

    ``True`` est un entier pour Python : sans ce garde-fou, ``[true, 90]``
    passerait pour ``[1, 90]``.
    """

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        return super().to_internal_value(data)


class WorkflowConfigurationSerializer(serializers.ModelSerializer):
    """Modification partielle de la politique du circuit.

    Un paramètre inconnu est refusé plutôt qu'ignoré : un nom mal orthographié
    donnerait sinon l'impression qu'un réglage a été appliqué.
    """

    require_review_step = StrictBooleanField()
    warn_without_proof_submission = StrictBooleanField()
    unjustified_alert_days = SeuilField(min_value=0)
    alert_thresholds = serializers.ListField(child=SeuilField(min_value=0))
    unusual_expense_factor = serializers.DecimalField(
        max_digits=8, decimal_places=2, coerce_to_string=True
    )
    default_overrun_policy_display = serializers.CharField(
        source="get_default_overrun_policy_display", read_only=True
    )

    class Meta:
        model = WorkflowConfiguration
        fields = [
            "require_review_step",
            "unjustified_alert_days",
            "alert_thresholds",
            "unusual_expense_factor",
            "default_overrun_policy",
            "default_overrun_policy_display",
            "warn_without_proof_submission",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            raise serializers.ValidationError("Un objet est attendu.")
        inconnus = set(data) - {
            name for name, field in self.fields.items() if not field.read_only
        }
        if inconnus:
            raise serializers.ValidationError(
                {name: "Paramètre inconnu." for name in sorted(inconnus)}
            )
        return super().to_internal_value(data)

    def validate_unusual_expense_factor(self, value):
        # DRF refuse déjà ``NaN`` et l'infini ; reste le signe.
        if not value.is_finite() or value <= Decimal("0"):
            raise serializers.ValidationError(
                "Un facteur strictement positif est attendu."
            )
        return value