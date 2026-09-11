from django.contrib import admin

from .models import Invoice, InvoiceDelivery, Payment, Return, ReturnUnit


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Rows here are only ever written through the checkout/payment API --
    same stance as ``apps.products``'s ``SerializedUnit``/``LabelBatch``
    admin (a direct edit here would desync from the sale/inventory state)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class InvoiceDeliveryInline(admin.TabularInline):
    model = InvoiceDelivery
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(_ReadOnlyAdmin):
    list_display = ["invoice_number", "sale", "status", "grand_total", "created_at"]
    list_filter = ["status"]
    search_fields = ["invoice_number", "sale__id"]
    inlines = [InvoiceDeliveryInline]


@admin.register(Payment)
class PaymentAdmin(_ReadOnlyAdmin):
    list_display = ["id", "sale", "method", "type", "amount", "created_at"]
    list_filter = ["method", "type"]


class ReturnUnitInline(admin.TabularInline):
    model = ReturnUnit
    extra = 0
    can_delete = False
    fields = ["serialized_unit", "sale_line_unit", "refund_amount", "condition", "inspected_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Return)
class ReturnAdmin(_ReadOnlyAdmin):
    list_display = ["id", "sale", "reason", "refund_total", "created_at"]
    search_fields = ["sale__id", "reason"]
    inlines = [ReturnUnitInline]


@admin.register(ReturnUnit)
class ReturnUnitAdmin(_ReadOnlyAdmin):
    list_display = ["id", "return_record", "serialized_unit", "refund_amount", "condition"]
    list_filter = ["condition"]
