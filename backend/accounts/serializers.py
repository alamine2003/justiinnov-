"""Sérialiseurs des comptes et des profils."""

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.models import Country, Team, WorkflowConfiguration

from .models import DEFAULT_LANGUAGE, Role, UserProfile, aligner_drapeaux
from .permissions import CAPACITES, CAPACITES_PAR_CLE, capacites_du_role
from .validators import valider_email_professionnel


class ScopeCountrySerializer(serializers.ModelSerializer):
    """Pays du périmètre, en représentation compacte.

    Le fuseau et la devise y sont : un compte pays borne ses périodes dans
    l'heure de son pays et lit ses montants dans sa devise, et l'interface
    n'a pas à charger le référentiel entier pour le savoir.
    """

    class Meta:
        model = Country
        fields = ["id", "name", "code", "country_ref", "timezone", "currency"]


class ScopeTeamSerializer(serializers.ModelSerializer):
    """Équipe du périmètre d'un manager, en représentation compacte."""

    class Meta:
        model = Team
        fields = ["id", "name", "country"]


def _password_field(**kwargs):
    return serializers.CharField(write_only=True, style={"input_type": "password"}, **kwargs)


# ---------------------------------------------------------------------------
# Formes documentaires (schéma OpenAPI)
# ---------------------------------------------------------------------------
# Ces sérialiseurs ne lisent ni n'écrivent rien : ils décrivent, pour le
# schéma et les types du frontend, des réponses composées à la main par les
# vues. Ils portent ``read_only`` pour ne figurer qu'en réponse.

#: Droits par capacité, tirés de la matrice : un droit ajouté à
#: ``CAPACITES`` apparaît dans le schéma sans rien recopier.
PermissionsSerializer = type(
    "PermissionsSerializer",
    (serializers.Serializer,),
    {
        capacite.key: serializers.BooleanField(read_only=True, help_text=capacite.description)
        for capacite in CAPACITES
    },
)


class MeWorkflowSerializer(serializers.Serializer):
    """Politique du circuit que l'interface doit connaître."""

    require_review_step = serializers.BooleanField(read_only=True)


class TokenAuthSerializer(serializers.Serializer):
    """Identifiants présentés à ``/api/token-auth/``."""

    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})
    code = serializers.CharField(
        required=False,
        help_text=gettext_lazy(
            "Code de double authentification, exigé dès que le compte est "
            "enrôlé (réponse 400 avec ``totp_required`` sinon)."
        ),
    )


class TokenAuthErrorSerializer(serializers.Serializer):
    """Refus de ``/api/token-auth/`` quand le second facteur manque ou est faux."""

    code = serializers.ListField(child=serializers.CharField(), read_only=True)
    totp_required = serializers.BooleanField(read_only=True)



class TokenSerializer(serializers.Serializer):
    """Jeton d'API remis à la connexion et au changement de mot de passe."""

    token = serializers.CharField(read_only=True)


class TotpEnrolmentSerializer(serializers.Serializer):
    """Secret d'enrôlement, remis une seule fois."""

    otpauth_uri = serializers.CharField(read_only=True)
    qr_png_base64 = serializers.CharField(read_only=True)
    secret = serializers.CharField(read_only=True)


class TotpConfirmedSerializer(serializers.Serializer):
    totp_confirmed = serializers.BooleanField(read_only=True)


class PermissionMatrixRoleSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=Role.choices, read_only=True)
    label = serializers.CharField(read_only=True)
    siege = serializers.BooleanField(read_only=True)
    always_global = serializers.BooleanField(read_only=True)


def _liste_de_roles(**kwargs):
    return serializers.ListField(child=serializers.ChoiceField(choices=Role.choices), **kwargs)


class PermissionMatrixCapabilitySerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True)
    group = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    #: Rôles qui la portent aujourd'hui, verrous appliqués.
    roles = _liste_de_roles(read_only=True)
    #: Rôles par défaut, pour montrer ce qui a été changé et y revenir.
    default_roles = _liste_de_roles(read_only=True)
    #: Rôles qui l'ont toujours et rôles qui ne l'auront jamais : cases figées.
    fixed_roles = _liste_de_roles(read_only=True)
    locked_roles = _liste_de_roles(read_only=True)
    #: Rôles qui peuvent régler cette ligne : la RH, sauf pour l'argent.
    settable_by_roles = _liste_de_roles(read_only=True)


