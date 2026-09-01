"""Logging que serve para diagnosticar sem virar vazamento.

O NutriPlan não tinha configuração de log nenhuma: uma exceção não tratada
sumia, e o único sinal era `/saude/` — que responde 200 enquanto o processo
estiver de pé. No beta, o erro que quarenta pessoas encontram e ninguém reporta
é o que mata o produto em silêncio.

O que este módulo entrega, e por que cada peça existe:

  IDENTIFICADOR DE PEDIDO  — sem ele, "deu 500" e "o usuário reclamou" são duas
  informações que nunca se encontram. Com ele, a linha do erro e a linha do
  acesso carregam a mesma marca, e dá para reconstruir o que aconteceu.

  REDAÇÃO DE CAMINHO  — o link de redefinição de senha carrega o token NA URL
  (`/conta/senha/nova/<uid>/<token>/`). O logger de request do Django registra
  o caminho; um 500 ali gravaria um token VÁLIDO no log da plataforma, que é
  exatamente o cenário que `accounts/checks.py` existe para evitar do lado do
  e-mail. Aqui ele é fechado do lado do log.

O que este módulo deliberadamente NÃO faz: registrar corpo de requisição,
cabeçalho, cookie, ou qualquer campo de perfil. Um log de saúde e dieta é dado
sensível — e um log que ninguém pode mostrar é um log que ninguém consulta.
"""
import logging
import re
import uuid
from contextvars import ContextVar

#: O identificador do pedido em curso. `ContextVar` e não thread-local porque
#: o Django moderno atende em contextos assíncronos também, e thread-local
#: vazaria entre corrotinas.
_pedido_atual: ContextVar[str] = ContextVar("pedido_atual", default="-")

#: Cabeçalho que plataformas e proxies costumam propagar. Se vier de fora, é
#: reaproveitado — assim o mesmo identificador atravessa camadas.
CABECALHO = "HTTP_X_REQUEST_ID"

#: O que nunca pode aparecer num log, por mais conveniente que fosse.
#:
#: O token de redefinição é o caso urgente: ele vale três horas e dá acesso à
#: conta. Os outros estão aqui porque o dia em que alguém logar uma URL de
#: callback do OAuth, o segredo vai junto.
PADROES = (
    # /conta/senha/nova/<uidb64>/<token>/
    (re.compile(r"(/senha/nova/)[^/\s]+/[^/\s]+"), r"\1[REDIGIDO]"),
    # ?code=... &state=... &token=...
    (re.compile(r"([?&](?:code|state|token|key|password)=)[^&\s]+", re.I), r"\1[REDIGIDO]"),
    # chaves de SMTP e URLs de banco, caso alguma exceção as carregue
    (re.compile(r"xsmtpsib-[A-Za-z0-9]+"), "[REDIGIDO]"),
    (re.compile(r"postgres(?:ql)?://[^\s]+"), "postgresql://[REDIGIDO]"),
)


def redigir(texto: str) -> str:
    """Apaga de um texto o que não pode ser guardado."""
    for padrao, troca in PADROES:
        texto = padrao.sub(troca, texto)
    return texto


class IdentificadorDePedido(logging.Filter):
    """Põe o identificador em toda linha, e redige o que ela carrega.

    Filtro e não formatter: um formatter só é aplicado no handler que o usa, e
    a redação precisa valer para TODOS — inclusive um handler que alguém
    acrescente depois sem lembrar deste arquivo.
    """

    def filter(self, record):
        record.pedido = _pedido_atual.get()
        if isinstance(record.msg, str):
            record.msg = redigir(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redigir(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(redigir(str(a)) for a in record.args)
        return True


class MarcaDePedidoMiddleware:
    """Dá um identificador a cada pedido e devolve no cabeçalho da resposta.

    Devolver importa: quando alguém relata um problema, o identificador está na
    resposta que a pessoa recebeu, e ela pode citá-lo sem que ninguém precise
    adivinhar o horário exato.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        marca = request.META.get(CABECALHO) or uuid.uuid4().hex[:12]
        # Só o que veio de fora e parece identificador; um cabeçalho de cliente
        # não pode virar veículo de injeção no log.
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", marca):
            marca = uuid.uuid4().hex[:12]

        ficha = _pedido_atual.set(marca)
        try:
            resposta = self.get_response(request)
        finally:
            _pedido_atual.reset(ficha)

        resposta["X-Request-ID"] = marca
        return resposta


def configuracao(debug: bool) -> dict:
    """O dicionário de `LOGGING`.

    Em produção o destino é a saída padrão, e não arquivo: o Render captura
    stdout e o disco do plano gratuito é efêmero — log em arquivo desaparece
    no próximo deploy, que é justamente quando alguém iria procurá-lo.
    """
    nivel = "DEBUG" if debug else "INFO"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "pedido": {"()": "config.observabilidade.IdentificadorDePedido"},
        },
        "formatters": {
            "nutriplan": {
                "format": "%(levelname)s %(asctime)s [%(pedido)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "nutriplan",
                "filters": ["pedido"],
            },
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
        "loggers": {
            # O que interessa de verdade: 5xx com traceback e endpoint.
            "django.request": {
                "handlers": ["console"],
                "level": "ERROR",
                "propagate": False,
            },
            # SQL fica de fora mesmo em DEBUG: consulta com parâmetro carrega
            # e-mail e peso, e um log de dado de saúde é dado de saúde.
            "django.db.backends": {"level": "WARNING", "propagate": False},
            "nutriplan": {"handlers": ["console"], "level": nivel, "propagate": False},
        },
    }
