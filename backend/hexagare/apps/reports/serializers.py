"""Reports + exports API serializers (Phase 14).

Each report has its own small query serializer (validates the GET params for
its data endpoint) that doubles as the validator for the same report's export
``filters`` payload on ``POST /reports/exports/`` -- one validation path for
"show me this on screen" and "export this to a file".
"""

from __future__ import annotations

import datetime

from rest_framework import serializers

from .models import ReportExport
from .services import create_export


def _json_safe(value):
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    return value


def _json_safe_filters(data: dict) -> dict:
    return {key: _json_safe(value) for key, value in data.items() if value not in (None, "")}


# --------------------------------------------------------------------------- #
# Query / filter serializers
# --------------------------------------------------------------------------- #


class DateRangeChannelQuerySerializer(serializers.Serializer):
    """Sales, Products and Financial reports: a required date range, an
    optional :class:`~apps.sales.models.SalesChannel` code."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    channel = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs


class SalesQuerySerializer(DateRangeChannelQuerySerializer):
    group_by = serializers.ChoiceField(
        choices=["product", "variant", "category", "serial"],
        required=False,
        allow_blank=True,
    )


class InventoryQuerySerializer(serializers.Serializer):
    """Current stock is point-in-time (no date range needed); the stock
    movement view (``view=movement``) is the one time-bounded sub-view."""

    location = serializers.CharField(required=False, allow_blank=True)
    variant = serializers.IntegerField(required=False)
    category = serializers.IntegerField(required=False)
    view = serializers.ChoiceField(
        choices=["balance", "movement"], required=False, default="balance"
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get("view") == "movement" and not (
            attrs.get("date_from") and attrs.get("date_to")
        ):
            raise serializers.ValidationError(
                "date_from and date_to are required for the stock movement view."
            )
        if (
            attrs.get("date_from")
            and attrs.get("date_to")
            and attrs["date_from"] > attrs["date_to"]
        ):
            raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs


class SerialNumbersQuerySerializer(serializers.Serializer):
    location = serializers.CharField(required=False, allow_blank=True)
    variant = serializers.IntegerField(required=False)
    category = serializers.IntegerField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("date_from")
            and attrs.get("date_to")
            and attrs["date_from"] > attrs["date_to"]
        ):
            raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs


class SerialNumberHistoryQuerySerializer(serializers.Serializer):
    serial_number = serializers.CharField()


class DashboardFinanceQuerySerializer(serializers.Serializer):
    """Finance dashboard widget: optional date range, defaulting to the
    current calendar month (applied in the view, not here, since a
    serializer field can't carry a "today"-relative default)."""

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("date_from")
            and attrs.get("date_to")
            and attrs["date_from"] > attrs["date_to"]
        ):
            raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs


#: One query serializer per :class:`ReportExport.ReportType` -- reused to
#: validate both a GET's query params and a POST export's ``filters``.
REPORT_QUERY_SERIALIZERS: dict[str, type[serializers.Serializer]] = {
    ReportExport.ReportType.SALES: SalesQuerySerializer,
    ReportExport.ReportType.INVENTORY: InventoryQuerySerializer,
    ReportExport.ReportType.SERIAL_NUMBERS: SerialNumbersQuerySerializer,
    ReportExport.ReportType.SERIAL_NUMBER_HISTORY: SerialNumberHistoryQuerySerializer,
    ReportExport.ReportType.PRODUCTS: DateRangeChannelQuerySerializer,
    ReportExport.ReportType.FINANCIAL: DateRangeChannelQuerySerializer,
}


# --------------------------------------------------------------------------- #
# Report result (GET responses)
# --------------------------------------------------------------------------- #


class ReportResultSerializer(serializers.Serializer):
    """The shape every ``GET /reports/<type>/`` endpoint returns --
    ``summary`` for tiles, ``rows`` for the on-screen table (and the export)."""

    summary = serializers.DictField()
    rows = serializers.ListField(child=serializers.DictField())


