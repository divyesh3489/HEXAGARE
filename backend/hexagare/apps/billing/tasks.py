"""Celery tasks for the billing app.

``render_invoice_pdf`` renders an :class:`~apps.billing.models.Invoice`'s PDF
and stores it on ``STORAGES["default"]`` (S3 in staging/production, the local
media volume in development). Enqueued via ``transaction.on_commit`` right
after :class:`apps.billing.services.checkout.CompleteSaleService` commits the
sale -- CLAUDE.md's Celery pattern: commit the business transaction first,
enqueue after.

A render failure never touches the sale -- the units are already sold and the
payment already recorded by the time this runs. It just marks the invoice
``FAILED`` with the error; same recoverable-by-design shape as
``apps.products.tasks.render_label_pdf``.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def render_invoice_pdf(invoice_id: int) -> str:
    from .models import Invoice
    from .services.invoice_pdf import build_invoice_pdf

    try:
        invoice = Invoice.objects.select_related("sale__sales_channel").get(pk=invoice_id)
    except Invoice.DoesNotExist:
        return "missing"

    try:
        pdf_bytes = build_invoice_pdf(invoice)
    except Exception as exc:  # noqa: BLE001 - record and stop; recoverable
        logger.exception("Invoice PDF render failed for invoice %s", invoice_id)
        Invoice.objects.filter(pk=invoice_id).update(
            status=Invoice.Status.FAILED,
            error_message=str(exc)[:2000],
        )
        return "failed"

    if invoice.pdf_file:
        invoice.pdf_file.delete(save=False)
    invoice.pdf_file.save(
        f"{invoice.invoice_number}.pdf", ContentFile(pdf_bytes), save=False
    )
    invoice.status = Invoice.Status.READY
    invoice.pdf_generated_at = timezone.now()
    invoice.error_message = ""
    invoice.save(
        update_fields=["pdf_file", "status", "pdf_generated_at", "error_message", "updated_at"]
    )
    return "ready"
