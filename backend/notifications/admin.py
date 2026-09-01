from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "kind", "level", "title", "read_at")
    list_filter = ("kind", "level", "country")
    search_fields = ("title", "recipient__username")
    readonly_fields = ("dedup_key", "emailed_at", "created_at")