class PermissionMatrixSerializer(serializers.Serializer):
    """Matrice rôle × capacité, telle que ``RolePermission`` l'applique."""

    roles = PermissionMatrixRoleSerializer(many=True, read_only=True)
    capabilities = PermissionMatrixCapabilitySerializer(many=True, read_only=True)
    note = serializers.CharField(read_only=True)


class PermissionMatrixUpdateSerializer(serializers.Serializer):
    """Modification de la matrice : capacité → rôles, verrous vérifiés.

    Une clé inconnue est refusée plutôt qu'ignorée ; une case figée qu'on
    tente de changer aussi, pour que l'appelant sache que rien n'a bougé.
    """

    capabilities = serializers.DictField(child=_liste_de_roles(allow_empty=True))

    def validate_capabilities(self, choix):
        erreurs = {}
        propres = {}
        for cle, roles in choix.items():
            capacite = CAPACITES_PAR_CLE.get(cle)
            if capacite is None:
                erreurs[cle] = _("Capacité inconnue.")
                continue
            roles = set(roles)
            manquants = capacite.fixes - roles
            interdits = roles & (capacite.verrouillees - capacite.fixes)
            if self.context.get("role") not in capacite.reglable_par:
                erreurs[cle] = _("Ce droit se règle par la direction seule.")
            elif manquants:
                erreurs[cle] = _("Ce droit ne se retire pas à : {roles}.").format(
                    roles=", ".join(str(Role(r).label) for r in sorted(manquants))
                )
            elif interdits:
                erreurs[cle] = _("Ce droit ne se donne pas à : {roles}.").format(
                    roles=", ".join(str(Role(r).label) for r in sorted(interdits))
                )
            else:
                propres[cle] = sorted(roles)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return propres


