"""Sales domain models: channel-agnostic ``Sale`` / ``SaleLine`` over any
:class:`SalesChannel` (ADR-012).

- :class:`SalesChannel` -- a data-driven sales channel (Amazon, Offline, ...).
  Seed rows come from a ``post_migrate`` hook (:mod:`apps.sales.bootstrap`);
  a new channel is just a new row, never a code branch.
- :class:`Sale` -- one generic order/sale record for every channel. No
  per-channel schema: channel-specific vocabulary (e.g. Amazon's shipment
  states) lives as *values* of the single :attr:`Sale.status` field, not as
  separate fields or subclasses. ``subtotal``/``discount_total``/
  ``tax_total``/``grand_total`` are a rebuildable cache -- written only by
  :class:`apps.sales.services.totals.SalesTotalsService`.
- :class:`SaleLine` -- one line of a sale. ``unit_price``/``tax_rate`` are a
  snapshot of the variant's effective pricing at the moment the line was
  added (prices can change later; a placed order must not).

Reservation of specific :class:`apps.products.SerializedUnit` rows against a
line is :class:`SaleLineUnit` (Phase 8, ADR-013) -- one row per physical unit
bound to a line. Completion (selling the units, recording payment, generating
the invoice) lives in ``apps.billing`` (Phase 8), not here.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MinValueValidator
from django.db import models

_MONEY = Decimal("0.01")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0.00")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


class SalesChannel(models.Model):
    """A place a sale originates from -- Amazon, Offline, and whatever the
    business adds later. Seed rows via ``post_migrate``
    (:mod:`apps.sales.bootstrap`); extending to a new channel is a new row,
    never a code change."""

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Sale(models.Model):
    """A channel-agnostic order/sale. This *is* the "Order" of
    HEXAGARE_FEATURES.md section 27 -- one model, no per-channel schema.

    ``external_reference`` is pulled forward from Phase 9's Amazon import
    idempotency key (``(sales_channel, external_reference)``), the same way
    ``inventory.Location`` was pulled forward ahead of the Phase 4 ledger
    (ADR-007). Blank for a sale with no external order id (e.g. a manually
    created offline sale) -- the uniqueness constraint below only applies once
    it's set.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        RESERVED = "RESERVED", "Reserved"
        SHIPPED = "SHIPPED", "Shipped"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        DELIVERED = "DELIVERED", "Delivered"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        RETURNED = "RETURNED", "Returned"
        REFUNDED = "REFUNDED", "Refunded"

    #: Statuses a sale's lines may still be edited in.
    EDITABLE_STATUSES = (Status.DRAFT,)

    sales_channel = models.ForeignKey(
        SalesChannel,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales",
        help_text="Who this sale is for. Null is a true walk-in with no customer "
        "record at all (HEXAGARE_FEATURES.md section 30) -- distinct from a "
        "Customer row with type=WALK_IN, which is a lightweight name/phone on "
        "record without full registration.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    external_reference = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="The channel's own order id (e.g. an Amazon order id). Blank for a "
        "sale with no external order, such as one created directly offline.",
    )
    note = models.CharField(max_length=255, blank=True)

    # -- derived totals -- written only by SalesTotalsService (never edit directly) --
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["sales_channel", "external_reference"],
                condition=~models.Q(external_reference=""),
                name="uniq_channel_external_reference",
            ),
        ]

    def __str__(self) -> str:
        return f"Sale #{self.pk} ({self.sales_channel_id}, {self.status})"

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    @property
    def amount_paid(self) -> Decimal:
        """Sum of every :class:`~apps.billing.models.Payment` recorded against
        this sale (a refund-type row subtracts). Walked via the reverse FK
        accessor only -- ``apps.sales`` never imports ``apps.billing``
        (cross-app references stay one-directional, same reasoning as the
        string-FK convention)."""
        total = _ZERO
        for payment in self.payments.all():
            total += payment.amount if payment.type == "PAYMENT" else -payment.amount
        return total

    @property
    def balance_due(self) -> Decimal:
        return self.grand_total - self.amount_paid


class SaleLine(models.Model):
    """One line of a :class:`Sale`.

    ``unit_price``/``tax_rate`` snapshot the variant's effective pricing at
    add-time -- a placed order must not drift when the catalog price changes
    later. Pricing follows the same GST-inclusive convention as
    ``ProductVariant.base_price``/``gst_amount``: ``unit_price`` is tax
    inclusive, and the taxable value / GST are derived backward from it.
    """

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="sale_lines",
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(_ZERO)]
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=_ZERO, validators=[MinValueValidator(_ZERO)]
    )
    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=_ZERO, validators=[MinValueValidator(_ZERO)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.variant_id} on sale #{self.sale_id}"

    @property
    def gross_amount(self) -> Decimal:
        """``unit_price * quantity``, before the per-line discount."""
        return _quantize(self.unit_price * self.quantity)

    @property
    def net_amount(self) -> Decimal:
        """Tax-inclusive amount actually charged for this line (never negative)."""
        return _quantize(max(self.gross_amount - self.discount_amount, _ZERO))

    @property
    def taxable_value(self) -> Decimal:
        """The GST-exclusive value backed out of ``net_amount`` (2 dp)."""
        divisor = Decimal("1") + (self.tax_rate / _HUNDRED)
        if divisor == 0:
            return self.net_amount
        return _quantize(self.net_amount / divisor)

    @property
    def tax_amount(self) -> Decimal:
        return _quantize(self.net_amount - self.taxable_value)

    @property
    def cgst_amount(self) -> Decimal:
        """Even split of ``tax_amount`` (intra-state only -- see ADR-013)."""
        return _quantize(self.tax_amount / 2)

    @property
    def sgst_amount(self) -> Decimal:
        return _quantize(self.tax_amount - self.cgst_amount)


class SaleLineUnit(models.Model):
    """One physical :class:`~apps.products.models.SerializedUnit` bound to a
    :class:`SaleLine` (ADR-013 -- the schema decision ADR-012 deferred).

    The ``OneToOneField`` guarantees a unit is bound to at most one line
    anywhere at a time; deleting the row (on cart-removal / cancel, via
    :class:`apps.sales.services.units.SaleUnitService`) frees the unit for
    rebinding. Rows created once a sale completes are a **permanent record**
    (never deleted) -- ``apps.billing`` and, later, Phase 10 returns need to
    resolve "which sale/line did this serial sell on".
    """

    sale_line = models.ForeignKey(SaleLine, on_delete=models.CASCADE, related_name="units")
    serialized_unit = models.OneToOneField(
        "products.SerializedUnit",
        on_delete=models.PROTECT,
        related_name="sale_line_unit",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.serialized_unit_id} on line #{self.sale_line_id}"
