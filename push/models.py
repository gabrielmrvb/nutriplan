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


class DispositivoNativo(models.Model):
    """Um aparelho com o app INSTALADO (a casca nativa, `nativo/`) — o token
    do FCM que ele registrou (Fase 2 da missão Capacitor, 22/09/2026).

    O Web Push não existe dentro do app instalado: o WebView do Android não
    expõe `PushManager`, o WKWebView do iPhone também não. A casca pede o
    token ao Firebase (`@capacitor-firebase/messaging`; no iOS o FCM
    encaminha ao APNs com a chave que o dono sobe no Firebase) e o manda
    para `push:dispositivo_registrar`. É a mesma pessoa e o mesmo lembrete
    de `PushSubscription`, por outro cano — `services.notify_user` manda
    para os dois.

    A chave natural é o TOKEN (um por instalação); a pessoa é quem entrou
    por último naquele aparelho. Token que o FCM declara morto
    (`UNREGISTERED`) é desativado, nunca apagado — pelo mesmo motivo da
    assinatura web: o histórico continua legível.
    """

    class Plataforma(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dispositivos_nativos"
    )
    token = models.CharField("token do FCM", max_length=512, unique=True)
    plataforma = models.CharField(max_length=8, choices=Plataforma.choices)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    visto_em = models.DateTimeField("último envio", null=True, blank=True)

    class Meta:
        verbose_name = "dispositivo nativo"
        verbose_name_plural = "dispositivos nativos"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.user} - {self.get_plataforma_display()}"
