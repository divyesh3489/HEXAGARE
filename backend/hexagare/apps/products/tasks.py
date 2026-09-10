"""Celery tasks for the products app.

``render_label_pdf`` renders a :class:`~apps.products.models.LabelBatch`'s label
sheet and stores it on ``STORAGES["default"]`` (S3 in staging/production, the
local media volume in development). It is enqueued *after* the unit-creation
transaction commits (``apps.products.services.bulk_generate``) -- CLAUDE.md's
Celery pattern.

A failure here never affects the already-created units: the batch is marked
``FAILED`` with the error recorded, and an operator re-runs it with the
``regenerate`` action (section 11 -- "if PDF generation fails, units still exist
and the PDF can be regenerated/reprinted").
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def render_label_pdf(batch_id: int) -> str:
    from .models import LabelBatch
    from .services.labels import build_label_pdf

    try:
        batch = LabelBatch.objects.select_related(
            "variant__product", "location", "label_size"
        ).get(pk=batch_id)
    except LabelBatch.DoesNotExist:
        return "missing"

    try:
        pdf_bytes = build_label_pdf(batch)
    except Exception as exc:  # noqa: BLE001 - record and stop; operator re-runs
        logger.exception("Label PDF render failed for batch %s", batch_id)
        LabelBatch.objects.filter(pk=batch_id).update(
            status=LabelBatch.Status.FAILED,
            error_message=str(exc)[:2000],
        )
        return "failed"

    if batch.pdf_file:
        # A re-render (``regenerate``) replaces the previous sheet.
        batch.pdf_file.delete(save=False)
    batch.pdf_file.save(f"batch-{batch_id}.pdf", ContentFile(pdf_bytes), save=False)
    batch.status = LabelBatch.Status.READY
    batch.pdf_generated_at = timezone.now()
    batch.error_message = ""
    batch.save(
        update_fields=[
            "pdf_file",
            "status",
            "pdf_generated_at",
            "error_message",
            "updated_at",
        ]
    )
    return "ready"
