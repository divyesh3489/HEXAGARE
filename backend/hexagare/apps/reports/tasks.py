"""Celery task for the reports app.

``generate_report_export`` renders a :class:`~apps.reports.models.ReportExport`
and stores it on ``STORAGES["default"]`` (S3 in staging/production, the local
media volume in development). Enqueued via ``transaction.on_commit`` right
after :func:`apps.reports.services.create_export` commits the row -- CLAUDE.md's
Celery pattern: commit first, enqueue after.

Same recoverable-by-design shape as ``apps.billing.tasks.render_invoice_pdf`` --
a render failure just marks the export ``FAILED`` with the error.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)

_EXTENSIONS = {"CSV": "csv", "XLSX": "xlsx"}


@shared_task
def generate_report_export(export_id: int) -> str:
    from .exporters import rows_to_csv, rows_to_xlsx
    from .models import ReportExport
    from .services import run_report

    try:
        export = ReportExport.objects.get(pk=export_id)
    except ReportExport.DoesNotExist:
        return "missing"

    try:
        summary, rows = run_report(export.report_type, export.filters)
        fieldnames = list(rows[0].keys()) if rows else list(summary.keys())
        if export.export_format == ReportExport.ExportFormat.XLSX:
            file_bytes = rows_to_xlsx(fieldnames, rows, title=export.get_report_type_display())
        else:
            file_bytes = rows_to_csv(fieldnames, rows)
    except Exception as exc:  # noqa: BLE001 - record and stop; recoverable
        logger.exception("Report export failed for export %s", export_id)
        ReportExport.objects.filter(pk=export_id).update(
            status=ReportExport.Status.FAILED,
            error_message=str(exc)[:2000],
        )
        return "failed"

    extension = _EXTENSIONS[export.export_format]
    if export.file:
        export.file.delete(save=False)
    export.file.save(
        f"{export.report_type.lower()}-{export.pk}.{extension}",
        ContentFile(file_bytes),
        save=False,
    )
    export.status = ReportExport.Status.READY
    export.completed_at = timezone.now()
    export.error_message = ""
    export.save(update_fields=["file", "status", "completed_at", "error_message"])
    return "ready"
