"""Sérialiseurs de l'API de gestion des pays et organisations."""

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
    WorkflowConfiguration,
)


# ---------------------------------------------------------------------------
# Champs JSON typés pour le schéma
# ---------------------------------------------------------------------------
# Un ``JSONField`` est « n'importe quoi » pour OpenAPI, donc ``unknown`` pour
# le frontend, qui devait alors tester ce que le serveur écrit toujours de la
# même façon. Ces sous-classes ne changent rien au rendu — un ``JSONField``
# rend la valeur telle quelle — elles ne portent que la forme.


@extend_schema_field({"type": "array", "items": {"type": "string"}})
class ChampsModifiesField(serializers.JSONField):
    """Noms des champs touchés par un changement."""


@extend_schema_field(
    {
        "type": "object",
        "additionalProperties": {
            "type": "array",
            "items": {},
            "minItems": 2,
            "maxItems": 2,
            "description": "[ancienne valeur, nouvelle valeur]",
        },
    }
)
class DiffField(serializers.JSONField):
    """Par champ : ancienne et nouvelle valeur."""


@extend_schema_field({"type": "object", "additionalProperties": {}})
class DetailField(serializers.JSONField):
    """Détail libre d'une entrée de journal, propre à chaque action."""


def champ_montant(**kwargs):
    """Montant rendu en chaîne décimale, comme partout dans l'API."""
    return serializers.DecimalField(
        max_digits=16, decimal_places=2, coerce_to_string=True, read_only=True, **kwargs
    )


def champ_taux(**kwargs):
    """Taux de change, quatre décimales, absent quand aucun taux ne s'applique."""
    return serializers.DecimalField(
        max_digits=10, decimal_places=4, coerce_to_string=True, read_only=True,
        allow_null=True, **kwargs
    )


class ManagerSerializer(serializers.ModelSerializer):
    """Un responsable, et les pays auxquels il est rattaché.

    **Le rattachement s'écrit ici, et nulle part ailleurs.** Il était un
    champ de ``CountryWriteSerializer`` : inscrire un responsable dans son
    pays exigeait donc ``countries.update``, la capacité qui change aussi la
    devise, le fuseau et l'activation de la filiale — et que le verrou du
    pays refuse au principal intéressé. Les deux actes ne se délèguent pas
    de la même façon ; ils ont chacun leur porte depuis, et la relation un
    seul chemin d'écriture. Le rattachement reste journalisé du côté du
    pays : ``core.signals._track_country_managers`` traite déjà le sens
    inverse (``manager.countries.set(...)``).
    """

    countries = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Country.objects.all(), required=False
    )

    class Meta:
        model = Manager
        fields = [
            "id", "name", "email", "title", "is_active", "countries",
            "created_at", "updated_at",
        ]


class PaysFigeMixin:
    """Une entité du référentiel ne change plus de pays dès qu'on s'y réfère.

    Les lignes, les dossiers, les enveloppes et les profils qui la portent
    sont cloisonnés par **leur** pays : déplacer l'équipe les laisserait
    derrière elle, et une équipe du Togo lirait des lignes ivoiriennes. On
    corrige ce qui la porte d'abord, ou l'on en crée une autre.
    """

    #: Relations inverses qui retiennent l'entité dans son pays.
    RELATIONS_QUI_RETIENNENT = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        country = attrs.get("country")
        if instance is None or country is None or country.pk == instance.country_id:
            return attrs
        if any(
            getattr(instance, relation).exists()
            for relation in self.RELATIONS_QUI_RETIENNENT
        ):
            raise serializers.ValidationError(
                {
                    "country": _(
                        "Des lignes, dossiers, enveloppes ou comptes s'y réfèrent : "
                        "cette entité ne change plus de pays."
                    )
                }
            )
        return attrs


