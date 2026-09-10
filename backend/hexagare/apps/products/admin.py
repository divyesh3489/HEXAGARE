from django.contrib import admin

from .models import (
    Category,
    LabelSize,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
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
