"""Reports + exports API (Phase 14).

- ``reports/sales/``                    -- ``reports.view``
- ``reports/inventory/``                -- ``reports.view`` (``?view=movement``
  switches to the stock-movement ledger view)
- ``reports/serial-numbers/``           -- ``reports.view``
- ``reports/serial-number-history/``    -- ``reports.view`` (``?serial_number=``)
- ``reports/products/``                 -- ``reports.view``
- ``reports/financial/``                -- ``reports.view``
- ``reports/exports/``                  -- create/list/retrieve, ``reports.export``
- ``reports/exports/{id}/download/``    -- binary download once READY, ``reports.export``
"""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.accounts.permissions import require
from apps.common.renderers import BinaryRenderer

from .models import ReportExport
from .serializers import (
    DateRangeChannelQuerySerializer,
    InventoryQuerySerializer,
    ReportExportCreateSerializer,
    ReportExportSerializer,
    ReportResultSerializer,
    SalesQuerySerializer,
    SerialNumberHistoryQuerySerializer,
    SerialNumbersQuerySerializer,
)
from .services import run_report

_VIEW = "reports.view"
_EXPORT = "reports.export"


class ReportsViewSet(GenericViewSet):
    """No ``queryset`` -- every action computes its response from
    :func:`apps.reports.services.run_report` rather than a model queryset."""

    permission_classes = [require(_VIEW)]
    serializer_class = ReportResultSerializer

    @staticmethod
    def _respond(report_type: str, query_serializer_cls, request) -> Response:
        query = query_serializer_cls(data=request.query_params)
        query.is_valid(raise_exception=True)
        summary, rows = run_report(report_type, dict(query.validated_data))
        return Response({"summary": summary, "rows": rows})

    @extend_schema(responses=ReportResultSerializer)
    @action(detail=False, methods=["get"])
    def sales(self, request):
        return self._respond(ReportExport.ReportType.SALES, SalesQuerySerializer, request)

    @extend_schema(responses=ReportResultSerializer)
    @action(detail=False, methods=["get"])
    def inventory(self, request):
        return self._respond(ReportExport.ReportType.INVENTORY, InventoryQuerySerializer, request)

    @extend_schema(responses=ReportResultSerializer)
    @action(detail=False, methods=["get"], url_path="serial-numbers")
    def serial_numbers(self, request):
        return self._respond(
            ReportExport.ReportType.SERIAL_NUMBERS, SerialNumbersQuerySerializer, request
        )

    @extend_schema(responses=ReportResultSerializer)
    @action(detail=False, methods=["get"], url_path="serial-number-history")
    def serial_number_history(self, request):
        return self._respond(
            ReportExport.ReportType.SERIAL_NUMBER_HISTORY,
            SerialNumberHistoryQuerySerializer,
            request,
        )

    @extend_schema(responses=ReportResultSerializer)
    @action(detail=False, methods=["get"])
    def products(self, request):
        return self._respond(
            ReportExport.ReportType.PRODUCTS, DateRangeChannelQuerySerializer, request
        )

    @extend_schema(responses=ReportResultSerializer)
    @action(detail=False, methods=["get"])
    def financial(self, request):
        return self._respond(
            ReportExport.ReportType.FINANCIAL, DateRangeChannelQuerySerializer, request
        )


class ReportExportDownloadRenderer(BinaryRenderer):
    """Streams a ready export file with its own content type (set per-request
    in the view, since it varies with ``export_format``)."""

    format = "file"


class ReportExportViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """Export job history. ``create`` validates ``filters`` and enqueues the
    Celery render; poll ``GET {id}/`` for ``status`` PENDING -> READY/FAILED,
    then ``GET {id}/download/``."""

    queryset = ReportExport.objects.select_related("requested_by").all()
    permission_classes = [require(_EXPORT)]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        if report_type := self.request.query_params.get("report_type"):
            qs = qs.filter(report_type=report_type)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ReportExportCreateSerializer
        return ReportExportSerializer

    _CONTENT_TYPES = {
        ReportExport.ExportFormat.CSV: "text/csv",
        ReportExport.ExportFormat.XLSX: (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    }

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], renderer_classes=[ReportExportDownloadRenderer])
    def download(self, request, pk=None):
        export = self.get_object()
        if export.status != ReportExport.Status.READY or not export.file:
            raise ValidationError("This export is not ready yet.")
        with export.file.open("rb") as handle:
            data = handle.read()
        response = Response(data, content_type=self._CONTENT_TYPES[export.export_format])
        filename = export.file.name.rsplit("/", 1)[-1]
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
