"""Filtres de lecture : journal d'audit (décision 111), liste des dossiers
(décision 117), corbeille (décision 120)."""

from datetime import date

import django_filters
from django import forms
from django.db.models import Q
from django_filters import rest_framework as filtres_de_l_api
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from .historique import retirees_des_dossiers
from .models import AuditLog, Dossier, ElementSupprime, Expense, Proof, Rectification


class AuditLogFilter(django_filters.FilterSet):
    """Par utilisateur, action, objet, pays, période — et par projet."""

    debut = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    fin = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    projet = django_filters.NumberFilter(method="filtrer_par_projet")

    class Meta:
        model = AuditLog
        fields = ["user", "action", "object_type", "country"]

    def filtrer_par_projet(self, queryset, name, value):
        """Ce qui est arrivé aux dossiers du projet, à leurs lignes et à leurs pièces."""
        dossiers = Dossier.objects.filter(project=value).values("pk")
        lignes = Expense.objects.filter(dossier__project=value).values("pk")
        return queryset.filter(
            Q(object_type="Dossier", object_id__in=dossiers)
            | Q(object_type="Expense", object_id__in=lignes)
            | Q(
                object_type="Proof",
                object_id__in=Proof.objects.filter(dossier__project=value).values("pk"),
            )
            | retirees_des_dossiers(dossiers.values_list("pk", flat=True))
            | Q(
                object_type="Rectification",
                object_id__in=Rectification.objects.filter(
                    expense__dossier__project=value
                ).values("pk"),
            )
        )


@extend_schema_field(OpenApiTypes.INT)
class FiltreEntier(django_filters.NumberFilter):
    """Un nombre entier : ``NumberFilter`` lit un décimal, et ``2026.7``
    devenait 2026 sans un mot."""

    field_class = forms.IntegerField


class DossierFilter(filtres_de_l_api.FilterSet):
    """Les filtres de la liste des dossiers, plus ce qu'une tuile du tableau
    de bord compte (décision 117) : ``ouverts`` (tout sauf clôturé, la
    définition de ``DossierQuerySet.ouverts``) et ``exercice``, l'année de
    la date du dossier. ``Dossier.date`` est un jour : les bornes sont
    celles de ``reporting.scope.bornes_periode``, sans fuseau à appliquer.

    Le ``FilterSet`` et le ``BooleanFilter`` sont ceux de DRF, comme ce que
    ``filterset_fields`` générait : leur widget lit ``1``/``0`` autant que
    ``true``/``false`` — le générique ignorait ``?ouverts=1``, la forme de
    l'adresse de l'interface. ``ouverts=false`` ne filtre rien : il rend
    tous les dossiers, clôturés compris. ``exercice`` est un entier : une
    décimale répond 400."""

    ouverts = filtres_de_l_api.BooleanFilter(method="filtrer_les_ouverts")
    exercice = FiltreEntier(method="filtrer_par_exercice")

    class Meta:
        model = Dossier
        fields = [
            "country", "country__country_ref", "status", "team", "owner",
            "project", "project__kind", "kind",
        ]

    def filtrer_les_ouverts(self, queryset, name, value):
        return queryset.ouverts() if value else queryset

    def filtrer_par_exercice(self, queryset, name, value):
        annee = int(value)
        # Une année hors du calendrier ne désigne aucun dossier : une liste
        # vide, pas une erreur 500 sur ``date()``.
        if not date.min.year <= annee <= date.max.year:
            return queryset.none()
        return queryset.filter(date__range=(date(annee, 1, 1), date(annee, 12, 31)))


class ElementSupprimeFilter(filtres_de_l_api.FilterSet):
    """Par nature, pays, période ; les têtes seules, ou ce qu'une tête a emporté."""

    debut = django_filters.DateFilter(field_name="supprime_le", lookup_expr="date__gte")
    fin = django_filters.DateFilter(field_name="supprime_le", lookup_expr="date__lte")
    #: Ce que le super administrateur a choisi de retirer, sans ce qui est
    #: parti avec : la liste de la corbeille se lit ainsi.
    tetes = filtres_de_l_api.BooleanFilter(field_name="racine", lookup_expr="isnull")

    class Meta:
        model = ElementSupprime
        fields = ["nature", "country", "racine"]
