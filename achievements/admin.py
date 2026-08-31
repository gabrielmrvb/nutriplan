from django.contrib import admin

from .models import UserAchievement


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "slug", "chave", "unlocked_at", "seen_at")
    list_filter = ("slug",)
    search_fields = ("user__email", "slug")
    # Conquista e registro do que aconteceu: editar a mao seria reescrever o
    # passado de alguem.
    readonly_fields = ("user", "slug", "chave", "unlocked_at", "contexto")
