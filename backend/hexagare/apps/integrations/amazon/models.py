"""Amazon integration domain models (Phase 9, ADR-014): CSV order import,
Amazon-SKU-to-variant mapping, a configurable fee structure, and per-line
settlement financials.

These live in an ``amazon`` subpackage of the single ``apps.integrations``
Django app (not a separate app) -- ``apps/integrations/models.py`` imports
the classes below so Django's app registry picks them up under the
``integrations`` app label (a model's containing app is resolved from its
module path, and ``apps.integrations.amazon.models`` starts with the app's
own ``apps.integrations`` name). Migrations live at the app root
(``apps/integrations/migrations/``), the normal Django location.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

_ZERO = Decimal("0.00")
_MONEY = Decimal("0.01")
_HUNDRED = Decimal("100")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


class AmazonSkuMapping(models.Model):
    """Amazon SKU -> Hexagare :class:`~apps.products.models.ProductVariant`.

    The importer resolves every CSV row's ``amazon_sku`` through this table;
    an unmapped SKU fails that order (see
    :mod:`apps.integrations.amazon.services.importer`). A row is
    auto-created only when the Amazon SKU exactly matches an existing
    ``ProductVariant.sku`` -- anything else needs an explicit mapping here
    (the SKU Mapping UI), so a typo'd or genuinely different Amazon SKU never
    silently attaches to the wrong variant.
    """

    amazon_sku = models.CharField(max_length=64, unique=True)
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="amazon_sku_mappings",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["amazon_sku"]

    def __str__(self) -> str:
        return f"{self.amazon_sku} -> {self.variant_id}"


class AmazonFeeConfig(models.Model):
    """A configurable Amazon fee/charge rule (HEXAGARE_FEATURES.md section 22
    -- "Amazon fees and charges must be configurable because rates can
    change").

    Consulted by the importer **only as a fallback** when a CSV row leaves
    that fee column blank -- an actual figure from Amazon's own report always
    wins (see ``docs/amazon-order-import.md``). Matching precedence at import
    time: product-specific > category-specific > channel-wide, narrowed to
    rows whose ``effective_from``/``effective_to`` covers the order date.
    """

    class FeeType(models.TextChoices):
        PERCENTAGE = "PERCENTAGE", "Percentage of taxable value"
        FIXED = "FIXED", "Fixed amount"

    class FeeName(models.TextChoices):
        REFERRAL = "REFERRAL", "Referral fee"
        CLOSING = "CLOSING", "Closing fee"
        FULFILLMENT = "FULFILLMENT", "Fulfillment fee"
        SHIPPING = "SHIPPING", "Shipping / courier"
        ADVERTISING = "ADVERTISING", "Advertising"
        OTHER = "OTHER", "Other charges"

    fee_name = models.CharField(max_length=16, choices=FeeName.choices)
    fee_type = models.CharField(max_length=10, choices=FeeType.choices)
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(_ZERO)],
        help_text="A percentage (0-100) when fee_type=PERCENTAGE, else a fixed rupee amount.",
    )
    sales_channel = models.ForeignKey(
        "sales.SalesChannel",
        on_delete=models.CASCADE,
        related_name="amazon_fee_configs",
    )
    applicable_category = models.ForeignKey(
        "products.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="amazon_fee_configs",
        help_text="Leave blank to apply to every category.",
    )
    applicable_product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="amazon_fee_configs",
        help_text="Leave blank to apply to every product. Takes precedence over category.",
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True, help_text="Blank = open-ended.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fee_name", "-effective_from"]

    def __str__(self) -> str:
        return f"{self.fee_name} ({self.fee_type}) from {self.effective_from}"

    def covers(self, order_date) -> bool:
        if self.effective_from > order_date:
            return False
        return self.effective_to is None or self.effective_to >= order_date

    @classmethod
    def active_between(cls, order_date):
        return cls.objects.filter(is_active=True, effective_from__lte=order_date).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=order_date)
        )


class AmazonOrderSettlement(models.Model):
    """Amazon-specific per-line financials for one imported order line
    (HEXAGARE_FEATURES.md sections 20-21) -- kept off the generic
    ``Sale``/``SaleLine`` per CLAUDE.md's channel-specific-data pattern (same
    reasoning as any future channel's own settlement model).

    Keyed ``(sale, sku)`` for idempotent re-import. ``sku`` is the Amazon SKU
    exactly as imported, kept verbatim for audit even though it resolves to
    ``variant``. ``selling_price``/``gst_amount``/``taxable_value`` are line
    totals (already multiplied by quantity); the fee/charge columns are the
    line totals Amazon reports (or the configured fallback), not per-unit.
    """

    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.CASCADE, related_name="amazon_settlements"
    )
    sku = models.CharField(max_length=64)
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="amazon_settlements",
    )
    quantity = models.PositiveIntegerField()

    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)

    referral_fee = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    closing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    fulfillment_fee = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    advertising_cost = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    other_charges = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=_ZERO)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["sale", "sku"], name="uniq_amazon_settlement_sale_sku"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} settlement on sale #{self.sale_id}"

    @property
    def amazon_fees_total(self) -> Decimal:
        return _quantize(self.referral_fee + self.closing_fee + self.fulfillment_fee)

    @property
    def total_deductions(self) -> Decimal:
        """Every fee/charge/refund subtracted from the selling price."""
        return _quantize(
            self.amazon_fees_total
            + self.shipping_cost
            + self.advertising_cost
            + self.other_charges
            + self.refund_amount
        )

    @property
    def settlement_amount(self) -> Decimal:
        """What actually lands in the bank: selling price minus every deduction."""
        return _quantize(self.selling_price - self.total_deductions)

    @property
    def net_revenue(self) -> Decimal:
        """Taxable (GST-exclusive) revenue minus every deduction, before product cost."""
        return _quantize(self.taxable_value - self.total_deductions)

    @property
    def product_cost(self) -> Decimal:
        return _quantize(self.variant.effective_purchase_price * self.quantity)

    @property
    def net_profit(self) -> Decimal:
        """HEXAGARE_FEATURES.md section 21: taxable value - fees - courier -
        advertising - other charges - refunds - product cost."""
        return _quantize(self.net_revenue - self.product_cost)


class AmazonImportBatch(models.Model):
    """One CSV upload/import run.

    Same ``PENDING``/``…``/``READY`` async-job shape as
    :class:`apps.products.models.LabelBatch`, but a CSV spans many orders and
    is naturally partial-success, hence the extra ``PROCESSING``/``PARTIAL``
    values and the ``error_log`` (one entry per failed row or order,
    ``{"row"|"order_id": ..., "message": ...}``) instead of a single
    ``error_message``.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        READY = "READY", "Ready"
        PARTIAL = "PARTIAL", "Partially imported"
        FAILED = "FAILED", "Failed"

    file = models.FileField(upload_to="amazon-imports/")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    total_rows = models.PositiveIntegerField(default=0)
    total_orders = models.PositiveIntegerField(default=0)
    orders_created = models.PositiveIntegerField(default=0)
    orders_updated = models.PositiveIntegerField(default=0)
    orders_skipped = models.PositiveIntegerField(default=0)
    orders_failed = models.PositiveIntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    error_message = models.TextField(
        blank=True, help_text="Set only on a whole-batch failure (e.g. an unreadable file)."
    )

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
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
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Import batch #{self.pk} ({self.status})"
