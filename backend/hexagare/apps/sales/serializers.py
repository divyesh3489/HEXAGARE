"""Sales API serializers.

``SaleLine`` is never created/updated through the top-level ``ModelSerializer``
machinery -- ``SaleLineWriteSerializer`` (a plain ``Serializer``) validates the
input for the ``lines`` actions on ``SaleViewSet``, which snapshot pricing and
call ``SalesTotalsService`` themselves (see ``views.py``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.customers.models import Customer
from apps.products.models import Product, ProductVariant

from .models import Sale, SaleLine, SalesChannel
from .services.totals import SalesTotalsService


class SalesChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesChannel
        fields = ["id", "code", "name", "is_active", "created_at", "updated_at"]


class SaleLineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    gross_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    taxable_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SaleLine
        fields = [
            "id",
            "variant",
            "sku",
            "product_name",
            "quantity",
            "unit_price",
            "tax_rate",
            "discount_amount",
            "gross_amount",
            "net_amount",
            "taxable_value",
            "tax_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["unit_price", "tax_rate"]


class SaleListSerializer(serializers.ModelSerializer):
    """Light shape for the Orders list -- no nested lines."""

    sales_channel_code = serializers.CharField(source="sales_channel.code", read_only=True)
    sales_channel_name = serializers.CharField(source="sales_channel.name", read_only=True)
    customer_name = serializers.SerializerMethodField()
    line_count = serializers.IntegerField(source="lines.count", read_only=True)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "sales_channel",
            "sales_channel_code",
            "sales_channel_name",
            "customer",
            "customer_name",
            "status",
            "external_reference",
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

    def get_customer_name(self, obj: Sale) -> str | None:
        return obj.customer.name if obj.customer_id else None


class SaleDetailSerializer(SaleListSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)

    class Meta(SaleListSerializer.Meta):
        fields = SaleListSerializer.Meta.fields + ["note", "lines"]


class SaleLineWriteSerializer(serializers.Serializer):
    """Input for ``POST /sales/{id}/lines/`` and the create-time ``lines``
    convenience list. Snapshots pricing from the variant; ``unit_price`` may
    be overridden (e.g. a manual discount at the point of sale), ``tax_rate``
    is always the variant's own -- it is never client-supplied."""

    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    quantity = serializers.IntegerField(min_value=1, default=1)
    unit_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False
    )
    discount_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )

    def validate_variant(self, variant: ProductVariant) -> ProductVariant:
        if variant.effective_status != Product.Status.ACTIVE:
            raise serializers.ValidationError(
                f"{variant.sku} is {variant.effective_status}, not available for sale."
            )
        return variant

    def create_line(self, sale: Sale) -> SaleLine:
        data = self.validated_data
        variant = data["variant"]
        unit_price = data.get("unit_price")
        if unit_price is None:
            unit_price = variant.effective_selling_price
        return SaleLine.objects.create(
            sale=sale,
            variant=variant,
            quantity=data["quantity"],
            unit_price=unit_price,
            tax_rate=variant.effective_tax_rate,
            discount_amount=data["discount_amount"],
        )


class SaleLineUpdateSerializer(serializers.Serializer):
    """Input for ``PATCH /sales/{id}/lines/{line_id}/``. Only quantity and the
    manual per-line discount are editable after a line is added -- pricing
    stays a fixed snapshot. A ``quantity`` edit is rejected once the line has
    bound units (Phase 8, ADR-013) -- quantity must then only change via the
    ``units/`` scan-add/remove actions, which keep it in sync with the
    reserved unit count."""

    quantity = serializers.IntegerField(min_value=1, required=False)
    discount_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False
    )

    def apply(self, line: SaleLine) -> SaleLine:
        data = self.validated_data
        if "quantity" in data and line.units.exists() and data["quantity"] != line.units.count():
            raise serializers.ValidationError(
                {
                    "quantity": "This line has scanned/reserved units bound to it -- "
                    "change its quantity via the units add/remove actions instead."
                }
            )
        for field, value in data.items():
            setattr(line, field, value)
        line.save(update_fields=[*data.keys(), "updated_at"])
        return line


class SaleCreateSerializer(serializers.ModelSerializer):
    """Input for ``POST /sales/``. ``lines`` is an optional convenience for
    creating a sale with its lines in one request; each entry is validated the
    same way as the ``lines`` action."""

    external_reference = serializers.CharField(required=False, allow_blank=True, max_length=64)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    lines = serializers.ListField(child=serializers.DictField(), required=False, write_only=True)

    class Meta:
        model = Sale
        fields = ["sales_channel", "customer", "external_reference", "note", "lines"]
        # DRF's auto-generated UniqueTogetherValidator (from the model's
        # conditional UniqueConstraint) would require external_reference on
        # every create, even though it's optional -- validate() below does
        # the real (channel, reference) uniqueness check instead.
        validators = []

    def validate_lines(self, value):
        validated = []
        for entry in value:
            line_serializer = SaleLineWriteSerializer(data=entry)
            line_serializer.is_valid(raise_exception=True)
            validated.append(line_serializer)
        return validated

    def validate(self, attrs):
        channel = attrs.get("sales_channel")
        reference = attrs.get("external_reference")
        if channel and reference and Sale.objects.filter(
            sales_channel=channel, external_reference=reference
        ).exists():
            raise serializers.ValidationError(
                {"external_reference": "A sale with this reference already exists on this channel."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        line_serializers = validated_data.pop("lines", [])
        sale = Sale.objects.create(**validated_data)
        for line_serializer in line_serializers:
            line_serializer.create_line(sale)
        if line_serializers:
            SalesTotalsService.recalculate(sale)
        return sale


class SaleUnitAddSerializer(serializers.Serializer):
    """Input for ``POST /sales/{id}/units/`` (Phase 8) -- exactly one of
    ``code`` (a scanned/typed serial or barcode -- the exact-unit flow,
    HEXAGARE_FEATURES.md section 24) or ``variant`` (a product-search add,
    which lets :class:`~apps.sales.services.units.SaleUnitService` pick the
    oldest available unit). Resolution/reservation happens in the service,
    not here -- this only shapes the input."""

    code = serializers.CharField(required=False, allow_blank=False)
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(), required=False
    )

    def validate(self, attrs):
        if bool(attrs.get("code")) == bool(attrs.get("variant")):
            raise serializers.ValidationError("Provide exactly one of `code` or `variant`.")
        return attrs


class SaleCustomerSerializer(serializers.Serializer):
    """Input for ``POST /sales/{id}/customer/`` -- attach, change, or clear
    (``customer: null``) the customer on a sale. Not tied to cart
    editability: linking a customer is metadata, not a line/total change."""

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
