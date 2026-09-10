from django.contrib import admin

from .models import (
    Category,
    LabelBatch,
    LabelBatchItem,
    LabelSize,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
    SerializedUnit,
    SerializedUnitEvent,
)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["sku", "name", "code", "mrp", "selling_price", "tax_rate", "is_active"]
    show_change_link = True


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ["image", "variant", "alt_text", "is_primary", "sort_order"]


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "parent", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "brand", "status", "updated_at"]
    list_filter = ["status", "category", "brand"]
    search_fields = ["name", "code", "brand"]
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "name", "selling_price", "tax_rate", "is_active"]
    list_filter = ["is_active", "tax_rate"]
    search_fields = ["sku", "name", "barcode", "product__name"]
    inlines = [ProductAttributeValueInline]


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"code": ["name"]}


@admin.register(LabelSize)
class LabelSizeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "width_mm", "height_mm", "columns", "rows", "is_default"]
    list_filter = ["is_active", "orientation"]
    search_fields = ["name", "code"]


class SerializedUnitEventInline(admin.TabularInline):
    model = SerializedUnitEvent
    extra = 0
    can_delete = False
    fields = ["from_status", "to_status", "location", "note", "actor", "created_at"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SerializedUnit)
class SerializedUnitAdmin(admin.ModelAdmin):
    """View-only.

    A serial number is the permanent physical identity of a unit -- it is never
    edited or reused, and its variant/sequence must not drift from the serial
    string. Status and location move only through
    ``apps.products.services.serial_numbers`` (and, from Phase 4,
    ``SerializedInventoryService`` so the stock ledger stays in step). So the
    admin never mutates a unit: create/transition happen via the API.
    """

    list_display = ["serial_number", "variant", "status", "location", "created_at"]
    list_filter = ["status", "location"]
    search_fields = ["serial_number", "variant__sku", "variant__product__name"]
    list_select_related = ["variant", "variant__product", "location"]
    inlines = [SerializedUnitEventInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LabelBatchItemInline(admin.TabularInline):
    model = LabelBatchItem
    extra = 0
    can_delete = False
    fields = ["serialized_unit"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LabelBatch)
class LabelBatchAdmin(admin.ModelAdmin):
    """View-only: bulk-generation history. Batches (and their units) are created
    through the API in one atomic block; the PDF renders asynchronously."""

    list_display = ["id", "variant", "quantity", "location", "status", "created_at"]
    list_filter = ["status", "location", "barcode_type"]
    search_fields = ["variant__sku", "variant__product__name", "id"]
    list_select_related = ["variant", "variant__product", "location", "label_size"]
    inlines = [LabelBatchItemInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SerializedUnitEvent)
class SerializedUnitEventAdmin(admin.ModelAdmin):
    """View-only: the append-only unit history log."""

    list_display = ["unit", "from_status", "to_status", "location", "actor", "created_at"]
    list_filter = ["to_status", "location"]
    search_fields = ["unit__serial_number"]
    list_select_related = ["unit", "location", "actor"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
