from django.contrib import admin

from .models import AuditLog, Beneficiary, Dossier, Expense, Proof


class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 0
    fields = ("title", "date", "amount", "justified_amount", "status")
    readonly_fields = ("status",)


class ProofInline(admin.TabularInline):
    model = Proof
    fk_name = "dossier"
    extra = 0
    fields = ("original_name", "kind", "status", "version", "sha256")
    readonly_fields = ("original_name", "sha256", "version")


@admin.register(Dossier)
class DossierAdmin(admin.ModelAdmin):
    list_display = ("number", "label", "country", "date", "status")
    list_filter = ("status", "country")
    search_fields = ("number", "label")
    inlines = [ExpenseInline, ProofInline]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "dossier", "country", "date", "amount", "status")
    list_filter = ("status", "country", "payment_method")
    search_fields = ("title", "dossier__number")


@admin.register(Proof)
class ProofAdmin(admin.ModelAdmin):
    list_display = ("original_name", "dossier", "kind", "status", "version")
    list_filter = ("kind", "status", "is_complete")
    readonly_fields = ("sha256", "size", "content_type", "version", "uploaded_by")


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "contact", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "contact")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "object_type", "label")
    list_filter = ("action", "object_type", "country")
    search_fields = ("user", "label")
    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)
