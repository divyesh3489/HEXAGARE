"""``AmazonOrderImportService`` -- turns parsed Amazon order rows into
``Sale``/``SaleLine``/``AmazonOrderSettlement`` rows (Phase 9, ADR-014).

Depends only on the :class:`~apps.integrations.amazon.sources.AmazonOrderSource`
interface, never on CSV parsing directly -- a future SP-API adapter needs no
change here.

**Order-level atomicity.** Rows are grouped by ``order_id``; each order
commits (or rolls back) independently in its own ``transaction.atomic()``, so
one bad order (unknown SKU, insufficient stock, conflicting statuses) never
blocks the rest of the file. Re-running the whole batch is always safe --
already-imported orders are idempotent (see below).

**Deliberately bypasses ``apps.sales.services.units.SaleUnitService`` and
``apps.billing.services.checkout.CompleteSaleService``.** An imported Amazon
order already happened -- it is not a cart being assembled locally, and
Amazon issues its own invoice, so no ``Payment``/``Invoice`` is created here.
Serialized units still only ever move through
``apps.products.services.serialized_inventory.SerializedInventoryService``
(the one path the architecture allows): for an order whose status means
stock actually left the business, each unit goes ``AVAILABLE -> RESERVED ->
SOLD`` (both calls in the same order transaction -- the state machine has no
direct ``AVAILABLE -> SOLD`` edge), picked FIFO by ``sequence`` from the
``amazon`` :class:`~apps.inventory.models.Location`.

**Idempotency.** ``Sale`` is keyed on ``(sales_channel, external_reference)``
(the Amazon order id); ``AmazonOrderSettlement`` on ``(sale, sku)``. Once an
order has any bound ``SaleLineUnit`` (its units were sold), it is treated as
**finalized**: re-importing it only ever advances ``Sale.status`` forward
along the pre-cancellation happy path (e.g. SHIPPED -> DELIVERED); its lines
and settlement are left untouched, and a CSV trying to move a finalized order
to CANCELLED/RETURNED/REFUNDED is logged and skipped rather than silently
reversing units it can't actually reverse -- that is Phase 10 Returns' job.
An order that hasn't sold units yet is fully rebuilt on every re-import
(lines/settlement recreated from the latest CSV values).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.inventory.models import Location
from apps.products.models import ProductVariant, SerializedUnit
from apps.products.services.serialized_inventory import SerializedInventoryService
from apps.sales.models import Sale, SaleLine, SaleLineUnit, SalesChannel
from apps.sales.services.totals import SalesTotalsService

from ..models import AmazonFeeConfig, AmazonImportBatch, AmazonOrderSettlement, AmazonSkuMapping
from ..sources import AmazonOrderRow, AmazonOrderRowError, AmazonOrderSource
from .fees import resolve_fee

_ZERO = Decimal("0.00")
_MONEY = Decimal("0.01")

#: Amazon CSV order_status values -> Sale.Status (case-insensitive). Anything
#: else is an order-level error -- fail loudly rather than silently default,
#: a mapping gap should surface, not be guessed at.
STATUS_MAP: dict[str, str] = {
    "pending": Sale.Status.PENDING,
    "confirmed": Sale.Status.CONFIRMED,
    "shipped": Sale.Status.SHIPPED,
    "in_transit": Sale.Status.IN_TRANSIT,
    "delivered": Sale.Status.DELIVERED,
    "completed": Sale.Status.COMPLETED,
    "cancelled": Sale.Status.CANCELLED,
    "canceled": Sale.Status.CANCELLED,
    "returned": Sale.Status.RETURNED,
    "refunded": Sale.Status.REFUNDED,
}

#: Statuses that mean stock actually left the business -- the only ones the
#: importer sells serialized units for.
FULFILLED_STATUSES = {
    Sale.Status.SHIPPED,
    Sale.Status.IN_TRANSIT,
    Sale.Status.DELIVERED,
    Sale.Status.COMPLETED,
}

#: The normal pre-cancellation lifecycle, in order. CANCELLED/RETURNED/
#: REFUNDED are terminal branches handled separately (see module docstring).
_HAPPY_PATH = [
    Sale.Status.PENDING,
    Sale.Status.CONFIRMED,
    Sale.Status.RESERVED,
    Sale.Status.SHIPPED,
    Sale.Status.IN_TRANSIT,
    Sale.Status.DELIVERED,
    Sale.Status.COMPLETED,
]
_TERMINAL_BRANCH = {Sale.Status.CANCELLED, Sale.Status.RETURNED, Sale.Status.REFUNDED}

_FEE_FIELD_TO_NAME = {
    "referral_fee": AmazonFeeConfig.FeeName.REFERRAL,
    "closing_fee": AmazonFeeConfig.FeeName.CLOSING,
    "fulfillment_fee": AmazonFeeConfig.FeeName.FULFILLMENT,
    "shipping_cost": AmazonFeeConfig.FeeName.SHIPPING,
    "advertising_cost": AmazonFeeConfig.FeeName.ADVERTISING,
    "other_charges": AmazonFeeConfig.FeeName.OTHER,
}


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _derive_tax_rate(selling_price: Decimal, gst_amount: Decimal) -> Decimal:
    taxable = selling_price - gst_amount
    if taxable <= 0:
        return _ZERO
    return _quantize(gst_amount / taxable * 100)


class OrderImportError(Exception):
    """Raised to fail one order's import -- caught per-order by
    :meth:`AmazonOrderImportService.run`, rolling back just that order."""


class AmazonOrderImportService:
    """Namespace for the import operation. Not instantiated."""

    # -- lookups ---------------------------------------------------------
    @staticmethod
    def _map_status(raw_status: str) -> str:
        mapped = STATUS_MAP.get(raw_status.strip().lower())
        if mapped is None:
            raise OrderImportError(
                f"Unknown order_status '{raw_status}'."
            )
        return mapped

    @staticmethod
    def _resolve_variant(amazon_sku: str) -> ProductVariant:
        mapping = (
            AmazonSkuMapping.objects.filter(amazon_sku=amazon_sku, is_active=True)
            .select_related("variant")
            .first()
        )
        if mapping is not None:
            return mapping.variant

        variant = ProductVariant.objects.filter(sku=amazon_sku).first()
        if variant is not None:
            AmazonSkuMapping.objects.create(amazon_sku=amazon_sku, variant=variant)
            return variant

        raise OrderImportError(
            f"Unknown Amazon SKU '{amazon_sku}' -- add a mapping before importing."
        )

    @staticmethod
    def _amazon_location() -> Location:
        try:
            return Location.objects.get(code="amazon")
        except Location.DoesNotExist as exc:  # pragma: no cover - seeded by post_migrate
            raise OrderImportError("The 'amazon' stock location is missing.") from exc

    # -- unit selling -----------------------------------------------------
    @classmethod
    def _sell_units(cls, line: SaleLine, quantity: int, *, order_id: str, actor) -> None:
        location = cls._amazon_location()
        units = list(
            SerializedUnit.objects.select_for_update(skip_locked=True)
            .filter(
                variant=line.variant,
                location=location,
                status=SerializedUnit.Status.AVAILABLE,
            )
            .order_by("sequence")[:quantity]
        )
        if len(units) < quantity:
            raise OrderImportError(
                f"Insufficient stock for {line.variant.sku} at Amazon: need {quantity}, "
                f"have {len(units)} available."
            )
        for unit in units:
            note = f"Amazon order {order_id}"
            unit = SerializedInventoryService.reserve(unit, actor=actor, note=note)
            unit = SerializedInventoryService.sell(unit, actor=actor, note=note)
            SaleLineUnit.objects.create(sale_line=line, serialized_unit=unit)

    # -- fees ---------------------------------------------------------
    @classmethod
    def _fee_value(
        cls,
        row: AmazonOrderRow,
        field: str,
        *,
        sales_channel_id: int,
        variant: ProductVariant,
        taxable_value: Decimal,
    ) -> Decimal:
        explicit = getattr(row, field)
        if explicit is not None:
            return explicit
        return resolve_fee(
            _FEE_FIELD_TO_NAME[field],
            sales_channel_id=sales_channel_id,
            product=variant.product,
            order_date=row.order_date,
            taxable_value=taxable_value,
        )

    # -- one order -------------------------------------------------------
    @classmethod
    @transaction.atomic
    def _import_order(
        cls, order_id: str, rows: list[AmazonOrderRow], *, channel: SalesChannel, actor
    ) -> str:
        """Returns ``"created"``, ``"updated"``, or ``"skipped"``. Raises
        :class:`OrderImportError` (rolling back this order only) on failure."""
        status_values = {cls._map_status(r.order_status) for r in rows}
        if len(status_values) > 1:
            raise OrderImportError(
                f"Order has conflicting statuses across its rows: {sorted(status_values)}."
            )
        mapped_status = status_values.pop()

        skus = [r.amazon_sku for r in rows]
        if len(skus) != len(set(skus)):
            raise OrderImportError(
                "Duplicate amazon_sku rows for this order -- merge quantities in the CSV."
            )

        sale, created = Sale.objects.select_for_update().get_or_create(
            sales_channel=channel,
            external_reference=order_id,
            defaults={"status": mapped_status},
        )

        already_finalized = SaleLineUnit.objects.filter(sale_line__sale=sale).exists()
        if not created and already_finalized:
            return cls._advance_finalized_order(sale, mapped_status)

        for row in rows:
            variant = cls._resolve_variant(row.amazon_sku)
            tax_rate = _derive_tax_rate(row.selling_price, row.gst_amount)

            line, _ = SaleLine.objects.update_or_create(
                sale=sale,
                variant=variant,
                defaults={
                    "quantity": row.quantity,
                    "unit_price": row.selling_price,
                    "tax_rate": tax_rate,
                },
            )

            if mapped_status in FULFILLED_STATUSES:
                cls._sell_units(line, row.quantity, order_id=order_id, actor=actor)

            cls._upsert_settlement(sale, row, variant=variant, channel=channel)

        if not created and sale.status != mapped_status:
            sale.status = mapped_status
            sale.save(update_fields=["status", "updated_at"])
        SalesTotalsService.recalculate(sale)
        return "created" if created else "updated"

    @staticmethod
    def _advance_finalized_order(sale: Sale, mapped_status: str) -> str:
        """A finalized order (units already sold) only ever has its status
        advanced along the happy path; a terminal-branch status is logged and
        skipped rather than silently mismatching the (unreversed) units."""
        if mapped_status in _TERMINAL_BRANCH:
            raise OrderImportError(
                f"Order already sold its units; a CSV status of {mapped_status} would need a "
                "manual return (Phase 10), not supported by import -- left unchanged."
            )
        if sale.status in _HAPPY_PATH and mapped_status in _HAPPY_PATH:
            if _HAPPY_PATH.index(mapped_status) > _HAPPY_PATH.index(sale.status):
                sale.status = mapped_status
                sale.save(update_fields=["status", "updated_at"])
                return "updated"
        return "skipped"

    @classmethod
    def _upsert_settlement(
        cls, sale: Sale, row: AmazonOrderRow, *, variant: ProductVariant, channel: SalesChannel
    ) -> None:
        taxable_value = _quantize((row.selling_price - row.gst_amount) * row.quantity)
        fee_values = {
            field: cls._fee_value(
                row,
                field,
                sales_channel_id=channel.pk,
                variant=variant,
                taxable_value=taxable_value,
            )
            for field in _FEE_FIELD_TO_NAME
        }
        AmazonOrderSettlement.objects.update_or_create(
            sale=sale,
            sku=row.amazon_sku,
            defaults={
                "variant": variant,
                "quantity": row.quantity,
                "selling_price": _quantize(row.selling_price * row.quantity),
                "gst_amount": _quantize(row.gst_amount * row.quantity),
                "taxable_value": taxable_value,
                "refund_amount": row.refund_amount,
                **fee_values,
            },
        )

    # -- the whole file -------------------------------------------------
    @classmethod
    def run(cls, batch: AmazonImportBatch, source: AmazonOrderSource, *, actor=None) -> None:
        """Parses and imports every order in ``source``, then records the
        outcome on ``batch`` (status, counts, ``error_log``) and saves it."""
        channel = SalesChannel.objects.get(code="AMAZON")

        groups: dict[str, list[AmazonOrderRow]] = defaultdict(list)
        error_log: list[dict] = []
        total_rows = 0

        for entry in source.rows():
            if isinstance(entry, AmazonOrderRowError):
                error_log.append({"row": entry.row_number, "message": entry.message})
                continue
            total_rows += 1
            groups[entry.order_id].append(entry)

        created = updated = skipped = failed = 0
        for order_id, rows in groups.items():
            try:
                outcome = cls._import_order(order_id, rows, channel=channel, actor=actor)
            except OrderImportError as exc:
                failed += 1
                error_log.append({"order_id": order_id, "message": str(exc)})
                continue
            except Exception as exc:  # noqa: BLE001 - never let one bad order kill the batch
                failed += 1
                error_log.append({"order_id": order_id, "message": f"Unexpected error: {exc}"})
                continue

            if outcome == "created":
                created += 1
            elif outcome == "updated":
                updated += 1
            else:
                skipped += 1

        if not groups:
            status = AmazonImportBatch.Status.FAILED
            if not error_log:
                batch.error_message = "The file contained no importable rows."
        elif failed and not (created or updated or skipped):
            status = AmazonImportBatch.Status.FAILED
        elif failed:
            status = AmazonImportBatch.Status.PARTIAL
        else:
            status = AmazonImportBatch.Status.READY

        batch.status = status
        batch.total_rows = total_rows
        batch.total_orders = len(groups)
        batch.orders_created = created
        batch.orders_updated = updated
        batch.orders_skipped = skipped
        batch.orders_failed = failed
        batch.error_log = error_log
        batch.finished_at = timezone.now()
        batch.save()


__all__ = ["AmazonOrderImportService", "OrderImportError", "STATUS_MAP", "FULFILLED_STATUSES"]
