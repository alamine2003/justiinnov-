"""Sérialiseurs des comptes et des profils."""

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers

from core.models import Country, Team, WorkflowConfiguration

from .models import DEFAULT_LANGUAGE, Role, UserProfile
from .permissions import capabilities_for
from .validators import valider_email_professionnel


class ScopeCountrySerializer(serializers.ModelSerializer):
    """Pays du périmètre, en représentation compacte."""

    class Meta:
        model = Country
        fields = ["id", "name", "code", "country_ref"]


class ScopeTeamSerializer(serializers.ModelSerializer):
    """Équipe du périmètre d'un manager, en représentation compacte."""

    class Meta:
        model = Team
        fields = ["id", "name", "country"]


def _password_field(**kwargs):
    return serializers.CharField(write_only=True, style={"input_type": "password"}, **kwargs)


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
    totp_confirmed = serializers.SerializerMethodField()
    language = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    workflow = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email",
            "role", "role_display", "countries", "teams", "has_global_scope",
            "must_change_password", "totp_confirmed", "language",
            "permissions", "workflow",
        ]

    def _role(self, user):
        # Sans profil, pas de rôle : les drapeaux Django du compte ne donnent
        # aucun droit sur l'API (cf. ``get_access``).
        profile = getattr(user, "profile", None)
        return profile.role if profile is not None else None

    def get_role(self, user):
        return self._role(user)

    def get_role_display(self, user):
        role = self._role(user)
        # Résolu maintenant, langue de la requête active : un objet paresseux
        # dans ``response.data`` se traduirait à sa lecture, pas à l'envoi.
        return str(Role(role).label) if role else None

    def get_countries(self, user):
        profile = getattr(user, "profile", None)
        if profile is None:
            return []
        return ScopeCountrySerializer(profile.countries.all(), many=True).data

    def get_teams(self, user):
        """Équipes rattachées au profil.

        Pour un manager, ce sont celles auxquelles sa vue est restreinte ;
        vide, il voit tout son pays (cf. ``UserProfile.team_ids``).
        """
        profile = getattr(user, "profile", None)
        if profile is None:
            return []
        return ScopeTeamSerializer(profile.teams.all(), many=True).data

    def get_must_change_password(self, user):
        profile = getattr(user, "profile", None)
        return bool(profile and profile.must_change_password)

    def get_totp_confirmed(self, user):
        profile = getattr(user, "profile", None)
        return bool(profile and profile.totp_confirmed)

    def get_language(self, user):
        profile = getattr(user, "profile", None)
        return profile.language if profile is not None else DEFAULT_LANGUAGE

    def get_has_global_scope(self, user):
        profile = getattr(user, "profile", None)
        return profile is not None and profile.has_global_scope

    def get_permissions(self, user):
        """Droits dérivés du rôle.

        Lus dans la même matrice que celle qui les applique : les recopier ici
        les ferait diverger de la réalité au premier changement.
        """
        return capabilities_for(self._role(user))

    def get_workflow(self, user):
        """Réglages du circuit qui décident de ce que l'interface propose.

        Sans eux, le frontend afficherait « mettre en contrôle » alors que
        le serveur refuserait l'étape, ou l'inverse.
        """
        configuration = WorkflowConfiguration.charger()
        return {"require_review_step": configuration.require_review_step}


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


def aligner_drapeaux(user, role):
    """Aligne l'accès à l'admin Django sur le rôle du profil.

    Le back-office Django est réservé au siège. Sans cet alignement, un super
    administrateur rétrogradé garderait ``is_superuser`` — et donc tous les
    droits sur l'admin — alors que l'API ne lui reconnaît plus rien.
    """
    user.is_staff = role in (Role.SUPER_ADMIN, Role.ADMIN)
    user.is_superuser = role == Role.SUPER_ADMIN


class UserSerializer(serializers.ModelSerializer):
    """Création et mise à jour d'un compte par le siège.

    ``must_change_password`` n'est pas modifiable : il est vrai dès qu'un
    mot de passe a été posé par un tiers, et seul son titulaire l'efface, en
    le remplaçant. Le siège ne peut pas déclarer personnel un mot de passe
    qu'il connaît. ``totp_confirmed`` non plus : seul le titulaire enrôle
    son application, le siège ne peut que réinitialiser (``reset-2fa``).

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
            "role", "countries", "countries_detail", "must_change_password",
            "totp_confirmed", "password",
        ]

    def validate_email(self, value):
        return _validate_email(value)

    def validate_password(self, value):
        return _validate_password(value)

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError(
                {"password": _("Un mot de passe est requis à la création.")}
            )
        return attrs

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
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        countries = profile_data.pop("countries", None)
        password = validated_data.pop("password", None)

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
        return instance