def _validate_password(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return password


def _validate_email(value):
    """Adresse professionnelle, normalisée — même règle que ``seed_users``."""
    try:
        return valider_email_professionnel(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc


class MeSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur connecté, consommé par le frontend.

    Un compte technique d'amorçage peut ne pas avoir de profil : les champs
    sont donc calculés, pour que la réponse garde toujours la même forme.
    """

    role = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    countries = serializers.SerializerMethodField()
    teams = serializers.SerializerMethodField()
    has_global_scope = serializers.SerializerMethodField()
    must_change_password = serializers.SerializerMethodField()
    totp_required = serializers.SerializerMethodField()
    totp_confirmed = serializers.SerializerMethodField()
    language = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    workflow = serializers.SerializerMethodField()
    supervision = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email",
            "role", "role_display", "countries", "teams", "has_global_scope",
            "must_change_password", "totp_required", "totp_confirmed", "language",
            "permissions", "workflow", "supervision",
        ]

    def _role(self, user):
        # Sans profil, pas de rôle : les drapeaux Django du compte ne donnent
        # aucun droit sur l'API (cf. ``get_access``).
        profile = getattr(user, "profile", None)
        return profile.role if profile is not None else None

    @extend_schema_field(serializers.ChoiceField(choices=Role.choices, allow_null=True))
    def get_role(self, user):
        return self._role(user)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_role_display(self, user):
        role = self._role(user)
        # Résolu maintenant, langue de la requête active : un objet paresseux
        # dans ``response.data`` se traduirait à sa lecture, pas à l'envoi.
        return str(Role(role).label) if role else None

    @extend_schema_field(ScopeCountrySerializer(many=True))
    def get_countries(self, user):
        profile = getattr(user, "profile", None)
        if profile is None:
            return []
        return ScopeCountrySerializer(profile.countries.all(), many=True).data

    @extend_schema_field(ScopeTeamSerializer(many=True))
    def get_teams(self, user):
        """Équipes rattachées au profil.

        Pour un manager, ce sont celles auxquelles sa vue est restreinte ;
        vide, il voit tout son pays (cf. ``UserProfile.team_ids``).
        """
        profile = getattr(user, "profile", None)
        if profile is None:
            return []
        return ScopeTeamSerializer(profile.teams.all(), many=True).data

    @extend_schema_field(serializers.BooleanField())
    def get_must_change_password(self, user):
        profile = getattr(user, "profile", None)
        return bool(profile and profile.must_change_password)

    @extend_schema_field(serializers.BooleanField())
    def get_totp_required(self, user):
        """La politique de la plateforme, pas l'état du compte.

        Vrai : un compte non enrôlé est cantonné à l'enrôlement, et
        l'interface doit l'y conduire. Faux : l'enrôlement reste proposé,
        jamais imposé — et ``totp_confirmed`` dit si ce compte-ci l'a fait.
        """
        return bool(settings.TOTP_REQUIRED)

    @extend_schema_field(serializers.BooleanField())
    def get_totp_confirmed(self, user):
        profile = getattr(user, "profile", None)
        return bool(profile and profile.totp_confirmed)

    @extend_schema_field(serializers.ChoiceField(choices=settings.LANGUAGES))
    def get_language(self, user):
        profile = getattr(user, "profile", None)
        return profile.language if profile is not None else DEFAULT_LANGUAGE

    @extend_schema_field(serializers.BooleanField())
    def get_has_global_scope(self, user):
        profile = getattr(user, "profile", None)
        return profile is not None and profile.has_global_scope

    @extend_schema_field(PermissionsSerializer)
    def get_permissions(self, user):
        """Droits dérivés du rôle.

        Lus dans la même matrice que celle qui les applique : les recopier ici
        les ferait diverger de la réalité au premier changement.
        """
        return capacites_du_role(self._role(user))

    @extend_schema_field(MeWorkflowSerializer)
    def get_workflow(self, user):
        """Réglages du circuit qui décident de ce que l'interface propose.

        Sans eux, le frontend afficherait « mettre en contrôle » alors que
        le serveur refuserait l'étape, ou l'inverse.
        """
        configuration = WorkflowConfiguration.charger()
        return {"require_review_step": configuration.require_review_step}

    @extend_schema_field(serializers.BooleanField())
    def get_supervision(self, user):
        """La pile expose-t-elle un tableau de bord de supervision ?

        Réglage de déploiement (``SUPERVISION=1``), pas un droit : le menu du
        compte ne propose « Supervision » que là où Grafana existe.
        """
        return bool(settings.SUPERVISION)


class MePreferencesSerializer(serializers.Serializer):
    """Préférences que le titulaire règle lui-même (``PATCH /api/me/``).

    Seule la langue pour l'instant : le rôle, le périmètre et l'adresse
    e-mail restent du ressort du siège.
    """

    language = serializers.ChoiceField(choices=settings.LANGUAGES)

    def update(self, profile, validated_data):
        profile.language = validated_data["language"]
        profile.save(update_fields=["language", "updated_at"])
        return profile


class ChangePasswordSerializer(serializers.Serializer):
    current_password = _password_field()
    new_password = _password_field()

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError(_("Mot de passe actuel incorrect."))
        return value

    def validate_new_password(self, value):
        return _validate_password(value, user=self.context["request"].user)


class TotpCodeSerializer(serializers.Serializer):
    """Code à six chiffres présenté pour confirmer l'enrôlement."""

    code = serializers.CharField(max_length=16)


class UserSerializer(serializers.ModelSerializer):
    """Création et mise à jour d'un compte par le siège.

    ``username`` se choisit à la création et ne change plus. Toutes les
    identités de la plateforme sont stockées en texte sous ce nom — auteur
    d'une dépense, déposant d'une pièce, signataire d'une entrée de journal —
    et la règle des quatre yeux compare ce nom à celui de qui justifie.
    Renommer un compte romprait ces traces et permettrait, en changeant de
    nom entre la saisie et le constat, de justifier sa propre dépense. Le
    prénom et le nom, eux, restent libres : ils n'identifient rien.

    ``must_change_password`` n'est pas modifiable : il est vrai dès qu'un
    mot de passe a été posé par un tiers, et seul son titulaire l'efface, en
    le remplaçant. Le siège ne peut pas déclarer personnel un mot de passe
    qu'il connaît. ``totp_confirmed`` non plus : seul le titulaire enrôle
    son application, le siège ne peut que réinitialiser (``reset-2fa``).

    ``teams`` restreint la vue d'un manager à ces équipes (cf.
    ``UserProfile.team_ids``) ; chacune doit appartenir à un pays de
    ``countries``, sans quoi le compte verrait une équipe d'un pays qu'il
    n'a pas — ou n'en verrait aucune, sans que rien ne le dise.

    L'adresse e-mail est obligatoire et professionnelle : c'est elle qui
    nomme le compte dans l'application d'authentification, et un compte
    d'entreprise ne se rattache pas à une adresse personnelle.
    """

    email = serializers.EmailField(required=True, allow_blank=False)
    role = serializers.ChoiceField(choices=Role.choices, source="profile.role")
    countries = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Country.objects.all(), source="profile.countries",
        required=False,
    )
    countries_detail = ScopeCountrySerializer(
        source="profile.countries", many=True, read_only=True
    )
    teams = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Team.objects.all(), source="profile.teams",
        required=False,
    )
    teams_detail = ScopeTeamSerializer(
        source="profile.teams", many=True, read_only=True
    )
    must_change_password = serializers.BooleanField(
        source="profile.must_change_password", read_only=True
    )
    totp_confirmed = serializers.BooleanField(
        source="profile.totp_confirmed", read_only=True
    )
    password = _password_field(required=False)

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "is_active",
            "role", "countries", "countries_detail", "teams", "teams_detail",
            "must_change_password", "totp_confirmed", "password",
        ]

    def validate_email(self, value):
        return _validate_email(value)

    def validate_password(self, value):
        return _validate_password(value)

    def validate_username(self, value):
        if self.instance is not None and value != self.instance.username:
            raise serializers.ValidationError(
                _(
                    "Le nom de compte ne se modifie pas : les traces et la "
                    "règle des quatre yeux reposent sur lui. Créez un autre "
                    "compte et désactivez celui-ci."
                )
            )
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError(
                {"password": _("Un mot de passe est requis à la création.")}
            )
        self._verifier_equipes(attrs)
        return attrs

    def _verifier_equipes(self, attrs):
        """Chaque équipe doit appartenir à un pays du périmètre — tel qu'il
        sera après cette écriture, que les pays ou les équipes viennent de
        la charge utile ou soient déjà en base."""
        profile_data = attrs.get("profile", {})
        profil = getattr(self.instance, "profile", None) if self.instance else None
        if "teams" in profile_data:
            teams = profile_data["teams"]
        else:
            teams = list(profil.teams.all()) if profil is not None else []
        if not teams:
            return
        if "countries" in profile_data:
            pays = {c.pk for c in profile_data["countries"]}
        else:
            pays = set(profil.countries.values_list("pk", flat=True)) if profil else set()
        etrangeres = sorted(t.name for t in teams if t.country_id not in pays)
        if etrangeres:
            raise serializers.ValidationError(
                {
                    "teams": _(
                        "Une équipe doit appartenir à un pays du périmètre du "
                        "compte : %(equipes)s."
                    ) % {"equipes": ", ".join(etrangeres)}
                }
            )

    def to_representation(self, instance):
        """Garantit une forme de réponse stable.

        Un compte hérité peut ne pas avoir de profil. DRF traduit alors chaque
        champ traversant ``profile`` par ``null``, y compris les listes : sans
        ces valeurs de repli, l'interface planterait en lisant la longueur
        d'une liste nulle. Seul ``role`` reste à ``null``, ce qui est
        l'information exacte — ce compte n'a pas de rôle.
        """
        data = super().to_representation(instance)
        for key, fallback in (
            ("countries", []),
            ("countries_detail", []),
            ("teams", []),
            ("teams_detail", []),
            ("must_change_password", False),
            ("totp_confirmed", False),
        ):
            if data.get(key) is None:
                data[key] = fallback
        return data

    @transaction.atomic
    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        countries = profile_data.pop("countries", [])
        teams = profile_data.pop("teams", [])
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        aligner_drapeaux(user, profile_data["role"])
        user.save()

        # Le mot de passe vient du siège : il est provisoire par construction.
        profile = UserProfile.objects.create(
            user=user, must_change_password=True, **profile_data
        )
        profile.countries.set(countries)
        profile.teams.set(teams)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        countries = profile_data.pop("countries", None)
        teams = profile_data.pop("teams", None)
        password = validated_data.pop("password", None)
        # Validé identique à l'existant : rien à écrire, et surtout pas à
        # journaliser comme un changement.
        validated_data.pop("username", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        # Le profil déjà chargé sur le compte, pas une seconde copie : la
        # réponse et le journal lisent ``instance.profile`` et doivent voir
        # les valeurs enregistrées, pas celles d'avant.
        profile = getattr(instance, "profile", None)
        if profile is None:
            profile = UserProfile(user=instance, role=Role.MANAGER)
        for field, value in profile_data.items():
            setattr(profile, field, value)
        if password:
            instance.set_password(password)
            # Un mot de passe fixé par un administrateur est provisoire.
            profile.must_change_password = True
        aligner_drapeaux(instance, profile.role)
        instance.save()
        profile.save()
        if countries is not None:
            profile.countries.set(countries)
        if teams is not None:
            profile.teams.set(teams)
        return instance