# --------------------------------------------------------------------------- #
# Dashboard (Phase 16) -- one loosely-typed serializer per widget group,
# matching how ReportResultSerializer above stays a DictField wrapper rather
# than pinning every aggregate field: apps.reports.dashboard.DashboardService
# is the single source of truth for the actual keys.
# --------------------------------------------------------------------------- #


class DashboardSalesSerializer(serializers.Serializer):
    total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    today_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    weekly_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    monthly_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    yearly_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    by_channel = serializers.DictField()
    total_orders = serializers.IntegerField()
    products_sold = serializers.IntegerField()
    units_sold = serializers.IntegerField()


class DashboardInventorySerializer(serializers.Serializer):
    total_inventory = serializers.IntegerField()
    total_serialized_units = serializers.IntegerField()
    available_units = serializers.IntegerField()
    reserved_units = serializers.IntegerField()
    in_transit_units = serializers.IntegerField()
    sold_units = serializers.IntegerField()
    returned_units = serializers.IntegerField()
    damaged_units = serializers.IntegerField()
    lost_units = serializers.IntegerField()
    low_stock_products = serializers.IntegerField()
    out_of_stock_products = serializers.IntegerField()
    overstock_products = serializers.IntegerField()


class DashboardFinanceSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxable_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    gst_collected = serializers.DecimalField(max_digits=12, decimal_places=2)
    product_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    amazon_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    shipping = serializers.DecimalField(max_digits=12, decimal_places=2)
    advertising = serializers.DecimalField(max_digits=12, decimal_places=2)
    packaging = serializers.DecimalField(max_digits=12, decimal_places=2)
    other_expenses = serializers.DecimalField(max_digits=12, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    profit_margin = serializers.DecimalField(max_digits=12, decimal_places=2)


class DashboardAnalyticsSerializer(serializers.Serializer):
    sales_graph = serializers.ListField(child=serializers.DictField())
    top_selling_products = serializers.ListField(child=serializers.DictField())
    top_selling_skus = serializers.ListField(child=serializers.DictField())
    low_stock_products = serializers.ListField(child=serializers.DictField())
    recent_orders = serializers.ListField(child=serializers.DictField())
    recent_returns = serializers.ListField(child=serializers.DictField())
    recent_stock_movements = serializers.ListField(child=serializers.DictField())


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #


class ReportExportSerializer(serializers.ModelSerializer):
    report_type_display = serializers.CharField(source="get_report_type_display", read_only=True)
    download_url = serializers.SerializerMethodField()
    requested_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ReportExport
        fields = [
            "id",
            "report_type",
            "report_type_display",
            "export_format",
            "filters",
            "status",
            "download_url",
            "error_message",
            "requested_by_email",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_download_url(self, obj: ReportExport) -> str | None:
        if obj.status != ReportExport.Status.READY or not obj.file:
            return None
        request = self.context.get("request")
        path = f"/api/v1/reports/exports/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request is not None else path

    def get_requested_by_email(self, obj: ReportExport) -> str | None:
        return obj.requested_by.email if obj.requested_by_id else None


class ReportExportCreateSerializer(serializers.Serializer):
    """Input for ``POST /reports/exports/``. ``filters`` is validated against
    the query serializer for the chosen ``report_type`` -- the same rules a
    GET to that report's data endpoint would apply."""

    report_type = serializers.ChoiceField(choices=ReportExport.ReportType.choices)
    export_format = serializers.ChoiceField(choices=ReportExport.ExportFormat.choices)
    filters = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        query_serializer_cls = REPORT_QUERY_SERIALIZERS[attrs["report_type"]]
        query = query_serializer_cls(data=attrs.get("filters") or {})
        query.is_valid(raise_exception=True)
        attrs["filters"] = _json_safe_filters(query.validated_data)
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return create_export(
            report_type=validated_data["report_type"],
            export_format=validated_data["export_format"],
            filters=validated_data["filters"],
            actor=request.user,
        )

    def to_representation(self, instance):
        return ReportExportSerializer(instance, context=self.context).data
