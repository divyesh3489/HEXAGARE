"""Read-only purchase-history aggregation for a :class:`Supplier`.

Walks ``apps.purchases`` reverse relations at call time -- one-directional
(``apps.suppliers`` reads ``apps.purchases``, which never imports back;
``PurchaseOrder.supplier`` is a string FK) -- same pattern as
``apps.customers.services``.
"""

from __future__ import annotations

from decimal import Decimal

from apps.purchases.models import PurchaseOrder

from .models import Supplier

_ZERO = Decimal("0.00")

#: A draft order was never placed; a cancelled one never completed. Every
#: other status counts toward the supplier's lifetime figures.
_EXCLUDED_STATUSES = (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED)


def supplier_orders(supplier: Supplier):
    return supplier.purchase_orders.exclude(status__in=_EXCLUDED_STATUSES)


def total_purchase_value(supplier: Supplier) -> Decimal:
    total = _ZERO
    for order in supplier_orders(supplier):
        total += order.grand_total
    return total


def total_paid(supplier: Supplier) -> Decimal:
    total = _ZERO
    for order in supplier_orders(supplier):
        total += order.amount_paid
    return total


def outstanding_amount(supplier: Supplier) -> Decimal:
    total = _ZERO
    for order in supplier_orders(supplier):
        balance = order.balance_due
        if balance > 0:
            total += balance
    return total
