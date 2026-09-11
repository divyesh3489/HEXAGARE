from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderLineUnit, PurchaseOrderPayment


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


class PurchaseOrderPaymentInline(admin.TabularInline):
    model = PurchaseOrderPayment
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["id", "supplier", "status", "grand_total", "created_at"]
    list_filter = ["status"]
    search_fields = ["reference", "invoice_number", "supplier__name"]
    inlines = [PurchaseOrderLineInline, PurchaseOrderPaymentInline]


@admin.register(PurchaseOrderLineUnit)
class PurchaseOrderLineUnitAdmin(admin.ModelAdmin):
    list_display = ["id", "line", "serialized_unit", "created_at"]
    search_fields = ["serialized_unit__serial_number"]
