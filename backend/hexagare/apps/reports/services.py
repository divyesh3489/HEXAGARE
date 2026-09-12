"""``ReportsService`` -- read-only report aggregation (Phase 14).

Same Python-loop aggregation style as ``apps.expenses.services.FinanceService``
/ ``apps.customers.services`` -- nothing here is cached, every call re-derives
its numbers from the live tables. Where another app already owns the
computation (profit math, low/out-of-stock alerts), this module calls into it
rather than re-deriving it:

- :class:`apps.expenses.services.FinanceService` -- the Financial report's
  profit figures, and the Sales report's profit line.
- :func:`apps.inventory.services.alerts.compute_alerts` -- the Inventory
  report's low/out-of-stock/overstock rows.

Every method returns ``(summary: dict, rows: list[dict])``. ``rows`` is the
flat, one-record-per-line shape used **both** for on-screen display and for
CSV/Excel export (``apps.reports.exporters`` / ``apps.reports.tasks`` take a
report's ``rows`` as-is) -- nothing is computed twice for the two use cases.
``summary`` carries the aggregate figures/breakdowns a report's tiles show.

Two filter vocabularies, matching how the domain is actually shaped:
``channel`` (a :class:`~apps.sales.models.SalesChannel`) scopes the
Sales/Products/Financial reports; ``location`` (an
:class:`~apps.inventory.models.Location`) scopes the Inventory/Serial Number
reports, since stock buckets are location-scoped, not channel-scoped.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count
from rest_framework.exceptions import ValidationError

from apps.expenses.services import FinanceService
from apps.inventory.models import InventoryBalance, InventoryTransaction, Location
from apps.inventory.services.alerts import compute_alerts
from apps.products.models import Category, ProductVariant, SerializedUnit
from apps.sales.models import Sale, SaleLine, SaleLineUnit, SalesChannel

_ZERO = Decimal("0.00")
_MONEY = Decimal("0.01")

#: A sale that never reached checkout has no revenue yet; a cancelled one
#: never completed -- same exclusion apps.expenses.services.FinanceService uses.
_EXCLUDED_STATUSES = (Sale.Status.DRAFT, Sale.Status.CANCELLED)


def _quantize(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _unit_cost(unit: SerializedUnit) -> Decimal:
    """A unit's cost basis: its own receiving cost when set, else the
    catalog's current effective purchase price -- same fallback
    ``apps.expenses.services.FinanceService`` uses."""
    if unit.purchase_cost is not None:
        return unit.purchase_cost
    return unit.variant.effective_purchase_price


class ReportsService:
    """Namespace of report read operations. Not instantiated."""

    # -- Sales (section 38) ------------------------------------------------
    @staticmethod
    def sales(
        date_from: date,
        date_to: date,
        channel: SalesChannel | None = None,
        group_by: str | None = None,
    ) -> tuple[dict, list[dict]]:
        sales_qs = Sale.objects.exclude(status__in=_EXCLUDED_STATUSES).filter(
            created_at__date__gte=date_from, created_at__date__lte=date_to
        )
        if channel is not None:
            sales_qs = sales_qs.filter(sales_channel=channel)
        sale_ids = list(sales_qs.values_list("id", flat=True))

        finance = FinanceService.summary(date_from, date_to, channel)
        units_sold = SaleLineUnit.objects.filter(sale_line__sale_id__in=sale_ids).count()
        revenue = _quantize(finance["taxable_sales"] - finance["refunds"])
        summary = {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel.code if channel is not None else None,
            "orders": len(sale_ids),
            "units_sold": units_sold,
            "gross_sales": finance["gross_sales"],
            "taxable_sales": finance["taxable_sales"],
            "gst": finance["gst_collected"],
            "discounts": finance["discounts"],
            "refunds": finance["refunds"],
            "revenue": revenue,
            "profit": finance["net_profit"],
        }

        if not group_by:
            return summary, [dict(summary)]
        if group_by == "serial":
            return summary, ReportsService._sales_rows_by_serial(sale_ids)
        return summary, ReportsService._sales_rows_grouped(sale_ids, group_by)

    @staticmethod
    def _sales_rows_grouped(sale_ids: list[int], group_by: str) -> list[dict]:
        if group_by not in {"variant", "product", "category"}:
            raise ValueError(f"Unknown group_by {group_by!r}")

        costs: defaultdict[int, Decimal] = defaultdict(lambda: _ZERO)
        for slu in SaleLineUnit.objects.filter(
            sale_line__sale_id__in=sale_ids
        ).select_related("serialized_unit__variant"):
            costs[slu.sale_line_id] += _unit_cost(slu.serialized_unit)

        lines = (
            SaleLine.objects.filter(sale_id__in=sale_ids)
            .select_related("variant__product__category")
            .annotate(unit_count=Count("units"))
        )

        buckets: dict[int, dict] = {}
        orders_by_key: defaultdict[int, set] = defaultdict(set)
        for line in lines:
            variant = line.variant
            if group_by == "variant":
                key, name = variant.id, variant.sku
            elif group_by == "product":
                key, name = variant.product.id, variant.product.name
            else:
                category = variant.product.category
                key, name = category.id, category.name

            bucket = buckets.setdefault(
                key,
                {
                    "id": key,
                    "name": name,
                    "orders": 0,
                    "units_sold": 0,
                    "gross_sales": _ZERO,
                    "taxable_sales": _ZERO,
                    "gst": _ZERO,
                    "discounts": _ZERO,
                    "product_cost": _ZERO,
                },
            )
            orders_by_key[key].add(line.sale_id)
            bucket["units_sold"] += line.unit_count
            bucket["gross_sales"] += line.gross_amount
            bucket["taxable_sales"] += line.taxable_value
            bucket["gst"] += line.tax_amount
            bucket["discounts"] += line.discount_amount
            bucket["product_cost"] += costs.get(line.id, _ZERO)

        rows = []
        for key, bucket in buckets.items():
            bucket["orders"] = len(orders_by_key[key])
            for field in ("gross_sales", "taxable_sales", "gst", "discounts", "product_cost"):
                bucket[field] = _quantize(bucket[field])
            bucket["gross_profit"] = _quantize(bucket["taxable_sales"] - bucket["product_cost"])
            rows.append(bucket)
        rows.sort(key=lambda r: r["taxable_sales"], reverse=True)
        return rows

    @staticmethod
    def _sales_rows_by_serial(sale_ids: list[int]) -> list[dict]:
        unit_counts: defaultdict[int, int] = defaultdict(int)
        for row in (
            SaleLineUnit.objects.filter(sale_line__sale_id__in=sale_ids)
            .values("sale_line_id")
            .order_by()
            .annotate(q=Count("id"))
        ):
            unit_counts[row["sale_line_id"]] = row["q"]

        rows = []
        line_units = SaleLineUnit.objects.filter(sale_line__sale_id__in=sale_ids).select_related(
            "serialized_unit__variant__product",
            "sale_line",
            "sale_line__sale__sales_channel",
        )
        for slu in line_units:
            line = slu.sale_line
            sale = line.sale
            unit = slu.serialized_unit
            unit_count = unit_counts.get(line.id) or 1
            taxable_share = _quantize(line.taxable_value / unit_count)
            cost = _unit_cost(unit)
            rows.append(
                {
                    "serial_number": unit.serial_number,
                    "sku": unit.variant.sku,
                    "product_name": unit.variant.product.name,
                    "sale_id": sale.id,
                    "channel": sale.sales_channel.code,
                    "sold_at": sale.created_at,
                    "taxable_value": taxable_share,
                    "product_cost": cost,
                    "gross_profit": _quantize(taxable_share - cost),
                }
            )
        rows.sort(key=lambda r: r["sold_at"], reverse=True)
        return rows

    # -- Inventory (section 39) ---------------------------------------------
    @staticmethod
    def inventory(
        location: Location | None = None,
        variant: ProductVariant | None = None,
        category: Category | None = None,
    ) -> tuple[dict, list[dict]]:
        balances = InventoryBalance.objects.select_related(
            "variant__product__category", "location"
        ).filter(quantity__gt=0)
        if location is not None:
            balances = balances.filter(location=location)
        if variant is not None:
            balances = balances.filter(variant=variant)
        if category is not None:
            balances = balances.filter(variant__product__category=category)

        rows = []
        by_status: defaultdict[str, int] = defaultdict(int)
        valuation_available = _ZERO
        for balance in balances:
            by_status[balance.status] += balance.quantity
            row_value = _quantize(balance.variant.effective_purchase_price * balance.quantity)
            if balance.status == SerializedUnit.Status.AVAILABLE:
                valuation_available += row_value
            rows.append(
                {
                    "sku": balance.variant.sku,
                    "product_name": balance.variant.product.name,
                    "category": balance.variant.product.category.name,
                    "location": balance.location.name,
                    "status": balance.status,
                    "quantity": balance.quantity,
                    "valuation": row_value,
                }
            )
        rows.sort(key=lambda r: (r["product_name"], r["sku"], r["location"]))

        alerts = compute_alerts(
            variant_id=variant.id if variant else None,
            location_id=location.id if location else None,
        )
        if category is not None:
            alerts = [a for a in alerts if a["variant"]["sku"] in {r["sku"] for r in rows}]
        alert_counts: defaultdict[str, int] = defaultdict(int)
        for alert in alerts:
            alert_counts[alert["type"]] += 1

        summary = {
            "location": location.code if location else None,
            "by_status": dict(by_status),
            "total_units": sum(by_status.values()),
            "valuation_available": _quantize(valuation_available),
            "low_stock": alert_counts["low_stock"],
            "out_of_stock": alert_counts["out_of_stock"],
            "overstock": alert_counts["overstock"],
        }
        return summary, rows

    @staticmethod
    def inventory_movement(
        date_from: date,
        date_to: date,
        location: Location | None = None,
        variant: ProductVariant | None = None,
    ) -> tuple[dict, list[dict]]:
        txns = InventoryTransaction.objects.select_related(
            "variant__product", "location", "actor"
        ).filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        if location is not None:
            txns = txns.filter(location=location)
        if variant is not None:
            txns = txns.filter(variant=variant)

        rows = []
        by_kind: defaultdict[str, int] = defaultdict(int)
        for txn in txns:
            by_kind[txn.kind] += 1
            rows.append(
                {
                    "date": txn.created_at,
                    "kind": txn.kind,
                    "sku": txn.variant.sku,
                    "product_name": txn.variant.product.name,
                    "location": txn.location.name,
                    "status": txn.status,
                    "quantity": txn.quantity,
                    "serial_number": txn.serialized_unit.serial_number
                    if txn.serialized_unit_id
                    else "",
                    "note": txn.note,
                    "actor": txn.actor.email if txn.actor_id else "",
                }
            )
        summary = {
            "date_from": date_from,
            "date_to": date_to,
            "total_transactions": len(rows),
            "by_kind": dict(by_kind),
        }
        return summary, rows

    # -- Serial numbers (section 40) ----------------------------------------
    @staticmethod
    def serial_numbers(
        location: Location | None = None,
        variant: ProductVariant | None = None,
        category: Category | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[dict, list[dict]]:
        units = SerializedUnit.objects.select_related("variant__product", "location")
        if location is not None:
            units = units.filter(location=location)
        if variant is not None:
            units = units.filter(variant=variant)
        if category is not None:
            units = units.filter(variant__product__category=category)
        if date_from is not None:
            units = units.filter(created_at__date__gte=date_from)
        if date_to is not None:
            units = units.filter(created_at__date__lte=date_to)

        rows = []
        by_status: defaultdict[str, int] = defaultdict(int)
        for unit in units:
            by_status[unit.status] += 1
            rows.append(
                {
                    "serial_number": unit.serial_number,
                    "sku": unit.variant.sku,
                    "product_name": unit.variant.product.name,
                    "status": unit.status,
                    "location": unit.location.name,
                    "created_at": unit.created_at,
                }
            )
        rows.sort(key=lambda r: r["created_at"], reverse=True)

        summary = {
            "date_from": date_from,
            "date_to": date_to,
            "location": location.code if location else None,
            "total": len(rows),
            "by_status": dict(by_status),
        }
        return summary, rows

    @staticmethod
    def serial_number_history(unit: SerializedUnit) -> tuple[dict, list[dict]]:
        """Section 41. Reuses the existing append-only
        ``apps.products.models.SerializedUnitEvent`` log -- it doesn't (yet)
        track the *previous* location or a related order/invoice/purchase/
        transfer, only ``from_status``/``to_status``/the new ``location``/a
        free-text ``note``; this report surfaces exactly what's recorded,
        it doesn't add new fields to that model.
        """
        events = unit.events.select_related("location", "actor").order_by("created_at", "id")
        rows = [
            {
                "event": event.to_status,
                "previous_status": event.from_status,
                "new_status": event.to_status,
                "location": event.location.name if event.location_id else "",
                "user": event.actor.email if event.actor_id else "",
                "date": event.created_at,
                "reason": event.note,
            }
            for event in events
        ]
        summary = {
            "serial_number": unit.serial_number,
            "sku": unit.variant.sku,
            "product_name": unit.variant.product.name,
            "current_status": unit.status,
            "current_location": unit.location.name,
            "event_count": len(rows),
        }
        return summary, rows

    # -- Products (section 42) ----------------------------------------------
    @staticmethod
    def products(
        date_from: date,
        date_to: date,
        channel: SalesChannel | None = None,
    ) -> tuple[dict, list[dict]]:
        sales_qs = Sale.objects.exclude(status__in=_EXCLUDED_STATUSES).filter(
            created_at__date__gte=date_from, created_at__date__lte=date_to
        )
        if channel is not None:
            sales_qs = sales_qs.filter(sales_channel=channel)
        sale_ids = list(sales_qs.values_list("id", flat=True))

        sold_by_variant: defaultdict[int, dict] = defaultdict(
            lambda: {"units_sold": 0, "taxable_sales": _ZERO, "product_cost": _ZERO}
        )
        costs: defaultdict[int, Decimal] = defaultdict(lambda: _ZERO)
        unit_counts: defaultdict[int, int] = defaultdict(int)
        for slu in SaleLineUnit.objects.filter(
            sale_line__sale_id__in=sale_ids
        ).select_related("serialized_unit__variant", "sale_line"):
            variant_id = slu.serialized_unit.variant_id
            sold_by_variant[variant_id]["units_sold"] += 1
            costs[slu.sale_line_id] += _unit_cost(slu.serialized_unit)
            unit_counts[slu.sale_line_id] += 1

        for line in SaleLine.objects.filter(sale_id__in=sale_ids):
            variant_id = line.variant_id
            if not unit_counts.get(line.id):
                continue
            sold_by_variant[variant_id]["taxable_sales"] += line.taxable_value
            sold_by_variant[variant_id]["product_cost"] += costs.get(line.id, _ZERO)

        current_status_counts: defaultdict[int, defaultdict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for row in (
            SerializedUnit.objects.values("variant_id", "status")
            .order_by()
            .annotate(q=Count("id"))
        ):
            current_status_counts[row["variant_id"]][row["status"]] = row["q"]

        # Every catalog variant, not just ones with sales or generated units --
        # a product that has never been stocked is still "never sold" (worst-
        # selling), not simply absent from the report.
        variants = ProductVariant.objects.select_related("product")
        rows = []
        _empty_sold = {"units_sold": 0, "taxable_sales": _ZERO, "product_cost": _ZERO}
        for v in variants:
            sold = sold_by_variant.get(v.id, _empty_sold)
            statuses = current_status_counts.get(v.id, {})
            taxable_sales = _quantize(sold["taxable_sales"])
            product_cost = _quantize(sold["product_cost"])
            rows.append(
                {
                    "sku": v.sku,
                    "product_name": v.product.name,
                    "units_sold": sold["units_sold"],
                    "revenue": taxable_sales,
                    "gross_profit": _quantize(taxable_sales - product_cost),
                    "units_available": statuses.get(SerializedUnit.Status.AVAILABLE, 0),
                    "units_reserved": statuses.get(SerializedUnit.Status.RESERVED, 0),
                    "units_in_transit": statuses.get(SerializedUnit.Status.IN_TRANSIT, 0),
                    "units_damaged": statuses.get(SerializedUnit.Status.DAMAGED, 0),
                }
            )
        rows.sort(key=lambda r: r["units_sold"], reverse=True)

        summary = {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel.code if channel is not None else None,
            "products_sold": sum(1 for r in rows if r["units_sold"] > 0),
            "products_never_sold": sum(1 for r in rows if r["units_sold"] == 0),
        }
        return summary, rows

    # -- Financial (section 43) ----------------------------------------------
    @staticmethod
    def financial(
        date_from: date,
        date_to: date,
        channel: SalesChannel | None = None,
    ) -> tuple[dict, list[dict]]:
        summary = FinanceService.summary(date_from, date_to, channel)
        summary["outstanding_amount"] = ReportsService._outstanding(date_from, date_to, channel)

        if channel is not None:
            return summary, [dict(summary)]

        rows = []
        for row in FinanceService.by_channel(date_from, date_to):
            row = dict(row)
            row_channel = SalesChannel.objects.filter(code=row["channel"]).first()
            row["outstanding_amount"] = ReportsService._outstanding(
                date_from, date_to, row_channel
            )
            rows.append(row)
        return summary, rows

    @staticmethod
    def _outstanding(
        date_from: date, date_to: date, channel: SalesChannel | None
    ) -> Decimal:
        sales_qs = Sale.objects.exclude(status__in=_EXCLUDED_STATUSES).filter(
            created_at__date__gte=date_from, created_at__date__lte=date_to
        )
        if channel is not None:
            sales_qs = sales_qs.filter(sales_channel=channel)
        outstanding = _ZERO
        for sale in sales_qs:
            balance = sale.balance_due
            if balance > 0:
                outstanding += balance
        return _quantize(outstanding)


# --------------------------------------------------------------------------- #
# Dispatch -- one entry point both the GET report views and the export task
# call, so a report is queried exactly the same way whether it's rendered on
# screen or into a CSV/Excel file.
# --------------------------------------------------------------------------- #


def _resolve_channel(code: str | None) -> SalesChannel | None:
    if not code:
        return None
    try:
        return SalesChannel.objects.get(code=code)
    except SalesChannel.DoesNotExist as exc:
        raise ValidationError({"channel": f"Unknown sales channel {code!r}."}) from exc


def _resolve_location(code: str | None) -> Location | None:
    if not code:
        return None
    try:
        return Location.objects.get(code=code)
    except Location.DoesNotExist as exc:
        raise ValidationError({"location": f"Unknown location {code!r}."}) from exc


def _resolve_variant(variant_id) -> ProductVariant | None:
    if not variant_id:
        return None
    try:
        return ProductVariant.objects.select_related("product").get(pk=variant_id)
    except ProductVariant.DoesNotExist as exc:
        raise ValidationError({"variant": f"Unknown variant {variant_id!r}."}) from exc


def _resolve_category(category_id) -> Category | None:
    if not category_id:
        return None
    try:
        return Category.objects.get(pk=category_id)
    except Category.DoesNotExist as exc:
        raise ValidationError({"category": f"Unknown category {category_id!r}."}) from exc


def _resolve_unit(serial_number: str | None) -> SerializedUnit:
    if not serial_number:
        raise ValidationError({"serial_number": "This field is required."})
    try:
        return SerializedUnit.objects.select_related("variant__product", "location").get(
            serial_number=serial_number
        )
    except SerializedUnit.DoesNotExist as exc:
        raise ValidationError(
            {"serial_number": f"Unknown serial number {serial_number!r}."}
        ) from exc


def run_report(report_type: str, filters: dict) -> tuple[dict, list[dict]]:
    """Resolve ``filters`` (plain JSON-safe values -- exactly what's stored on
    ``ReportExport.filters`` and what a validated query-param serializer
    produces) and dispatch to the matching :class:`ReportsService` method."""
    from .models import ReportExport

    RT = ReportExport.ReportType

    if report_type == RT.SALES:
        return ReportsService.sales(
            filters.get("date_from"),
            filters.get("date_to"),
            _resolve_channel(filters.get("channel")),
            filters.get("group_by") or None,
        )
    if report_type == RT.INVENTORY:
        location = _resolve_location(filters.get("location"))
        variant = _resolve_variant(filters.get("variant"))
        if filters.get("view") == "movement":
            return ReportsService.inventory_movement(
                filters.get("date_from"), filters.get("date_to"), location, variant
            )
        return ReportsService.inventory(
            location, variant, _resolve_category(filters.get("category"))
        )
    if report_type == RT.SERIAL_NUMBERS:
        return ReportsService.serial_numbers(
            _resolve_location(filters.get("location")),
            _resolve_variant(filters.get("variant")),
            _resolve_category(filters.get("category")),
            filters.get("date_from"),
            filters.get("date_to"),
        )
    if report_type == RT.SERIAL_NUMBER_HISTORY:
        return ReportsService.serial_number_history(_resolve_unit(filters.get("serial_number")))
    if report_type == RT.PRODUCTS:
        return ReportsService.products(
            filters.get("date_from"),
            filters.get("date_to"),
            _resolve_channel(filters.get("channel")),
        )
    if report_type == RT.FINANCIAL:
        return ReportsService.financial(
            filters.get("date_from"),
            filters.get("date_to"),
            _resolve_channel(filters.get("channel")),
        )

    raise ValidationError({"report_type": f"Unknown report type {report_type!r}."})


def create_export(*, report_type: str, export_format: str, filters: dict, actor):
    """Validates the filters up front (via :func:`run_report`, thrown away --
    a bad filter should fail the request, not silently produce an empty
    export), then creates the ``PENDING`` row and enqueues the render.
    Commit-first, enqueue-after (CLAUDE.md's Celery pattern), same shape as
    ``apps.products.services.bulk_generate.bulk_generate_units``.
    """
    from django.db import transaction

    from .models import ReportExport
    from .tasks import generate_report_export

    run_report(report_type, filters)  # raises ValidationError on a bad filter

    export = ReportExport.objects.create(
        report_type=report_type,
        export_format=export_format,
        filters=filters,
        requested_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    transaction.on_commit(lambda: generate_report_export.delay(export.pk))
    return export
