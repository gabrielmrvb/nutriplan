"""Endpoints do PWA: manifest, service worker e assinatura de notificações.

O manifest e o service worker são servidos por view, e não como arquivo
estático, por dois motivos: o SW precisa vir da RAIZ do site (um arquivo em
/static/ só controlaria /static/), e as duas respostas dependem de settings —
cor do tema, nome do app, versão do cache.
"""
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.templatetags.static import static

from .assets import asset, version
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View

from . import tarefas
from .models import PushSubscription
from .services import push_is_configured

# Sob o namespace `nutriplan`, e não `push.views`: em produção o root é WARNING
# e só `nutriplan` está em INFO (`config/observabilidade.py`), então um
# `logger.info` fora desse namespace fica MUDO — a auditoria "quem disparou" o
# lembrete precisa emitir de verdade. `config/observabilidade` redige o handler.
logger = logging.getLogger("nutriplan.push")


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
                "description": "Estimativa de calorias, cardápio de exemplo e o treino da semana.",
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
                #
                # O SVG saiu da lista com a identidade nova. Ele era o desenho
                # geométrico da marca anterior — retângulos e um círculo, que
                # cabem num vetor de 600 bytes. A arte aprovada tem sombra no
                # "N", gradiente e nervura na folha: vetorizá-la produziria
                # outra marca, e embrulhar o PNG em base64 daria o mesmo peso
                # sem nenhuma vantagem de vetor. Ficam os dois PNGs, que são o
                # que Chrome e Android exigem de qualquer jeito.
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
                        # O diário é o `start_url`, então tocar no ícone já
                        # abre aqui. O atalho existe assim mesmo por um caso
                        # concreto: quem está com o app aberto no treino e
                        # segura o ícone quer voltar para a comida sem
                        # navegar — e quem instalou há semanas não lembra o
                        # que o ícone abre.
                        "name": "Diário de hoje",
                        "short_name": "Diário",
                        "url": "/",
                        "icons": [{"src": static("icons/icon-192.png"), "sizes": "192x192"}],
                    },
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
                #
                # v6 é a identidade nova. Os ícones entram no shell por
                # `static()` e não por `asset()` — de propósito, para o endereço
                # do ícone instalado não mudar a cada deploy —, então a URL do
                # `icon-192.png` é a mesma de antes e o cache de quem já usa o
                # app continuaria servindo a marca antiga para sempre. Subir a
                # versão é o que faz o service worker descartar aquele registro
                # na ativação.
                "cache_version": "nutriplan-v6",
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
                    asset("js/fila.js"),
                    # Analytics no shell: uma página aberta sem rede (do cache)
                    # ainda dispara e enfileira eventos; a drenagem espera a
                    # rede voltar. Sem isto o arquivo faria fetch e falharia.
                    asset("js/analytics.js"),
                    static("icons/icon-192.png"),
                    static("icons/icon-512.png"),
                    # As duas fontes (CORTE, T3.2): entram pelo `static()` como
                    # os ícones — em produção o manifesto de estáticos já põe o
                    # hash no NOME do arquivo (e reescreve o `url()` do CSS
                    # para ele), então a URL é imutável sem `?v=`. Pré-cacheadas
                    # para o `font-display: swap` só trocar de fonte na
                    # primeira visita, nunca a cada abertura sem rede.
                    static("fonts/big-shoulders-display-latin.woff2"),
                    static("fonts/archivo-latin.woff2"),
                ],
            }
        )
        return context


class OfflineView(TemplateView):
    """Página mostrada quando o navegador está sem rede e o cache não tem a rota.

    Ela é PRÉ-CACHEADA no install do service worker e servida a qualquer pessoa
    que use o aparelho depois. Por isso renderiza sem identidade: `shell_offline`
    faz o `base.html` omitir `data-usuario`, forçar `data-autenticado="0"` e
    pular as mensagens da sessão.

    O service worker já pede a página sem cookie, e esta é a segunda camada: se
    alguém um dia trocar aquele `Request` por uma URL crua, o shell continua
    saindo neutro em vez de congelar a sessão de quem instalou o app.
    """

    template_name = "pwa/offline.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["shell_offline"] = True
        return contexto


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


@method_decorator(csrf_exempt, name="dispatch")
class TarefaLembretesView(View):
    """`POST /tarefas/lembretes/` — o agendador de fora (GitHub Actions) bate
    aqui de 5 em 5 minutos; a regra está em `push.tarefas`.

    Sem sessão e sem CSRF: é servidor falando com servidor, e o portão é o
    token em `Authorization: Bearer …` comparado em tempo constante. Só
    POST — o GET responde 405 e a rota está em `FORA` de
    `config/test_acoes_com_tela.py` com o motivo: não é destino de
    navegação de ninguém.
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        if not tarefas.configurada():
            return JsonResponse({"error": "tarefa não configurada"}, status=503)
        if not tarefas.token_confere(request.headers.get("Authorization")):
            return JsonResponse({"error": "não autorizado"}, status=403)
        return JsonResponse(tarefas.rodar())


@method_decorator(csrf_exempt, name="dispatch")
class DisparoExternoView(View):
    """`GET /tarefas/lembretes/externo/<token>/` — o disparo PONTUAL, para um
    monitor externo (UptimeRobot) que bate a cada 5 minutos e é confiável, ao
    contrário do `schedule` do GitHub (MEDIDO em 18/09/2026: ~9 rodadas em
    31 h). O UptimeRobot free só manda GET/HEAD e NÃO manda cabeçalho, então o
    token vem na URL (`config/observabilidade.py` o redige do log do Django; no
    log de ACESSO do Render ele aparece, e por isso é um token separado, de
    baixo dano — só dispara lembretes vencidos, idempotente e com limite de
    taxa).

    GET puro, sem sessão. O `schedule` do Actions continua no `POST
    /tarefas/lembretes/` como FALLBACK: `push.tarefas.rodar` se abstém no
    fallback quando este disparo pontual cuidou há < 4 min.
    """

    http_method_names = ["get"]

    def get(self, request, token, *args, **kwargs):
        if not tarefas.disparo_configurado():
            return JsonResponse({"error": "disparo não configurado"}, status=503)
        if not tarefas.token_de_disparo_confere(token):
            return JsonResponse({"error": "não autorizado"}, status=403)
        # Auditoria: QUEM disparou (nunca o token) — user-agent e origem.
        logger.info(
            "disparo externo de lembretes: ua=%r origem=%s",
            (request.META.get("HTTP_USER_AGENT") or "?")[:120],
            request.META.get("REMOTE_ADDR", "?"),
        )
        return JsonResponse(tarefas.rodar(externo=True))


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
