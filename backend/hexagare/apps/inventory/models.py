"""Inventory domain models.

- :class:`Location` -- the generic stock-holding place a unit lives at
  (``apps.products.SerializedUnit.location``). Introduced in Phase 3 (ADR-007),
  made writable by the Phase 4 ledger.
- :class:`InventoryTransaction` -- the immutable stock ledger. Every balance
  change is one row; :class:`apps.inventory.services.ledger.InventoryService` is
  the only writer (ADR-009).
- :class:`InventoryBalance` -- a rebuildable read-cache of on-hand quantity per
  ``(variant, location, status)``. Never written outside ``InventoryService``.
- :class:`StockLevelPolicy` -- min/max thresholds that drive the alerts.
- :class:`StockTransfer` / :class:`StockTransferLine` -- the scan-based transfer
  flow and its history (HEXAGARE_FEATURES.md section 16).

``Location.kind`` classifies a location for reporting only -- never branch on it
in business logic, and never hardcode a location *name*.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models


class Location(models.Model):
    """A place that holds stock: a warehouse, a marketplace, a retail counter.

    Seed rows (Warehouse / Amazon / Offline) are created by a ``post_migrate``
    hook (:mod:`apps.inventory.bootstrap`). Businesses add their own via the
    admin or the write API.
    """

    class Kind(models.TextChoices):
        WAREHOUSE = "warehouse", "Warehouse"
        MARKETPLACE = "marketplace", "Marketplace"
        RETAIL = "retail", "Retail"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=40, unique=True)
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.OTHER,
        help_text="Classification for reporting only -- do not branch on it.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class InventoryTransaction(models.Model):
    """One immutable line of the stock ledger.

    A row records a *signed* change to the on-hand quantity of one stock bucket
    -- ``(variant, location, status)`` -- and never changes or is deleted after
    it is written. A business action that moves stock between buckets (a
    transfer, a sale, a reservation) produces **two** rows that share a
    ``reference`` UUID: ``-1`` leaving the source bucket and ``+1`` entering the
    destination.

    ``serialized_unit`` tags the row when the movement is a specific unit;
    it is null for a bulk / non-serialized quantity adjustment.

    Written only by :class:`apps.inventory.services.ledger.InventoryService`.
    """

    class Kind(models.TextChoices):
        OPENING = "OPENING", "Opening stock"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer in"
        RESERVE = "RESERVE", "Reserve"
        RELEASE = "RELEASE", "Release reservation"
        SALE = "SALE", "Sale"
        RETURN = "RETURN", "Customer return"
        DAMAGE = "DAMAGE", "Damage"
        LOSS = "LOSS", "Loss"
        RESTORE = "RESTORE", "Restore to available"
        CANCEL = "CANCEL", "Allocation cancelled"
        ADJUSTMENT = "ADJUSTMENT", "Manual adjustment"

    reference = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="Groups the rows produced by one operation (the -1/+1 pair of a move).",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="inventory_transactions",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="inventory_transactions",
    )
    status = models.CharField(
        max_length=16,
        help_text="The stock bucket this row moves -- a SerializedUnit.Status value.",
    )
    quantity = models.IntegerField(
        help_text="Signed change to (variant, location, status): +in / -out. Never 0.",
    )
    serialized_unit = models.ForeignKey(
        "products.SerializedUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_transactions",
    )
    note = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["variant", "location", "status"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self) -> str:
        sign = "+" if self.quantity >= 0 else ""
        return f"{self.kind} {sign}{self.quantity} {self.status} @ {self.location_id}"

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValueError(
                "InventoryTransaction rows are immutable -- write a compensating "
                "row instead of editing one."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "InventoryTransaction rows are an append-only ledger; they are not deleted."
        )


class InventoryBalance(models.Model):
    """Rebuildable read-cache: on-hand quantity for one ``(variant, location,
    status)`` bucket.

    Maintained by :class:`apps.inventory.services.ledger.InventoryService` on
    every ledger write and fully reconstructable from the serialized units via
    ``InventoryService.rebuild_balances()``. Nothing else writes here, and no
    business logic should read a total from here without being willing to fall
    back to a live count (see the ``/inventory/overview/`` endpoint).
    """

    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="inventory_balances",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="inventory_balances",
    )
    status = models.CharField(max_length=16)
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["variant_id", "location_id", "status"]
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "location", "status"],
                name="uniq_balance_bucket",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant_id} {self.status} @ {self.location_id}: {self.quantity}"


class StockLevelPolicy(models.Model):
    """Min / max on-hand thresholds for a variant, optionally per location.

    ``location`` blank means the policy is compared against the variant's total
    ``AVAILABLE`` quantity across every location; a location makes it
    location-specific. Drives low-stock / out-of-stock / overstock alerts
    (HEXAGARE_FEATURES.md section 18).
    """

    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.CASCADE,
        related_name="stock_policies",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_policies",
        help_text="Blank = applies to the variant's total across all locations.",
    )
    min_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Low-stock at or below this level; out-of-stock at 0.",
    )
    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Overstock at or above this level. Blank = no ceiling.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["variant_id", "location_id"]
        verbose_name_plural = "stock level policies"
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "location"],
                condition=models.Q(location__isnull=False),
                name="uniq_policy_per_variant_location",
            ),
            models.UniqueConstraint(
                fields=["variant"],
                condition=models.Q(location__isnull=True),
                name="uniq_global_policy_per_variant",
            ),
        ]

    def __str__(self) -> str:
        scope = self.location.name if self.location_id else "all locations"
        return f"{self.variant_id} @ {scope}: min {self.min_quantity} / max {self.max_quantity}"

    def clean(self):
        if (
            self.max_quantity is not None
            and self.min_quantity is not None
            and self.max_quantity < self.min_quantity
        ):
            raise DjangoValidationError(
                {"max_quantity": "Maximum stock level cannot be below the minimum."}
            )


class StockTransfer(models.Model):
    """A scan-built movement of serialized units from one location to another.

    Lifecycle: ``OPEN`` while units are being scanned onto it (each scan moves
    that unit ``AVAILABLE -> IN_TRANSIT`` via ``SerializedInventoryService`` and
    writes the ledger pair). ``receive`` completes it (each line
    ``IN_TRANSIT -> AVAILABLE`` at ``to_location``); ``cancel`` rolls every
    line back to ``AVAILABLE`` at ``from_location``.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    from_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )
    to_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return (
            f"Transfer #{self.pk}: {self.from_location_id} -> "
            f"{self.to_location_id} ({self.status})"
        )

    def clean(self):
        if self.from_location_id and self.from_location_id == self.to_location_id:
            raise DjangoValidationError(
                {"to_location": "Source and destination locations must differ."}
            )


class StockTransferLine(models.Model):
    """One serialized unit on a :class:`StockTransfer`."""

    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    serialized_unit = models.ForeignKey(
        "products.SerializedUnit",
        on_delete=models.PROTECT,
        related_name="transfer_lines",
    )
    received = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["transfer", "serialized_unit"],
                name="uniq_unit_per_transfer",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.serialized_unit_id} on transfer #{self.transfer_id}"
