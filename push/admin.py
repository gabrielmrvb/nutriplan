from django.contrib import admin

from .models import NotificationLog, PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    """A assinatura push, sem o material que a assina.

    `endpoint`, `p256dh_key` e `auth_key` são o que permite ENVIAR notificação
    para o navegador de alguém. A versão anterior não declarava `fields` nem
    `readonly_fields`, então o formulário de detalhe renderizava os três em
    campos de texto editáveis. Não era exposição ativa — o papel administrativo
    não tem `view_pushsubscription` e a URL responde 403 —, mas bastava alguém
    conceder a permissão um dia para o material de assinatura aparecer na tela.

    A pergunta que decidiu o desenho: QUAL É O CASO OPERACIONAL para um humano
    ver isso? Para "não estou recebendo notificação", o que responde é: existe
    assinatura, está ativa, de qual dispositivo, quando foi o último envio.
    Endpoint e chaves não respondem nada — e um `endpoint` copiado da tela é
    suficiente para mandar notificação em nome do app.

    Então eles não estão em `fields`. Não é `readonly_fields`: campo somente
    leitura ainda é RENDERIZADO, e o valor apareceria no HTML.
    """

    list_display = ("user", "dispositivo", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("user__email",)
    fields = ("user", "dispositivo", "is_active", "created_at", "last_used_at")
    readonly_fields = fields

    @admin.display(description="dispositivo")
    def dispositivo(self, obj):
        """O user agent cortado. Inteiro ele é impressão digital de navegador."""
        agente = obj.user_agent or ""
        return (agente[:40] + "…") if len(agente) > 40 else (agente or "—")

    def has_add_permission(self, request):
        # Assinatura nasce do navegador da pessoa, com chaves que só ele tem.
        # Criar uma pela mão produziria uma linha que nunca recebe nada.
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """Histórico de envio, para diagnóstico. Nunca editável — é o registro do
    que aconteceu, e reescrevê-lo apagaria a evidência de uma falha."""

    list_display = ("user", "date", "slot", "success", "sent_at")
    list_filter = ("success", "date")
    search_fields = ("user__email",)
    fields = ("user", "date", "slot", "success", "sent_at")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
