from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            "id", "kind", "kind_display", "level", "level_display",
            "title", "body", "link", "country", "country_name",
            "read_at", "created_at",
        ]
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    """Forme documentaire de ``/api/notifications/unread_count/``."""

    unread = serializers.IntegerField(read_only=True)


class MarkedReadSerializer(serializers.Serializer):
    """Forme documentaire de ``/api/notifications/read-all/``."""

    marked = serializers.IntegerField(read_only=True)
