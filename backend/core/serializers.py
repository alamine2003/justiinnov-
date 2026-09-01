"""Sérialiseurs de l'API de gestion des pays et organisations."""

from rest_framework import serializers

from .models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
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
            "from_value", "to_value", "changed_fields",
            "performed_by", "created_at",
        ]