class TeamSerializer(PaysFigeMixin, serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    RELATIONS_QUI_RETIENNENT = ("expenses", "dossiers", "budgets", "profiles")

    class Meta:
        model = Team
        fields = [
            "id", "country", "country_name", "name", "description",
            "is_active", "created_at", "updated_at",
        ]
        # Le message par défaut de la contrainte d'unicité est illisible ;
        # celui-ci dit ce qu'il faut corriger.
        validators = [
            UniqueTogetherValidator(
                queryset=Team.objects.all(),
                fields=["country", "name"],
                message=_("Cette équipe existe déjà pour ce pays."),
            )
        ]


class CostCenterSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = CostCenter
        fields = [
            "id", "country", "country_name", "code", "name",
            "is_active", "created_at", "updated_at",
        ]


class ProjectSerializer(PaysFigeMixin, serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    RELATIONS_QUI_RETIENNENT = ("expenses", "budgets")

    class Meta:
        model = Project
        fields = [
            "id", "country", "country_name", "name", "description",
            "status", "status_display", "budget",
            "is_active", "created_at", "updated_at",
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=Project.objects.all(),
                fields=["country", "name"],
                message=_("Ce projet existe déjà pour ce pays."),
            )
        ]


class ExpenseTitleSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = ExpenseTitle
        fields = [
            "id", "country", "country_name", "label", "description",
            "is_active", "created_at", "updated_at",
        ]


class MarketingCategorySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = MarketingCategory
        fields = [
            "id", "country", "country_name", "name", "description",
            "is_active", "created_at", "updated_at",
        ]


class CountryListSerializer(serializers.ModelSerializer):
    """Représentation compacte pour la liste des pays."""

    managers = ManagerSerializer(many=True, read_only=True)
    team_count = serializers.IntegerField(source="teams.count", read_only=True)
    cost_center_count = serializers.IntegerField(source="cost_centers.count", read_only=True)
    project_count = serializers.IntegerField(source="projects.count", read_only=True)

    class Meta:
        model = Country
        fields = [
            "id", "name", "code", "country_ref", "currency", "currency_symbol",
            "timezone", "is_active", "managers", "team_count",
            "cost_center_count", "project_count", "created_at", "updated_at",
        ]


class CountryDetailSerializer(CountryListSerializer):
    teams = TeamSerializer(many=True, read_only=True)
    cost_centers = CostCenterSerializer(many=True, read_only=True)
    projects = ProjectSerializer(many=True, read_only=True)
    expense_titles = ExpenseTitleSerializer(many=True, read_only=True)
    marketing_categories = MarketingCategorySerializer(many=True, read_only=True)
    expense_title_count = serializers.IntegerField(
        source="expense_titles.count", read_only=True
    )
    marketing_category_count = serializers.IntegerField(
        source="marketing_categories.count", read_only=True
    )

    class Meta(CountryListSerializer.Meta):
        fields = CountryListSerializer.Meta.fields + [
            "teams", "cost_centers", "projects",
            "expense_titles", "marketing_categories",
            "expense_title_count", "marketing_category_count",
        ]


class CountryWriteSerializer(serializers.ModelSerializer):
    """Le pays lui-même. Ses responsables s'écrivent par ``ManagerSerializer``."""

    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Country
        fields = [
            "id", "name", "code", "country_ref", "currency", "currency_symbol",
            "timezone", "is_active",
        ]

    #: Champs qui deviennent intangibles dès que le pays porte de l'argent :
    #: les montants sont stockés dans la devise du pays, et le code le nomme
    #: dans les traces et les exports. Changer l'un ou l'autre ferait lire
    #: 1 000 000 de francs comme 1 000 000 de dirhams, ou attribuerait à un
    #: autre pays ce qui a été déclaré dans celui-ci.
    CHAMPS_FIGES = ("code", "currency")

    def validate_code(self, value):
        """Normalise le code avant de l'enregistrer.

        « ci » et « CI » désignent le même pays ; sans cela, la contrainte
        d'unicité laisserait passer un doublon de casse.
        """
        return value.strip().upper()

    def validate(self, attrs):
        self._verifier_les_champs_figes(attrs)
        return attrs

    def _verifier_les_champs_figes(self, attrs):
        if self.instance is None:
            return
        modifies = [
            name for name in self.CHAMPS_FIGES
            if name in attrs and attrs[name] != getattr(self.instance, name)
        ]
        if not modifies:
            return
        if self.instance.expenses.exists() or self.instance.budgets.exists():
            raise serializers.ValidationError(
                {
                    name: _(
                        "Ce pays porte des dépenses ou des enveloppes : son code "
                        "et sa devise ne se modifient plus."
                    )
                    for name in modifies
                }
            )


class ChangeLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    model_name_display = serializers.CharField(
        source="get_model_name_display", read_only=True
    )
    # Le pays peut être nul (entité sans pays, ou pays supprimé) : sans
    # `allow_null`, DRF omettrait purement et simplement la clé.
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )
    changed_fields = ChampsModifiesField(read_only=True)
    diff = DiffField(read_only=True)

    class Meta:
        model = ChangeLog
        fields = [
            "id", "model_name", "model_name_display", "object_id", "label",
            "action", "action_display", "country", "country_name",
            "from_value", "to_value", "changed_fields", "diff",
            "performed_by", "ip_address", "created_at",
        ]


class StrictBooleanField(serializers.BooleanField):
    """N'accepte que ``true``/``false`` JSON.

    Le champ standard de DRF prend aussi ``"yes"``, ``1`` ou ``"faux"`` ;
    pour une politique de contrôle, un réglage doit être ce qu'il paraît.
    """

    def to_internal_value(self, data):
        if not isinstance(data, bool):
            self.fail("invalid", input=data)
        return data


class SeuilField(serializers.IntegerField):
    """Entier positif ou nul, jamais un booléen.

    ``True`` est un entier pour Python : sans ce garde-fou, ``[true, 90]``
    passerait pour ``[1, 90]``.
    """

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        return super().to_internal_value(data)


