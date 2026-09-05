"""Sérialiseurs des dossiers, dépenses et justificatifs."""

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from accounts.perimetre import ChampCloisonne
from accounts.permissions import get_access, roles_pour
from budget.aggregates import convert
from core.models import Country, Team, WorkflowConfiguration
from core.serializers import DetailField

from .models import AuditLog, Beneficiary, Dossier, Expense, Proof, compute_sha256
from .workflow import (
    LOCKED_STATUSES,
    PROOF_LOCKED_STATUSES,
    PROOF_TRANSITIONS,
    dossier_allowed_actions,
    expense_allowed_actions,
)

#: États d'une pièce après lesquels plus rien ne se modifie.
PROOF_FINAL_STATUSES = frozenset(
    {
        Proof.ProofStatus.VALIDATED,
        Proof.ProofStatus.REJECTED,
        Proof.ProofStatus.ARCHIVED,
    }
)


#: Actions qu'une dépense ou un dossier peut se voir proposer, pour le
#: schéma (``allowed_actions``) : la saisie (modifier, ajouter une ligne,
#: déposer une pièce, supprimer) puis les transitions du circuit.
TRANSITION_CHOICES = [
    (name, name)
    for name in (
        "edit", "add_line", "upload", "delete",
        "submit", "review", "justify", "reject", "close", "reopen",
    )
]


class DossierTotalsSerializer(serializers.Serializer):
    """Totaux d'un dossier, calculés en base (``Dossier.totals``)."""

    amount = serializers.DecimalField(max_digits=16, decimal_places=2, coerce_to_string=True, read_only=True)
    justified = serializers.DecimalField(max_digits=16, decimal_places=2, coerce_to_string=True, read_only=True)
    gap = serializers.DecimalField(max_digits=16, decimal_places=2, coerce_to_string=True, read_only=True)


def _verifier_le_manager(owner, country):
    """Un manager ne porte une dépense que dans un pays où il est rattaché."""
    if owner is None or country is None:
        return
    if not owner.countries.filter(pk=country.pk).exists():
        raise serializers.ValidationError(
            {"owner": _("Ce manager n'est pas rattaché à ce pays.")}
        )


def _acces(serializer):
    """Droits du demandeur, ou ``None`` hors requête."""
    request = serializer.context.get("request")
    return get_access(getattr(request, "user", None)) if request else None


def _demandeur(serializer):
    """Nom du compte qui demande, pour la règle des quatre yeux."""
    request = serializer.context.get("request")
    return getattr(getattr(request, "user", None), "username", "")


def _configuration(serializer):
    """Politique du circuit, lue une fois par requête.

    ``charger`` passe par le cache de la base : la relire pour chaque ligne
    sérialisée coûterait une requête par ligne. Le contexte est partagé par
    le sérialiseur racine et ses sérialiseurs imbriqués, qui en profitent.
    """
    context = serializer.context
    configuration = context.get("workflow_configuration")
    if configuration is None:
        configuration = WorkflowConfiguration.charger()
        context["workflow_configuration"] = configuration
    return configuration


def _exiger_une_equipe_du_perimetre(serializer, team):
    """Un manager rattaché à des équipes déclare toujours dans l'une d'elles.

    Sans équipe, le dossier ou la ligne sortirait de sa propre vue : le
    cloisonnement par équipe ne montre que ce qui porte une de ses équipes,
    et il aurait créé quelque chose qu'il ne peut plus relire. Le champ
    ``team`` ne lui propose déjà que les siennes (``ChampCloisonne``) ; il
    reste à refuser l'absence. Les autres rôles gardent l'équipe facultative
    en brouillon, comme l'import l'exige.
    """
    access = _acces(serializer)
    if access is None or not access.team_ids:
        return
    if team is None or team.pk not in access.team_ids:
        raise serializers.ValidationError(
            {"team": _("Choisissez une de vos équipes.")}
        )


def _equipe_effective(serializer, attrs):
    """Équipe après écriture : celle de la charge utile, sinon celle en place."""
    if "team" in attrs:
        return attrs["team"]
    return getattr(serializer.instance, "team", None)


class BeneficiarySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )

    class Meta:
        model = Beneficiary
        fields = [
            "id", "country", "country_name", "name", "kind", "kind_display",
            "contact", "is_active", "created_at", "updated_at",
        ]
        # Le message par défaut de la contrainte d'unicité est illisible ;
        # celui-ci dit ce qu'il faut corriger.
        validators = [
            UniqueTogetherValidator(
                queryset=Beneficiary.objects.all(),
                fields=["country", "name"],
                message=_("Ce bénéficiaire existe déjà pour ce pays."),
            )
        ]


class ProofSerializer(serializers.ModelSerializer):
    dossier = ChampCloisonne(
        queryset=Dossier.objects.all(), chemin_pays="country", chemin_equipe="team"
    )
    replaces = ChampCloisonne(
        queryset=Proof.objects.all(), chemin_pays="dossier__country",
        chemin_equipe="dossier__team", required=False, allow_null=True,
    )
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()
    allowed_reviews = serializers.SerializerMethodField()

    #: Fixés au dépôt. Une pièce est une preuve : on n'en change ni le
    #: contenu, ni le dossier, ni la filiation — on en dépose une nouvelle
    #: version, qui archive l'ancienne.
    IMMUABLES = ("file", "dossier", "replaces")

    class Meta:
        model = Proof
        fields = [
            "id", "dossier", "file", "original_name", "kind", "kind_display",
            "status", "status_display", "is_complete", "sha256", "size",
            "content_type", "version", "replaces", "uploaded_by",
            "rejection_reason", "download_url", "allowed_reviews",
            "created_at", "updated_at",
        ]
        # ``is_complete`` ne se modifie que par ``review`` : c'est un constat
        # de la direction financière, pas une case que le déposant coche.
        read_only_fields = [
            "original_name", "sha256", "size", "content_type", "version",
            "uploaded_by", "status", "rejection_reason", "is_complete",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    @extend_schema_field(serializers.CharField())
    def get_download_url(self, proof):
        """Le fichier n'est jamais servi directement : le téléchargement passe
        par une vue qui vérifie le périmètre de l'utilisateur."""
        return f"/api/proofs/{proof.pk}/download/"

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(choices=Proof.ProofStatus.choices))
    )
    def get_allowed_reviews(self, proof):
        """États que le demandeur peut donner à la pièce par ``review``.

        Calculés d'après ``PROOF_TRANSITIONS`` et le rôle, pour que
        l'interface ne propose que le possible : rien pour une pièce
        validée, rejetée ou archivée, rien sur un dossier clôturé, rien
        pour qui ne contrôle pas. L'ordre est celui des états du modèle.
        """
        access = _acces(self)
        if access is None or access.role not in roles_pour(
            "proofs.review", _configuration(self)
        ):
            return []
        if proof.dossier.status in PROOF_LOCKED_STATUSES:
            return []
        reachable = PROOF_TRANSITIONS.get(proof.status, frozenset())
        return [value for value, _label in Proof.ProofStatus.choices if value in reachable]

    def validate_file(self, uploaded):
        if uploaded.size > settings.MAX_PROOF_SIZE:
            limit = settings.MAX_PROOF_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                _("Fichier trop volumineux (maximum {limit} Mo).").format(limit=limit)
            )
        extension = Path(uploaded.name).suffix.lower()
        if extension not in settings.ALLOWED_PROOF_EXTENSIONS:
            accepted = ", ".join(settings.ALLOWED_PROOF_EXTENSIONS)
            raise serializers.ValidationError(
                _(
                    "Format non accepté ({extension}). Formats autorisés : "
                    "{accepted}."
                ).format(
                    extension=extension or _("sans extension"), accepted=accepted
                )
            )
        return uploaded

    def validate(self, attrs):
        if self.instance is not None:
            self._verifier_la_mise_a_jour()

        dossier = attrs.get("dossier") or getattr(self.instance, "dossier", None)
        if dossier is not None and dossier.status in PROOF_LOCKED_STATUSES:
            raise serializers.ValidationError(
                _(
                    "Le dossier est clôturé : plus aucun justificatif ne peut y "
                    "être ajouté."
                )
            )

        replaces = attrs.get("replaces")
        if replaces is not None and dossier is not None:
            self.verifier_le_remplacement(replaces, dossier)

        uploaded = attrs.get("file")
        if uploaded is not None:
            attrs["sha256"] = compute_sha256(uploaded)
            attrs["size"] = uploaded.size
            attrs["original_name"] = uploaded.name[:255]
            attrs["content_type"] = getattr(uploaded, "content_type", "") or ""
            self._check_duplicate(dossier, attrs["sha256"], replaces)
        return attrs

    def _verifier_la_mise_a_jour(self):
        """Ce qui reste modifiable sur une pièce déposée : presque rien."""
        if self.instance.status in PROOF_FINAL_STATUSES:
            raise serializers.ValidationError(
                _(
                    "Ce justificatif est {status} : il ne se modifie plus. "
                    "Déposez une nouvelle version s'il doit être corrigé."
                ).format(status=self.instance.get_status_display().lower())
            )
        figes = [champ for champ in self.IMMUABLES if champ in self.initial_data]
        if figes:
            raise serializers.ValidationError(
                {
                    champ: _(
                        "Ce champ est fixé au dépôt : déposez une nouvelle "
                        "version plutôt que de modifier celle-ci."
                    )
                    for champ in figes
                }
            )

    @staticmethod
    def verifier_le_remplacement(replaces, dossier):
        """La pièce remplacée doit appartenir au même dossier.

        Sans ce contrôle, un pays pouvait archiver — via ``replaces`` — une
        pièce d'un dossier qu'il n'a pas le droit de voir : le remplacement
        change le statut de la pièce remplacée. Le message ne distingue pas
        « autre dossier » de « inexistante », pour ne rien révéler.
        """
        if replaces.dossier_id != dossier.pk:
            raise serializers.ValidationError(
                {"replaces": _("Pièce invalide pour ce dossier.")}
            )
        if replaces.status == Proof.ProofStatus.ARCHIVED:
            raise serializers.ValidationError(
                {"replaces": _("Cette pièce a déjà été remplacée.")}
            )

    def _check_duplicate(self, dossier, digest, replaces):
        """Refuse un fichier identique déjà présent sur le même dossier (§5.4).

        Un remplacement explicite reste possible : c'est le seul cas où
        redéposer le même contenu a un sens.
        """
        if dossier is None or replaces is not None:
            return
        existing = Proof.objects.filter(dossier=dossier, sha256=digest)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                {"file": _("Ce fichier est déjà rattaché à ce dossier (doublon).")}
            )


