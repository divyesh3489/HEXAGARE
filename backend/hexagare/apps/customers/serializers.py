"""Customers API serializers (Phase 11).

``CustomerDetailSerializer`` is the one shape the frontend detail page needs
in a single request -- profile fields, the lifetime aggregates, a light order
history, and the serial-number history (HEXAGARE_FEATURES.md section 29) --
rather than a separate paginated endpoint per section, matching this
project's scale (a business with dozens/hundreds of orders per customer, not
thousands).
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.products.models import SerializedUnit
from apps.sales.models import Sale

from . import services
from .models import Customer


class CustomerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email", "type", "created_at"]


class CustomerSaleSerializer(serializers.ModelSerializer):
    sales_channel_name = serializers.CharField(source="sales_channel.name", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "sales_channel_name",
            "status",
            "grand_total",
            "balance_due",
            "created_at",
        ]


class CustomerSerialUnitSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)

    class Meta:
        model = SerializedUnit
        fields = ["id", "serial_number", "status", "sku", "product_name"]


class CustomerDetailSerializer(CustomerListSerializer):
    total_purchases = serializers.SerializerMethodField()
    total_refunds = serializers.SerializerMethodField()
    outstanding_amount = serializers.SerializerMethodField()
    sales = serializers.SerializerMethodField()
    serial_numbers = serializers.SerializerMethodField()

    class Meta(CustomerListSerializer.Meta):
        fields = CustomerListSerializer.Meta.fields + [
            "address",
            "gstin",
            "notes",
            "updated_at",
            "total_purchases",
            "total_refunds",
            "outstanding_amount",
            "sales",
            "serial_numbers",
        ]

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total_purchases(self, obj: Customer):
        return services.total_purchases(obj)

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total_refunds(self, obj: Customer):
        return services.total_refunds(obj)

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_outstanding_amount(self, obj: Customer):
        return services.outstanding_amount(obj)

    @extend_schema_field(CustomerSaleSerializer(many=True))
    def get_sales(self, obj: Customer):
        qs = obj.sales.select_related("sales_channel").order_by("-created_at")
        return CustomerSaleSerializer(qs, many=True).data

    @extend_schema_field(CustomerSerialUnitSerializer(many=True))
    def get_serial_numbers(self, obj: Customer):
        qs = services.serial_number_history(obj)
        return CustomerSerialUnitSerializer(qs, many=True).data


class CustomerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "address", "gstin", "notes", "type"]
