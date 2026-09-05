"""Centre de notifications de l'utilisateur connecté."""

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import (
    MarkedReadSerializer,
    NotificationSerializer,
    UnreadCountSerializer,
)


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Notifications du destinataire courant, et lui seul."""

    # Sans requête (génération du schéma), ``get_queryset`` n'a pas de
    # destinataire : le modèle vient de ce queryset vide.
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer
    filterset_fields = ["kind", "level", "country"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        # Le filtrage sur le destinataire est la seule protection nécessaire :
        # une notification appartient à une personne, pas à un pays.
        return Notification.objects.filter(
            recipient=self.request.user
        ).select_related("country")

    @extend_schema(responses=UnreadCountSerializer)
    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({"unread": count})

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(self.get_serializer(notification).data)

    @extend_schema(request=None, responses=MarkedReadSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = self.get_queryset().filter(read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return Response({"marked": updated})
