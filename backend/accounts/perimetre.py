"""Le périmètre d'un compte, appliqué à un queryset : une seule primitive.

Décision 39. Six endroits appliquaient chacun la règle du cloisonnement —
le mixin des vues, deux champs de sérialiseur, un queryset d'enveloppes, la
restriction des rapports, le choix des destinataires d'une notification —
et chacun pouvait dériver. La règle vit ici, une fois :

- un compte au **périmètre global** (direction, RH, siège sans restriction)
  voit tout ; un compte restreint ne voit que ses pays (``country_ids``) ;
- un **manager rattaché à des équipes** ne voit, dans son pays, que ce qui
  porte une de ses équipes (``team_ids``) ; sans équipe rattachée, il voit
  tout son pays (décision 19). Une entité **sans équipe** (``team IS NULL``)
  lui échappe : c'est la règle en vigueur, et la raison pour laquelle un
  manager cloisonné ne crée rien sans équipe (les sérialiseurs de
  ``expenses`` l'exigent) — une ligne sans équipe sortirait de son
  périmètre à peine créée ;
- les rôles du siège ne sont jamais cloisonnés par équipe.

:func:`filtrer` la lit depuis le compte (« que voit-il ? ») ;
:func:`comptes_couvrant` la lit depuis l'objet (« qui le voit ? »), pour
les notifications. Un test vérifie que les deux répondent la même chose.
:class:`ChampCloisonne` l'applique aux clés étrangères d'une charge utile.
"""

from django.db.models import Q
from rest_framework import serializers

from .models import ALWAYS_GLOBAL_ROLES, HEADQUARTERS_ROLES, Role
from .permissions import get_access


def filtrer(queryset, access, *, pays="country", equipe=None, distinct=False):
    """Ce que ``access`` a le droit de voir dans ``queryset``.

    ``pays`` est le chemin ORM menant au pays (``pk`` pour le pays lui-même,
    ``dossier__country`` pour une pièce) ; ``equipe`` celui menant à
    l'équipe, ou ``None`` quand la ressource n'est pas cloisonnée par équipe
    — une enveloppe se lit par pays entier, même par un manager qui n'en
    voit qu'une partie des lignes. ``distinct`` s'impose quand un chemin
    traverse une relation multiple (``countries``), qui multiplierait les
    lignes ; il est à proscrire sur un queryset agrégé.

    Sans droits (``access`` nul), rien : un compte sans profil ne voit pas
    un objet de plus qu'un anonyme.
    """
    if access is None:
        return queryset.none()
    filtre = {}
    if not access.has_global_scope:
        filtre[f"{pays}__in"] = access.country_ids
    if equipe is not None and access.team_ids is not None:
        filtre[f"{equipe}__in"] = access.team_ids
    if not filtre:
        return queryset
    queryset = queryset.filter(**filtre)
    return queryset.distinct() if distinct else queryset


def comptes_couvrant(users, country, equipe=None):
    """Les comptes de ``users`` dont le périmètre contient ``country``.

    La réciproque de :func:`filtrer`, lue depuis l'objet : rattaché au pays
    — et, pour un manager cloisonné, à ``equipe`` quand la ressource en
    porte une —, ou rôle du siège sans restriction, ou rôle toujours global.
    Les deux conditions sur ``teams`` tiennent dans le même ``filter`` :
    elles portent sur la même jointure, donc « aucune équipe » ou « cette
    équipe », jamais « une autre équipe ».
    """
    dans_le_pays = Q(profile__countries=country)
    if equipe is not None:
        dans_le_pays &= (
            ~Q(profile__role=Role.MANAGER)
            | Q(profile__teams__isnull=True)
            | Q(profile__teams=equipe)
        )
    return users.filter(
        dans_le_pays
        | Q(profile__role__in=HEADQUARTERS_ROLES, profile__countries__isnull=True)
        | Q(profile__role__in=ALWAYS_GLOBAL_ROLES)
    ).distinct()


class ChampCloisonne(serializers.PrimaryKeyRelatedField):
    """Clé étrangère limitée au périmètre du demandeur.

    Sans cela, un responsable pays pouvait sonder l'existence des dossiers du
    voisin : une clé inconnue répondait « invalide », une clé existante mais
    hors périmètre répondait « pays interdit » — et le dossier était trahi.
    Le queryset du champ est filtré comme celui des lectures : une clé hors
    périmètre est, pour le demandeur, une clé qui n'existe pas.

    ``chemin_pays`` mène du modèle visé au pays (``pk`` pour le pays
    lui-même) ; ``chemin_equipe`` mène à l'équipe, pour les ressources qu'un
    manager rattaché à des équipes ne voit qu'en partie — sans lui, il
    pouvait rattacher une ligne au dossier d'une équipe voisine qu'il ne
    peut pourtant pas lire. ``distinct`` suit un chemin multiple.
    """

    def __init__(self, *, chemin_pays, chemin_equipe=None, distinct=False, **kwargs):
        self.chemin_pays = chemin_pays
        self.chemin_equipe = chemin_equipe
        self.distinct = distinct
        super().__init__(**kwargs)

    def get_queryset(self):
        request = self.context.get("request")
        access = get_access(getattr(request, "user", None)) if request else None
        return filtrer(
            super().get_queryset(), access,
            pays=self.chemin_pays, equipe=self.chemin_equipe, distinct=self.distinct,
        )
