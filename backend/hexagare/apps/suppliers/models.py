"""Suppliers domain model (Phase 12, ADR-017).

:class:`Supplier` is a standalone record -- purchase-history/balance figures
(total purchase value, amount paid, outstanding balance) are computed on read
in ``apps.suppliers.services`` by walking the reverse ``purchase_orders``
relation on ``apps.purchases.PurchaseOrder``, same reasoning as
``apps.customers.services`` (not cached columns here).
"""

from __future__ import annotations

from django.db import models


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    payment_terms = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
