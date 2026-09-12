from django.contrib import admin

from .models import ReportExport


@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = ["report_type", "export_format", "status", "requested_by", "created_at"]
    list_filter = ["report_type", "export_format", "status"]
    readonly_fields = ["filters", "file", "error_message", "completed_at", "created_at"]
