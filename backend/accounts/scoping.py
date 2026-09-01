"""Cloisonnement par pays.

Un représentant pays ne doit voir ni modifier les données d'un autre pays, y
compris par appel direct à l'API. Le filtrage est appliqué au *queryset* — un
objet hors périmètre répond donc 404, sans révéler son existence — et les
écritures sont revalidées, pour qu'on ne puisse pas déplacer une entité vers un
pays auquel on n'a pas droit.
"""

from rest_framework.exceptions import PermissionDenied

from .permissions import get_access


class CountryScopedMixin:
    """Restreint lectures et écritures au périmètre du profil.

    ``country_lookup`` est le chemin ORM menant au pays depuis le modèle de la
    vue ; ``country_field`` le champ du sérialiseur qui le porte (``None`` si
    le modèle n'en a pas, comme ``Manager``).
    """

    country_lookup = "country"
    country_field = "country"

    def get_queryset(self):
        queryset = super().get_queryset()
        access = get_access(self.request.user)
        if access is None:
            return queryset.none()
        if access.has_global_scope:
            return queryset
        return queryset.filter(
            **{f"{self.country_lookup}__in": access.country_ids}
        ).distinct()

    def _check_country_scope(self, serializer):
        """Interdit d'affecter une entité à un pays hors périmètre."""
        if self.country_field is None:
            return
        access = get_access(self.request.user)
        if access is None or access.has_global_scope:
            return
        country = serializer.validated_data.get(self.country_field)
        if country is None:
            # Absent de la charge utile : l'instance visée est déjà filtrée par
            # ``get_queryset``, elle est donc dans le périmètre.
            return
        if country.pk not in access.country_ids:
            raise PermissionDenied("Ce pays n'est pas dans votre périmètre.")

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        super().perform_update(serializer)
