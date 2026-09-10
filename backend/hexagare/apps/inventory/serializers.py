"""Serializers for the inventory API (Phase 4 ledger).

Reads go through ``StandardPagination`` and errors through the global exception
handler, so these return plain object representations only.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.products.models import ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import resolve_unit

from .models import (
    InventoryBalance,
    InventoryTransaction,
    Location,
    StockLevelPolicy,
    StockTransfer,
    StockTransferLine,
)


class LocationSerializer(serializers.ModelSerializer):
    """Read + write. Writes need ``stock_adjustments`` (see the viewset)."""

    class Meta:
        model = Location
        fields = ["id", "name", "code", "kind", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class InventoryBalanceSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_id = serializers.IntegerField(source="variant.product_id", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = InventoryBalance
        fields = [
            "id",
            "variant",
            "sku",
            "product_id",
            "product_name",
            "location",
            "location_name",
            "status",
            "quantity",
            "updated_at",
        ]


class InventoryTransactionSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    serial_number = serializers.CharField(source="serialized_unit.serial_number", read_only=True)
    actor_email = serializers.CharField(source="actor.email", read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = [
            "id",
            "reference",
            "kind",
            "variant",
            "sku",
            "product_name",
            "location",
            "location_name",
            "status",
            "quantity",
            "serialized_unit",
            "serial_number",
            "note",
            "actor",
            "actor_email",
            "created_at",
        ]


class StockLevelPolicySerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = StockLevelPolicy
        fields = [
            "id",
            "variant",
            "sku",
            "product_name",
            "location",
            "location_name",
            "min_quantity",
            "max_quantity",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance
        minimum = attrs.get("min_quantity", getattr(instance, "min_quantity", 0))
        maximum = attrs.get("max_quantity", getattr(instance, "max_quantity", None))
        if maximum is not None and maximum < minimum:
            raise serializers.ValidationError(
                {"max_quantity": "Maximum stock level cannot be below the minimum."}
            )
        return attrs


class StockTransferLineSerializer(serializers.ModelSerializer):
    serial_number = serializers.CharField(source="serialized_unit.serial_number", read_only=True)
    sku = serializers.CharField(source="serialized_unit.variant.sku", read_only=True)
    product_name = serializers.CharField(
        source="serialized_unit.variant.product.name", read_only=True
    )
    unit_status = serializers.CharField(source="serialized_unit.status", read_only=True)

    class Meta:
        model = StockTransferLine
        fields = [
            "id",
            "serialized_unit",
            "serial_number",
            "sku",
            "product_name",
            "unit_status",
            "received",
            "added_at",
        ]


class StockTransferSerializer(serializers.ModelSerializer):
    from_location_name = serializers.CharField(source="from_location.name", read_only=True)
    to_location_name = serializers.CharField(source="to_location.name", read_only=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True)
    lines = StockTransferLineSerializer(many=True, read_only=True)
    line_count = serializers.IntegerField(source="lines.count", read_only=True)

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "reference",
            "from_location",
            "from_location_name",
            "to_location",
            "to_location_name",
            "status",
            "note",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
            "completed_at",
            "line_count",
            "lines",
        ]
        read_only_fields = ["status", "created_by", "completed_at", "created_at", "updated_at"]

    def validate(self, attrs):
        from_location = attrs.get("from_location") or getattr(self.instance, "from_location", None)
        to_location = attrs.get("to_location") or getattr(self.instance, "to_location", None)
        if from_location and to_location and from_location == to_location:
            raise serializers.ValidationError(
                {"to_location": "Source and destination locations must differ."}
            )
        return attrs


class StockTransferScanSerializer(serializers.Serializer):
    """Input for ``POST /inventory/transfers/{id}/scan/``."""

    serial = serializers.CharField()

    def validate_serial(self, value):
        transfer: StockTransfer = self.context["transfer"]
        if transfer.status != StockTransfer.Status.OPEN:
            raise serializers.ValidationError("This transfer is no longer open.")
        unit = resolve_unit(value)  # raises Http404 on an unknown serial
        if unit.status != SerializedUnit.Status.AVAILABLE:
            raise serializers.ValidationError(
                f"{unit.serial_number} is {unit.status}, not AVAILABLE -- it cannot be transferred."
            )
        if unit.location_id != transfer.from_location_id:
            raise serializers.ValidationError(
                f"{unit.serial_number} is at {unit.location.name}, "
                f"not the transfer's source ({transfer.from_location.name})."
            )
        if transfer.lines.filter(serialized_unit=unit).exists():
            raise serializers.ValidationError(f"{unit.serial_number} is already on this transfer.")
        self.context["unit"] = unit
        return value


class InventoryAdjustmentSerializer(serializers.Serializer):
    """Input for ``POST /inventory/adjustments/`` -- a manual, non-serialized
    quantity correction (permission ``stock_adjustments``)."""

    variant = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all())
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    status = serializers.ChoiceField(choices=SerializedUnit.Status.choices)
    quantity = serializers.IntegerField()
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("An adjustment must be a non-zero quantity.")
        return value


class InventoryOverviewRowSerializer(serializers.Serializer):
    variant = serializers.IntegerField()
    sku = serializers.CharField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    location = serializers.IntegerField()
    location_name = serializers.CharField()
    status = serializers.CharField()
    quantity = serializers.IntegerField()


class InventoryOverviewSerializer(serializers.Serializer):
    computed_from = serializers.CharField()
    rows = InventoryOverviewRowSerializer(many=True)
    totals_by_status = serializers.DictField(child=serializers.IntegerField())
    cache_matches = serializers.BooleanField()


class InventoryAlertSerializer(serializers.Serializer):
    type = serializers.CharField()
    variant = serializers.DictField()
    location = serializers.DictField(allow_null=True)
    available = serializers.IntegerField(required=False)
    threshold = serializers.IntegerField(required=False, allow_null=True)
    min_quantity = serializers.IntegerField(required=False)
    max_quantity = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.CharField(required=False)
    cached = serializers.IntegerField(required=False)
    expected = serializers.IntegerField(required=False)
