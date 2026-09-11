"""Customers domain model (Phase 11, ADR-016).

- :class:`Customer` -- one model for both a fully registered customer and a
  walk-in (``type``). A walk-in needs only ``name`` -- every other field is
  optional regardless of type, so "registering" a walk-in later is just
  filling in more fields on the same row, not a migration to a different
  model. :attr:`Sale.customer` (``apps.sales``) is a nullable FK to this
  model -- a sale with no customer record at all (HEXAGARE_FEATURES.md
  section 30, "no registration required") is simply ``customer=None``, never
  a placeholder row.

Purchase-history/aggregate figures (total purchases, total refunds,
outstanding amount, serial-number history) are computed on read in
``apps.customers.services`` by walking the reverse ``sales`` relation --
not cached columns here, same reasoning as ``Sale.amount_paid`` /
``Return.refund_total``.
"""

from __future__ import annotations

from django.db import models


class Customer(models.Model):
    class Type(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered"
        WALK_IN = "WALK_IN", "Walk-in"

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    notes = models.TextField(blank=True)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.REGISTERED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
