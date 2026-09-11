"""Expense domain model (Phase 13, ADR-018).

``Expense.category`` is a fixed, closed taxonomy (HEXAGARE_FEATURES.md
section 35) -- a ``TextChoices`` field, not a separate ``ExpenseCategory``
model, since the business doesn't add categories of its own (same reasoning
as ``apps.integrations.amazon.models.AmazonFeeConfig.FeeName``). ``expense``
rows are read by ``apps.expenses.services.FinanceService`` alongside
``apps.integrations.amazon.models.AmazonOrderSettlement`` (Phase 9 Amazon
fees) and per-unit ``apps.products.models.SerializedUnit.purchase_cost``
(Phase 12) to compute gross/net profit -- see ``services.py``.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

_MIN_AMOUNT = Decimal("0.01")


class Expense(models.Model):
    class Category(models.TextChoices):
        AMAZON_FEES = "AMAZON_FEES", "Amazon fees"
        SHIPPING = "SHIPPING", "Shipping"
        COURIER = "COURIER", "Courier"
        PACKAGING = "PACKAGING", "Packaging"
        ADVERTISING = "ADVERTISING", "Advertising"
        MANUFACTURING = "MANUFACTURING", "Manufacturing"
        RAW_MATERIALS = "RAW_MATERIALS", "Raw materials"
        OFFLINE_EXPENSES = "OFFLINE_EXPENSES", "Offline expenses"
        OTHER = "OTHER", "Other expenses"

    category = models.CharField(max_length=20, choices=Category.choices)
    sales_channel = models.ForeignKey(
        "sales.SalesChannel",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="expenses",
        help_text="Optional -- which channel this expense belongs to, for "
        "channel-wise reporting. Leave blank for a general/business-wide expense.",
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(_MIN_AMOUNT)]
    )
    expense_date = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-id"]

    def __str__(self) -> str:
        return f"{self.category} {self.amount} on {self.expense_date}"
