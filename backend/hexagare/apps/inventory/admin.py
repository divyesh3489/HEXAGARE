from django.contrib import admin

from .models import (
    InventoryBalance,
    InventoryTransaction,
    Location,
    StockLevelPolicy,
    StockTransfer,
    StockTransferLine,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "kind", "is_active", "updated_at"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"code": ["name"]}


class _ReadOnlyAdmin(admin.ModelAdmin):
    """The stock ledger and its cache are written only by ``InventoryService``;
    the admin shows them but never edits them."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(_ReadOnlyAdmin):
    list_display = [
        "created_at", "kind", "variant", "location", "status", "quantity", "serialized_unit",
    ]
    list_filter = ["kind", "status", "location"]
    search_fields = ["serialized_unit__serial_number", "variant__sku", "reference", "note"]
    date_hierarchy = "created_at"


@admin.register(InventoryBalance)
class InventoryBalanceAdmin(_ReadOnlyAdmin):
    list_display = ["variant", "location", "status", "quantity", "updated_at"]
    list_filter = ["status", "location"]
    search_fields = ["variant__sku"]


@admin.register(StockLevelPolicy)
class StockLevelPolicyAdmin(admin.ModelAdmin):
    list_display = ["variant", "location", "min_quantity", "max_quantity", "is_active"]
    list_filter = ["is_active", "location"]
    search_fields = ["variant__sku", "variant__product__name"]


class StockTransferLineInline(admin.TabularInline):
    model = StockTransferLine
    extra = 0
    readonly_fields = ["serialized_unit", "received", "added_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ["id", "from_location", "to_location", "status", "created_by", "created_at"]
    list_filter = ["status", "from_location", "to_location"]
    readonly_fields = [
        "reference", "status", "created_by", "created_at", "updated_at", "completed_at",
    ]
    inlines = [StockTransferLineInline]
