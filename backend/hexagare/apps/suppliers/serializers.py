"""Suppliers API serializers (Phase 12).

``SupplierDetailSerializer`` mirrors ``apps.customers.CustomerDetailSerializer``
-- profile fields, lifetime aggregates and a light order history in one
response, matching this project's scale.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.purchases.models import PurchaseOrder

from . import services
from .models import Supplier


class SupplierListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "company", "phone", "email", "created_at"]


class SupplierOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = ["id", "status", "reference", "grand_total", "balance_due", "created_at"]


class SupplierDetailSerializer(SupplierListSerializer):
    total_purchase_value = serializers.SerializerMethodField()
    total_paid = serializers.SerializerMethodField()
    outstanding_amount = serializers.SerializerMethodField()
    orders = serializers.SerializerMethodField()

    class Meta(SupplierListSerializer.Meta):
        fields = SupplierListSerializer.Meta.fields + [
            "address",
            "gstin",
            "payment_terms",
            "notes",
            "updated_at",
            "total_purchase_value",
            "total_paid",
            "outstanding_amount",
            "orders",
        ]

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total_purchase_value(self, obj: Supplier):
        return services.total_purchase_value(obj)

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total_paid(self, obj: Supplier):
        return services.total_paid(obj)

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_outstanding_amount(self, obj: Supplier):
        return services.outstanding_amount(obj)

    @extend_schema_field(SupplierOrderSerializer(many=True))
    def get_orders(self, obj: Supplier):
        qs = obj.purchase_orders.order_by("-created_at")
        return SupplierOrderSerializer(qs, many=True).data


class SupplierWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "name",
            "company",
            "phone",
            "email",
            "address",
            "gstin",
            "payment_terms",
            "notes",
        ]
