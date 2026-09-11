"""Billing API serializers."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.sales.models import Sale
from apps.sales.serializers import SaleDetailSerializer

from .models import Invoice, InvoiceDelivery, Payment


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
        fields = ["id", "channel", "status", "sent_at", "error_message", "created_at"]
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
