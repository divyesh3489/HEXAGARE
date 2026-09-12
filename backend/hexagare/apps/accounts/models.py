"""Accounts domain models: the custom email-based ``User``, ``LoginHistory``,
and (Phase 17, ADR-020) the rest of Hexagare's "Administration" surface --
``BusinessSettings``, ``AuditLogEntry`` and ``BackupJob`` -- kept here rather
than a new app because they map 1:1 onto the Administration permissions
(``settings.manage``/``users.manage``/``audit.view``) this app already owns.

RBAC (roles -> permission-name sets) lives in :mod:`apps.accounts.rbac`; the
custom permission base class other apps extend lives in
:mod:`apps.accounts.permissions`.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
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


class BusinessSettings(models.Model):
    """Singleton (``pk=1``) editable business/tax/numbering configuration.

    Every field is blank/``None`` by default and *overrides* the matching
    ``HEXAGARE_*`` env-backed Django setting only when actually filled in --
    ``apps.products.services.{serial_numbers,sku}`` and
    ``apps.billing.services.numbering`` consult :meth:`get_solo` first and
    fall back to ``django.conf.settings`` unchanged. This keeps
    ``@override_settings(HEXAGARE_SKU_PREFIX=...)``-style tests working: a
    freshly bootstrapped row never shadows the env default.
    """

    business_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=20, blank=True)
    logo = models.ImageField(upload_to="settings/", blank=True, null=True)

    currency = models.CharField(max_length=8, default="INR")
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Pre-filled as the default GST rate (%) on a new product; not enforced.",
    )

    sku_prefix = models.CharField(
        max_length=16, blank=True, help_text="Blank falls back to HEXAGARE_SKU_PREFIX."
    )
    serial_prefix = models.CharField(
        max_length=16, blank=True, help_text="Blank falls back to HEXAGARE_SERIAL_PREFIX."
    )
    serial_padding = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Blank falls back to HEXAGARE_SERIAL_PADDING."
    )
    invoice_prefix = models.CharField(
        max_length=16, blank=True, help_text="Blank falls back to HEXAGARE_INVOICE_PREFIX."
    )
    invoice_padding = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Blank falls back to HEXAGARE_INVOICE_PADDING."
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "business settings"
        verbose_name_plural = "business settings"

    def __str__(self) -> str:
        return self.business_name or "Business settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("BusinessSettings is a singleton and cannot be deleted.")

    @classmethod
    def get_solo(cls) -> BusinessSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AuditLogEntry(models.Model):
    """Append-only record of a tracked business action (HEXAGARE_FEATURES.md
    section 53's "Activity Log" list).

    Written by :func:`apps.accounts.audit.log_activity`, called either from a
    shared ``AuditMixin`` on a simple CRUD viewset or explicitly from the one
    canonical service method that already owns a given mutation (Hexagare's
    single-writer-per-concern architecture means there are only a handful of
    these call sites, not one per view). ``target`` is a generic FK so one
    model covers every tracked resource without a table per domain.
    """

    class Action(models.TextChoices):
        PRODUCT_CREATED = "product.created", _("Product created")
        PRODUCT_UPDATED = "product.updated", _("Product/variant/SKU/price updated")
        PRODUCT_DELETED = "product.deleted", _("Product deleted")
        SERIAL_CREATED = "serial.created", _("Serial number / unit created")
        BARCODE_GENERATED = "barcode.generated", _("Barcode / label batch generated")
        STOCK_CHANGED = "stock.changed", _("Stock adjusted")
        STATUS_CHANGED = "status.changed", _("Unit status changed")
        LOCATION_CREATED = "location.created", _("Location created")
        LOCATION_UPDATED = "location.updated", _("Location updated")
        LOCATION_DELETED = "location.deleted", _("Location deleted")
        INVOICE_CREATED = "invoice.created", _("Invoice created")
        ORDER_CREATED = "order.created", _("Order created")
        ORDER_CANCELLED = "order.cancelled", _("Order cancelled")
        RETURN_CREATED = "return.created", _("Return processed")
        PURCHASE_CREATED = "purchase.created", _("Purchase order created")
        PURCHASE_CANCELLED = "purchase.cancelled", _("Purchase order cancelled")
        PAYMENT_RECORDED = "payment.recorded", _("Payment recorded")
        EXPENSE_CREATED = "expense.created", _("Expense created")
        EXPENSE_UPDATED = "expense.updated", _("Expense updated")
        EXPENSE_DELETED = "expense.deleted", _("Expense deleted")
        USER_CREATED = "user.created", _("User created")
        USER_UPDATED = "user.updated", _("User updated")
        USER_DEACTIVATED = "user.deactivated", _("User deactivated")
        USER_REACTIVATED = "user.reactivated", _("User reactivated")
        SETTINGS_UPDATED = "settings.updated", _("Business settings updated")
        BACKUP_TRIGGERED = "backup.triggered", _("Database backup triggered")

    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_log_entries",
    )
    action = models.CharField(max_length=32, choices=Action.choices)

    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("content_type", "object_id")
    object_repr = models.CharField(max_length=255, blank=True)

    changes = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="{field: {'old': ..., 'new': ...}} for an update.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "audit log entry"
        verbose_name_plural = "audit log"
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        who = self.actor.email if self.actor_id else "system"
        return f"{self.action} by {who} @ {self.created_at:%Y-%m-%d %H:%M}"


class BackupJob(models.Model):
    """One manual database backup run (HEXAGARE_FEATURES.md section 54).

    ``PENDING`` (row created, task enqueued) -> ``RUNNING`` (task picked it
    up) -> ``SUCCESS``/``FAILED``. Same shape as ``apps.reports.ReportExport``/
    ``apps.products.LabelBatch``. Restore and scheduled/automatic backups are
    explicitly out of scope this phase -- see the Current Phase note in
    CLAUDE.md.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        RUNNING = "RUNNING", _("Running")
        SUCCESS = "SUCCESS", _("Success")
        FAILED = "FAILED", _("Failed")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    file = models.FileField(upload_to="backups/", blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    triggered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "backup job"
        verbose_name_plural = "backup jobs"

    def __str__(self) -> str:
        return f"Backup #{self.pk} ({self.status})"
