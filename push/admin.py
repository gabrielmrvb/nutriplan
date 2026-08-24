from django.contrib import admin

from .models import NotificationLog, PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "user_agent", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("user__email",)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "slot", "success", "sent_at")
    list_filter = ("success", "date")
    search_fields = ("user__email",)
