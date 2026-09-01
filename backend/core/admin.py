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
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "currency", "timezone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    filter_horizontal = ("managers",)


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "title", "is_active")
    search_fields = ("name", "email")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "status", "is_active")
    list_filter = ("country", "status", "is_active")


@admin.register(ExpenseTitle)
class ExpenseTitleAdmin(admin.ModelAdmin):
    list_display = ("label", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(MarketingCategory)
class MarketingCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "is_active")
    list_filter = ("country", "is_active")


@admin.register(ChangeLog)
class ChangeLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "label", "action", "country", "performed_by")
    list_filter = ("action", "model_name", "country")
    readonly_fields = (
        "model_name", "object_id", "label", "action", "country",
        "from_value", "to_value", "changed_fields", "performed_by", "created_at",
    )