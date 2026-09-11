"""Purchases domain models (Phase 12, ADR-017).

- :class:`PurchaseOrder` / :class:`PurchaseOrderLine` -- a supplier order for
  one or more variants, the mirror image of ``apps.sales``'s ``Sale`` /
  ``SaleLine``. ``subtotal``/``discount_total``/``tax_total``/``grand_total``
  are a rebuildable cache, written only by
  :class:`apps.purchases.services.PurchaseTotalsService` (same shape as
  ``SalesTotalsService``). Lines are editable only while ``DRAFT``
  (:attr:`PurchaseOrder.EDITABLE_STATUSES`), same reasoning as
  ``Sale.is_editable``.
- :class:`PurchaseOrderLineUnit` -- links one received physical unit back to
  the PO line it came from, mirrors ``apps.sales.models.SaleLineUnit``. Units
  themselves are created through
  ``apps.products.services.serialized_inventory.SerializedInventoryService.generate``
  (see ``apps.purchases.services.ReceiveStockService``), never here directly.
- :class:`PurchaseOrderPayment` -- a separate model from ``apps.billing.Payment``
  (that model's ``sale`` FK is a hard-required ``PROTECT`` field tied to
  ``Sale``; extending it to also cover purchase orders would touch a tested,
  unrelated app for no shared benefit -- see ADR-017). Same method/type
  vocabulary, own table.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

_MONEY = Decimal("0.01")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0.00")


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ORDERED = "ORDERED", "Ordered"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially received"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    #: Statuses a PO's lines may still be edited in.
    EDITABLE_STATUSES = (Status.DRAFT,)
    #: Statuses receiving stock is allowed against.
    RECEIVABLE_STATUSES = (Status.ORDERED, Status.PARTIALLY_RECEIVED)
    #: Statuses that may still move to CANCELLED.
    CANCELLABLE_STATUSES = (Status.DRAFT, Status.ORDERED, Status.PARTIALLY_RECEIVED)

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    reference = models.CharField(
        max_length=64,
        blank=True,
        help_text="This business's own PO reference/number, if any.",
    )
    invoice_number = models.CharField(
        max_length=64,
        blank=True,
        help_text="The supplier's invoice number against this order.",
    )
    note = models.CharField(max_length=255, blank=True)

    # -- derived totals -- written only by PurchaseTotalsService (never edit directly) --
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)

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
        return f"PO #{self.pk} ({self.supplier_id}, {self.status})"

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    @property
    def is_receivable(self) -> bool:
        return self.status in self.RECEIVABLE_STATUSES

    @property
    def amount_paid(self) -> Decimal:
        """Sum of every :class:`PurchaseOrderPayment` recorded against this
        order (a refund-type row subtracts)."""
        total = _ZERO
        for payment in self.payments.all():
            total += (
                payment.amount
                if payment.type == PurchaseOrderPayment.Type.PAYMENT
                else -payment.amount
            )
        return total

    @property
    def balance_due(self) -> Decimal:
        return self.grand_total - self.amount_paid


class PurchaseOrderLine(models.Model):
    """One line of a :class:`PurchaseOrder`. ``unit_price``/``tax_rate`` are
    entered at order time (a supplier's quoted purchase price), not derived
    from the catalog -- the same snapshot reasoning as ``SaleLine``."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="purchase_order_lines",
    )
    quantity_ordered = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_received = models.PositiveIntegerField(default=0)
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
        return f"{self.quantity_ordered} x {self.variant_id} on PO #{self.purchase_order_id}"

    @property
    def gross_amount(self) -> Decimal:
        return _quantize(self.unit_price * self.quantity_ordered)

    @property
    def net_amount(self) -> Decimal:
        return _quantize(max(self.gross_amount - self.discount_amount, _ZERO))

    @property
    def taxable_value(self) -> Decimal:
        divisor = Decimal("1") + (self.tax_rate / _HUNDRED)
        if divisor == 0:
            return self.net_amount
        return _quantize(self.net_amount / divisor)

    @property
    def tax_amount(self) -> Decimal:
        return _quantize(self.net_amount - self.taxable_value)

    @property
    def quantity_pending(self) -> int:
        return max(self.quantity_ordered - self.quantity_received, 0)

    @property
    def is_fully_received(self) -> bool:
        return self.quantity_received >= self.quantity_ordered


class PurchaseOrderLineUnit(models.Model):
    """One physical :class:`~apps.products.models.SerializedUnit` bound to a
    :class:`PurchaseOrderLine` it was received against -- the cost-basis
    traceability link (mirrors ``apps.sales.models.SaleLineUnit``). A unit is
    only ever received once, so this is a permanent, never-deleted record."""

    line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="units"
    )
    serialized_unit = models.OneToOneField(
        "products.SerializedUnit",
        on_delete=models.PROTECT,
        related_name="purchase_order_line_unit",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.serialized_unit_id} from PO line #{self.line_id}"


class PurchaseOrderPayment(models.Model):
    """One payment (or refund) recorded against a :class:`PurchaseOrder`.

    A standalone model, not a reuse of ``apps.billing.Payment`` -- see the
    module docstring and ADR-017.
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Card"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        CREDIT = "CREDIT", "Credit / due"

    class Type(models.TextChoices):
        PAYMENT = "PAYMENT", "Payment"
        REFUND = "REFUND", "Refund"

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="payments"
    )
    method = models.CharField(max_length=16, choices=Method.choices)
    type = models.CharField(max_length=8, choices=Type.choices, default=Type.PAYMENT)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.type} {self.amount} on PO #{self.purchase_order_id}"
