from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "language", "must_change_password", "totp_confirmed_at")
    list_filter = ("role", "language", "must_change_password")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    filter_horizontal = ("countries", "teams")
    autocomplete_fields = ("manager",)
    # Le secret ne s'affiche ni ne se saisit : il ne sort qu'une fois, dans
    # le QR d'enrôlement, vers le titulaire. L'admin ne peut que le lire
    # comme « présent » via la date de confirmation.
    exclude = ("totp_secret",)
    readonly_fields = ("totp_confirmed_at",)

    def has_delete_permission(self, request, obj=None):
        # Un profil supprimé laisserait un compte sans rôle, et ses actions
        # passées sans auteur identifiable : on désactive le compte.
        return False
