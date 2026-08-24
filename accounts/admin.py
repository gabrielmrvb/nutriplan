from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Profile, TrainingDay, User, WeightEntry


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    filter_horizontal = ("dietary_tags",)


class TrainingDayInline(admin.TabularInline):
    model = TrainingDay
    extra = 0


class WeightEntryInline(admin.TabularInline):
    model = WeightEntry
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline, TrainingDayInline, WeightEntryInline]
    list_display = ("email", "first_name", "last_name", "is_staff", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name")}),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(WeightEntry)
class WeightEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "weight_kg")
    list_filter = ("date",)
    search_fields = ("user__email",)
