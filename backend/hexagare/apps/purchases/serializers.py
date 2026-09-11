"""Purchases API serializers (Phase 12).

Mirrors ``apps.sales.serializers``: ``PurchaseOrderLine`` is never created or
updated through the top-level ``ModelSerializer`` machinery --
``PurchaseOrderLineWriteSerializer`` (a plain ``Serializer``) validates the
input for the ``lines`` action / create-time convenience list, and
``PurchaseTotalsService`` is called explicitly afterwards (see ``views.py``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.inventory.models import Location
from apps.products.models import ProductVariant
from apps.suppliers.models import Supplier

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderLineUnit, PurchaseOrderPayment
from .services import PurchaseTotalsService


class PurchaseOrderLineUnitSerializer(serializers.ModelSerializer):
    serial_number = serializers.CharField(source="serialized_unit.serial_number", read_only=True)
    status = serializers.CharField(source="serialized_unit.status", read_only=True)

    class Meta:
        model = PurchaseOrderLineUnit
        fields = ["id", "serialized_unit", "serial_number", "status", "created_at"]


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    gross_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    taxable_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    quantity_pending = serializers.IntegerField(read_only=True)
    units = PurchaseOrderLineUnitSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "variant",
            "sku",
            "product_name",
            "quantity_ordered",
            "quantity_received",
            "quantity_pending",
            "unit_price",
            "tax_rate",
            "discount_amount",
            "gross_amount",
            "net_amount",
            "taxable_value",
            "tax_amount",
            "units",
            "created_at",
            "updated_at",
        ]


class PurchaseOrderPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderPayment
        fields = ["id", "method", "type", "amount", "reference", "note", "created_at"]


class PurchaseOrderListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    line_count = serializers.IntegerField(source="lines.count", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "status",
            "reference",
            "invoice_number",
            "line_count",
            "subtotal",
            "discount_total",
            "tax_total",
            "grand_total",
            "amount_paid",
            "balance_due",
            "created_at",
            "updated_at",
        ]


class PurchaseOrderDetailSerializer(PurchaseOrderListSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    payments = PurchaseOrderPaymentSerializer(many=True, read_only=True)

    class Meta(PurchaseOrderListSerializer.Meta):
        fields = PurchaseOrderListSerializer.Meta.fields + ["note", "lines", "payments"]


class PurchaseOrderLineWriteSerializer(serializers.Serializer):
    """Input for ``POST /purchases/orders/{id}/lines/`` and the create-time
    ``lines`` convenience list. Unlike a sale line, ``unit_price`` is always
    client-supplied -- a purchase price is what the supplier quoted, not a
    catalog value. ``tax_rate`` falls back to the variant's own effective
    rate when omitted."""

    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    quantity_ordered = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), required=False
    )
    discount_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )

    def create_line(self, purchase_order: PurchaseOrder) -> PurchaseOrderLine:
        data = self.validated_data
        variant = data["variant"]
        tax_rate = data.get("tax_rate")
        if tax_rate is None:
            tax_rate = variant.effective_tax_rate
        return PurchaseOrderLine.objects.create(
            purchase_order=purchase_order,
            variant=variant,
            quantity_ordered=data["quantity_ordered"],
            unit_price=data["unit_price"],
            tax_rate=tax_rate,
            discount_amount=data["discount_amount"],
        )


class PurchaseOrderLineUpdateSerializer(serializers.Serializer):
    """Input for ``PATCH /purchases/orders/{id}/lines/{line_id}/``. Only
    while the order is ``DRAFT`` -- once placed, lines are a fixed record of
    what was ordered."""

    quantity_ordered = serializers.IntegerField(min_value=1, required=False)
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), required=False
    )
    discount_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False
    )

    def apply(self, line: PurchaseOrderLine) -> PurchaseOrderLine:
        data = self.validated_data
        for field, value in data.items():
            setattr(line, field, value)
        line.save(update_fields=[*data.keys(), "updated_at"])
        return line


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    """Input for ``POST /purchases/orders/``. ``lines`` is an optional
    convenience for creating an order with its lines in one request."""

    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    lines = serializers.ListField(child=serializers.DictField(), required=False, write_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "reference", "invoice_number", "note", "lines"]

    def validate_lines(self, value):
        validated = []
        for entry in value:
            line_serializer = PurchaseOrderLineWriteSerializer(data=entry)
            line_serializer.is_valid(raise_exception=True)
            validated.append(line_serializer)
        return validated

    @transaction.atomic
    def create(self, validated_data):
        line_serializers = validated_data.pop("lines", [])
        actor = self.context["request"].user
        purchase_order = PurchaseOrder.objects.create(
            **validated_data,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        for line_serializer in line_serializers:
            line_serializer.create_line(purchase_order)
        if line_serializers:
            PurchaseTotalsService.recalculate(purchase_order)
        return purchase_order


class ReceiveStockEntrySerializer(serializers.Serializer):
    line = serializers.PrimaryKeyRelatedField(queryset=PurchaseOrderLine.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())


class ReceiveStockSerializer(serializers.Serializer):
    """Input for ``POST /purchases/orders/{id}/receive/`` -- one or more
    ``{line, quantity, location}`` entries, one call per receiving session."""

    receipts = ReceiveStockEntrySerializer(many=True)

    def validate_receipts(self, value):
        if not value:
            raise serializers.ValidationError("Provide at least one line to receive.")
        return value


class PurchaseOrderPaymentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderPayment
        fields = ["method", "type", "amount", "reference", "note"]
