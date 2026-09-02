"""Mixins partagés par les vues de l'API."""

from rest_framework import mixins, viewsets


class NoDestroyModelViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD complet **sans suppression physique**.

    Le module repose sur la désactivation (``is_active``) et non sur la
    suppression : effacer un pays supprimerait en cascade ses équipes, centres
    de coûts, projets, intitulés et catégories, sans que le solde budgétaire ni
    l'historique ne puissent être reconstitués. ``destroy`` n'est donc pas
    exposé et ``DELETE`` répond 405.
    """