class ExpenseSerializer(serializers.ModelSerializer):
    dossier = ChampCloisonne(
        queryset=Dossier.objects.all(), chemin_pays="country", chemin_equipe="team"
    )
    country = ChampCloisonne(queryset=Country.objects.all(), chemin_pays="pk")
    # Une équipe hors périmètre est, pour le demandeur, une équipe qui
    # n'existe pas : un manager cloisonné ne voit que les siennes.
    team = ChampCloisonne(
        queryset=Team.objects.all(), chemin_pays="country", chemin_equipe="pk",
        required=False, allow_null=True,
    )
    country_name = serializers.CharField(source="country.name", read_only=True)
    currency = serializers.CharField(source="country.currency", read_only=True)
    # §6 : la date est conservée en UTC, mais doit se lire dans le fuseau du
    # pays où la dépense a eu lieu. La direction financière verrait sinon
    # l'heure de son propre fuseau, ce qui fausse le « quand ».
    country_timezone = serializers.CharField(
        source="country.timezone", read_only=True
    )
    dossier_number = serializers.CharField(source="dossier.number", read_only=True)
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )
    owner_name = serializers.CharField(
        source="owner.name", read_only=True, allow_null=True
    )
    project_name = serializers.CharField(
        source="project.name", read_only=True, allow_null=True
    )
    beneficiary_name = serializers.CharField(
        source="beneficiary.name", read_only=True, allow_null=True
    )
    # Un `source="budget.__str__"` renverrait la représentation du
    # method-wrapper de None quand la dépense n'est pas encore imputée.
    budget_label = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    gap = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
        help_text=_("Toujours calculé : dépense − montant justifié."),
    )
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id", "dossier", "dossier_number", "country", "country_name",
            "currency", "country_timezone", "team", "team_name",
            "owner", "owner_name",
            "date", "place", "title", "description",
            "project", "project_name", "expense_title", "marketing_category",
            "beneficiary", "beneficiary_name", "budget", "budget_label",
            "amount", "justified_amount", "gap",
            "original_currency", "original_amount", "original_rate",
            "payment_method", "payment_method_display",
            "status", "status_display", "note", "control_note", "created_by",
            "allowed_actions", "created_at", "updated_at",
        ]
        # Le statut ne se modifie que par les actions de workflow ;
        # l'imputation budgétaire et le taux appliqué sont résolus par le
        # serveur — un taux fourni par le client serait un taux choisi.
        # Le montant justifié appartient au siège : le pays déclare ce qu'il
        # a dépensé, le siège (DF) constate ce qui est prouvé (``justify``).
        # Le laisser saisir revenait à laisser le déclarant se donner quitus.
        read_only_fields = [
            "status", "budget", "created_by", "original_rate",
            "justified_amount", "control_note",
        ]
        extra_kwargs = {
            # Calculé lorsque la dépense est décaissée dans une autre devise.
            "amount": {"required": False},
        }

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_budget_label(self, expense):
        return str(expense.budget) if expense.budget_id else None

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(choices=TRANSITION_CHOICES))
    )
    def get_allowed_actions(self, expense):
        """Transitions que le demandeur peut tenter sur cette ligne.

        Calculées par le serveur (rôle, état, étape de contrôle, quatre
        yeux) : l'interface les affiche, elle ne recopie pas les règles.
        Vide hors requête. Voir ``workflow.expense_allowed_actions``.
        """
        access = _acces(self)
        if access is None:
            return []
        return expense_allowed_actions(
            expense,
            role=access.role,
            username=_demandeur(self),
            configuration=_configuration(self),
        )

    def validate(self, attrs):
        if self.instance is not None and self.instance.status in LOCKED_STATUSES:
            raise serializers.ValidationError(
                _(
                    "Cette dépense est déclarée : elle ne peut plus être "
                    "modifiée. Seul un brouillon reste modifiable."
                )
            )

        dossier = attrs.get("dossier") or getattr(self.instance, "dossier", None)
        country = attrs.get("country") or getattr(self.instance, "country", None)
        if dossier is not None and country is not None and dossier.country_id != country.pk:
            raise serializers.ValidationError(
                {"dossier": _("Le dossier appartient à un autre pays.")}
            )
        for field in (
            "team", "project", "expense_title", "marketing_category", "beneficiary",
        ):
            value = attrs.get(field)
            if value is not None and country is not None and value.country_id != country.pk:
                raise serializers.ValidationError(
                    {field: _("Cette entité appartient à un autre pays.")}
                )
        team = _equipe_effective(self, attrs)
        if (
            dossier is not None
            and team is not None
            and dossier.team_id is not None
            and team.pk != dossier.team_id
        ):
            # Le dossier est lu par l'équipe qu'il porte : une ligne d'une
            # autre équipe y serait visible par la première et invisible
            # pour la seconde. Une ligne sans équipe reste possible en
            # brouillon, la soumission l'exigera.
            raise serializers.ValidationError(
                {
                    "team": _(
                        "Cette ligne doit porter l'équipe de son dossier ({team})."
                    ).format(team=dossier.team.name)
                }
            )
        _exiger_une_equipe_du_perimetre(self, team)
        _verifier_le_manager(attrs.get("owner"), country)

        self._resoudre_la_devise(attrs, country)
        return attrs

    def _resoudre_la_devise(self, attrs, country):
        """Convertit un décaissement fait dans une autre devise (§5.3).

        Une mission au Togo peut payer un hôtel en euros : la pièce porte
        120 EUR. Le montant d'origine est conservé pour que le siège
        retrouve le chiffre du justificatif, et ``amount`` reçoit sa
        conversion dans la devise du pays — c'est elle qui pèse sur
        l'enveloppe, et c'est elle qui garde les agrégats monodevise.

        Le taux est celui du jour de la dépense, figé à la saisie : un
        rapport tiré l'an prochain doit donner le même chiffre
        qu'aujourd'hui.
        """
        if self.partial and not (
            "original_currency" in self.initial_data
            or "original_amount" in self.initial_data
        ):
            # Une modification qui ne touche pas au décaissement d'origine le
            # laisse intact : un PATCH du libellé effaçait la devise.
            if getattr(self.instance, "original_currency", "") and "amount" in attrs:
                raise serializers.ValidationError(
                    {
                        "amount": _(
                            "Cette dépense a été décaissée en {currency} : son "
                            "montant se calcule à partir du montant décaissé. "
                            "Modifiez celui-ci plutôt que la conversion."
                        ).format(currency=self.instance.original_currency)
                    }
                )
            return

        # En modification partielle, le champ absent garde sa valeur : ne
        # corriger que le montant décaissé ne doit pas faire perdre la devise.
        courant = self.instance if self.partial else None
        devise = attrs.get(
            "original_currency", getattr(courant, "original_currency", None)
        )
        montant = attrs.get(
            "original_amount", getattr(courant, "original_amount", None)
        )
        if devise is not None:
            devise = devise.strip().upper()
            attrs["original_currency"] = devise

        if not devise or montant is None:
            # Dépense dans la devise du pays : rien à convertir, et rien à
            # conserver qui ferait croire à un décaissement étranger.
            if not devise and montant is None:
                attrs["original_currency"] = ""
                attrs["original_amount"] = None
                attrs["original_rate"] = None
            if attrs.get("amount") is None and self.instance is None:
                raise serializers.ValidationError(
                    {"amount": _("Le montant de la dépense est requis.")}
                )
            if devise or montant is not None:
                raise serializers.ValidationError(
                    {
                        "original_currency": _(
                            "Indiquez à la fois la devise et le montant "
                            "décaissés, ou aucun des deux."
                        )
                    }
                )
            return

        if country is None:
            return

        if devise == country.currency:
            # Même devise : la conversion serait l'identité, et conserver un
            # « montant d'origine » laisserait croire à un décaissement
            # étranger.
            attrs["amount"] = montant
            attrs["original_currency"] = ""
            attrs["original_amount"] = None
            attrs["original_rate"] = None
            return

        date = attrs.get("date") or getattr(self.instance, "date", None)
        converti, taux = convert(
            montant, devise, country.currency, date.date() if date else None
        )
        if converti is None:
            raise serializers.ValidationError(
                {
                    "original_currency": _(
                        "Aucun taux connu pour convertir {source} en {target} "
                        "à cette date. Publiez-le dans Configuration › Taux "
                        "de change."
                    ).format(source=devise, target=country.currency)
                }
            )
        attrs["amount"] = converti
        attrs["original_rate"] = taux


