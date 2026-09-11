"""``SaleUnitService`` -- binds/unbinds physical :class:`SerializedUnit` rows to
a :class:`~apps.sales.models.SaleLine` (ADR-013, the schema decision ADR-012
deferred).

This is the **only** path that adds/removes a unit from a sale's cart: it
reserves the unit through
:class:`apps.products.services.serialized_inventory.SerializedInventoryService`
(so the stock ledger stays in step, per CLAUDE.md), creates/removes the
:class:`~apps.sales.models.SaleLineUnit` join row, keeps
:attr:`SaleLine.quantity` in sync with the bound-unit count, and recalculates
the sale's totals -- all in one atomic block per call.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.products.models import Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import resolve_unit
from apps.products.services.serialized_inventory import SerializedInventoryService

from ..models import Sale, SaleLine, SaleLineUnit
from .totals import SalesTotalsService


class SaleUnitService:
    """Namespace of cart unit-binding operations. Not instantiated."""

    @staticmethod
    def _pick_available_unit(variant: ProductVariant) -> SerializedUnit:
        unit = (
            SerializedUnit.objects.filter(
                variant=variant, status=SerializedUnit.Status.AVAILABLE
            )
            .order_by("sequence")
            .first()
        )
        if unit is None:
            raise ValidationError(
                {"variant": f"No available unit of {variant.sku} to add to this sale."}
            )
        return unit

    @classmethod
    @transaction.atomic
    def add(
        cls,
        sale: Sale,
        *,
        code: str | None = None,
        variant: ProductVariant | None = None,
        actor=None,
    ) -> SaleLine:
        """Resolve a unit (by scanned/typed ``code``, or the oldest available
        unit of ``variant``), reserve it, and bind it to (a new or existing)
        line for its variant on ``sale``. Returns the affected line."""
        if not sale.is_editable:
            raise ValidationError(f"Sale is {sale.status} -- its cart can no longer be edited.")
        if bool(code) == bool(variant):
            raise ValidationError("Provide exactly one of `code` or `variant`.")

        unit = resolve_unit(code) if code else cls._pick_available_unit(variant)

        if unit.status != SerializedUnit.Status.AVAILABLE:
            raise ValidationError(
                {"code": f"{unit.serial_number} is {unit.status}, not available for sale."}
            )

        line_variant = unit.variant
        if line_variant.effective_status != Product.Status.ACTIVE:
            raise ValidationError(
                f"{line_variant.sku} is {line_variant.effective_status}, not available for sale."
            )

        line = sale.lines.filter(variant=line_variant).first()
        if line is None:
            line = SaleLine.objects.create(
                sale=sale,
                variant=line_variant,
                quantity=0,
                unit_price=line_variant.effective_selling_price,
                tax_rate=line_variant.effective_tax_rate,
            )

        # Reserve first -- raises (AVAILABLE -> RESERVED only) if the unit was
        # already taken between the lookup above and this lock.
        unit = SerializedInventoryService.reserve(unit, actor=actor)
        SaleLineUnit.objects.create(sale_line=line, serialized_unit=unit)
        line.quantity = line.units.count()
        line.save(update_fields=["quantity", "updated_at"])

        SalesTotalsService.recalculate(sale)
        return line

    @staticmethod
    @transaction.atomic
    def remove(sale: Sale, unit_id: int, actor=None) -> None:
        """Release and unbind one unit (by its ``SerializedUnit`` id) from
        ``sale``. Deletes the line entirely once its last unit is removed."""
        if not sale.is_editable:
            raise ValidationError(f"Sale is {sale.status} -- its cart can no longer be edited.")

        try:
            join = SaleLineUnit.objects.select_related("sale_line").get(
                sale_line__sale=sale, serialized_unit_id=unit_id
            )
        except SaleLineUnit.DoesNotExist:
            raise ValidationError({"unit": "This unit is not on this sale."})

        line = join.sale_line
        unit = join.serialized_unit
        join.delete()
        SerializedInventoryService.release(unit, actor=actor)

        remaining = line.units.count()
        if remaining == 0:
            line.delete()
        else:
            line.quantity = remaining
            line.save(update_fields=["quantity", "updated_at"])

        SalesTotalsService.recalculate(sale)

    @staticmethod
    @transaction.atomic
    def release_all(sale: Sale, actor=None) -> None:
        """Release every bound unit on ``sale`` and delete the join rows
        (used by ``cancel`` -- a discarded cart keeps no unit history)."""
        joins = SaleLineUnit.objects.select_related("serialized_unit").filter(
            sale_line__sale=sale
        )
        units = [join.serialized_unit for join in joins]
        joins.delete()
        for unit in units:
            SerializedInventoryService.release(unit, actor=actor)


__all__ = ["SaleUnitService"]
