"""Expenses + finance API serializers (Phase 13)."""

from __future__ import annotations

from rest_framework import serializers

from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    sales_channel_code = serializers.SerializerMethodField()
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id",
            "category",
            "category_display",
            "sales_channel",
            "sales_channel_code",
            "amount",
            "expense_date",
            "note",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_sales_channel_code(self, obj: Expense) -> str | None:
        return obj.sales_channel.code if obj.sales_channel_id else None

    def get_created_by_email(self, obj: Expense) -> str | None:
        return obj.created_by.email if obj.created_by_id else None


class FinanceSummarySerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    channel = serializers.CharField(allow_null=True)
    gross_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxable_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    gst_collected = serializers.DecimalField(max_digits=12, decimal_places=2)
    discounts = serializers.DecimalField(max_digits=12, decimal_places=2)
    refunds = serializers.DecimalField(max_digits=12, decimal_places=2)
    product_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    amazon_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    shipping = serializers.DecimalField(max_digits=12, decimal_places=2)
    advertising = serializers.DecimalField(max_digits=12, decimal_places=2)
    packaging = serializers.DecimalField(max_digits=12, decimal_places=2)
    other_expenses = serializers.DecimalField(max_digits=12, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    profit_margin = serializers.DecimalField(max_digits=12, decimal_places=2)


class UnitProfitSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    sale_id = serializers.IntegerField()
    sales_channel = serializers.CharField()
    purchase_cost = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxable_selling_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    amazon_fees = serializers.DecimalField(max_digits=12, decimal_places=2)
    courier = serializers.DecimalField(max_digits=12, decimal_places=2)
    advertising = serializers.DecimalField(max_digits=12, decimal_places=2)
    other_charges = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_profit = serializers.DecimalField(max_digits=12, decimal_places=2)


class DateRangeQuerySerializer(serializers.Serializer):
    """Validates the ``date_from``/``date_to`` query params every finance
    endpoint requires -- explicit, no implicit default window."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    channel = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs
