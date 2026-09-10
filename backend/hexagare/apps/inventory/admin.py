from django.contrib import admin

from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "kind", "is_active", "updated_at"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "code"]
    prepopulated_fields = {"code": ["name"]}
