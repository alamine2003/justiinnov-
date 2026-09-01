"""Sérialiseurs des comptes et des profils."""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from core.models import Country

from .models import Role, UserProfile
from .permissions import (
    BUDGET_WRITE_ROLES,
    REFERENTIAL_WRITE_ROLES,
    SUBENTITY_WRITE_ROLES,
    USER_WRITE_ROLES,
)


class ScopeCountrySerializer(serializers.ModelSerializer):
    """Pays du périmètre, en représentation compacte."""

    class Meta:
        model = Country
        fields = ["id", "name", "code", "country_ref"]


def _password_field(**kwargs):
    return serializers.CharField(write_only=True, style={"input_type": "password"}, **kwargs)


def _validate_password(password, user=None):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return password


class MeSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur connecté, consommé par le frontend.

    Un compte technique d'amorçage peut ne pas avoir de profil : les champs
    sont donc calculés, pour que la réponse garde toujours la même forme.
    """

    role = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    countries = serializers.SerializerMethodField()
    has_global_scope = serializers.SerializerMethodField()
    must_change_password = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email",
            "role", "role_display", "countries", "has_global_scope",
            "must_change_password", "permissions",
        ]

    def _role(self, user):
        profile = getattr(user, "profile", None)
        if profile is not None:
            return profile.role
        return Role.SUPER_ADMIN if user.is_superuser else None

    def get_role(self, user):
        return self._role(user)

    def get_role_display(self, user):
        role = self._role(user)
        return Role(role).label if role else None

    def get_countries(self, user):
        profile = getattr(user, "profile", None)
        if profile is None:
            return []
        return ScopeCountrySerializer(profile.countries.all(), many=True).data

    def get_must_change_password(self, user):
        profile = getattr(user, "profile", None)
        return bool(profile and profile.must_change_password)

    def get_has_global_scope(self, user):
        profile = getattr(user, "profile", None)
        if profile is None:
            return bool(user.is_superuser)
        return profile.has_global_scope

    def get_permissions(self, user):
        role = self._role(user)
        return {
            "manage_users": role in USER_WRITE_ROLES,
            "manage_countries": role in REFERENTIAL_WRITE_ROLES,
            "manage_subentities": role in SUBENTITY_WRITE_ROLES,
            "manage_budgets": role in BUDGET_WRITE_ROLES,
        }


class ChangePasswordSerializer(serializers.Serializer):
    current_password = _password_field()
    new_password = _password_field()

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        return _validate_password(value, user=self.context["request"].user)


class UserSerializer(serializers.ModelSerializer):
    """Création et mise à jour d'un compte par le siège."""

    role = serializers.ChoiceField(choices=Role.choices, source="profile.role")
    countries = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Country.objects.all(), source="profile.countries",
        required=False,
    )
    countries_detail = ScopeCountrySerializer(
        source="profile.countries", many=True, read_only=True
    )
    must_change_password = serializers.BooleanField(
        source="profile.must_change_password", required=False
    )
    password = _password_field(required=False)

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "email", "is_active",
            "role", "countries", "countries_detail", "must_change_password",
            "password",
        ]

    def validate_password(self, value):
        return _validate_password(value)

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError(
                {"password": "Un mot de passe est requis à la création."}
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
        user.save()

        profile = UserProfile.objects.create(user=user, **profile_data)
        profile.countries.set(countries)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        countries = profile_data.pop("countries", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
            # Un mot de passe fixé par un administrateur est provisoire.
            profile_data.setdefault("must_change_password", True)
        instance.save()

        profile, _ = UserProfile.objects.get_or_create(
            user=instance, defaults={"role": Role.OWNER}
        )
        for field, value in profile_data.items():
            setattr(profile, field, value)
        profile.save()
        if countries is not None:
            profile.countries.set(countries)
        return instance
