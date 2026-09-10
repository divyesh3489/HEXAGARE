"""Serializers for auth, profile and password management."""

from __future__ import annotations

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .rbac import OPERATIONAL_PERMISSIONS

User = get_user_model()

_PERM_PREFIX = "accounts."


class UserSerializer(serializers.ModelSerializer):
    """Read representation of a user, including resolved roles + permissions."""

    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "is_staff",
            "is_superuser",
            "roles",
            "permissions",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    def get_roles(self, obj) -> list[str]:
        return sorted(group.name for group in obj.groups.all())

    def get_permissions(self, obj) -> list[str]:
        if obj.is_superuser:
            return sorted(OPERATIONAL_PERMISSIONS)
        held = {
            perm[len(_PERM_PREFIX) :]
            for perm in obj.get_all_permissions()
            if perm.startswith(_PERM_PREFIX)
        }
        return sorted(held & set(OPERATIONAL_PERMISSIONS))


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """``TokenObtainPairSerializer`` that also returns the authenticated user."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "email"]
        extra_kwargs = {"email": {"required": False}}

    def validate_email(self, value):
        qs = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self, **kwargs):
        """Return ``(uid, token)`` when the email maps to an active user, else
        ``None``. The view responds identically either way so account existence
        is not leaked."""
        try:
            user = User.objects.get(email__iexact=self.validated_data["email"], is_active=True)
        except User.DoesNotExist:
            return None
        return (
            urlsafe_base64_encode(force_bytes(user.pk)),
            default_token_generator.make_token(user),
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            pk = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=pk)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Invalid reset link."})
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Invalid or expired reset link."})
        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def save(self, **kwargs):
        try:
            RefreshToken(self.validated_data["refresh"]).blacklist()
        except TokenError:
            raise serializers.ValidationError({"refresh": "Invalid or already-expired token."})
