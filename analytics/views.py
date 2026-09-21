"""A porta de entrada dos eventos.

Um POST em lote, e três coisas que ele NÃO faz de propósito:

- **não bloqueia a tela.** É um endpoint à parte (`/analytics/e/`), disparado
  por `sendBeacon`/`fetch` em segundo plano — a resposta da página do usuário
  nunca espera por ele. A gravação é um `bulk_create`, uma ida ao banco.
- **não confia no cliente.** Nome fora do catálogo, timestamp do futuro,
  propriedade gigante: tudo aparado em `ingest.py` antes de gravar.
- **não trava o usuário.** Passou do teto da janela, ou o corpo veio quebrado?
  Responde 204 mesmo assim — o cliente não deve reenviar, e analytics perdido
  é barato. O que não pode é o beacon virar retentativa eterna.

Anônimo por padrão: o `anon_id` é um cookie de primeira parte, `HttpOnly`,
sorteado no servidor. Só vira PESSOA se ela estiver logada e não tiver pedido
para não ser rastreada (`privacidade.pode_identificar`).
"""
import uuid

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import ingest
from .identidade import COOKIE_ANON
from .models import Event
from .privacidade import pode_identificar

#: Teto por janela, best-effort (o cache é por processo). Generoso: uma sessão
#: ativa de treino dispara dezenas de eventos por minuto; abuso são milhares.
LIMITE_POR_JANELA = 500
JANELA_SEGUNDOS = 60
COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # dois anos


@method_decorator(csrf_exempt, name="dispatch")
class IngestView(View):
    """POST em lote. CSRF-exempt porque `sendBeacon` não manda o token e o
    endpoint só ANEXA evento — mas recusa POST de outra origem."""

    def post(self, request):
        origem = request.META.get("HTTP_ORIGIN")
        if origem and origem.rsplit("://", 1)[-1] != request.get_host():
            return HttpResponse(status=403)

        anon = request.COOKIES.get(COOKIE_ANON) or uuid.uuid4().hex

        try:
            dados = ingest.parse_lote(request.body)
        except (ValueError, UnicodeDecodeError):
            return self._resposta(request, anon)

        eventos = ingest.eventos_validos(dados)
        eventos = self._dentro_do_teto(anon, eventos)

        user = None
        if request.user.is_authenticated and pode_identificar(request):
            user = request.user

        objetos = [
            Event(
                name=e["name"],
                props=e["props"],
                user=user,
                anon_id=anon,
                session_id=e["session_id"],
                route=e["route"],
                referrer=e["referrer"],
                device=e["device"],
                width=e["width"],
                theme=e["theme"],
                pwa=e["pwa"],
                app_version=e["app_version"],
                ts=e["ts"],
            )
            for e in eventos
        ]
        if objetos:
            Event.objects.bulk_create(objetos)
        return self._resposta(request, anon)

    def _dentro_do_teto(self, anon, eventos):
        chave = f"analytics:rl:{anon}"
        atual = cache.get(chave, 0)
        if atual >= LIMITE_POR_JANELA:
            return []
        permitidos = eventos[: LIMITE_POR_JANELA - atual]
        if permitidos:
            cache.add(chave, 0, JANELA_SEGUNDOS)
            try:
                cache.incr(chave, len(permitidos))
            except ValueError:
                cache.set(chave, len(permitidos), JANELA_SEGUNDOS)
        return permitidos

    def _resposta(self, request, anon):
        resp = HttpResponse(status=204)
        if COOKIE_ANON not in request.COOKIES:
            resp.set_cookie(
                COOKIE_ANON,
                anon,
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
        return resp
