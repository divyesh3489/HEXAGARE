"""Celery tasks for the Amazon integration.

``import_amazon_orders`` runs an
:class:`~apps.integrations.amazon.models.AmazonImportBatch` through
:class:`~apps.integrations.amazon.services.importer.AmazonOrderImportService`.
Enqueued via ``transaction.on_commit`` right after the batch row + uploaded
file are saved (CLAUDE.md's Celery pattern: commit the business transaction
first, enqueue after) -- never inline on the upload request.

Per-order failures are handled and recorded by
``AmazonOrderImportService.run`` itself (the batch still ends up
``READY``/``PARTIAL``). This task's own ``try/except`` only catches a
whole-batch problem (an unreadable file, a missing ``AMAZON`` sales channel,
...) that happens *before* per-order handling can even start.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def import_amazon_orders(batch_id: int) -> str:
    from .models import AmazonImportBatch
    from .services.importer import AmazonOrderImportService
    from .sources import CSVAmazonOrderSource

    try:
        batch = AmazonImportBatch.objects.get(pk=batch_id)
    except AmazonImportBatch.DoesNotExist:
        return "missing"

    batch.status = AmazonImportBatch.Status.PROCESSING
    batch.started_at = timezone.now()
    batch.save(update_fields=["status", "started_at", "updated_at"])

    try:
        with batch.file.open("rb") as fh:
            source = CSVAmazonOrderSource(fh)
            AmazonOrderImportService.run(batch, source, actor=batch.created_by)
    except Exception as exc:  # noqa: BLE001 - record and stop; operator re-uploads
        logger.exception("Amazon import failed for batch %s", batch_id)
        batch.status = AmazonImportBatch.Status.FAILED
        batch.error_message = str(exc)[:2000]
        batch.finished_at = timezone.now()
        batch.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        return "failed"

    return batch.status.lower()
