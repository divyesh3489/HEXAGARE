"""``CompleteSaleService`` -- the "Complete Sale" flow (HEXAGARE_FEATURES.md
section 26, rule 7).

One call always records whatever payment was tendered, then branches on
whether that's enough to cover the sale:

    Recalculate totals
        v
    Record Payment row(s)
        v
    amount_paid >= grand_total?
        NO  -> Sale.status -> RESERVED (on hold); units stay RESERVED,
               no invoice yet -- the sale can be resumed later with more
               payment (``complete`` also accepts an already-``RESERVED``
               sale, not just ``DRAFT``)
        YES -> Sell every reserved unit (RESERVED/IN_TRANSIT -> SOLD, ledger
               updated), allocate the invoice number, create the Invoice
               (PENDING), Sale.status -> COMPLETED

then, on commit (only on the YES branch), enqueues the invoice PDF render
(``apps.billing.tasks.render_invoice_pdf``) -- CLAUDE.md's commit-first,
enqueue-after Celery pattern. A PDF render failure never unwinds the sale: the
units are already sold and the payment already recorded by the time the task
runs.

A "Credit/Due" payment (HEXAGARE_FEATURES.md section 23) is just another
``Payment.Method`` -- a cashier recording one for the deferred amount makes
``amount_paid`` reach the total and the sale completes normally, same as any
other method. What must never happen is treating an *unrecorded* shortfall as
paid: partial cash with nothing recorded for the rest leaves the sale on hold.

A completed sale can still carry a receivable (a ``CREDIT`` row covered the
gap at completion time, not real cash) -- :meth:`CompleteSaleService.record_payment`
is the separate path for settling that later: more ``Payment`` rows against an
already-``COMPLETED`` sale, no re-selling of units and no new invoice (the
one from completion is unchanged; its ``balance_due`` just reads lower).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.products.services.serialized_inventory import SerializedInventoryService
from apps.sales.models import Sale
from apps.sales.services.totals import SalesTotalsService

from ..models import Invoice, Payment
from .numbering import allocate_invoice_number


class CompleteSaleService:
    """Namespace for the checkout operation. Not instantiated."""

    @staticmethod
    def _validate_unit_backed(sale: Sale) -> None:
        """Every line must be fully backed by bound units -- a line built
        through the generic ``POST lines/`` endpoint (quantity, no units) is a
        draft/quote, not something that can be sold (rule 5/8 -- a sale can
        only ever move real serialized units)."""
        if not sale.lines.exists():
            raise ValidationError("Sale has no lines to complete.")
        short = [
            f"line #{line.pk} ({line.variant.sku}): {line.units.count()}/{line.quantity} units"
            for line in sale.lines.select_related("variant").all()
            if line.units.count() != line.quantity
        ]
        if short:
            raise ValidationError(
                {
                    "lines": "Every line must be fully backed by scanned/reserved units "
                    f"before completing the sale: {'; '.join(short)}."
                }
            )

    @classmethod
    @transaction.atomic
    def complete(
        cls, sale: Sale, *, payments: list[dict], actor=None
    ) -> tuple[Sale, Invoice | None]:
        """Record ``payments`` against ``sale``. Returns ``(sale, invoice)`` --
        ``invoice`` is ``None`` when the payment doesn't cover the total yet
        (the sale is left ``RESERVED``, on hold)."""
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.status not in (Sale.Status.DRAFT, Sale.Status.RESERVED):
            raise ValidationError(
                f"Sale is {sale.status} -- it cannot be completed or held for payment."
            )

        cls._validate_unit_backed(sale)
        sale = SalesTotalsService.recalculate(sale)

        from apps.accounts.audit import log_activity
        from apps.accounts.models import AuditLogEntry

        for entry in payments:
            payment = Payment.objects.create(
                sale=sale,
                method=entry["method"],
                amount=entry["amount"],
                reference=entry.get("reference", ""),
                note=entry.get("note", ""),
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )
            log_activity(actor=actor, action=AuditLogEntry.Action.PAYMENT_RECORDED, target=payment)

        amount_paid: Decimal = sale.amount_paid  # re-reads Payment rows, incl. those just created

        if amount_paid < sale.grand_total:
            sale.status = Sale.Status.RESERVED
            sale.save(update_fields=["status", "updated_at"])
            return sale, None

        for line in sale.lines.prefetch_related("units__serialized_unit"):
            for join in line.units.all():
                SerializedInventoryService.sell(
                    join.serialized_unit, actor=actor, note=f"Sale #{sale.pk}"
                )

        invoice_number, sequence = allocate_invoice_number()
        invoice = Invoice.objects.create(
            sale=sale,
            invoice_number=invoice_number,
            sequence=sequence,
            subtotal=sale.subtotal,
            discount_total=sale.discount_total,
            tax_total=sale.tax_total,
            grand_total=sale.grand_total,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )

        sale.status = Sale.Status.COMPLETED
        sale.save(update_fields=["status", "updated_at"])

        log_activity(actor=actor, action=AuditLogEntry.Action.INVOICE_CREATED, target=invoice)

        from ..tasks import render_invoice_pdf

        transaction.on_commit(lambda: render_invoice_pdf.delay(invoice.pk))
        return sale, invoice

    @staticmethod
    @transaction.atomic
    def record_payment(sale: Sale, *, payments: list[dict], actor=None) -> Invoice:
        """Settle more of a **completed** sale's receivable (e.g. the
        customer paying back a ``CREDIT`` balance). Adds ``Payment`` rows
        only -- the units are already ``SOLD`` and the invoice already
        exists; neither is touched here."""
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.status != Sale.Status.COMPLETED:
            raise ValidationError(
                f"Sale is {sale.status} -- only a completed sale's balance can be settled "
                "this way (a DRAFT/RESERVED sale uses `complete` instead)."
            )
        if not payments:
            raise ValidationError({"payments": "At least one payment entry is required."})

        from apps.accounts.audit import log_activity
        from apps.accounts.models import AuditLogEntry

        for entry in payments:
            payment = Payment.objects.create(
                sale=sale,
                method=entry["method"],
                amount=entry["amount"],
                reference=entry.get("reference", ""),
                note=entry.get("note", ""),
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )
            log_activity(actor=actor, action=AuditLogEntry.Action.PAYMENT_RECORDED, target=payment)

        return Invoice.objects.get(sale=sale)


__all__ = ["CompleteSaleService"]
