from django.contrib import admin

from .models import Budget, BudgetReallocation, ExchangeRate


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("country", "year", "project", "amount", "overrun_policy", "is_active")
    list_filter = ("year", "country", "overrun_policy", "is_active")
    search_fields = ("country__name", "country__country_ref", "project__name")


@admin.register(BudgetReallocation)
class BudgetReallocationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "target", "amount", "status", "decided_by")
    list_filter = ("status",)
    readonly_fields = ("requested_by", "decided_by", "decided_at")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("currency", "rate_to_xof", "valid_from")
    list_filter = ("currency",)
