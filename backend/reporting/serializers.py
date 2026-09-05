"""Formes documentaires du pilotage et des imports (schéma OpenAPI).

Les vues de ``reporting`` composent leurs réponses à la main, à partir
d'agrégats SQL. Ces sérialiseurs ne lisent ni n'écrivent rien : ils décrivent
ces réponses pour ``manage.py spectacular``, donc pour les types du frontend.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.serializers import champ_montant, champ_taux
from notifications.models import Notification


class DashboardTotalsSerializer(serializers.Serializer):
    """Totaux consolidés en FCFA (``totals``)."""

    currency = serializers.CharField(read_only=True)
    allocated = champ_montant()
    engaged = champ_montant()
    consumed = champ_montant()
    justified = champ_montant()
    gap = champ_montant(help_text=_("Dépensé sans preuve à l'appui."))
    remaining = champ_montant()
    execution_rate = champ_taux()
    justification_rate = champ_taux()
    unconverted_currencies = serializers.ListField(
        child=serializers.CharField(), read_only=True,
        help_text=_("Devises sans taux connu, laissées hors des totaux."),
    )


class DashboardCountryRowSerializer(serializers.Serializer):
    country = serializers.IntegerField(read_only=True)
    country_name = serializers.CharField(read_only=True)
    country_ref = serializers.CharField(read_only=True, allow_null=True)
    currency = serializers.CharField(read_only=True)
    allocated = champ_montant()
    sub_allocated = champ_montant()
    engaged = champ_montant()
    consumed = champ_montant()
    justified = champ_montant()
    gap = champ_montant()
    remaining = champ_montant()
    execution_rate = champ_taux()
    justification_rate = champ_taux()
    remaining_xof = champ_montant(allow_null=True)


class ConsolidatedXofSerializer(serializers.Serializer):
    allocated = champ_montant()
    remaining = champ_montant()
    unconverted_currencies = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )


class WorkloadSerializer(serializers.Serializer):
    expenses_to_review = serializers.IntegerField(read_only=True)
    expenses_draft = serializers.IntegerField(read_only=True)
    expenses_unjustified = serializers.IntegerField(read_only=True)
    dossiers_open = serializers.IntegerField(read_only=True)


class AlertSerializer(serializers.Serializer):
    """Alerte calculée à la lecture (``reporting.alerts``)."""

    kind = serializers.ChoiceField(choices=Notification.Kind.choices, read_only=True)
    level = serializers.ChoiceField(choices=Notification.Level.choices, read_only=True)
    title = serializers.CharField(read_only=True)
    detail = serializers.CharField(read_only=True)
    country = serializers.IntegerField(read_only=True, allow_null=True)
    country_name = serializers.CharField(read_only=True, allow_null=True)
    link = serializers.CharField(read_only=True)
    key = serializers.CharField(read_only=True)


class DashboardSerializer(serializers.Serializer):
    year = serializers.IntegerField(read_only=True)
    totals = DashboardTotalsSerializer(read_only=True)
    consolidated_xof = ConsolidatedXofSerializer(read_only=True)
    countries = DashboardCountryRowSerializer(many=True, read_only=True)
    workload = WorkloadSerializer(read_only=True)
    alerts = AlertSerializer(
        many=True, read_only=True,
        help_text=_("Les plus graves seulement ; ``alerts_total`` donne le compte réel."),
    )
    alerts_total = serializers.IntegerField(read_only=True)


class BreakdownRowSerializer(serializers.Serializer):
    label = serializers.CharField(read_only=True)
    amount = champ_montant()
    justified = champ_montant()
    gap = champ_montant()
    lines = serializers.IntegerField(read_only=True)


class BreakdownSerializer(serializers.Serializer):
    year = serializers.IntegerField(read_only=True)
    by_team = BreakdownRowSerializer(many=True, read_only=True)
    by_owner = BreakdownRowSerializer(many=True, read_only=True)
    by_project = BreakdownRowSerializer(many=True, read_only=True)
    by_category = BreakdownRowSerializer(many=True, read_only=True)
    by_expense_title = BreakdownRowSerializer(many=True, read_only=True)
    by_month = BreakdownRowSerializer(many=True, read_only=True)


class ImportSerializer(serializers.Serializer):
    """Classeur à importer, et le pays d'un classeur sans colonne PAYS."""

    file = serializers.FileField()
    country = serializers.IntegerField(required=False)


class ImportErrorSerializer(serializers.Serializer):
    ligne = serializers.IntegerField(read_only=True)
    motif = serializers.CharField(read_only=True)


class ImportResultSerializer(serializers.Serializer):
    dossiers_crees = serializers.IntegerField(read_only=True)
    lignes_creees = serializers.IntegerField(read_only=True)
    equipes_creees = serializers.IntegerField(read_only=True)
    managers_crees = serializers.IntegerField(read_only=True)
    erreurs = ImportErrorSerializer(many=True, read_only=True)
    dry_run = serializers.BooleanField(read_only=True)
