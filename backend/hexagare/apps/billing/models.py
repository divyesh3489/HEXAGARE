"""Billing domain models (Phase 8, ADR-013): the pieces ADR-012 deliberately
left out of ``apps.sales`` -- ``Payment`` against a ``Sale``, the generated
``Invoice``, and ``InvoiceDelivery`` (send-status tracking, populated from
Phase 15).

Sale completion -- selling the reserved units, recording payment, allocating
the invoice number and creating the ``Invoice`` row, all atomically -- lives
in :mod:`apps.billing.services.checkout`, not here.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

_ZERO = Decimal("0.00")


class Payment(models.Model):
    """One payment (or refund) recorded against a :class:`~apps.sales.models.Sale`.

    Multiple rows per sale support split-tender ("Multiple payment methods",
    HEXAGARE_FEATURES.md section 23) and partial/credit sales -- completion
    does not require ``sum(amount) == Sale.grand_total``. ``type`` distinguishes
    a payment from a refund (``amount`` is always positive either way); Phase
    10 (Returns) reuses this model for refunds rather than inventing a new one.
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

    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    method = models.CharField(max_length=16, choices=Method.choices)
    type = models.CharField(max_length=8, choices=Type.choices, default=Type.PAYMENT)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    reference = models.CharField(
        max_length=120,
        blank=True,
        help_text="Transaction/UTR/card-auth reference, if any.",
    )
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
        return f"{self.type} {self.amount} ({self.method}) on sale #{self.sale_id}"


class Invoice(models.Model):
    """The generated invoice for a completed :class:`~apps.sales.models.Sale`.

    Created by :class:`apps.billing.services.checkout.CompleteSaleService` in
    the same atomic block as selling the units and recording payment; the PDF
    itself renders asynchronously (``apps.billing.tasks.render_invoice_pdf``,
    enqueued on commit) -- ``status``/``pdf_file``/``pdf_generated_at``/
    ``error_message`` mirror ``apps.products.models.LabelBatch``'s PENDING ->
    READY/FAILED shape.

    The four totals are a **snapshot** at completion time, not a live read of
    ``Sale`` -- an invoice is a point-in-time document (same convention as
    ``SaleLine.unit_price``/``tax_rate``).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    sale = models.OneToOneField(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="invoice",
    )
    invoice_number = models.CharField(max_length=32, unique=True, editable=False)
    #: The bare counter behind ``invoice_number`` -- lets allocation use a
    #: ``Max()`` aggregate (like ``SerializedUnit.sequence``) instead of
    #: re-parsing the formatted string.
    sequence = models.PositiveIntegerField(unique=True, editable=False)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=_ZERO)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    pdf_file = models.FileField(upload_to="invoices/", blank=True)
    pdf_generated_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

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
        return self.invoice_number

    @property
    def amount_paid(self) -> Decimal:
        """Delegates to :attr:`Sale.amount_paid` -- the sale, not the
        invoice, is the durable record of every payment (it exists before
        completion too, while a sale is on hold)."""
        return self.sale.amount_paid

    @property
    def balance_due(self) -> Decimal:
        return self.grand_total - self.amount_paid


class InvoiceDelivery(models.Model):
    """Send-status tracking for an :class:`Invoice` -- schema only in Phase 8;
    Phase 15 (Notifications) is what actually creates/updates rows here when
    the "Send invoice" action goes out over email/WhatsApp."""

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    channel = models.CharField(max_length=16, choices=Channel.choices)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "invoice deliveries"

    def __str__(self) -> str:
        return f"{self.channel} delivery for {self.invoice_id} ({self.status})"
