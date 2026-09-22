# -*- coding: utf-8 -*-
"""Content-Security-Policy — a rede de segurança que não existia (22/09/2026).

MEDIDO na auditoria desta missão: **nenhuma rota do app mandava CSP** —
nem a landing, nem a tela logada, nem o cadastro. CSP não conserta um XSS;
ela limita o estrago de um que exista, e num app que sabe peso, altura e
histórico de treino esse limite vale o trabalho.

A política é a MEDIDA do que o app carrega, e nada além:

- `script-src 'self' 'nonce-…'` — todo JavaScript é do próprio site, e os
  `<script>` inline dos templates levam o nonce desta resposta. **Não há
  `'unsafe-inline'`**, que é o que faz a política valer alguma coisa;
- `style-src 'self' 'unsafe-inline'` — o `'unsafe-inline'` aqui é ESTILO, e
  é decisão: o app escreve `style="width: {{ pct }}%"` em barra de progresso
  (valor calculado pelo servidor, a exceção já documentada no `CLAUDE.md`).
  Estilo inline não executa código;
- `img-src 'self' data: blob: https://cdn.jsdelivr.net` — as fotos de
  exercício vêm do jsDelivr (free-exercise-db), e o cartão do placar nasce
  de um `canvas.toBlob`;
- `frame-src https://www.youtube-nocookie.com` — o único iframe do app é a
  demonstração do exercício, e ela já usa o domínio sem rastreio;
- `form-action 'self' https://accounts.google.com` — o botão do Google
  posta para o próprio site e o servidor redireciona para o Google; o
  Chrome já aplicou `form-action` a redirect de formulário, e sem a origem
  o "Continuar com Google" morria sem mensagem;
- `frame-ancestors 'none'` — o mesmo que o `X-Frame-Options: DENY` que já
  existe, dito na linguagem que os navegadores de hoje leem;
- `object-src 'none'` e `base-uri 'self'` — `<object>` não é usado, e
  `<base>` injetado reescreveria todo link relativo da página.

**A casca nativa não recebe a política**, e a razão é medida, não
preguiçosa: o Capacitor injeta a própria ponte no WebView, e nenhuma
política que este servidor escreva conhece o nonce dela. Isto não abre
buraco para um ataque real: a marca `NutriPlanNativo/` é do User-Agent de
QUEM PEDE, e um XSS rodando no navegador da vítima não muda o User-Agent
dela. O que um atacante conseguiria falsificando a marca é desligar a CSP
do PRÓPRIO navegador — contra si mesmo.
"""
import secrets

from config.nativo import e_app_nativo

#: Origens que a medição achou. Mexer aqui é mexer no que o app pode carregar.
FOTOS = "https://cdn.jsdelivr.net"
VIDEO = "https://www.youtube-nocookie.com"
GOOGLE = "https://accounts.google.com"


def politica(nonce: str) -> str:
    return "; ".join((
        "default-src 'self'",
        "script-src 'self' 'nonce-%s'" % nonce,
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: %s" % FOTOS,
        "font-src 'self'",
        "connect-src 'self'",
        "frame-src %s" % VIDEO,
        "media-src 'self' blob:",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self' %s" % GOOGLE,
        "frame-ancestors 'none'",
    ))


class CSPMiddleware:
    """Sorteia o nonce ANTES da view (o template precisa dele) e escreve o
    cabeçalho depois. Um nonce por RESPOSTA: reusar entre pedidos seria o
    mesmo que não ter nonce."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        resposta = self.get_response(request)
        if resposta.has_header("Content-Security-Policy"):
            return resposta
        if e_app_nativo(request):
            return resposta
        resposta["Content-Security-Policy"] = politica(request.csp_nonce)
        return resposta


def contexto(request):
    """`{{ csp_nonce }}` nos templates. Vazio quando não há middleware (o
    atributo some em teste que monta o request à mão), e um `<script>` sem
    nonce simplesmente não roda — nunca um erro de template."""
    return {"csp_nonce": getattr(request, "csp_nonce", "")}
