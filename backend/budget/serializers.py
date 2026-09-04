"""Sérialiseurs des budgets."""

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import serializers

from accounts.permissions import get_access
from core.models import WorkflowConfiguration

from .aggregates import budget_figures, consumption, current_rates
from .models import Budget, BudgetReallocation, ExchangeRate


class PerimetreMixin:
    """Borne les champs « clé étrangère » au périmètre du demandeur.

    Un responsable pays qui poste l'identifiant d'une enveloppe voisine doit
    recevoir la même réponse que pour un identifiant inexistant : « invalide ».
    Une erreur distincte (« hors périmètre ») lui confirmerait que l'objet
    existe. Le queryset de chaque champ est donc restreint ici, avant toute
    validation métier.
    """

    #: Champ → chemin ORM menant au pays (``None`` : filtrer par ``pk``).
    champs_perimetre = {}

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request is None:
            return fields
        access = get_access(request.user)
        for name, lookup in self.champs_perimetre.items():
            field = fields.get(name)
            if field is None or getattr(field, "queryset", None) is None:
                continue
            if access is None:
                field.queryset = field.queryset.none()
            elif not access.has_global_scope:
                field.queryset = field.queryset.filter(
                    **{f"{lookup}__in": access.country_ids}
                ).distinct()
        return fields


class BudgetSerializer(PerimetreMixin, serializers.ModelSerializer):
    champs_perimetre = {
        "country": "pk",
        "project": "country",
        "team": "country",
        "manager": "countries",
    }
    #: Champs qui deviennent intangibles dès qu'une dépense est imputée : les
    #: déplacer changerait le pays, l'année ou le découpage de dépenses déjà
    #: déclarées, et le disponible cesserait de correspondre à ce qui a été
    #: dépensé. On crée alors une autre enveloppe.
    CHAMPS_FIGES = ("country", "year", "project", "team", "manager")

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
        figures = budget_figures(budget, rates=self._rates())
        return {key: _as_str(value) for key, value in figures.items()}

    def _rates(self):
        """Taux courants, lus une fois par requête.

        La vue les met dans le contexte ; à défaut (sérialiseur instancié
        seul), ils sont chargés une fois et mémorisés sur l'instance — qui
        est partagée par toutes les enveloppes d'une liste.
        """
        rates = self.context.get("rates")
        if rates is None:
            rates = getattr(self, "_rates_cache", None)
            if rates is None:
                rates = self._rates_cache = current_rates()
        return rates

    def validate(self, attrs):
        self._check_figes(attrs)
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
                _(
                    "Une sous-enveloppe ne découpe qu'une dimension à la fois "
                    "(reçu : {received})."
                ).format(received=", ".join(renseignees))
            )

        for name in ("project", "team"):
            value = dimensions[name]
            if value is not None and country is not None and value.country_id != country.pk:
                raise serializers.ValidationError(
                    {name: _("Cette entité doit appartenir au pays de l'enveloppe.")}
                )
        manager = dimensions["manager"]
        if (
            manager is not None
            and country is not None
            and not country.managers.filter(pk=manager.pk).exists()
        ):
            # Un manager n'a pas de pays propre : c'est le pays qui le
            # rattache. Une sous-enveloppe pour un manager étranger au pays
            # ne recevrait jamais aucune dépense.
            raise serializers.ValidationError(
                {"manager": _("Ce manager n'est pas rattaché au pays de l'enveloppe.")}
            )

        if country is not None and year is not None:
            self._check_unique(country, dimensions, year)
        return attrs

    def _check_figes(self, attrs):
        """Refuse de déplacer une enveloppe qui porte déjà des dépenses."""
        if self.instance is None:
            return
        modifies = [
            name for name in self.CHAMPS_FIGES
            if name in attrs and attrs[name] != getattr(self.instance, name)
        ]
        if modifies and self.instance.expenses.exists():
            raise serializers.ValidationError(
                {
                    name: _(
                        "Des dépenses sont imputées à cette enveloppe : son "
                        "pays, son année et son découpage ne se modifient plus."
                    )
                    for name in modifies
                }
            )

    def create(self, validated_data):
        if "overrun_policy" not in self.initial_data:
            validated_data["overrun_policy"] = (
                WorkflowConfiguration.charger().default_overrun_policy
            )
        return super().create(validated_data)

    def _resolve(self, attrs, field):
        """Valeur soumise, ou celle de l'instance lors d'une mise à jour."""
        if field in attrs:
            return attrs[field]
        return getattr(self.instance, field, None)

    LIBELLES = {
        "project": gettext_lazy("ce projet"),
        "team": gettext_lazy("cette équipe"),
        "manager": gettext_lazy("ce manager"),
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
            message = _("Une enveloppe existe déjà pour ce pays et cette année.")
        else:
            message = _(
                "Une sous-enveloppe existe déjà pour {scope} et cette année."
            ).format(scope=self.LIBELLES[portee])
        raise serializers.ValidationError({"non_field_errors": [message]})


def _as_str(value):
    return str(value) if value is not None else None


class BudgetReallocationSerializer(PerimetreMixin, serializers.ModelSerializer):
    champs_perimetre = {"source": "country", "target": "country"}

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
            raise serializers.ValidationError(_("La justification est obligatoire."))
        return value

    def validate(self, attrs):
        source = attrs.get("source")
        target = attrs.get("target")
        if source and target and source.pk == target.pk:
            raise serializers.ValidationError(
                {"target": _("La source et la destination doivent différer.")}
            )
        if source and target and source.country.currency != target.country.currency:
            # Les montants sont stockés dans la devise du pays : transférer
            # 1 000 000 d'une enveloppe en FCFA vers une enveloppe en dirhams
            # créerait de l'argent. Une réallocation change d'enveloppe, pas
            # de devise.
            raise serializers.ValidationError(
                {
                    "target": _(
                        "Les deux enveloppes doivent être dans la même devise "
                        "({source} → {target})."
                    ).format(
                        source=source.country.currency,
                        target=target.country.currency,
                    )
                }
            )
        if source and attrs.get("amount"):
            totals = consumption(source)
            disponible = source.amount - totals["consumed"] - totals["engaged"]
            if attrs["amount"] > disponible:
                # L'argent déjà sorti ou engagé n'est plus transférable : la
                # source doit couvrir ses dépenses après le transfert. La
                # décision revérifie, une dépense pouvant sortir entre-temps.
                raise serializers.ValidationError(
                    {
                        "amount": _(
                            "Le montant dépasse le disponible de l'enveloppe "
                            "source ({available})."
                        ).format(available=disponible)
                    }
                )
        return attrs


class ReallocationDecisionSerializer(serializers.Serializer):
    """Motif accompagnant une décision ; obligatoire en cas de refus (§5.5)."""

    note = serializers.CharField(required=False, allow_blank=True)


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = ["id", "currency", "rate_to_xof", "valid_from", "created_at"]

    def validate_currency(self, value):
        # Un même code saisi en « mad » et « MAD » donnerait deux devises aux
        # yeux de la consolidation, dont une sans taux.
        return value.strip().upper()

    def validate_rate_to_xof(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                _("Le taux doit être strictement positif.")
            )
        return value

    def validate_valid_from(self, value):
        # Le taux « courant » d'une devise est le dernier publié : un taux
        # daté de demain s'appliquerait dès aujourd'hui à la consolidation,
        # avant d'être en vigueur. Publier à l'avance se fait le jour même.
        if value > timezone.localdate():
            raise serializers.ValidationError(
                _("Un taux ne se publie pas pour une date future.")
            )
        return value
