"""Mixins partagés par les vues de l'API."""

from django.db import transaction
from rest_framework import mixins, viewsets


class NoDestroyModelViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD complet **sans suppression physique**, chaque écriture atomique.

    Le module repose sur la désactivation (``is_active``) et non sur la
    suppression : effacer un pays supprimerait en cascade ses équipes, centres
    de coûts, projets, intitulés et catégories, sans que le solde budgétaire ni
    l'historique ne puissent être reconstitués. ``destroy`` n'est donc pas
    exposé et ``DELETE`` répond 405.

    Une création ou une modification et sa trace — ``AuditLog`` écrit par la
    vue, ``ChangeLog`` écrit par les signaux du référentiel — réussissent ou
    échouent **ensemble** : ``create`` et ``update`` tiennent dans une seule
    transaction. Hors transaction, ``serializer.save()`` commitait, puis la
    trace s'écrivait à part : une trace qui échouait laissait la
    modification sans trace, et le ``ChangeLog`` écrit en ``pre_save``
    attestait d'un mouvement que l'écriture suivante pouvait ne jamais
    faire. Le choix est fait ici, à la porte de toutes les vues d'écriture,
    plutôt que par ``ATOMIC_REQUESTS`` : les lectures, les exports en flux
    et les téléchargements n'ont rien à faire dans une transaction.
    """

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        # ``partial_update`` passe par ici.
        return super().update(request, *args, **kwargs)
