"""Inventory domain models.

Phase 3 introduces only :class:`Location` -- the generic stock-holding place a
serialized unit lives at (``apps.products.SerializedUnit.location``). The stock
ledger (``InventoryBalance`` + ``InventoryTransaction`` + ``InventoryService``)
lands in Phase 4; see ADR-007 for why ``Location`` is pulled forward.

``kind`` classifies a location for reporting only -- never branch on it in
business logic, and never hardcode a location *name*.
"""

from __future__ import annotations

from django.db import models


class Location(models.Model):
    """A place that holds stock: a warehouse, a marketplace, a retail counter.

    Seed rows (Warehouse / Amazon / Offline) are created by a ``post_migrate``
    hook (:mod:`apps.inventory.bootstrap`). Businesses add their own via the
    admin; the write API arrives with the Phase 4 ledger.
    """

    class Kind(models.TextChoices):
        WAREHOUSE = "warehouse", "Warehouse"
        MARKETPLACE = "marketplace", "Marketplace"
        RETAIL = "retail", "Retail"
        OTHER = "other", "Other"

    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=40, unique=True)
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.OTHER,
        help_text="Classification for reporting only -- do not branch on it.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
