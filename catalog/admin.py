from django.contrib import admin

from .models import (
    DietaryTag,
    Food,
    FoodPortion,
    MealTemplate,
    MealTemplateItem,
)


class FoodPortionInline(admin.TabularInline):
    model = FoodPortion
    extra = 1


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    inlines = [FoodPortionInline]
    list_display = ("name", "brand", "kcal", "protein_g", "carb_g", "fat_g", "source", "is_active")
    list_filter = ("source", "is_active", "base_unit")
    search_fields = ("name", "brand")
    list_editable = ("is_active",)
    fieldsets = (
        (None, {"fields": ("name", "brand", "base_unit", "source", "is_active")}),
        (
            "Valores por 100 g / 100 ml",
            {"fields": ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g")},
        ),
    )


@admin.register(DietaryTag)
class DietaryTagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind")
    list_filter = ("kind",)
    prepopulated_fields = {"slug": ("name",)}


class MealTemplateItemInline(admin.TabularInline):
    model = MealTemplateItem
    extra = 3
    autocomplete_fields = ["food"]


@admin.register(MealTemplate)
class MealTemplateAdmin(admin.ModelAdmin):
    inlines = [MealTemplateItemInline]
    list_display = (
        "name",
        "category",
        "kcal_cache",
        "protein_g_cache",
        "carb_g_cache",
        "fat_g_cache",
        "prep_minutes",
        "everyday",
        "is_active",
    )
    list_filter = ("category", "everyday", "is_active", "tags")
    list_editable = ("everyday",)
    search_fields = ("name",)
    filter_horizontal = ("tags",)
    readonly_fields = ("kcal_cache", "protein_g_cache", "carb_g_cache", "fat_g_cache")
    actions = ["recalcular_macros"]

    @admin.action(description="Recalcular macros das refeições selecionadas")
    def recalcular_macros(self, request, queryset):
        for template in queryset:
            template.refresh_macros()
        self.message_user(request, f"{queryset.count()} refeição(ões) recalculada(s).")
