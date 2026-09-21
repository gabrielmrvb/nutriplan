# -*- coding: utf-8 -*-
"""O AMBIENTE em que a instância roda — produção ou staging (21/09/2026).

`NUTRIPLAN_AMBIENTE` é uma variável do painel do Render: vazia em produção,
`staging` no segundo serviço (`nutriplan-staging`, que recebe todo merge em
`main` sozinho). O que a marca decide, e por quê:

* `X-Robots-Tag: noindex, nofollow` em TODA resposta e a `<meta name="robots">`
  no `<head>`: o staging é um app inteiro, com o mesmo nome, no mesmo domínio
  `.onrender.com` — sem isso o buscador indexa dois NutriPlan e a pessoa cai
  no de teste;
* a faixa "STAGING" em toda tela (`templates/base.html`): quem está olhando
  sabe onde está, e um QA em staging nunca é confundido com produção numa
  captura;
* `"ambiente"` no `/saude/`: a prova de deploy diz QUAL instância respondeu.

Em produção a variável não existe e nada disto acontece — a instância de
verdade não muda um byte por causa do staging.
"""
from django.conf import settings

STAGING = "staging"


def ambiente() -> str:
    return getattr(settings, "NUTRIPLAN_AMBIENTE", "") or ""


def e_staging() -> bool:
    return ambiente() == STAGING


class AmbienteMiddleware:
    """Cabeçalho `X-Robots-Tag` no staging; em produção, nada."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        if e_staging():
            resposta["X-Robots-Tag"] = "noindex, nofollow"
        return resposta


def contexto(request):
    """`NUTRIPLAN_AMBIENTE` nos templates (a meta e a faixa)."""
    return {"NUTRIPLAN_AMBIENTE": ambiente()}
