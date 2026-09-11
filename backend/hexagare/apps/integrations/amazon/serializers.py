"""Amazon integration API serializers (Phase 9)."""

from __future__ import annotations

from rest_framework import serializers

from .models import AmazonFeeConfig, AmazonImportBatch, AmazonOrderSettlement, AmazonSkuMapping


class AmazonSkuMappingSerializer(serializers.ModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)

    class Meta:
        model = AmazonSkuMapping
        fields = [
            "id",
            "amazon_sku",
            "variant",
            "variant_sku",
            "product_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AmazonFeeConfigSerializer(serializers.ModelSerializer):
    sales_channel_code = serializers.CharField(source="sales_channel.code", read_only=True)
    applicable_category_name = serializers.CharField(
        source="applicable_category.name", read_only=True, default=None
    )
    applicable_product_name = serializers.CharField(
        source="applicable_product.name", read_only=True, default=None
    )

    class Meta:
        model = AmazonFeeConfig
        fields = [
            "id",
            "fee_name",
            "fee_type",
            "value",
            "sales_channel",
            "sales_channel_code",
            "applicable_category",
            "applicable_category_name",
            "applicable_product",
            "applicable_product_name",
            "effective_from",
            "effective_to",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        effective_from = attrs.get(
            "effective_from", getattr(self.instance, "effective_from", None)
        )
        effective_to = attrs.get("effective_to", getattr(self.instance, "effective_to", None))
        if (
            effective_to is not None
            and effective_from is not None
            and effective_to < effective_from
        ):
            raise serializers.ValidationError(
                {"effective_to": "Must not be before effective_from."}
            )
        product = attrs.get(
            "applicable_product", getattr(self.instance, "applicable_product", None)
        )
        category = attrs.get(
            "applicable_category", getattr(self.instance, "applicable_category", None)
        )
        if product is not None and category is not None:
            raise serializers.ValidationError(
                {
                    "applicable_category": "Set either a product or a category, not both "
                    "(product takes precedence)."
                }
            )
        return attrs


class AmazonOrderSettlementSerializer(serializers.ModelSerializer):
    sale_external_reference = serializers.CharField(
        source="sale.external_reference", read_only=True
    )
    amazon_fees_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    settlement_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_revenue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    product_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net_profit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = AmazonOrderSettlement
        fields = [
            "id",
            "sale",
            "sale_external_reference",
            "sku",
            "variant",
            "quantity",
            "selling_price",
            "gst_amount",
            "taxable_value",
            "referral_fee",
            "closing_fee",
            "fulfillment_fee",
            "shipping_cost",
            "advertising_cost",
            "other_charges",
            "refund_amount",
            "amazon_fees_total",
            "settlement_amount",
            "net_revenue",
            "product_cost",
            "net_profit",
            "created_at",
        ]
        read_only_fields = fields


class AmazonImportBatchListSerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model = AmazonImportBatch
        fields = [
            "id",
            "status",
            "total_rows",
            "total_orders",
            "orders_created",
            "orders_updated",
            "orders_skipped",
            "orders_failed",
            "created_by",
            "created_by_email",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields


class AmazonImportBatchDetailSerializer(AmazonImportBatchListSerializer):
    class Meta(AmazonImportBatchListSerializer.Meta):
        fields = AmazonImportBatchListSerializer.Meta.fields + ["error_log", "error_message"]
        read_only_fields = fields


class AmazonImportBatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AmazonImportBatch
        fields = ["id", "file"]
        read_only_fields = ["id"]