class ExpenseProofSerializer(serializers.ModelSerializer):
    """Pièce vue depuis une dépense : de quoi juger sans ouvrir le dossier."""

    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Proof
        fields = [
            "id", "original_name", "kind", "kind_display",
            "status", "status_display", "is_complete", "sha256", "version",
        ]


class ExpenseRegisterSerializer(ExpenseSerializer):
    """Registre de justification : la dépense et ses preuves d'un seul tenant.

    Répond à la question que l'application existe pour trancher — on vous a
    confié un budget, qu'avez-vous dépensé, et qu'est-ce qui l'atteste ? Aucun
    détail de la dépense n'est écarté.
    """

    proofs = ExpenseProofSerializer(
        source="dossier.proofs", many=True, read_only=True
    )
    dossier_label = serializers.CharField(source="dossier.label", read_only=True)
    expense_title_label = serializers.CharField(
        source="expense_title.label", read_only=True, allow_null=True
    )
    marketing_category_name = serializers.CharField(
        source="marketing_category.name", read_only=True, allow_null=True
    )
    has_proof = serializers.SerializerMethodField()

    class Meta(ExpenseSerializer.Meta):
        fields = ExpenseSerializer.Meta.fields + [
            "dossier_label", "expense_title_label", "marketing_category_name",
            "proofs", "has_proof",
        ]

    @extend_schema_field(serializers.BooleanField())
    def get_has_proof(self, expense):
        """Une pièce rejetée ou archivée ne prouve rien."""
        return any(
            proof.status
            not in (Proof.ProofStatus.REJECTED, Proof.ProofStatus.ARCHIVED)
            for proof in expense.dossier.proofs.all()
        )


