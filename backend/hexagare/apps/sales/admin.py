from django.contrib import admin

from .models import Sale, SaleLine, SalesChannel


@admin.register(SalesChannel)
class SalesChannelAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"code": ["name"]}


class SaleLineInline(admin.TabularInline):
    """Read-only -- lines are only ever added/edited via SaleViewSet's
    ``lines`` actions, which also keep the Sale's totals in sync."""

    model = SaleLine
    extra = 0
    readonly_fields = ["variant", "quantity", "unit_price", "tax_rate", "discount_amount"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["id", "sales_channel", "status", "grand_total", "created_at"]
    list_filter = ["status", "sales_channel"]
    search_fields = ["external_reference"]
    readonly_fields = [
        "subtotal",
        "discount_total",
        "tax_total",
        "grand_total",
        "created_at",
        "updated_at",
    ]
    inlines = [SaleLineInline]
