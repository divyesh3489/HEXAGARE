"""Bulk serialized-unit generation + label-batch creation (Phase 5).

One :func:`bulk_generate_units` call creates the :class:`~apps.products.models.LabelBatch`
row **and** its ``quantity`` :class:`~apps.products.models.SerializedUnit` rows in a
single ``transaction.atomic`` block -- all-or-nothing (section 11 "Transaction
Safety"). Each unit goes through
:meth:`~apps.products.services.serialized_inventory.SerializedInventoryService.generate`,
so the serial is allocated by the same per-variant advisory-locked counter the
single-unit path uses -- there is no caller-supplied "starting serial" (ADR-010).

The label PDF is **not** rendered here. Once the transaction commits,
``transaction.on_commit`` enqueues ``apps.products.tasks.render_label_pdf`` --
CLAUDE.md's Celery pattern: commit the business transaction first, enqueue after,
never hold the request open for the PDF. A render failure leaves the units intact
and the batch re-renderable.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from ..models import LabelBatch, LabelBatchItem, SerializedUnit
from .serial_numbers import format_serial
from .serialized_inventory import SerializedInventoryService


def next_serial_preview(variant) -> dict:
    """The serial the next allocation for ``variant`` will produce.

    A **preview only** -- it takes no advisory lock, so a concurrent generator
    could claim it first; the real value is assigned under the lock inside
    :func:`bulk_generate_units`. Used by the wizard's review step.
    """
    highest = (
        SerializedUnit.objects.filter(variant=variant)
        .order_by("-sequence")
        .values_list("sequence", flat=True)
        .first()
    ) or 0
    sequence = highest + 1
    return {"serial_number": format_serial(variant, sequence), "sequence": sequence}


@transaction.atomic
def bulk_generate_units(
    *,
    variant,
    location,
    quantity: int,
    initial_status: str | None = None,
    label_size,
    barcode_type: str = LabelBatch.BarcodeType.CODE128,
    label_content: dict | None = None,
    actor=None,
) -> LabelBatch:
    """Create ``quantity`` units of ``variant`` at ``location`` and their label
    batch, atomically. Returns the ``PENDING`` :class:`LabelBatch`; the PDF render
    task is enqueued on commit.
    """
    if quantity < 1:
        raise ValidationError({"quantity": "Generate at least one unit."})
    if quantity > LabelBatch.MAX_QUANTITY:
        raise ValidationError(
            {"quantity": f"A batch is limited to {LabelBatch.MAX_QUANTITY} units."}
        )

    initial_status = initial_status or SerializedUnit.Status.AVAILABLE
    if initial_status not in SerializedUnit.INITIAL_STATUSES:
        raise ValidationError(
            {"initial_status": f"A new unit must start as one of "
                               f"{sorted(SerializedUnit.INITIAL_STATUSES)}."}
        )

    content = label_content or {}
    batch = LabelBatch.objects.create(
        variant=variant,
        location=location,
        quantity=quantity,
        initial_status=initial_status,
        label_size=label_size,
        barcode_type=barcode_type,
        include_product_name=content.get("include_product_name", True),
        include_variant=content.get("include_variant", True),
        include_sku=content.get("include_sku", True),
        include_mrp=content.get("include_mrp", False),
        include_selling_price=content.get("include_selling_price", False),
        custom_text=content.get("custom_text", ""),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )

    items = []
    for _ in range(quantity):
        unit = SerializedInventoryService.generate(
            variant=variant,
            location=location,
            status=initial_status,
            actor=actor,
        )
        items.append(LabelBatchItem(batch=batch, serialized_unit=unit))
    LabelBatchItem.objects.bulk_create(items)

    from apps.accounts.audit import log_activity
    from apps.accounts.models import AuditLogEntry

    log_activity(actor=actor, action=AuditLogEntry.Action.BARCODE_GENERATED, target=batch)

    # Commit first, enqueue after -- never inside the atomic block.
    from ..tasks import render_label_pdf

    transaction.on_commit(lambda: render_label_pdf.delay(batch.pk))
    return batch


def enqueue_render(batch: LabelBatch) -> None:
    """Re-queue the PDF render for an existing batch (the ``regenerate`` action).

    Units are left untouched. Safe to call outside a transaction; if inside one,
    the task still only fires on commit.
    """
    from ..tasks import render_label_pdf

    LabelBatch.objects.filter(pk=batch.pk).update(
        status=LabelBatch.Status.PENDING, error_message=""
    )
    transaction.on_commit(lambda: render_label_pdf.delay(batch.pk))


__all__ = ["bulk_generate_units", "next_serial_preview", "enqueue_render"]
