from django.contrib import admin

from .models import Supplement, SupplementLog


@admin.register(Supplement)
class SupplementAdmin(admin.ModelAdmin):
    list_display = ("name", "evidence", "unit", "is_active", "order")
    list_filter = ("evidence", "is_active")
    search_fields = ("name", "slug")


@admin.register(SupplementLog)
class SupplementLogAdmin(admin.ModelAdmin):
    list_display = ("user", "supplement", "date")
    list_filter = ("supplement",)
