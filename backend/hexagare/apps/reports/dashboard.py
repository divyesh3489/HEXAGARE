"""``DashboardService`` -- read-only aggregation behind Phase 16's four
dashboard widget groups (HEXAGARE_FEATURES.md section 3).

One method per group, each independently callable (and so independently
cacheable by the view/frontend) -- deliberately not one combined payload.
Nothing here re-derives math another service already owns:

- :class:`apps.expenses.services.FinanceService` -- the Finance group.
- :func:`apps.inventory.services.alerts.compute_alerts` -- low/out-of-stock/
  overstock counts (Inventory group) and the low-stock list (Analytics group).
- :class:`apps.reports.services.ReportsService` -- top-selling grouping
  (Analytics group), same ``sales(group_by=...)`` the Products report uses.

Scope note: HEXAGARE_FEATURES.md section 3's Analytics list also names
"Recent barcode scans" and "Recent notifications" -- neither has a backing
data model yet (no scan-log model; ``apps.notifications`` has no models of
its own, per the Phase 15 note in CLAUDE.md). Both are left for Phase 17's
activity/audit log rather than stubbed out here.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count
from django.utils import timezone

from apps.billing.models import Return
from apps.expenses.services import FinanceService
from apps.inventory.models import InventoryTransaction
from apps.inventory.services.alerts import compute_alerts
from apps.products.models import SerializedUnit
from apps.sales.models import Sale, SaleLineUnit, SalesChannel

from .services import ReportsService

_ZERO = Decimal("0.00")
_MONEY = Decimal("0.01")

#: Same exclusion every other aggregation in the codebase uses -- a sale that
#: never reached checkout has no revenue yet, a cancelled one never completed.
_EXCLUDED_STATUSES = (Sale.Status.DRAFT, Sale.Status.CANCELLED)

#: How many rows a "recent ..." / "top ..." list carries.
_RECENT_LIMIT = 10
_TOP_LIMIT = 5

#: How many trailing days the sales trend / channel comparison chart covers.
_TREND_DAYS = 30


def _quantize(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _period_start(today: date, *, days: int | None = None, calendar: str | None = None) -> date:
    if calendar == "week":
        return today - timedelta(days=today.weekday())
    if calendar == "month":
        return today.replace(day=1)
    if calendar == "year":
        return today.replace(month=1, day=1)
    assert days is not None
    return today - timedelta(days=days - 1)


def _sales_total(
    date_from: date | None, date_to: date | None, channel: SalesChannel | None = None
) -> Decimal:
    qs = Sale.objects.exclude(status__in=_EXCLUDED_STATUSES)
    if date_from is not None:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__date__lte=date_to)
    if channel is not None:
        qs = qs.filter(sales_channel=channel)
    total = _ZERO
    for grand_total in qs.values_list("grand_total", flat=True):
        total += grand_total
    return _quantize(total)


class DashboardService:
    """Namespace of dashboard read operations. Not instantiated."""

    # -- Sales widget group --------------------------------------------- #
    @staticmethod
    def sales() -> dict:
        """A fixed, param-free snapshot -- every figure here is a running
        total or a fixed calendar window, not a user-selectable range, so
        the endpoint has a stable cache key."""
        today = timezone.localdate()

        qs = Sale.objects.exclude(status__in=_EXCLUDED_STATUSES)
        total_orders = qs.count()
        products_sold = (
            SaleLineUnit.objects.filter(sale_line__sale__in=qs)
            .values("serialized_unit__variant__product_id")
            .distinct()
            .count()
        )
        units_sold = SaleLineUnit.objects.filter(sale_line__sale__in=qs).count()

        channel_totals = {
            channel.code: _sales_total(None, None, channel)
            for channel in SalesChannel.objects.filter(is_active=True)
        }

        return {
            "total_sales": _sales_total(None, None),
            "today_sales": _sales_total(today, today),
            "weekly_sales": _sales_total(_period_start(today, calendar="week"), today),
            "monthly_sales": _sales_total(_period_start(today, calendar="month"), today),
            "yearly_sales": _sales_total(_period_start(today, calendar="year"), today),
            "by_channel": channel_totals,
            "total_orders": total_orders,
            "products_sold": products_sold,
            "units_sold": units_sold,
        }

    # -- Inventory widget group ------------------------------------------ #
    @staticmethod
    def inventory() -> dict:
        status_counts = (
            SerializedUnit.objects.values("status").order_by().annotate(count=Count("id"))
        )
        by_status: dict[str, int] = {row["status"]: row["count"] for row in status_counts}
        total = sum(by_status.values())

        alerts = compute_alerts(include_reconciliation=False)
        alert_counts = {"low_stock": 0, "out_of_stock": 0, "overstock": 0}
        for alert in alerts:
            if alert["type"] in alert_counts:
                alert_counts[alert["type"]] += 1

        status = SerializedUnit.Status
        return {
            "total_inventory": total,
            "total_serialized_units": total,
            "available_units": by_status.get(status.AVAILABLE, 0),
            "reserved_units": by_status.get(status.RESERVED, 0),
            "in_transit_units": by_status.get(status.IN_TRANSIT, 0),
            "sold_units": by_status.get(status.SOLD, 0),
            "returned_units": by_status.get(status.RETURNED, 0),
            "damaged_units": by_status.get(status.DAMAGED, 0),
            "lost_units": by_status.get(status.LOST, 0),
            "low_stock_products": alert_counts["low_stock"],
            "out_of_stock_products": alert_counts["out_of_stock"],
            "overstock_products": alert_counts["overstock"],
        }

    # -- Finance widget group --------------------------------------------- #
    @staticmethod
    def finance(date_from: date, date_to: date) -> dict:
        summary = FinanceService.summary(date_from, date_to)
        return {
            "date_from": date_from,
            "date_to": date_to,
            "revenue": summary["gross_sales"],
            "taxable_sales": summary["taxable_sales"],
            "gst_collected": summary["gst_collected"],
            "product_cost": summary["product_cost"],
            "amazon_fees": summary["amazon_fees"],
            "shipping": summary["shipping"],
            "advertising": summary["advertising"],
            "packaging": summary["packaging"],
            "other_expenses": summary["other_expenses"],
            "gross_profit": summary["gross_profit"],
            "net_profit": summary["net_profit"],
            "profit_margin": summary["profit_margin"],
        }

    # -- Analytics widget group ------------------------------------------- #
    @staticmethod
    def analytics() -> dict:
        today = timezone.localdate()
        date_from = today - timedelta(days=_TREND_DAYS - 1)

        return {
            "sales_graph": DashboardService._sales_graph(date_from, today),
            "top_selling_products": DashboardService._top_selling(date_from, today, "product"),
            "top_selling_skus": DashboardService._top_selling(date_from, today, "variant"),
            "low_stock_products": DashboardService._low_stock_list(),
            "recent_orders": DashboardService._recent_orders(),
            "recent_returns": DashboardService._recent_returns(),
            "recent_stock_movements": DashboardService._recent_stock_movements(),
        }

    @staticmethod
    def _sales_graph(date_from: date, date_to: date) -> list[dict]:
        channels = list(SalesChannel.objects.filter(is_active=True))
        sales = list(
            Sale.objects.exclude(status__in=_EXCLUDED_STATUSES)
            .filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
            .select_related("sales_channel")
        )

        by_day: dict[date, dict] = {}
        cursor = date_from
        while cursor <= date_to:
            by_day[cursor] = {
                "date": cursor,
                "total": _ZERO,
                "by_channel": {c.code: _ZERO for c in channels},
            }
            cursor += timedelta(days=1)

        for sale in sales:
            day = timezone.localtime(sale.created_at).date()
            bucket = by_day.get(day)
            if bucket is None:
                continue
            bucket["total"] += sale.grand_total
            bucket["by_channel"][sale.sales_channel.code] = (
                bucket["by_channel"].get(sale.sales_channel.code, _ZERO) + sale.grand_total
            )

        rows = []
        for day in sorted(by_day):
            bucket = by_day[day]
            rows.append(
                {
                    "date": day,
                    "total": _quantize(bucket["total"]),
                    "by_channel": {k: _quantize(v) for k, v in bucket["by_channel"].items()},
                }
            )
        return rows

    @staticmethod
    def _top_selling(date_from: date, date_to: date, group_by: str) -> list[dict]:
        _, rows = ReportsService.sales(date_from, date_to, group_by=group_by)
        rows = sorted(rows, key=lambda r: r["units_sold"], reverse=True)
        return rows[:_TOP_LIMIT]

    @staticmethod
    def _low_stock_list() -> list[dict]:
        alerts = compute_alerts(include_reconciliation=False)
        seen: set[str] = set()
        rows = []
        for alert in alerts:
            if alert["type"] not in {"low_stock", "out_of_stock"}:
                continue
            sku = alert["variant"]["sku"]
            if sku in seen:
                continue
            seen.add(sku)
            rows.append(
                {
                    "sku": sku,
                    "product_name": alert["variant"]["product_name"],
                    "available": alert["available"],
                    "type": alert["type"],
                }
            )
            if len(rows) >= _RECENT_LIMIT:
                break
        return rows

    @staticmethod
    def _recent_orders() -> list[dict]:
        sales = (
            Sale.objects.exclude(status__in=_EXCLUDED_STATUSES)
            .select_related("sales_channel", "customer")
            .order_by("-created_at")[:_RECENT_LIMIT]
        )
        return [
            {
                "id": sale.id,
                "channel": sale.sales_channel.code,
                "customer_name": sale.customer.name if sale.customer_id else None,
                "grand_total": sale.grand_total,
                "status": sale.status,
                "created_at": sale.created_at,
            }
            for sale in sales
        ]

    @staticmethod
    def _recent_returns() -> list[dict]:
        returns = Return.objects.select_related("sale").order_by("-created_at")[:_RECENT_LIMIT]
        return [
            {
                "id": ret.id,
                "sale_id": ret.sale_id,
                "reason": ret.reason,
                "refund_total": ret.refund_total,
                "created_at": ret.created_at,
            }
            for ret in returns
        ]

    @staticmethod
    def _recent_stock_movements() -> list[dict]:
        movements = (
            InventoryTransaction.objects.select_related("variant__product", "location")
            .order_by("-created_at")[:_RECENT_LIMIT]
        )
        return [
            {
                "id": txn.id,
                "kind": txn.kind,
                "sku": txn.variant.sku,
                "product_name": txn.variant.product.name,
                "location": txn.location.name,
                "quantity": txn.quantity,
                "created_at": txn.created_at,
            }
            for txn in movements
        ]
