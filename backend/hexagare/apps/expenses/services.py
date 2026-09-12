"""``FinanceService`` -- profit/finance aggregation (Phase 13, ADR-018).

Read-only: walks ``apps.sales``/``apps.billing``/``apps.integrations.amazon``
reverse relations plus this app's own ``Expense`` rows at call time (same
Python-loop aggregation style as ``apps.customers.services`` /
``apps.suppliers.services`` -- no cached columns). Nothing here writes to
another app's models.

HEXAGARE_FEATURES.md section 36's profit waterfall::

    Sales Revenue (taxable, post-discount)
          - Product cost
          - Packaging
          - Shipping
          - Amazon fees
          - Advertising
          - Other expenses
          = NET PROFIT

GST collected, discounts and refunds are reported for visibility but are
**not** subtracted again in the waterfall: ``Sale.subtotal`` (this module's
"taxable sales") is already the post-discount, GST-exclusive figure, and
refunds/GST are explicitly called out in section 36 as separate, non-profit
figures.

Report buckets fold in both a manually entered ``Expense`` row and the
matching automatic ``AmazonOrderSettlement`` column, since either can be the
source of a given cost for a given order:

- ``packaging``     = Expense[PACKAGING]
- ``shipping``      = Expense[SHIPPING] + Expense[COURIER] + settlement.shipping_cost
- ``advertising``   = Expense[ADVERTISING] + settlement.advertising_cost
- ``amazon_fees``   = Expense[AMAZON_FEES] + settlement.amazon_fees_total
- ``other_expenses``= Expense[MANUFACTURING, RAW_MATERIALS, OFFLINE_EXPENSES, OTHER]
                      + settlement.other_charges
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import ValidationError

from apps.billing.models import Return
from apps.integrations.amazon.models import AmazonOrderSettlement
from apps.products.models import SerializedUnit
from apps.sales.models import Sale, SaleLineUnit, SalesChannel

from .models import Expense

_ZERO = Decimal("0.00")
_MONEY = Decimal("0.01")

#: A sale that never reached checkout has no revenue yet; a cancelled one
#: never completed -- same exclusion apps.customers.services uses.
_EXCLUDED_STATUSES = (Sale.Status.DRAFT, Sale.Status.CANCELLED)

_OTHER_EXPENSE_CATEGORIES = (
    Expense.Category.MANUFACTURING,
    Expense.Category.RAW_MATERIALS,
    Expense.Category.OFFLINE_EXPENSES,
    Expense.Category.OTHER,
)


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _unit_cost(unit: SerializedUnit) -> Decimal:
    """A unit's cost basis: its own receiving cost (Phase 12) when set, else
    the catalog's current effective purchase price (for units that predate
    per-unit cost tracking)."""
    if unit.purchase_cost is not None:
        return unit.purchase_cost
    return unit.variant.effective_purchase_price


class FinanceService:
    """Namespace of finance/profit read operations. Not instantiated."""

    @staticmethod
    def summary(date_from: date, date_to: date, channel: SalesChannel | None = None) -> dict:
        sales = Sale.objects.exclude(status__in=_EXCLUDED_STATUSES).filter(
            created_at__date__gte=date_from, created_at__date__lte=date_to
        )
        if channel is not None:
            sales = sales.filter(sales_channel=channel)
        sale_ids = list(sales.values_list("id", flat=True))

        gross_sales = _ZERO
        taxable_sales = _ZERO
        gst_collected = _ZERO
        discounts = _ZERO
        for sale in sales:
            gross_sales += sale.grand_total
            taxable_sales += sale.subtotal
            gst_collected += sale.tax_total
            discounts += sale.discount_total

        product_cost = _ZERO
        for sale_line_unit in SaleLineUnit.objects.filter(
            sale_line__sale_id__in=sale_ids
        ).select_related("serialized_unit", "serialized_unit__variant"):
            product_cost += _unit_cost(sale_line_unit.serialized_unit)

        amazon_fees = _ZERO
        shipping = _ZERO
        advertising = _ZERO
        other_expenses = _ZERO
        for settlement in AmazonOrderSettlement.objects.filter(sale_id__in=sale_ids):
            amazon_fees += settlement.amazon_fees_total
            shipping += settlement.shipping_cost
            advertising += settlement.advertising_cost
            other_expenses += settlement.other_charges

        returns = Return.objects.filter(
            created_at__date__gte=date_from, created_at__date__lte=date_to
        )
        if channel is not None:
            returns = returns.filter(sale__sales_channel=channel)
        refunds = _ZERO
        for return_ in returns:
            refunds += return_.refund_total

        expenses = Expense.objects.filter(expense_date__gte=date_from, expense_date__lte=date_to)
        if channel is not None:
            expenses = expenses.filter(sales_channel=channel)
        by_category = {category: _ZERO for category in Expense.Category.values}
        for expense in expenses:
            by_category[expense.category] += expense.amount

        packaging = by_category[Expense.Category.PACKAGING]
        shipping += by_category[Expense.Category.SHIPPING] + by_category[Expense.Category.COURIER]
        advertising += by_category[Expense.Category.ADVERTISING]
        amazon_fees += by_category[Expense.Category.AMAZON_FEES]
        other_expenses += sum(
            (by_category[category] for category in _OTHER_EXPENSE_CATEGORIES), _ZERO
        )

        gross_profit = _quantize(taxable_sales - product_cost)
        net_profit = _quantize(
            gross_profit - packaging - shipping - amazon_fees - advertising - other_expenses
        )
        profit_margin = _quantize(net_profit / taxable_sales * 100) if taxable_sales else _ZERO

        return {
            "date_from": date_from,
            "date_to": date_to,
            "channel": channel.code if channel is not None else None,
            "gross_sales": _quantize(gross_sales),
            "taxable_sales": _quantize(taxable_sales),
            "gst_collected": _quantize(gst_collected),
            "discounts": _quantize(discounts),
            "refunds": _quantize(refunds),
            "product_cost": _quantize(product_cost),
            "amazon_fees": _quantize(amazon_fees),
            "shipping": _quantize(shipping),
            "advertising": _quantize(advertising),
            "packaging": _quantize(packaging),
            "other_expenses": _quantize(other_expenses),
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "profit_margin": profit_margin,
        }

    @staticmethod
    def by_channel(date_from: date, date_to: date) -> list[dict]:
        return [
            FinanceService.summary(date_from, date_to, channel)
            for channel in SalesChannel.objects.filter(is_active=True)
        ]

    @staticmethod
    def unit_profit(unit: SerializedUnit) -> dict:
        """Section 37: per-serial-number profit. Only meaningful for a unit
        that has actually been sold -- resolves its ``SaleLineUnit`` the same
        channel-agnostic way ``apps.billing.services.returns.ReturnService``
        does.

        The line's ``taxable_value`` (and, for an Amazon order, the matching
        ``AmazonOrderSettlement``'s fee columns) are apportioned evenly across
        the line's bound units -- there is no per-unit breakdown of either,
        same even-split reasoning ``ReturnService`` uses for refund amounts.
        """
        sale_line_unit = getattr(unit, "sale_line_unit", None)
        if sale_line_unit is None:
            raise ValidationError("This unit has not been sold -- it has no profit to track.")

        sale_line = sale_line_unit.sale_line
        sale = sale_line.sale
        unit_count = sale_line.units.count() or 1

        purchase_cost = _unit_cost(unit)
        taxable_selling_value = _quantize(sale_line.taxable_value / unit_count)

        amazon_fees = courier = advertising = other_charges = _ZERO
        settlement = AmazonOrderSettlement.objects.filter(
            sale=sale, variant=sale_line.variant
        ).first()
        if settlement is not None and settlement.quantity:
            amazon_fees = _quantize(settlement.amazon_fees_total / settlement.quantity)
            courier = _quantize(settlement.shipping_cost / settlement.quantity)
            advertising = _quantize(settlement.advertising_cost / settlement.quantity)
            other_charges = _quantize(settlement.other_charges / settlement.quantity)

        unit_profit_value = _quantize(
            taxable_selling_value - purchase_cost - amazon_fees - courier - advertising
            - other_charges
        )

        return {
            "serial_number": unit.serial_number,
            "sale_id": sale.id,
            "sales_channel": sale.sales_channel.code,
            "purchase_cost": purchase_cost,
            "taxable_selling_value": taxable_selling_value,
            "amazon_fees": amazon_fees,
            "courier": courier,
            "advertising": advertising,
            "other_charges": other_charges,
            "unit_profit": unit_profit_value,
        }
