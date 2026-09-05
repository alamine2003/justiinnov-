"""Cloisonnement par pays et, pour un manager, par équipe.

Un représentant pays ne doit voir ni modifier les données d'un autre pays, y
compris par appel direct à l'API. Le filtrage est appliqué au *queryset* — un
objet hors périmètre répond donc 404, sans révéler son existence — et les
écritures sont revalidées, pour qu'on ne puisse pas déplacer une entité vers un
pays auquel on n'a pas droit.

Le manager subit un second cloisonnement, à l'intérieur de son pays : quand
des équipes lui sont rattachées, il ne voit que les leurs (``team_lookup``).
Sans équipe rattachée, il voit tout son pays — voir ``UserProfile.team_ids``.

Un manager cloisonné ne crée rien *sans* équipe : un dossier ou une ligne
sans équipe échapperait à son propre filtre — il ne le reverrait plus — et
resterait invisible à ses collègues, tout en pesant sur l'enveloppe. Cette
exigence est portée par les sérialiseurs des ressources concernées
(``expenses.serializers._exiger_une_equipe_du_perimetre``), pas par ce
mixin : lui revalide seulement qu'une équipe *présente* dans la charge
utile est une des siennes. Les clés étrangères de la charge utile suivent
la même règle par ``accounts.perimetre.ChampCloisonne``.

La règle elle-même — pays, équipes, ``team IS NULL`` — vit dans
``accounts.perimetre.filtrer`` (décision 39) ; ce mixin l'applique aux vues.
"""

from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied

from .perimetre import filtrer
from .permissions import get_access


class CountryScopedMixin:
    """Restreint lectures et écritures au périmètre du profil.

    ``country_lookup`` est le chemin ORM menant au pays depuis le modèle de la
    vue ; ``country_field`` le champ du sérialiseur qui le porte (``None`` si
    le modèle n'en a pas, comme ``Manager``).

    ``team_lookup`` est le chemin ORM menant à l'équipe ; ``None`` (défaut)
    signifie que la ressource n'est pas cloisonnée par équipe. Une vue qui le
    déclare filtre les managers rattachés à des équipes et refuse qu'ils
    écrivent une entité portant un champ ``team`` hors de leurs équipes.
    """

    country_lookup = "country"
    country_field = "country"
    #: Champ dont la valeur *porte* un pays (ex. le dossier d'une preuve),
    #: quand la ressource n'a pas de champ « pays » propre.
    country_via = None
    team_lookup = None
    #: Champ du sérialiseur qui porte l'équipe, revalidé à l'écriture.
    team_field = "team"

    def get_queryset(self):
        return filtrer(
            super().get_queryset(),
            get_access(self.request.user),
            pays=self.country_lookup,
            equipe=self.team_lookup,
            # Un chemin peut traverser une relation multiple (``countries``
            # d'un manager) : sans DISTINCT, l'objet sortirait en double.
            distinct=True,
        )

    def _check_country_scope(self, serializer):
        """Interdit d'affecter une entité à un pays ou à une équipe hors périmètre.

        Indispensable : le champ « pays » d'une charge utile n'est pas limité
        au périmètre du demandeur, contrairement au queryset de lecture. Même
        chose pour l'équipe d'un manager cloisonné. Une équipe *absente* de
        la charge utile n'est pas jugée ici : en modification, c'est celle de
        l'instance, déjà filtrée par le queryset ; en création, c'est au
        sérialiseur de la ressource d'en exiger une.
        """
        access = get_access(self.request.user)
        if access is None:
            return
        if not access.has_global_scope:
            country_id = self._target_country_id(serializer)
            # Absent de la charge utile : l'instance visée est déjà filtrée
            # par ``get_queryset``, elle est donc dans le périmètre.
            if country_id is not None and country_id not in access.country_ids:
                raise PermissionDenied(_("Ce pays n'est pas dans votre périmètre."))
        if self.team_lookup is not None and access.team_ids is not None:
            team_id = self._target_team_id(serializer)
            if team_id is not None and team_id not in access.team_ids:
                raise PermissionDenied(_("Cette équipe n'est pas dans votre périmètre."))

    def _target_country_id(self, serializer):
        data = serializer.validated_data
        if self.country_field is not None:
            country = data.get(self.country_field)
            if country is not None:
                return country.pk
        if self.country_via is not None:
            related = data.get(self.country_via)
            if related is not None:
                return related.country_id
        return None

    def _target_team_id(self, serializer):
        team = serializer.validated_data.get(self.team_field)
        return None if team is None else team.pk

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        super().perform_update(serializer)
