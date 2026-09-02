"""Sérialiseurs des budgets."""

from rest_framework import serializers

from .aggregates import budget_figures, to_xof
from .models import Budget, BudgetReallocation, ExchangeRate


class BudgetSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    country_ref = serializers.CharField(source="country.country_ref", read_only=True)
    currency = serializers.CharField(source="country.currency", read_only=True)
    # `allow_null` est indispensable : sans lui, DRF *omet* la clé lorsque le
    # projet est nul (enveloppe de pays) au lieu de renvoyer `null`, et le
    # contrat de l'API devient variable selon les données.
    project_name = serializers.CharField(
        source="project.name", read_only=True, allow_null=True
    )
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )
    manager_name = serializers.CharField(
        source="manager.name", read_only=True, allow_null=True
    )
    scope_kind = serializers.CharField(read_only=True)
    scope_label = serializers.CharField(read_only=True, allow_null=True)
    overrun_policy_display = serializers.CharField(
        source="get_overrun_policy_display", read_only=True
    )
    figures = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id", "country", "country_name", "country_ref", "currency",
            "year", "project", "project_name", "team", "team_name",
            "manager", "manager_name", "scope_kind", "scope_label", "amount",
            "overrun_policy", "overrun_policy_display", "is_active",
            "figures", "created_at", "updated_at",
        ]
        # Les validateurs d'unicité déduits des contraintes rendraient
        # ``project`` obligatoire, alors qu'il est justement absent pour une
        # enveloppe de pays. L'unicité est donc vérifiée explicitement dans
        # ``validate``, avec des messages parlants ; les contraintes en base
        # restent le dernier rempart.
        validators = []

    def get_figures(self, budget):
        """Consommation, écart et disponible — calculés côté serveur."""
        figures = budget_figures(budget)
        return {
            **{key: str(value) if value is not None else None
               for key, value in figures.items()},
            "amount_xof": _as_str(to_xof(budget.amount, budget.country.currency)),
            "remaining_xof": _as_str(
                to_xof(figures["remaining"], budget.country.currency)
            ),
        }

    def validate(self, attrs):
        country = self._resolve(attrs, "country")
        year = self._resolve(attrs, "year")
        dimensions = {
            "project": self._resolve(attrs, "project"),
            "team": self._resolve(attrs, "team"),
            "manager": self._resolve(attrs, "manager"),
        }

        renseignees = [name for name, value in dimensions.items() if value is not None]
        if len(renseignees) > 1:
            raise serializers.ValidationError(
                "Une sous-enveloppe ne découpe qu'une dimension à la fois "
                f"(reçu : {', '.join(renseignees)})."
            )

        for name in ("project", "team"):
            value = dimensions[name]
            if value is not None and country is not None and value.country_id != country.pk:
                raise serializers.ValidationError(
                    {name: "Cette entité doit appartenir au pays de l'enveloppe."}
                )

        if country is not None and year is not None:
            self._check_unique(country, dimensions, year)
        return attrs

    def _resolve(self, attrs, field):
        """Valeur soumise, ou celle de l'instance lors d'une mise à jour."""
        if field in attrs:
            return attrs[field]
        return getattr(self.instance, field, None)

    LIBELLES = {
        "project": "ce projet",
        "team": "cette équipe",
        "manager": "ce manager",
    }

    def _check_unique(self, country, dimensions, year):
        existing = Budget.objects.filter(country=country, year=year, **dimensions)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if not existing.exists():
            return

        portee = next(
            (name for name, value in dimensions.items() if value is not None), None
        )
        if portee is None:
            message = "Une enveloppe existe déjà pour ce pays et cette année."
        else:
            message = (
                f"Une sous-enveloppe existe déjà pour {self.LIBELLES[portee]} "
                "et cette année."
            )
        raise serializers.ValidationError({"non_field_errors": [message]})


def _as_str(value):
    return str(value) if value is not None else None


class BudgetReallocationSerializer(serializers.ModelSerializer):
    source_label = serializers.CharField(source="source.__str__", read_only=True)
    target_label = serializers.CharField(source="target.__str__", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = BudgetReallocation
        fields = [
            "id", "source", "source_label", "target", "target_label",
            "amount", "reason", "status", "status_display",
            "requested_by", "decided_by", "decided_at", "decision_note",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "requested_by", "decided_by", "decided_at", "decision_note",
        ]

    def validate_reason(self, value):
        # §5.2 : une réallocation sans justification n'est pas recevable.
        if not value.strip():
            raise serializers.ValidationError("La justification est obligatoire.")
        return value

    def validate(self, attrs):
        source = attrs.get("source")
        target = attrs.get("target")
        if source and target and source.pk == target.pk:
            raise serializers.ValidationError(
                {"target": "La source et la destination doivent différer."}
            )
        if source and attrs.get("amount") and attrs["amount"] > source.amount:
            raise serializers.ValidationError(
                {"amount": "Le montant dépasse l'enveloppe source."}
            )
        return attrs


class ReallocationDecisionSerializer(serializers.Serializer):
    """Motif accompagnant une décision ; obligatoire en cas de refus (§5.5)."""

    note = serializers.CharField(required=False, allow_blank=True)


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = ["id", "currency", "rate_to_xof", "valid_from", "created_at"]
