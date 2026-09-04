from django.contrib import admin

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


class SansSuppressionAdmin(admin.ModelAdmin):
    """Rien ne se supprime : le retrait d'une entité est une désactivation.

    L'admin Django est un chemin d'écriture comme un autre ; sans ce verrou,
    un pays effacé ici emporterait en cascade ses équipes, ses centres de
    coûts et ses projets, que l'API refuse pourtant de supprimer.
    """

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Country)
class CountryAdmin(SansSuppressionAdmin):
    list_display = ("name", "code", "currency", "timezone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    filter_horizontal = ("managers",)


@admin.register(Manager)
class ManagerAdmin(SansSuppressionAdmin):
    list_display = ("name", "email", "title", "is_active")
    search_fields = ("name", "email")


@admin.register(Team)
class TeamAdmin(SansSuppressionAdmin):
    list_display = ("name", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(CostCenter)
class CostCenterAdmin(SansSuppressionAdmin):
    list_display = ("code", "name", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(Project)
class ProjectAdmin(SansSuppressionAdmin):
    list_display = ("name", "country", "status", "is_active")
    list_filter = ("country", "status", "is_active")


@admin.register(ExpenseTitle)
class ExpenseTitleAdmin(SansSuppressionAdmin):
    list_display = ("label", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(MarketingCategory)
class MarketingCategoryAdmin(SansSuppressionAdmin):
    list_display = ("name", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(ChangeLog)
class ChangeLogAdmin(SansSuppressionAdmin):
    """Le journal se lit ; il ne s'écrit ni ne s'efface à la main."""

    list_display = (
        "created_at", "label", "action", "country", "performed_by", "ip_address",
    )
    list_filter = ("action", "model_name", "country")
    search_fields = ("label", "performed_by")
    readonly_fields = (
        "model_name", "object_id", "label", "action", "country",
        "from_value", "to_value", "changed_fields", "diff", "performed_by",
        "ip_address", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WorkflowConfiguration)
class WorkflowConfigurationAdmin(SansSuppressionAdmin):
    """Le singleton se modifie via le back-office, sans suppression."""

    list_display = (
        "require_review_step",
        "unjustified_alert_days",
        "default_overrun_policy",
        "updated_at",
    )
