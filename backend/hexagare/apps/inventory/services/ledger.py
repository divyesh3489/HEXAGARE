"""The stock ledger writer.

``InventoryService`` is the **only** code allowed to write
:class:`~apps.inventory.models.InventoryTransaction` and
:class:`~apps.inventory.models.InventoryBalance` (CLAUDE.md; ADR-009). Every
public method opens its own ``transaction.atomic`` block and takes a row lock on
the affected :class:`InventoryBalance` bucket, so concurrent movements of the
same stock serialise.

The ledger (``InventoryTransaction``) is the source of truth; the balance rows
are a cache that :meth:`InventoryService.rebuild_balances` can reconstruct from
the serialized units at any time.
"""

from __future__ import annotations

import uuid

from django.db import models, transaction
from rest_framework.exceptions import ValidationError

from ..models import InventoryBalance, InventoryTransaction


class InventoryService:
    """Namespace of ledger operations. Not instantiated."""

    @staticmethod
    @transaction.atomic
    def record(
        *,
        variant,
        location,
        status: str,
        quantity: int,
        kind: str,
        serialized_unit=None,
        reference=None,
        note: str = "",
        actor=None,
    ) -> InventoryTransaction:
        """Apply one signed change to a ``(variant, location, status)`` bucket.

        Writes the immutable :class:`InventoryTransaction` row and updates the
        matching :class:`InventoryBalance` under ``select_for_update``. Refuses a
        move that would drive the bucket negative.
        """
        if quantity == 0:
            raise ValidationError("An inventory movement must be non-zero.")

        reference = reference or uuid.uuid4()

        balance, _ = InventoryBalance.objects.select_for_update().get_or_create(
            variant=variant,
            location=location,
            status=status,
            defaults={"quantity": 0},
        )
        new_quantity = balance.quantity + quantity
        if new_quantity < 0:
            raise ValidationError(
                f"Not enough {status} stock of {variant.sku} at {location.name}: "
                f"have {balance.quantity}, tried to remove {abs(quantity)}."
            )
        balance.quantity = new_quantity
        balance.save(update_fields=["quantity", "updated_at"])

        return InventoryTransaction.objects.create(
            reference=reference,
            kind=kind,
            variant=variant,
            location=location,
            status=status,
            quantity=quantity,
            serialized_unit=serialized_unit,
            note=note,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
        )

    @staticmethod
    @transaction.atomic
    def move_unit(
        *,
        unit,
        from_location,
        from_status: str,
        to_location,
        to_status: str,
        kind: str,
        reference=None,
        note: str = "",
        actor=None,
    ):
        """Emit the ``-1`` / ``+1`` ledger pair for a serialized unit leaving one
        bucket and entering another, under a shared ``reference``.

        A no-op (same bucket in and out) writes nothing.
        """
        reference = reference or uuid.uuid4()
        if from_location == to_location and from_status == to_status:
            return reference
        InventoryService.record(
            variant=unit.variant,
            location=from_location,
            status=from_status,
            quantity=-1,
            kind=kind,
            serialized_unit=unit,
            reference=reference,
            note=note,
            actor=actor,
        )
        InventoryService.record(
            variant=unit.variant,
            location=to_location,
            status=to_status,
            quantity=1,
            kind=kind,
            serialized_unit=unit,
            reference=reference,
            note=note,
            actor=actor,
        )
        return reference

    @staticmethod
    @transaction.atomic
    def opening(*, unit, note: str = "opening", actor=None) -> InventoryTransaction:
        """Record a newly created serialized unit entering stock at its initial
        status / location. Called from ``create_unit``."""
        return InventoryService.record(
            variant=unit.variant,
            location=unit.location,
            status=unit.status,
            quantity=1,
            kind=InventoryTransaction.Kind.OPENING,
            serialized_unit=unit,
            note=note,
            actor=actor,
        )

    @staticmethod
    @transaction.atomic
    def adjust(
        *,
        variant,
        location,
        status: str,
        quantity: int,
        note: str = "",
        actor=None,
    ) -> InventoryTransaction:
        """Manual, non-serialized quantity correction (permission
        ``stock_adjustments``). Same guarantees as :meth:`record`."""
        txn = InventoryService.record(
            variant=variant,
            location=location,
            status=status,
            quantity=quantity,
            kind=InventoryTransaction.Kind.ADJUSTMENT,
            serialized_unit=None,
            note=note,
            actor=actor,
        )

        from apps.accounts.audit import log_activity
        from apps.accounts.models import AuditLogEntry

        log_activity(
            actor=actor,
            action=AuditLogEntry.Action.STOCK_CHANGED,
            target=txn,
            changes={
                "quantity": {"old": None, "new": quantity},
                "status": {"old": None, "new": status},
            },
        )
        return txn

    @staticmethod
    @transaction.atomic
    def rebuild_balances(*, variant=None) -> int:
        """Rebuild :class:`InventoryBalance` from the authoritative serialized
        units plus the net of non-serialized adjustment rows.

        Use this after the plain (ledger-free) ``transition`` endpoint has been
        used on a unit, or any time the cache is suspected stale. Returns the
        number of balance rows written.
        """
        from apps.products.models import SerializedUnit

        balances = InventoryBalance.objects.all()
        units = SerializedUnit.objects.all()
        adjustments = InventoryTransaction.objects.filter(
            serialized_unit__isnull=True,
            kind=InventoryTransaction.Kind.ADJUSTMENT,
        )
        if variant is not None:
            balances = balances.filter(variant=variant)
            units = units.filter(variant=variant)
            adjustments = adjustments.filter(variant=variant)

        buckets: dict[tuple[int, int, str], int] = {}
        for row in (
            units.values("variant_id", "location_id", "status")
            .order_by()
            .annotate(q=models.Count("id"))
        ):
            buckets[(row["variant_id"], row["location_id"], row["status"])] = row["q"]
        for row in (
            adjustments.values("variant_id", "location_id", "status")
            .order_by()
            .annotate(q=models.Sum("quantity"))
        ):
            key = (row["variant_id"], row["location_id"], row["status"])
            buckets[key] = max(buckets.get(key, 0) + (row["q"] or 0), 0)

        balances.delete()
        InventoryBalance.objects.bulk_create(
            [
                InventoryBalance(
                    variant_id=variant_id,
                    location_id=location_id,
                    status=status,
                    quantity=quantity,
                )
                for (variant_id, location_id, status), quantity in buckets.items()
                if quantity
            ]
        )
        return sum(1 for q in buckets.values() if q)
