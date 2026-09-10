"""Accounts domain models: the custom email-based ``User`` and ``LoginHistory``.

RBAC (roles -> permission-name sets) lives in :mod:`apps.accounts.rbac`; the
custom permission base class other apps extend lives in
:mod:`apps.accounts.permissions`.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Manager for a ``User`` that logs in with an email address, not a username."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Application user. Email is the login identifier; there is no username."""

    username = None
    email = models.EmailField(_("email address"), unique=True)
    phone = models.CharField(max_length=32, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email


class OperationalPermission(models.Model):
    """Anchor for Hexagare's action-level permissions (see ``rbac.py``).

    Not a real table. It exists only to give ``ensure_role_groups()`` a
    dedicated ``ContentType`` to hang the operational ``Permission`` rows on,
    keeping them cleanly separate from the model CRUD permissions Django
    auto-creates. The permission strings still resolve as
    ``accounts.<codename>`` because the app label is ``accounts``.
    """

    class Meta:
        managed = False
        default_permissions = ()
        verbose_name = "operational permission"

    def __str__(self) -> str:
        return "operational permissions"


class LoginHistory(models.Model):
    """Append-only record of authentication events, for later audit use (Phase 17)."""

    class Event(models.TextChoices):
        LOGIN_SUCCESS = "login_success", _("Login succeeded")
        LOGIN_FAILED = "login_failed", _("Login failed")
        LOGOUT = "logout", _("Logout")

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_history",
    )
    email_attempted = models.EmailField(blank=True)
    event = models.CharField(max_length=20, choices=Event.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "login history entry"
        verbose_name_plural = "login history"
        indexes = [
            models.Index(fields=["email_attempted", "-created_at"]),
            models.Index(fields=["event", "-created_at"]),
        ]

    def __str__(self) -> str:
        who = self.email_attempted or self.user_id
        return f"{self.event} {who} @ {self.created_at:%Y-%m-%d %H:%M}"