class WorkflowConfigurationSerializer(serializers.ModelSerializer):
    """Modification partielle de la politique du circuit.

    Un paramètre inconnu est refusé plutôt qu'ignoré : un nom mal orthographié
    donnerait sinon l'impression qu'un réglage a été appliqué.
    """

    require_review_step = StrictBooleanField()
    warn_without_proof_submission = StrictBooleanField()
    unjustified_alert_days = SeuilField(min_value=0)
    alert_thresholds = serializers.ListField(child=SeuilField(min_value=0))
    unusual_expense_factor = serializers.DecimalField(
        max_digits=8, decimal_places=2, coerce_to_string=True
    )
    default_overrun_policy_display = serializers.CharField(
        source="get_default_overrun_policy_display", read_only=True
    )

    class Meta:
        model = WorkflowConfiguration
        fields = [
            "require_review_step",
            "unjustified_alert_days",
            "alert_thresholds",
            "unusual_expense_factor",
            "default_overrun_policy",
            "default_overrun_policy_display",
            "warn_without_proof_submission",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            raise serializers.ValidationError(_("Un objet est attendu."))
        inconnus = set(data) - {
            name for name, field in self.fields.items() if not field.read_only
        }
        if inconnus:
            raise serializers.ValidationError(
                {name: _("Paramètre inconnu.") for name in sorted(inconnus)}
            )
        return super().to_internal_value(data)

    def validate_unusual_expense_factor(self, value):
        # DRF refuse déjà ``NaN`` et l'infini ; reste le signe.
        if not value.is_finite() or value <= Decimal("0"):
            raise serializers.ValidationError(
                _("Un facteur strictement positif est attendu.")
            )
        return value

# ---------------------------------------------------------------------------
# Formes documentaires (schéma OpenAPI)
# ---------------------------------------------------------------------------
# Ces sérialiseurs ne lisent ni n'écrivent rien : ils décrivent, pour le
# schéma et les types du frontend, des réponses composées à la main par les
# vues (``@extend_schema``).


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[("ok", "ok"), ("indisponible", "indisponible"), ("replique", "replique")],
        read_only=True,
    )
    database = serializers.ChoiceField(choices=[("ok", "ok"), ("ko", "ko")], read_only=True)
    #: La base accepte-t-elle les écritures ? Faux sur une réplique en
    #: attente chaude, dont la base répond parfaitement mais en lecture
    #: seule — c'est ce que le répartiteur de charge regarde pour ne pas y
    #: envoyer de monde (core/views.py).
    writable = serializers.BooleanField(read_only=True)
    #: Nom que la machine se donne (``SERVEUR_NOM``). Absent tant qu'il n'est
    #: pas réglé : derrière un aiguillage, c'est lui qui dit quelle machine a
    #: répondu, et c'est la seule trace d'une bascule vue du dehors.
    machine = serializers.CharField(read_only=True, required=False)


class AvailableCountrySerializer(serializers.Serializer):
    """Pays africain proposé à la création, non encore suivi."""

    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class ConfigurationAlertesSerializer(serializers.Serializer):
    seuils = serializers.ListField(child=serializers.IntegerField(), read_only=True)
    facteur_depense_inhabituelle = serializers.FloatField(read_only=True)


class ConfigurationJustificatifsSerializer(serializers.Serializer):
    taille_max_mo = serializers.IntegerField(read_only=True)
    formats_acceptes = serializers.ListField(child=serializers.CharField(), read_only=True)
    stockage = serializers.CharField(read_only=True)


class ConfigurationBudgetSerializer(serializers.Serializer):
    devise_de_consolidation = serializers.CharField(read_only=True)


class ConfigurationNotificationsSerializer(serializers.Serializer):
    email_actif = serializers.BooleanField(read_only=True)
    email_configure = serializers.BooleanField(read_only=True)
    expediteur = serializers.CharField(read_only=True)


class ConfigurationSystemeSerializer(serializers.Serializer):
    fuseau = serializers.CharField(read_only=True)
    mode_debug = serializers.BooleanField(read_only=True)


class ConfigurationSerializer(serializers.Serializer):
    """Réglages effectifs de la plateforme (``/api/configuration/``)."""

    alertes = ConfigurationAlertesSerializer(read_only=True)
    justificatifs = ConfigurationJustificatifsSerializer(read_only=True)
    budget = ConfigurationBudgetSerializer(read_only=True)
    notifications = ConfigurationNotificationsSerializer(read_only=True)
    systeme = ConfigurationSystemeSerializer(read_only=True)
    workflow = WorkflowConfigurationSerializer(read_only=True)
    supervision = serializers.BooleanField(
        read_only=True,
        help_text=_("Un tableau de bord de supervision (Grafana) est déployé avec cette pile."),
    )
