"""Billing API serializers."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.sales.models import Sale
from apps.sales.serializers import SaleDetailSerializer

from .models import Invoice, InvoiceDelivery, Payment, Return, ReturnUnit


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "sale",
            "method",
            "type",
            "amount",
            "reference",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class InvoiceDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceDelivery
        fields = [
            "id",
            "channel",
            "recipient",
            "status",
            "sent_at",
            "error_message",
            "created_at",
        ]
        read_only_fields = fields


class InvoiceListSerializer(serializers.ModelSerializer):
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "sale",
            "invoice_number",
            "status",
            "subtotal",
            "discount_total",
            "tax_total",
            "grand_total",
            "amount_paid",
            "balance_due",
            "pdf_generated_at",
            "error_message",
            "created_at",
        ]
        read_only_fields = fields


class InvoiceDetailSerializer(InvoiceListSerializer):
    sale_detail = SaleDetailSerializer(source="sale", read_only=True)
    payments = PaymentSerializer(source="sale.payments", many=True, read_only=True)
    deliveries = InvoiceDeliverySerializer(many=True, read_only=True)

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + ["sale_detail", "payments", "deliveries"]
        read_only_fields = fields


class InvoiceSendSerializer(serializers.Serializer):
    """Input for ``POST /billing/invoices/{id}/send/`` -- ``recipient`` is
    optional, overriding the sale's linked customer's email/phone (whichever
    the request resolves is what actually gets stored on the created
    ``InvoiceDelivery`` row)."""

    channel = serializers.ChoiceField(choices=InvoiceDelivery.Channel.choices)
    recipient = serializers.CharField(required=False, allow_blank=True, max_length=255)


class PaymentEntrySerializer(serializers.Serializer):
    """One entry of ``CheckoutSerializer.payments`` -- split-tender support
    (HEXAGARE_FEATURES.md section 23)."""

    method = serializers.ChoiceField(choices=Payment.Method.choices)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CheckoutSerializer(serializers.Serializer):
    """Input for ``POST /billing/checkout/``. ``payments`` need not sum to
    the sale's grand total -- a shortfall leaves the sale ``RESERVED`` (on
    hold) instead of completing it (``CompleteSaleService``)."""

    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())
    payments = PaymentEntrySerializer(many=True, required=False)

    def validate_payments(self, value):
        return [dict(entry) for entry in value]


class CheckoutResultSerializer(serializers.Serializer):
    """Output of ``POST /billing/checkout/`` -- ``invoice`` is ``null`` when
    the payment didn't cover the total and the sale is on hold instead."""

    sale = SaleDetailSerializer(read_only=True)
    invoice = InvoiceDetailSerializer(read_only=True, allow_null=True)


class ReturnResolveSerializer(serializers.Serializer):
    """Output of ``GET /billing/returns/resolve/?code=`` -- the read-only
    preview shown right after a scan, before the cashier confirms the
    return."""

    serial_number = serializers.CharField(source="unit.serial_number", read_only=True)
    sku = serializers.CharField(source="unit.variant.sku", read_only=True)
    product_name = serializers.CharField(source="unit.variant.product.name", read_only=True)
    sale = serializers.IntegerField(source="sale.id", read_only=True)
    sale_line = serializers.IntegerField(source="sale_line_unit.sale_line_id", read_only=True)
    unit_price = serializers.DecimalField(
        source="sale_line_unit.sale_line.unit_price", max_digits=10, decimal_places=2,
        read_only=True,
    )
    suggested_refund_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )


class ReturnUnitSerializer(serializers.ModelSerializer):
    serial_number = serializers.CharField(source="serialized_unit.serial_number", read_only=True)
    sku = serializers.CharField(source="serialized_unit.variant.sku", read_only=True)
    product_name = serializers.CharField(
        source="serialized_unit.variant.product.name", read_only=True
    )
    sale_line = serializers.IntegerField(source="sale_line_unit.sale_line_id", read_only=True)

    class Meta:
        model = ReturnUnit
        fields = [
            "id",
            "serialized_unit",
            "serial_number",
            "sku",
            "product_name",
            "sale_line",
            "refund_amount",
            "condition",
            "inspected_at",
            "inspected_by",
            "created_at",
        ]
        read_only_fields = fields


class ReturnListSerializer(serializers.ModelSerializer):
    refund_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    unit_count = serializers.IntegerField(source="units.count", read_only=True)
    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = Return
        fields = [
            "id",
            "sale",
            "reason",
            "note",
            "refund_total",
            "unit_count",
            "pending_count",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_pending_count(self, obj: Return) -> int:
        return sum(1 for unit in obj.units.all() if unit.condition == ReturnUnit.Condition.PENDING)


class ReturnDetailSerializer(ReturnListSerializer):
    sale_detail = SaleDetailSerializer(source="sale", read_only=True)
    units = ReturnUnitSerializer(many=True, read_only=True)

    class Meta(ReturnListSerializer.Meta):
        fields = ReturnListSerializer.Meta.fields + ["sale_detail", "units"]
        read_only_fields = fields


class ReturnEntrySerializer(serializers.Serializer):
    """One scanned unit for ``ReturnCreateSerializer.entries`` -- mirrors
    ``PaymentEntrySerializer``'s "list of rows" shape."""

    code = serializers.CharField()
    refund_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )


class ReturnCreateSerializer(serializers.Serializer):
    """Input for ``POST /billing/returns/`` -- every ``entries[].code`` must
    resolve to a ``SOLD`` unit on the same sale (validated by
    ``ReturnService.create``, not here)."""

    entries = ReturnEntrySerializer(many=True)
    reason = serializers.CharField(max_length=255)
    refund_method = serializers.ChoiceField(choices=Payment.Method.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_entries(self, value):
        if not value:
            raise serializers.ValidationError("At least one unit is required.")
        return [dict(entry) for entry in value]


class ReturnInspectSerializer(serializers.Serializer):
    """Input for ``POST /billing/returns/{id}/units/{unit_id}/inspect/``."""

    condition = serializers.ChoiceField(
        choices=[ReturnUnit.Condition.RESELLABLE, ReturnUnit.Condition.DAMAGED]
    )
