"""Inventory alerts, computed on demand from the balance cache.

Nothing here is stored -- :func:`compute_alerts` reads
:class:`~apps.inventory.models.InventoryBalance` and
:class:`~apps.inventory.models.StockLevelPolicy` and returns the alerts that
currently hold (HEXAGARE_FEATURES.md section 18):

- ``out_of_stock``  -- available quantity is 0
- ``low_stock``     -- 0 < available <= policy minimum
- ``overstock``     -- available >= policy maximum
- ``balance_mismatch`` -- the balance cache disagrees with the live serialized
  unit counts (usually because the ledger-free ``transition`` endpoint was used;
  run ``manage.py rebuild_inventory_balances`` to resync)
"""

from __future__ import annotations

from django.db import models

from ..models import InventoryBalance, InventoryTransaction, StockLevelPolicy

AVAILABLE = "AVAILABLE"


def _available_by_scope(variant_id=None, location_id=None):
    """``{(variant_id, location_id): qty}`` and ``{variant_id: qty}`` for the
    AVAILABLE bucket, from the balance cache."""
    qs = InventoryBalance.objects.filter(status=AVAILABLE)
    if variant_id is not None:
        qs = qs.filter(variant_id=variant_id)
    if location_id is not None:
        qs = qs.filter(location_id=location_id)

    per_location: dict[tuple[int, int], int] = {}
    per_variant: dict[int, int] = {}
    for row in qs.values("variant_id", "location_id").annotate(q=models.Sum("quantity")):
        per_location[(row["variant_id"], row["location_id"])] = row["q"] or 0
        per_variant[row["variant_id"]] = per_variant.get(row["variant_id"], 0) + (row["q"] or 0)
    return per_location, per_variant


def _policy_alerts(*, variant_id=None, location_id=None):
    policies = (
        StockLevelPolicy.objects.filter(is_active=True)
        .select_related("variant__product", "location")
    )
    if variant_id is not None:
        policies = policies.filter(variant_id=variant_id)
    if location_id is not None:
        policies = policies.filter(
            models.Q(location_id=location_id) | models.Q(location__isnull=True)
        )

    per_location, per_variant = _available_by_scope(variant_id, location_id)
    alerts = []
    for policy in policies:
        if policy.location_id is None:
            available = per_variant.get(policy.variant_id, 0)
            scope = None
        else:
            available = per_location.get((policy.variant_id, policy.location_id), 0)
            scope = {"id": policy.location_id, "name": policy.location.name}

        alert_type = None
        threshold = None
        if available == 0:
            alert_type, threshold = "out_of_stock", 0
        elif available <= policy.min_quantity:
            alert_type, threshold = "low_stock", policy.min_quantity
        elif policy.max_quantity is not None and available >= policy.max_quantity:
            alert_type, threshold = "overstock", policy.max_quantity
        if alert_type is None:
            continue

        alerts.append(
            {
                "type": alert_type,
                "variant": {
                    "id": policy.variant_id,
                    "sku": policy.variant.sku,
                    "product_name": policy.variant.product.name,
                },
                "location": scope,
                "available": available,
                "threshold": threshold,
                "min_quantity": policy.min_quantity,
                "max_quantity": policy.max_quantity,
            }
        )
    return alerts


def _mismatch_alerts(*, variant_id=None, location_id=None):
    """Balance-cache buckets that disagree with the live serialized unit counts."""
    from apps.products.models import SerializedUnit

    unit_qs = SerializedUnit.objects.all()
    bal_qs = InventoryBalance.objects.select_related("variant__product", "location")
    txn_qs = InventoryTransaction.objects.filter(
        serialized_unit__isnull=True, kind=InventoryTransaction.Kind.ADJUSTMENT
    )
    if variant_id is not None:
        unit_qs = unit_qs.filter(variant_id=variant_id)
        bal_qs = bal_qs.filter(variant_id=variant_id)
        txn_qs = txn_qs.filter(variant_id=variant_id)
    if location_id is not None:
        unit_qs = unit_qs.filter(location_id=location_id)
        bal_qs = bal_qs.filter(location_id=location_id)
        txn_qs = txn_qs.filter(location_id=location_id)

    expected: dict[tuple[int, int, str], int] = {}
    for row in unit_qs.values("variant_id", "location_id", "status").order_by().annotate(
        q=models.Count("id")
    ):
        expected[(row["variant_id"], row["location_id"], row["status"])] = row["q"]
    for row in txn_qs.values("variant_id", "location_id", "status").order_by().annotate(
        q=models.Sum("quantity")
    ):
        key = (row["variant_id"], row["location_id"], row["status"])
        expected[key] = max(expected.get(key, 0) + (row["q"] or 0), 0)

    alerts = []
    seen = set()
    for balance in bal_qs:
        key = (balance.variant_id, balance.location_id, balance.status)
        seen.add(key)
        want = expected.get(key, 0)
        if balance.quantity != want:
            alerts.append(
                _mismatch_row(
                    balance.variant, balance.location, balance.status, balance.quantity, want
                )
            )
    for key, want in expected.items():
        if key in seen or want == 0:
            continue
        variant, location, status = _resolve(key)
        alerts.append(_mismatch_row(variant, location, status, 0, want))
    return alerts


def _mismatch_row(variant, location, status, cached, expected):
    return {
        "type": "balance_mismatch",
        "variant": {"id": variant.id, "sku": variant.sku, "product_name": variant.product.name},
        "location": {"id": location.id, "name": location.name},
        "status": status,
        "cached": cached,
        "expected": expected,
    }


def _resolve(key):
    from apps.products.models import ProductVariant

    from ..models import Location

    variant_id, location_id, _status = key
    return (
        ProductVariant.objects.select_related("product").get(pk=variant_id),
        Location.objects.get(pk=location_id),
        _status,
    )


def compute_alerts(*, variant_id=None, location_id=None, include_reconciliation=True):
    alerts = _policy_alerts(variant_id=variant_id, location_id=location_id)
    if include_reconciliation:
        alerts += _mismatch_alerts(variant_id=variant_id, location_id=location_id)
    order = {"out_of_stock": 0, "low_stock": 1, "overstock": 2, "balance_mismatch": 3}
    alerts.sort(key=lambda a: (order.get(a["type"], 9), a["variant"]["sku"]))
    return alerts
