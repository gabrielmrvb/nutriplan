from django.contrib import admin

from .models import (
    Exercise,
    SessionExercise,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplate,
    WorkoutTemplateItem,
)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("name", "muscle_group", "is_compound", "is_active")
    list_filter = ("muscle_group", "is_compound", "is_active")
    search_fields = ("name",)


class WorkoutTemplateItemInline(admin.TabularInline):
    model = WorkoutTemplateItem
    extra = 1
    autocomplete_fields = ("exercise",)


@admin.register(WorkoutTemplate)
class WorkoutTemplateAdmin(admin.ModelAdmin):
    list_display = ("split", "label", "name", "focus", "is_active")
    list_filter = ("split", "is_active")
    inlines = [WorkoutTemplateItemInline]


class SessionExerciseInline(admin.TabularInline):
    model = SessionExercise
    extra = 0
    autocomplete_fields = ("exercise",)


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ("plan", "weekday", "label", "name")
    inlines = [SessionExerciseInline]


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    # A rotina é um snapshot: editar à mão o que foi gerado é o caminho mais
    # curto para uma ficha que não corresponde a divisão nenhuma.
    list_display = ("user", "split", "days_per_week", "is_active", "created_at")
    list_filter = ("split", "is_active")
    readonly_fields = ("created_at",)
