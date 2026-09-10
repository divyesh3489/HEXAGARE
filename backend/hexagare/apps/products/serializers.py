"""Serializers for the catalog API.

List endpoints go through ``StandardPagination`` and errors through the global
exception handler, so these return plain object representations only.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import (
    Category,
    LabelSize,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
)
from .services.sku import is_sku_available, suggest_sku


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "code",
            "parent",
            "parent_name",
            "description",
            "is_active",
            "product_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def validate_parent(self, value):
        if value is not None and self.instance is not None and value.pk == self.instance.pk:
            raise serializers.ValidationError("A category cannot be its own parent.")
        return value


class ProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = ["id", "name", "code", "is_active"]


class ProductAttributeValueSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)

    class Meta:
        model = ProductAttributeValue
        fields = ["id", "attribute", "attribute_name", "value"]


class LabelSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabelSize
        fields = [
            "id",
            "name",
            "code",
            "width_mm",
            "height_mm",
            "columns",
            "rows",
            "margin_mm",
            "gutter_mm",
            "orientation",
            "is_active",
            "is_default",
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "product",
            "variant",
            "image",
            "image_url",
            "alt_text",
            "is_primary",
            "sort_order",
            "created_at",
        ]
        extra_kwargs = {"image": {"write_only": True}}

    def get_image_url(self, obj) -> str | None:
        # Storage-relative on purpose: S3 returns an absolute https URL, local
        # file storage returns a root-relative ``/media/...`` path the browser
        # resolves against its own origin (the Vite dev proxy forwards it). Never
        # derive the host from the request -- behind the dev proxy that is the
        # container hostname.
        return obj.image.url if obj.image else None

    def validate(self, attrs):
        product = attrs.get("product") or getattr(self.instance, "product", None)
        variant = attrs.get("variant") or getattr(self.instance, "variant", None)
        if variant is not None and product is not None and variant.product_id != product.pk:
            raise serializers.ValidationError(
                {"variant": "The variant must belong to the selected product."}
            )
        return attrs


class ProductVariantSerializer(serializers.ModelSerializer):
    attribute_values = ProductAttributeValueSerializer(many=True, required=False)
    sku = serializers.CharField(max_length=64, required=False, allow_blank=True)

    # Resolved figures (variant override -> product default -> 0). Read-only.
    effective_mrp = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    effective_selling_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    effective_purchase_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    effective_tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    gst_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    cgst_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    sgst_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    # Availability follows the product's status (ADR-006). Read-only.
    effective_status = serializers.CharField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "name",
            "code",
            "sku",
            "barcode",
            # nullable overrides -- blank inherits the product default
            "mrp",
            "selling_price",
            "purchase_price",
            "tax_rate",
            # per-variant intent; only takes effect while the product is active
            "is_active",
            "attribute_values",
            # derived, read-only
            "effective_mrp",
            "effective_selling_price",
            "effective_purchase_price",
            "effective_tax_rate",
            "base_price",
            "gst_amount",
            "cgst_amount",
            "sgst_amount",
            "discount_amount",
            "discount_percent",
            "effective_status",
            "is_available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def _effective_after_save(self, attrs, field: str):
        """What ``field`` will resolve to once ``attrs`` is applied."""
        product = attrs.get("product") or getattr(self.instance, "product", None)
        if field in attrs:
            own = attrs[field]
        elif self.instance is not None:
            own = getattr(self.instance, field)
        else:
            own = None
        if own is not None:
            return own
        return getattr(product, field, None) if product is not None else None

    def validate(self, attrs):
        errors = {}
        if self._effective_after_save(attrs, "selling_price") is None:
            errors["selling_price"] = (
                "Set a selling price on the variant, or a default selling price on the product."
            )
        if self._effective_after_save(attrs, "mrp") is None:
            errors["mrp"] = (
                "Set an MRP on the variant, or a default MRP on the product."
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def validate_sku(self, value):
        value = (value or "").strip()
        if not value:
            return value
        exclude = self.instance.pk if self.instance is not None else None
        if not is_sku_available(value, exclude_variant_id=exclude):
            raise serializers.ValidationError("This SKU is already in use.")
        return value

    def _resolved_sku(self, validated_data) -> str:
        sku = (validated_data.get("sku") or "").strip()
        if sku:
            return sku
        product = validated_data.get("product") or getattr(self.instance, "product", None)
        values = [row["value"] for row in validated_data.get("attribute_values", [])]
        if not values and self.instance is not None:
            values = [v.value for v in self.instance.attribute_values.all()]
        return suggest_sku(
            category=product.category if product is not None else None,
            product=product,
            variant_code=validated_data.get("code")
            or getattr(self.instance, "code", ""),
            attribute_values=values,
        )

    def _sync_attribute_values(self, variant, rows):
        keep_ids = set()
        for row in rows:
            obj, _ = ProductAttributeValue.objects.update_or_create(
                variant=variant,
                attribute=row["attribute"],
                defaults={"value": row["value"]},
            )
            keep_ids.add(obj.pk)
        variant.attribute_values.exclude(pk__in=keep_ids).delete()

    @transaction.atomic
    def create(self, validated_data):
        rows = validated_data.pop("attribute_values", [])
        validated_data["sku"] = self._resolved_sku({**validated_data, "attribute_values": rows})
        variant = ProductVariant.objects.create(**validated_data)
        self._sync_attribute_values(variant, rows)
        return variant

    @transaction.atomic
    def update(self, instance, validated_data):
        rows = validated_data.pop("attribute_values", None)
        if not (validated_data.get("sku") or "").strip():
            validated_data.pop("sku", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if rows is not None:
            self._sync_attribute_values(instance, rows)
        return instance


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    variant_count = serializers.IntegerField(read_only=True)
    available_variant_count = serializers.SerializerMethodField()
    price_min = serializers.SerializerMethodField()
    price_max = serializers.SerializerMethodField()
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "code",
            "category",
            "category_name",
            "brand",
            "status",
            "variant_count",
            "available_variant_count",
            "price_min",
            "price_max",
            "primary_image_url",
            "updated_at",
        ]

    def get_available_variant_count(self, obj) -> int:
        # Zero unless the product itself is active (ADR-006).
        if obj.status != Product.Status.ACTIVE:
            return 0
        return sum(1 for v in obj.variants.all() if v.is_active)

    def _prices(self, obj) -> list:
        # Effective selling price per variant -- its own, else the product's
        # default. Computed from the already-loaded product row (no extra query).
        prices = []
        for v in obj.variants.all():
            price = v.selling_price if v.selling_price is not None else obj.selling_price
            if price is not None:
                prices.append(price)
        return prices

    def get_price_min(self, obj) -> Decimal | None:
        prices = self._prices(obj)
        return min(prices) if prices else None

    def get_price_max(self, obj) -> Decimal | None:
        prices = self._prices(obj)
        return max(prices) if prices else None

    def get_primary_image_url(self, obj) -> str | None:
        image = next((i for i in obj.images.all() if i.is_primary), None)
        image = image or next(iter(obj.images.all()), None)
        if image is None or not image.image:
            return None
        # Storage-relative -- see ``ProductImageSerializer.get_image_url``.
        return image.image.url


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "code",
            "description",
            "category",
            "category_name",
            "brand",
            "status",
            "hsn_sac",
            "weight",
            "dimensions",
            "tags",
            "notes",
            # optional default pricing; variants inherit these
            "mrp",
            "selling_price",
            "purchase_price",
            "tax_rate",
            "discount_amount",
            "discount_percent",
            "variants",
            "images",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_tags(self, value):
        if not isinstance(value, list) or any(not isinstance(t, str) for t in value):
            raise serializers.ValidationError("Tags must be a list of strings.")
        return value


class SkuSuggestionSerializer(serializers.Serializer):
    """Input for ``POST /products/sku/suggest/``."""

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), required=False, allow_null=True
    )
    variant_code = serializers.CharField(required=False, allow_blank=True)
    attribute_values = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )

    def suggest(self) -> str:
        data = self.validated_data
        product = data.get("product")
        category = data.get("category") or (product.category if product else None)
        return suggest_sku(
            category=category,
            product=product,
            variant_code=data.get("variant_code", ""),
            attribute_values=data.get("attribute_values", []),
        )
