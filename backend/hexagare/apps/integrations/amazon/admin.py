from django.contrib import admin

from .models import AmazonFeeConfig, AmazonImportBatch, AmazonOrderSettlement, AmazonSkuMapping


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Rows here are only ever written through the import task -- same stance
    as ``apps.products``'s ``LabelBatch`` admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AmazonSkuMapping)
class AmazonSkuMappingAdmin(admin.ModelAdmin):
    list_display = ["amazon_sku", "variant", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["amazon_sku", "variant__sku"]
    autocomplete_fields = ["variant"]


@admin.register(AmazonFeeConfig)
class AmazonFeeConfigAdmin(admin.ModelAdmin):
    list_display = [
        "fee_name",
        "fee_type",
        "value",
        "sales_channel",
        "applicable_category",
        "applicable_product",
        "effective_from",
        "effective_to",
        "is_active",
    ]
    list_filter = ["fee_name", "fee_type", "is_active"]


@admin.register(AmazonOrderSettlement)
class AmazonOrderSettlementAdmin(_ReadOnlyAdmin):
    list_display = ["sku", "sale", "variant", "quantity", "settlement_amount", "created_at"]
    search_fields = ["sku", "sale__id", "variant__sku"]
    list_select_related = ["sale", "variant"]


@admin.register(AmazonImportBatch)
class AmazonImportBatchAdmin(_ReadOnlyAdmin):
    list_display = [
        "id",
        "status",
        "total_rows",
        "orders_created",
        "orders_updated",
        "orders_failed",
        "created_by",
        "created_at",
    ]
    list_filter = ["status"]
