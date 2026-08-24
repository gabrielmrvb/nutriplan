from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    """Uma assinatura Web Push de um dispositivo.

    Uma pessoa pode ter várias (celular, tablet, desktop) — o navegador gera
    uma assinatura por dispositivo/instalação, então a chave natural é o
    endpoint, não o usuário.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.TextField("endpoint", unique=True)
    p256dh_key = models.CharField("chave p256dh", max_length=200)
    auth_key = models.CharField("chave auth", max_length=100)
    user_agent = models.CharField("dispositivo", max_length=255, blank=True)
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField("último envio", null=True, blank=True)

    class Meta:
        verbose_name = "assinatura push"
        verbose_name_plural = "assinaturas push"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.user_agent[:40] or 'dispositivo'}"

    def as_subscription_info(self) -> dict:
        """Formato esperado pela pywebpush."""
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh_key, "auth": self.auth_key},
        }


class NotificationLog(models.Model):
    """Registro de envio, com unicidade por (usuário, refeição, dia).

    Essa constraint é o que impede o app de disparar a mesma notificação duas
    vezes se o job rodar em duplicidade ou o servidor reiniciar no meio.
    Notificação repetida é a forma mais rápida de alguém desinstalar o PWA.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_logs"
    )
    slot = models.ForeignKey(
        "plans.MealSlot", on_delete=models.SET_NULL, null=True, related_name="notifications"
    )
    date = models.DateField()
    sent_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "envio de notificação"
        verbose_name_plural = "envios de notificação"
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slot", "date"], name="unique_notification_per_slot_per_day"
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.date:%d/%m} - {'ok' if self.success else 'falhou'}"
