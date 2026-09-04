from django.contrib import admin

from .models import Budget, BudgetReallocation, ExchangeRate


class SansSuppressionAdmin(admin.ModelAdmin):
    """Rien ne se supprime : l'administration Django n'y fait pas exception.

    Une enveloppe, un transfert ou un taux effacés depuis l'admin
    disparaîtraient sans passer par l'historique ; le référentiel se
    désactive, il ne se supprime pas.
    """

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Budget)
class BudgetAdmin(SansSuppressionAdmin):
    list_display = ("country", "year", "project", "amount", "overrun_policy", "is_active")
    list_filter = ("year", "country", "overrun_policy", "is_active")
    search_fields = ("country__name", "country__country_ref", "project__name")


@admin.register(BudgetReallocation)
class BudgetReallocationAdmin(SansSuppressionAdmin):
    list_display = ("created_at", "source", "target", "amount", "status", "decided_by")
    list_filter = ("status",)
    # La décision se prend par l'API, sous verrou et avec transfert des
    # montants : la modifier à la main ici approuverait sans rien transférer.
    readonly_fields = ("requested_by", "status", "decided_by", "decided_at")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(SansSuppressionAdmin):
    list_display = ("currency", "rate_to_xof", "valid_from")
    list_filter = ("currency",)