class DossierSerializer(serializers.ModelSerializer):
    country = ChampCloisonne(queryset=Country.objects.all(), chemin_pays="pk")
    team = ChampCloisonne(
        queryset=Team.objects.all(), chemin_pays="country", chemin_equipe="pk",
        required=False, allow_null=True,
    )
    country_name = serializers.CharField(source="country.name", read_only=True)
    country_ref = serializers.CharField(
        source="country.country_ref", read_only=True, allow_null=True
    )
    currency = serializers.CharField(source="country.currency", read_only=True)
    country_timezone = serializers.CharField(
        source="country.timezone", read_only=True
    )
    team_name = serializers.CharField(
        source="team.name", read_only=True, allow_null=True
    )
    owner_name = serializers.CharField(
        source="owner.name", read_only=True, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    totals = serializers.SerializerMethodField()
    expense_count = serializers.SerializerMethodField()
    proof_count = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Dossier
        fields = [
            "id", "number", "label", "country", "country_name", "country_ref",
            "currency", "country_timezone", "team", "team_name",
            "owner", "owner_name", "date",
            "status", "status_display", "note", "reopen_note", "totals",
            "expense_count", "proof_count", "allowed_actions", "created_by",
            "created_at", "updated_at",
        ]
        # Le motif de réouverture est posé par l'action ``reopen`` seule.
        read_only_fields = ["status", "created_by", "reopen_note"]
        # Le N°ORDRE est unique **par pays**. Le pays de la charge utile est
        # déjà limité au périmètre du demandeur (``ChampCloisonne``) : la
        # vérification ne porte donc que sur des dossiers qu'il a le droit
        # de voir, et le message ne révèle rien du voisin.
        validators = [
            UniqueTogetherValidator(
                queryset=Dossier.objects.all(),
                fields=["country", "number"],
                message=_("Ce N°ORDRE existe déjà pour ce pays."),
            )
        ]

    @extend_schema_field(DossierTotalsSerializer)
    def get_totals(self, dossier):
        return {key: str(value) for key, value in dossier.totals().items()}

    @extend_schema_field(serializers.IntegerField())
    def get_expense_count(self, dossier):
        return dossier.counts()["expenses"]

    @extend_schema_field(serializers.IntegerField())
    def get_proof_count(self, dossier):
        return dossier.counts()["proofs"]

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(choices=TRANSITION_CHOICES))
    )
    def get_allowed_actions(self, dossier):
        """Transitions que le demandeur peut tenter sur ce dossier.

        Rôle, état, étape de contrôle, quatre yeux, lignes tranchées et
        pièces exploitables : tout est jugé ici, sur les compteurs annotés
        par la liste. Voir ``workflow.dossier_allowed_actions``.
        """
        access = _acces(self)
        if access is None:
            return []
        return dossier_allowed_actions(
            dossier,
            role=access.role,
            username=_demandeur(self),
            configuration=_configuration(self),
        )

    def validate(self, attrs):
        if self.instance is not None and self.instance.status in LOCKED_STATUSES:
            raise serializers.ValidationError(
                _("Ce dossier est déclaré : il ne peut plus être modifié.")
            )
        country = attrs.get("country") or getattr(self.instance, "country", None)
        team = _equipe_effective(self, attrs)
        if team is not None and country is not None and team.country_id != country.pk:
            raise serializers.ValidationError(
                {"team": _("Cette équipe appartient à un autre pays.")}
            )
        if self.instance is not None:
            self._verifier_le_deplacement(attrs)
        _exiger_une_equipe_du_perimetre(self, team)
        _verifier_le_manager(attrs.get("owner"), country)
        return attrs

    def _verifier_le_deplacement(self, attrs):
        """Un dossier qui a un contenu ne change ni de pays ni d'équipe.

        Ses lignes portent le pays et l'équipe en propre (décision n°1) et
        ses pièces sont rangées par pays : déplacer le dossier les laisserait
        derrière lui — ou ferait lire à une équipe des lignes qui ne sont
        pas les siennes. Le choix est de **refuser**, pas de propager : une
        propagation silencieuse réécrirait des lignes que quelqu'un d'autre
        a saisies. On corrige les lignes d'abord, ou on ouvre un autre
        dossier.
        """
        dossier = self.instance
        country = attrs.get("country")
        if country is not None and country.pk != dossier.country_id:
            counts = dossier.counts()
            if counts["expenses"] or counts["proofs"]:
                raise serializers.ValidationError(
                    {
                        "country": _(
                            "Ce dossier porte des lignes ou des pièces : il "
                            "ne change plus de pays. Ouvrez un nouveau dossier."
                        )
                    }
                )
        if "team" not in attrs:
            return
        team_id = None if attrs["team"] is None else attrs["team"].pk
        if team_id == dossier.team_id:
            return
        autres = dossier.expenses.filter(team__isnull=False).select_related("team")
        if team_id is not None:
            autres = autres.exclude(team_id=team_id)
        premiere = autres.first()
        if premiere is None:
            return
        raise serializers.ValidationError(
            {
                "team": _(
                    "{count} ligne(s) de ce dossier portent une autre équipe "
                    "({team}). Corrigez-les avant de changer l'équipe du "
                    "dossier."
                ).format(count=autres.count(), team=premiere.team.name)
            }
        )


