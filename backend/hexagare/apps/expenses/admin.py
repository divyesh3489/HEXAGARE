from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["category", "amount", "expense_date", "sales_channel", "created_by"]
    list_filter = ["category", "sales_channel"]
    search_fields = ["note"]
