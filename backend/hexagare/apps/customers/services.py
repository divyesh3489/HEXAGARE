"""Read-only purchase-history aggregation for a :class:`Customer`.

Walks ``apps.sales``/``apps.products`` reverse relations at call time --
one-directional (``apps.customers`` reads those apps; neither imports
``apps.customers`` back, ``Sale.customer`` is a string FK) -- same pattern as
``Sale.amount_paid`` walking ``apps.billing`` today.
"""

from __future__ import annotations

from decimal import Decimal

from apps.products.models import SerializedUnit
from apps.sales.models import Sale

from .models import Customer

_ZERO = Decimal("0.00")

#: A sale that never reached checkout has no purchase value yet; a cancelled
#: one never completed. Every other status counts toward the customer's
#: lifetime figures.
_EXCLUDED_STATUSES = (Sale.Status.DRAFT, Sale.Status.CANCELLED)


def customer_sales(customer: Customer):
    return customer.sales.exclude(status__in=_EXCLUDED_STATUSES).select_related("sales_channel")


def total_purchases(customer: Customer) -> Decimal:
    total = _ZERO
    for sale in customer_sales(customer):
        total += sale.grand_total
    return total


def total_refunds(customer: Customer) -> Decimal:
    total = _ZERO
    for sale in customer_sales(customer):
        for return_ in sale.returns.all():
            total += return_.refund_total
    return total


def outstanding_amount(customer: Customer) -> Decimal:
    total = _ZERO
    for sale in customer_sales(customer):
        balance = sale.balance_due
        if balance > 0:
            total += balance
    return total


def serial_number_history(customer: Customer):
    """Every physical unit ever sold to this customer, most recent first."""
    return (
        SerializedUnit.objects.filter(sale_line_unit__sale_line__sale__customer=customer)
        .select_related("variant", "location")
        .order_by("-sale_line_unit__created_at")
    )
