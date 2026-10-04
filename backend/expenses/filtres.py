"""Filtres de lecture du journal d'audit (décision 111)."""

import django_filters
from django.db.models import Q

from .historique import retirees_des_dossiers
from .models import AuditLog, Dossier, Expense, Proof, Rectification


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
