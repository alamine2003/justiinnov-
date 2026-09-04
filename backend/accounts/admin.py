from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "must_change_password")
    list_filter = ("role", "must_change_password")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    filter_horizontal = ("countries", "teams")
    autocomplete_fields = ("manager",)

    def has_delete_permission(self, request, obj=None):
        # Un profil supprimé laisserait un compte sans rôle, et ses actions
        # passées sans auteur identifiable : on désactive le compte.
        return False
