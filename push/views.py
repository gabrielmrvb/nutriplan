"""Endpoints do PWA: manifest, service worker e assinatura de notificações.

O manifest e o service worker são servidos por view, e não como arquivo
estático, por dois motivos: o SW precisa vir da RAIZ do site (um arquivo em
/static/ só controlaria /static/), e as duas respostas dependem de settings —
cor do tema, nome do app, versão do cache.
"""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.templatetags.static import static

from .assets import asset, version
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.generic import TemplateView, View

from .models import PushSubscription
from .services import push_is_configured


class ManifestView(View):
    """O manifest do PWA — o que permite instalar o app na tela inicial.

    Servido por view, e não como arquivo estático, porque o conteúdo depende de
    settings (nome, cores) e das URLs com hash dos ícones. Um JSON parado no
    disco começaria a mentir no primeiro deploy que mudasse qualquer um dos dois.
    """

    def get(self, request, *args, **kwargs):
        return JsonResponse(
            {
                # `id` fixo: é o que faz o navegador reconhecer que a instalação
                # antiga e a nova são o mesmo app, mesmo que o domínio mude.
                "id": "/",
                "name": settings.PWA_NAME,
                "short_name": settings.PWA_SHORT_NAME,
                "description": "Sua dieta calculada, o cardápio do dia, o treino da semana.",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "display_override": ["standalone", "minimal-ui"],
                "orientation": "portrait",
                "lang": "pt-BR",
                "dir": "ltr",
                "categories": ["health", "fitness", "lifestyle"],
                "background_color": settings.PWA_BACKGROUND_COLOR,
                "theme_color": settings.PWA_THEME_COLOR,
                # Sem `?v=` de propósito, ao contrário do CSS e do JS: o
                # endereço do ícone é a identidade do app instalado, e trocá-lo
                # a cada mudança de folha de estilo faria o sistema baixar tudo
                # de novo por nada. Ícone que muda é ícone novo, com nome novo.
                #
                # Dois propósitos, dois arquivos. O ícone `maskable` é
                # desenhado com margem porque o Android recorta no formato que o
                # fabricante escolher — declarar "any maskable" no mesmo arquivo
                # é o atalho que faz a letra aparecer cortada em metade dos
                # aparelhos.
                "icons": [
                    {
                        "src": static("icons/icon-192.png"),
                        "sizes": "192x192",
                        "type": "image/png",
                        "purpose": "any",
                    },
                    {
                        "src": static("icons/icon-512.png"),
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "any",
                    },
                    {
                        "src": static("icons/icon-192-maskable.png"),
                        "sizes": "192x192",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                    {
                        "src": static("icons/icon-512-maskable.png"),
                        "sizes": "512x512",
                        "type": "image/png",
                        "purpose": "maskable",
                    },
                ],
                # Atalhos do ícone: segurar o app na tela inicial abre direto no
                # treino ou na lista de compras. É o equivalente ao menu de
                # contexto de um app nativo.
                "shortcuts": [
                    {
                        "name": "Treino de hoje",
                        "short_name": "Treino",
                        "url": "/treino/",
                        "icons": [{"src": static("icons/icon-192.png"), "sizes": "192x192"}],
                    },
                    {
                        "name": "Lista de compras",
                        "short_name": "Compras",
                        "url": "/lista-de-compras/",
                        "icons": [{"src": static("icons/icon-192.png"), "sizes": "192x192"}],
                    },
                ],
            },
            content_type="application/manifest+json",
        )


@method_decorator(cache_control(max_age=0, no_cache=True, no_store=True), name="get")
class ServiceWorkerView(TemplateView):
    """Serve o sw.js na raiz.

    O `no-store` é proposital: um service worker cacheado é um app congelado
    numa versão antiga, e é o erro mais chato de diagnosticar em PWA.
    """

    template_name = "pwa/sw.js"
    content_type = "application/javascript"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                # Mudar a versão invalida o cache antigo na ativação do SW.
                "cache_version": "nutriplan-v5",
                # A versão dos estáticos vai junto para o service worker poder
                # apagar do cache o que é de builds anteriores.
                "asset_version": version(),
                "offline_url": "/offline/",
                # As duas primeiras entram versionadas: é a mesma URL que o
                # base.html pede, então o cache do shell e o da página são o
                # mesmo registro em vez de duas cópias que podem divergir.
                "shell": [
                    asset("css/app.css"),
                    asset("js/pwa.js"),
                    static("icons/icon-192.png"),
                    static("icons/icon-512.png"),
                ],
            }
        )
        return context


class OfflineView(TemplateView):
    """Página mostrada quando o navegador está sem rede e o cache não tem a rota."""

    template_name = "pwa/offline.html"


@method_decorator(login_required, name="post")
class SubscribeView(View):
    """Guarda a assinatura que o navegador gerou.

    A chave natural é o `endpoint` (uma por dispositivo/instalação), então
    `update_or_create` por endpoint é o que evita acumular linha morta quando a
    mesma pessoa reinstala o app.
    """

    def post(self, request, *args, **kwargs):
        if not push_is_configured():
            return JsonResponse({"error": "push não configurado"}, status=503)

        try:
            data = json.loads(request.body or "{}")
            endpoint = data["endpoint"]
            keys = data["keys"]
        except (ValueError, KeyError):
            return JsonResponse({"error": "assinatura inválida"}, status=400)

        subscription, created = PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "p256dh_key": keys.get("p256dh", ""),
                "auth_key": keys.get("auth", ""),
                "user_agent": request.headers.get("User-Agent", "")[:255],
                "is_active": True,
            },
        )
        return JsonResponse({"ok": True, "created": created}, status=201 if created else 200)


@method_decorator(login_required, name="post")
class UnsubscribeView(View):
    def post(self, request, *args, **kwargs):
        try:
            endpoint = json.loads(request.body or "{}")["endpoint"]
        except (ValueError, KeyError):
            return JsonResponse({"error": "assinatura inválida"}, status=400)

        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).update(
            is_active=False
        )
        return JsonResponse({"ok": True})