class DossierDetailSerializer(DossierSerializer):
    expenses = ExpenseSerializer(many=True, read_only=True)
    proofs = ProofSerializer(many=True, read_only=True)

    class Meta(DossierSerializer.Meta):
        fields = DossierSerializer.Meta.fields + ["expenses", "proofs"]


class TransitionSerializer(serializers.Serializer):
    """Motif accompagnant une transition ; obligatoire pour un rejet (§5.5)
    et pour une réouverture."""

    note = serializers.CharField(required=False, allow_blank=True)


class TransitionWarningMixin(serializers.Serializer):
    """Avertissement qu'une transition peut joindre à la réponse.

    Dépassement d'enveloppe toléré, dossier soumis sans pièce : l'action
    passe, le message l'accompagne. Absent quand il n'y a rien à dire.
    """

    warning = serializers.CharField(read_only=True, required=False)


class ExpenseTransitionSerializer(TransitionSerializer):
    """Transition d'une ligne : le siège (DF) peut fixer ce qui est prouvé.

    Par défaut, justifier couvre toute la dépense ; une pièce partielle
    permet d'en constater une partie seulement. La borne haute (le montant
    de la dépense) se vérifie dans la vue, qui connaît la ligne.
    """

    justified_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False,
        min_value=Decimal("0"),
    )


class ProofReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Proof.ProofStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        rejected = attrs["status"] == Proof.ProofStatus.REJECTED
        if rejected and not attrs.get("reason", "").strip():
            raise serializers.ValidationError(
                {"reason": _("Un rejet doit être motivé.")}
            )
        return attrs


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    country_name = serializers.CharField(
        source="country.name", read_only=True, allow_null=True
    )
    detail = DetailField(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "action", "action_display", "object_type", "object_id",
            "label", "country", "country_name", "detail", "ip_address",
            "user_agent", "created_at",
        ]
