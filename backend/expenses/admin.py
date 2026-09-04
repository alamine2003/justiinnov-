"""Administration Django des dossiers, dépenses, pièces et du journal.

L'admin est une porte de service : elle ne doit pas permettre ce que l'API
interdit. Rien ne se supprime, les chiffres et les états ne se retouchent
pas à la main, et le journal d'audit se lit sans jamais s'écrire.
"""

from django.contrib import admin

from .models import AuditLog, Beneficiary, Dossier, Expense, Proof


class SansSuppressionMixin:
    """Aucune suppression depuis l'admin, brouillon ou non.

    L'API sait retirer un brouillon en journalisant ce qu'il emporte ;
    l'admin, elle, effacerait sans trace.
    """

    def has_delete_permission(self, request, obj=None):
        return False


class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 0
    can_delete = False
    fields = ("title", "date", "amount", "justified_amount", "status")
    readonly_fields = ("amount", "justified_amount", "status")


class ProofInline(admin.TabularInline):
    model = Proof
    fk_name = "dossier"
    extra = 0
    can_delete = False
    fields = ("original_name", "kind", "status", "version", "sha256")
    readonly_fields = ("original_name", "status", "sha256", "version")


@admin.register(Dossier)
class DossierAdmin(SansSuppressionMixin, admin.ModelAdmin):
    list_display = ("number", "label", "country", "date", "status")
    list_filter = ("status", "country")
    search_fields = ("number", "label")
    readonly_fields = ("status", "created_by")
    inlines = [ExpenseInline, ProofInline]


@admin.register(Expense)
class ExpenseAdmin(SansSuppressionMixin, admin.ModelAdmin):
    list_display = ("title", "dossier", "country", "date", "amount", "status")
    list_filter = ("status", "country", "payment_method")
    search_fields = ("title", "dossier__number")
    # Ce que le circuit fixe ne se corrige pas à la main : le statut vient
    # des transitions, le montant justifié du contrôleur, l'enveloppe de
    # l'imputation, l'auteur de la saisie.
    readonly_fields = (
        "status", "amount", "justified_amount", "budget", "created_by",
        "control_note", "original_rate",
    )


@admin.register(Proof)
class ProofAdmin(SansSuppressionMixin, admin.ModelAdmin):
    list_display = ("original_name", "dossier", "kind", "status", "version")
    list_filter = ("kind", "status", "is_complete")
    readonly_fields = (
        "status", "sha256", "size", "content_type", "version", "uploaded_by",
        "replaces", "is_complete", "rejection_reason",
    )


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "contact", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "contact")


@admin.register(AuditLog)
class AuditLogAdmin(SansSuppressionMixin, admin.ModelAdmin):
    """Le journal se consulte ; il ne s'écrit ni ne se corrige."""

    list_display = ("created_at", "user", "action", "object_type", "label")
    list_filter = ("action", "object_type", "country")
    search_fields = ("user", "label")
    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
