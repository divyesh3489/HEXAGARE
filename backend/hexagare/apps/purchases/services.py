"""``PurchaseTotalsService`` (the ``PurchaseOrder`` totals writer) and
``ReceiveStockService`` (the purchase -> unit flow, HEXAGARE_FEATURES.md
section 33).

``ReceiveStockService.receive`` is the only path that creates
``SerializedUnit`` rows for a purchase order -- one atomic call per receiving
session, all-or-nothing. Each unit goes through
``apps.products.services.serialized_inventory.SerializedInventoryService.generate``
(the same allocator every other unit-creation path uses), landing directly in
``AVAILABLE`` status per the section 33 flow ("Assign Location -> Mark Units
Available") with ``purchase_cost`` set from the line's ``unit_price`` for
cost-basis tracking, and a :class:`~apps.purchases.models.PurchaseOrderLineUnit`
row linking the unit back to the line it was received against.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.products.models import SerializedUnit
from apps.products.services.serialized_inventory import SerializedInventoryService

from .models import PurchaseOrder, PurchaseOrderLineUnit

_ZERO = Decimal("0.00")


class PurchaseTotalsService:
    """Namespace of totals operations. Not instantiated."""

    @staticmethod
    @transaction.atomic
    def recalculate(purchase_order: PurchaseOrder) -> PurchaseOrder:
        """Recompute ``purchase_order``'s derived totals from its current
        lines. Takes a row lock so concurrent line edits on the same order
        serialise. Returns the refreshed, locked instance."""
        purchase_order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)

        subtotal = _ZERO
        discount_total = _ZERO
        tax_total = _ZERO
        for line in purchase_order.lines.all():
            subtotal += line.taxable_value
            discount_total += line.discount_amount
            tax_total += line.tax_amount

        purchase_order.subtotal = subtotal
        purchase_order.discount_total = discount_total
        purchase_order.tax_total = tax_total
        purchase_order.grand_total = subtotal + tax_total
        purchase_order.save(
            update_fields=["subtotal", "discount_total", "tax_total", "grand_total"]
        )
        return purchase_order


class ReceiveStockService:
    """Namespace of receiving operations. Not instantiated."""

    @staticmethod
    @transaction.atomic
    def receive(
        purchase_order: PurchaseOrder, *, receipts: list[dict], actor=None
    ) -> PurchaseOrder:
        """Receive stock against one or more of ``purchase_order``'s lines.

        ``receipts`` is a list of ``{"line": PurchaseOrderLine, "quantity":
        int, "location": Location}``. Every line must belong to
        ``purchase_order`` and have enough ``quantity_pending`` left --
        checked up front so a bad entry fails the whole call before any unit
        is generated.
        """
        purchase_order = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
        if not purchase_order.is_receivable:
            raise ValidationError(
                f"Purchase order is {purchase_order.status} -- stock cannot be received against it."
            )

        line_ids = {entry["line"].pk for entry in receipts}
        lines = {
            line.pk: line
            for line in purchase_order.lines.select_for_update().filter(pk__in=line_ids)
        }
        for entry in receipts:
            line = lines.get(entry["line"].pk)
            if line is None:
                raise ValidationError(
                    {"line": f"Line {entry['line'].pk} does not belong to this purchase order."}
                )
            if entry["quantity"] > line.quantity_pending:
                raise ValidationError(
                    {
                        "quantity": f"Line {line.pk}: only {line.quantity_pending} unit(s) "
                        f"remain to be received (requested {entry['quantity']})."
                    }
                )

        for entry in receipts:
            line = lines[entry["line"].pk]
            for _ in range(entry["quantity"]):
                unit = SerializedInventoryService.generate(
                    variant=line.variant,
                    location=entry["location"],
                    status=SerializedUnit.Status.AVAILABLE,
                    purchase_cost=line.unit_price,
                    actor=actor,
                )
                PurchaseOrderLineUnit.objects.create(line=line, serialized_unit=unit)
            line.quantity_received += entry["quantity"]
            line.save(update_fields=["quantity_received", "updated_at"])

        if all(line.is_fully_received for line in purchase_order.lines.all()):
            purchase_order.status = PurchaseOrder.Status.RECEIVED
        else:
            purchase_order.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
        purchase_order.save(update_fields=["status", "updated_at"])
        return purchase_order
