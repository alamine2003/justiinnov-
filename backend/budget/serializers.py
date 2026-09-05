"""Sérialiseurs des budgets."""

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.perimetre import ChampCloisonne
from accounts.permissions import get_access
from core.models import Country, Manager, Project, Team, WorkflowConfiguration
from core.regles import RegleViolee

from .aggregates import budget_figures, current_rates
from .models import Budget, BudgetReallocation, ExchangeRate
from .transitions import exiger_le_disponible, peut_decider


def _montant(**kwargs):
    """Montant rendu en chaîne décimale, comme partout dans l'API."""
    return serializers.DecimalField(
        max_digits=16, decimal_places=2, coerce_to_string=True, read_only=True, **kwargs
    )


def _taux(**kwargs):
    return serializers.DecimalField(
        max_digits=10, decimal_places=4, coerce_to_string=True, read_only=True,
        allow_null=True, **kwargs
    )


class BudgetFiguresSerializer(serializers.Serializer):
    """Indicateurs d'une enveloppe, calculés par ``aggregates.budget_figures``.

    Forme documentaire : la vue rend le dictionnaire tel quel, ce sérialiseur
    ne sert qu'au schéma.
    """

    engaged = _montant(help_text=gettext_lazy("Soumis ou en contrôle : sorti de l'enveloppe, pas encore constaté."))
    consumed = _montant()
    justified = _montant()
    gap = _montant(help_text=gettext_lazy("Consommé sans preuve à l'appui."))
    remaining = _montant()
    execution_rate = _taux()
    justification_rate = _taux()
    amount_xof = _montant(allow_null=True)
    remaining_xof = _montant(allow_null=True)


class CountryBudgetRowSerializer(serializers.Serializer):
    """Ligne de la consolidation par pays (``/api/budgets/summary/``)."""

    country = serializers.IntegerField(read_only=True)
    country_name = serializers.CharField(read_only=True)
    country_ref = serializers.CharField(read_only=True, allow_null=True)
    currency = serializers.CharField(read_only=True)
    allocated = _montant()
    sub_allocated = _montant()
    engaged = _montant()
    consumed = _montant()
    justified = _montant()
    remaining = _montant()
    remaining_xof = _montant(allow_null=True)


class BudgetSummarySerializer(serializers.Serializer):
    countries = CountryBudgetRowSerializer(many=True, read_only=True)
    total_remaining_xof = _montant()
    unconverted_currencies = serializers.ListField(
        child=serializers.CharField(), read_only=True,
        help_text=gettext_lazy("Devises sans taux connu, laissées hors du total."),
    )


#: Dimensions qu'une sous-enveloppe peut découper (``Budget.scope_kind``).
SCOPE_CHOICES = [(kind, kind) for kind in ("country", "project", "team", "manager")]


@extend_schema_field(serializers.ChoiceField(choices=SCOPE_CHOICES))
class ScopeKindField(serializers.CharField):
    """``scope_kind`` est une propriété du modèle : un ``CharField`` en
    lecture seule, dont le schéma dit les quatre valeurs possibles."""


class BudgetSerializer(serializers.ModelSerializer):
    # Clés étrangères bornées au périmètre du demandeur : une enveloppe
    # voisine est « invalide », comme une inexistante, sans rien révéler.
    country = ChampCloisonne(
        queryset=Country.objects.all(), chemin_pays="pk", label=gettext_lazy("Pays")
    )
    project = ChampCloisonne(
        queryset=Project.objects.all(), chemin_pays="country",
        allow_null=True, required=False, label=gettext_lazy("Projet"),
    )
    team = ChampCloisonne(
        queryset=Team.objects.all(), chemin_pays="country",
        allow_null=True, required=False, label=gettext_lazy("Équipe"),
    )
    manager = ChampCloisonne(
        queryset=Manager.objects.all(), chemin_pays="countries", distinct=True,
        allow_null=True, required=False, label=gettext_lazy("Manager"),
    )
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
    scope_kind = ScopeKindField(read_only=True)
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

    @extend_schema_field(BudgetFiguresSerializer)
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


class BudgetReallocationSerializer(serializers.ModelSerializer):
    source = ChampCloisonne(
        queryset=Budget.objects.all(), chemin_pays="country",
        label=gettext_lazy("Enveloppe source"),
    )
    target = ChampCloisonne(
        queryset=Budget.objects.all(), chemin_pays="country",
        label=gettext_lazy("Enveloppe destinataire"),
    )

    source_label = serializers.CharField(source="source.__str__", read_only=True)
    target_label = serializers.CharField(source="target.__str__", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    can_decide = serializers.SerializerMethodField()

    class Meta:
        model = BudgetReallocation
        fields = [
            "id", "source", "source_label", "target", "target_label",
            "amount", "reason", "status", "status_display",
            "requested_by", "decided_by", "decided_at", "decision_note",
            "can_decide", "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "requested_by", "decided_by", "decided_at", "decision_note",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_can_decide(self, reallocation):
        """Le demandeur peut-il approuver ou refuser cette réallocation ?

        Les mêmes conditions que ``approuver`` et ``refuser``
        (``transitions.verifier_la_decision``), pour que l'interface n'ait
        pas à les recopier : réallocation encore en attente, rôle décideur,
        pas celui qui l'a demandée, destination dans le périmètre. Faux
        hors requête.
        """
        request = self.context.get("request")
        access = get_access(getattr(request, "user", None)) if request else None
        return peut_decider(reallocation, access)

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
            # L'argent déjà sorti ou engagé n'est plus transférable : la
            # même règle que le service, qui la rejuge sous verrou à la
            # demande comme à la décision.
            try:
                exiger_le_disponible(source, attrs["amount"])
            except RegleViolee as exc:
                raise serializers.ValidationError({exc.champ: str(exc)}) from exc
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
