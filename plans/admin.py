from django.contrib import admin

from .models import MealLog, MealOption, MealSlot, NutritionPlan


class MealOptionInline(admin.TabularInline):
    model = MealOption
    extra = 0
    autocomplete_fields = ["template"]
    readonly_fields = ("kcal", "protein_g", "carb_g", "fat_g")


class MealSlotInline(admin.TabularInline):
    model = MealSlot
    extra = 0
    show_change_link = True


@admin.register(NutritionPlan)
class NutritionPlanAdmin(admin.ModelAdmin):
    inlines = [MealSlotInline]
    list_display = ("user", "target_kcal", "protein_g", "carb_g", "fat_g", "goal", "is_active", "created_at")
    list_filter = ("is_active", "goal", "created_at")
    search_fields = ("user__email",)
    readonly_fields = ("created_at",)


@admin.register(MealSlot)
class MealSlotAdmin(admin.ModelAdmin):
    inlines = [MealOptionInline]
    list_display = ("name", "plan", "time", "target_kcal", "order")
    list_filter = ("category",)
    search_fields = ("plan__user__email", "name")


@admin.register(MealLog)
class MealLogAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "slot_name", "status", "kcal", "marked_at")
    list_filter = ("status", "date")
    search_fields = ("user__email",)
    date_hierarchy = "date"
