"""Report export tracking (Phase 14, HEXAGARE_FEATURES.md sections 38-44).

Report *data* (sales/inventory/serial-number/product/financial figures) is
computed on demand by :mod:`apps.reports.services` and never stored -- same
read-only, no-cached-columns approach as ``apps.expenses.services.FinanceService``.

:class:`ReportExport` is the one thing that *is* persisted: a CSV/Excel export
job. The file renders asynchronously (``apps.reports.tasks.generate_report_export``,
enqueued on commit) -- ``status``/``file``/``completed_at``/``error_message``
mirror ``apps.billing.models.Invoice``'s PENDING -> READY/FAILED shape.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ReportExport(models.Model):
    class ReportType(models.TextChoices):
        SALES = "SALES", "Sales"
        INVENTORY = "INVENTORY", "Inventory"
        SERIAL_NUMBERS = "SERIAL_NUMBERS", "Serial numbers"
        SERIAL_NUMBER_HISTORY = "SERIAL_NUMBER_HISTORY", "Serial number history"
        PRODUCTS = "PRODUCTS", "Products"
        FINANCIAL = "FINANCIAL", "Financial"

    class ExportFormat(models.TextChoices):
        CSV = "CSV", "CSV"
        XLSX = "XLSX", "Excel"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    report_type = models.CharField(max_length=24, choices=ReportType.choices)
    export_format = models.CharField(max_length=8, choices=ExportFormat.choices)
    filters = models.JSONField(
        default=dict,
        blank=True,
        help_text="The query params the export was requested with "
        "(date_from/date_to/channel/location/group_by, per report type).",
    )

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    file = models.FileField(upload_to="reports/", blank=True)
    error_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    requested_by = models.ForeignKey(
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
        return f"{self.report_type} export #{self.pk} ({self.export_format}, {self.status})"
