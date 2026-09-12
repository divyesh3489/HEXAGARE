"""``ReturnService`` -- the Returns flow (Phase 10, ADR-015).

    Scan barcode -> resolve serial -> find original Sale/SaleLine
        -> validate unit is SOLD -> create Return record -> refund via Payment
        -> unit status -> RETURNED
        -> inspection outcome branches to AVAILABLE (resellable) or DAMAGED

``resolve`` is the read-only preview step (what the frontend calls right
after a scan, before the cashier confirms). ``create`` does the actual
return: every serial must belong to the same :class:`~apps.sales.models.Sale`
(a return is one refund transaction), each unit is moved ``SOLD -> RETURNED``
through :class:`~apps.products.services.serialized_inventory.SerializedInventoryService`
(so the stock ledger stays in step), and one :class:`~apps.billing.models.Payment`
row (``type=REFUND``) records the money going back out. ``inspect`` is the
separate, later step that resolves a still-``PENDING`` :class:`ReturnUnit` to
``RESELLABLE`` (unit restored to ``AVAILABLE``) or ``DAMAGED``.

Works the same regardless of which channel originally sold the unit --
resolution goes through :class:`~apps.sales.models.SaleLineUnit`, which every
``SOLD`` unit has, whether it was sold through the offline POS checkout
(:mod:`apps.billing.services.checkout`) or the Amazon CSV importer
(:mod:`apps.integrations.amazon`). This is deliberately how Phase 9's gap
("a CSV reporting an already-finalized order as RETURNED/REFUNDED is logged
as a failed row rather than reversed") gets closed.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.products.models import SerializedUnit
from apps.products.services.serial_numbers import resolve_unit
from apps.products.services.serialized_inventory import SerializedInventoryService
from apps.sales.models import Sale, SaleLineUnit

from ..models import Payment, Return, ReturnUnit

_MONEY = Decimal("0.01")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _suggested_refund_amount(sale_line_unit: SaleLineUnit) -> Decimal:
    """An even split of the line's net amount across its bound units -- the
    line carries no per-unit discount breakdown, so this is the best
    available snapshot (ADR-015). The cashier may override it at creation."""
    line = sale_line_unit.sale_line
    return _quantize(line.net_amount / line.quantity)


def _resolve_sold_unit(code: str) -> tuple[SerializedUnit, SaleLineUnit]:
    """Resolve ``code`` to a ``SOLD`` unit and its ``SaleLineUnit``. Raises
    ``ValidationError`` for anything else -- not sold, or sold but somehow
    missing its line binding (shouldn't happen; every sale-completion path,
    offline or Amazon import, creates one)."""
    unit = resolve_unit(code)
    if unit.status != SerializedUnit.Status.SOLD:
        raise ValidationError({"code": f"{unit.serial_number} is {unit.status}, not sold."})
    try:
        sale_line_unit = unit.sale_line_unit
    except SaleLineUnit.DoesNotExist:
        raise ValidationError(
            {"code": f"{unit.serial_number} has no recorded sale to return it from."}
        )
    return unit, sale_line_unit


class ReturnService:
    """Namespace for the returns flow. Not instantiated."""

    @staticmethod
    def resolve(code: str) -> dict:
        """Read-only preview for one scanned code: the unit, its originating
        sale/line, and a suggested refund amount. Raises ``ValidationError``
        if the unit isn't ``SOLD``."""
        unit, sale_line_unit = _resolve_sold_unit(code)
        return {
            "unit": unit,
            "sale_line_unit": sale_line_unit,
            "sale": sale_line_unit.sale_line.sale,
            "suggested_refund_amount": _suggested_refund_amount(sale_line_unit),
        }

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        entries: list[dict],
        reason: str,
        refund_method: str,
        note: str = "",
        actor=None,
    ) -> Return:
        """``entries`` is a list of ``{"code": str, "refund_amount": Decimal | None}``.
        Every code must resolve to a ``SOLD`` unit on the **same** ``Sale`` --
        one ``Return`` is one refund transaction. Raises ``ValidationError``
        on any bad code, a mismatched sale, or a code repeated in the same
        call."""
        if not entries:
            raise ValidationError({"entries": "At least one unit is required."})

        sale: Sale | None = None
        resolved: list[tuple[SerializedUnit, SaleLineUnit, Decimal]] = []
        seen_units: set[int] = set()

        for entry in entries:
            code = (entry.get("code") or "").strip()
            unit, sale_line_unit = _resolve_sold_unit(code)
            if unit.pk in seen_units:
                raise ValidationError({"code": f"{unit.serial_number} was scanned twice."})
            seen_units.add(unit.pk)

            unit_sale = sale_line_unit.sale_line.sale
            if sale is None:
                sale = unit_sale
            elif unit_sale.pk != sale.pk:
                raise ValidationError(
                    {
                        "code": f"{unit.serial_number} belongs to sale #{unit_sale.pk}, "
                        f"not sale #{sale.pk} -- a return covers one sale at a time."
                    }
                )

            refund_amount = entry.get("refund_amount")
            if refund_amount is None:
                refund_amount = _suggested_refund_amount(sale_line_unit)
            resolved.append((unit, sale_line_unit, Decimal(refund_amount)))

        return_obj = Return.objects.create(sale=sale, reason=reason, note=note, created_by=actor)
        for unit, sale_line_unit, refund_amount in resolved:
            locked_unit = SerializedUnit.objects.select_for_update().get(pk=unit.pk)
            if locked_unit.status != SerializedUnit.Status.SOLD:
                raise ValidationError(
                    {"code": f"{locked_unit.serial_number} is {locked_unit.status}, not sold."}
                )
            SerializedInventoryService.return_unit(locked_unit, actor=actor, note=reason)
            ReturnUnit.objects.create(
                return_record=return_obj,
                sale_line_unit=sale_line_unit,
                serialized_unit=locked_unit,
                refund_amount=refund_amount,
            )

        Payment.objects.create(
            sale=sale,
            method=refund_method,
            type=Payment.Type.REFUND,
            amount=return_obj.refund_total,
            note=reason,
            created_by=actor,
        )

        from apps.accounts.audit import log_activity
        from apps.accounts.models import AuditLogEntry

        log_activity(actor=actor, action=AuditLogEntry.Action.RETURN_CREATED, target=return_obj)
        return return_obj

    @staticmethod
    @transaction.atomic
    def inspect(*, return_unit: ReturnUnit, condition: str, actor=None) -> ReturnUnit:
        """Resolve a still-``PENDING`` ``ReturnUnit`` to ``RESELLABLE`` (the
        unit goes back to ``AVAILABLE``) or ``DAMAGED``. Raises
        ``ValidationError`` if it was already inspected or the outcome isn't
        one of those two."""
        locked = ReturnUnit.objects.select_for_update().get(pk=return_unit.pk)
        if locked.condition != ReturnUnit.Condition.PENDING:
            raise ValidationError("This unit was already inspected.")

        unit = SerializedUnit.objects.select_for_update().get(pk=locked.serialized_unit_id)
        if condition == ReturnUnit.Condition.RESELLABLE:
            SerializedInventoryService.restore(unit, actor=actor)
        elif condition == ReturnUnit.Condition.DAMAGED:
            SerializedInventoryService.damage(unit, actor=actor)
        else:
            raise ValidationError({"condition": f"Invalid inspection outcome: {condition!r}."})

        locked.condition = condition
        locked.inspected_at = timezone.now()
        locked.inspected_by = actor
        locked.save(update_fields=["condition", "inspected_at", "inspected_by"])
        return locked


__all__ = ["ReturnService"]
