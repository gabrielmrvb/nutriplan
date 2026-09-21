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

  LINHA EM JSON (21/09/2026)  — em produção cada linha é UM objeto JSON
  (`FormatoJSON`): `t`, `nivel`, `logger`, `pedido`, `msg`, e o que o pedido
  carrega — `rota`, `metodo`, `status`, `ms`, `usuario` — mais `exc` quando há
  traceback. O Render guarda stdout; JSON é o que se filtra e se conta ali sem
  regex. Em DEBUG a linha continua legível para gente (o formato antigo).

  LOG DE ACESSO  — uma linha por pedido em `nutriplan.acesso`, com a ROTA
  (o padrão da URL, `resolver_match.route`, e não o caminho — o caminho pode
  carregar token; a rota agrega), a duração em ms e o USUÁRIO ANÔNIMO: um
  hash com chave (`blake2b` com a `SECRET_KEY`) do id, 12 hex. Dá para seguir
  o que uma pessoa fez sem que o log diga quem ela é, e sem a chave o hash
  não volta. Estático não entra (ruído), e o hash só é calculado quando a
  view já resolveu `request.user` — nunca custa uma consulta a mais.

  ALERTA DE 5xx  — `AlertaDe5xx` é um handler no logger `django.request`:
  conta os 5xx numa janela de 5 minutos e, passado o limite, manda UM e-mail
  (`NUTRIPLAN_ALERTA_EMAIL`, pelo SMTP de sempre) com rota, identificador e
  contagem — e fica calado por 30 minutos, senão um deploy quebrado vira
  cem e-mails. O contador é por PROCESSO (dois workers no Render, dois
  contadores): o limite é por worker, e está dito no CLAUDE.md. O envio
  roda numa thread para não segurar a resposta 500 que já está atrasada.

O que este módulo deliberadamente NÃO faz: registrar corpo de requisição,
cabeçalho, cookie, ou qualquer campo de perfil. Um log de saúde e dieta é dado
sensível — e um log que ninguém pode mostrar é um log que ninguém consulta.
"""
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone

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
    # /tarefas/lembretes/externo/<token>/ — o disparo pontual leva o token na
    # URL (o UptimeRobot free não manda cabeçalho); redige do log do Django.
    (re.compile(r"(/tarefas/lembretes/externo/)[^/\s]+"), r"\1[REDIGIDO]"),
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


#: O log de acesso: uma linha por pedido, com rota, status, duração e usuário
#: anônimo. Nível INFO; em teste ele fica desligado pelo `configuracao`.
acesso = logging.getLogger("nutriplan.acesso")

#: Prefixos que não entram no log de acesso: estático é ruído, não uso.
SEM_ACESSO = ("/static/",)


def usuario_anonimo(request) -> str:
    """Um pseudônimo ESTÁVEL da pessoa, ou "anon" — sem custar consulta.

    `blake2b` com a `SECRET_KEY` como chave: o mesmo id dá sempre o mesmo hash
    (dá para seguir uma sessão de uso no log), e sem a chave não se volta ao
    id. Só calcula quando a view já resolveu `request.user`: forçar o
    `SimpleLazyObject` aqui custaria a consulta de sessão em telas que não a
    fazem — `/saude/vivo/` promete ZERO consultas, e continua prometendo.
    """
    from django.conf import settings
    from django.utils.functional import empty

    usuario = getattr(request, "user", None)
    if usuario is None or getattr(usuario, "_wrapped", None) is empty:
        return "-"
    if not getattr(usuario, "is_authenticated", False):
        return "anon"
    chave = settings.SECRET_KEY.encode("utf-8")[:64]
    return hashlib.blake2b(str(usuario.pk).encode("utf-8"), key=chave, digest_size=6).hexdigest()


def rota_de(request) -> str:
    """O PADRÃO da URL (`saude/vivo/`), e não o caminho: agrega e não vaza."""
    casamento = getattr(request, "resolver_match", None)
    if casamento is not None and casamento.route:
        return casamento.route
    return redigir(request.path)[:80]


class MarcaDePedidoMiddleware:
    """Dá um identificador a cada pedido, devolve no cabeçalho da resposta e
    registra o acesso (rota, status, duração, usuário anônimo).

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

        inicio = time.monotonic()
        ficha = _pedido_atual.set(marca)
        try:
            resposta = self.get_response(request)
            if not request.path.startswith(SEM_ACESSO):
                self._registrar(request, resposta, inicio)
        finally:
            _pedido_atual.reset(ficha)

        resposta["X-Request-ID"] = marca
        return resposta

    @staticmethod
    def _registrar(request, resposta, inicio):
        rota = rota_de(request)
        acesso.info(
            "%s %s -> %s", request.method, rota, resposta.status_code,
            extra={
                "rota": rota, "metodo": request.method, "status": resposta.status_code,
                "ms": int((time.monotonic() - inicio) * 1000), "usuario": usuario_anonimo(request),
            },
        )


class FormatoJSON(logging.Formatter):
    """Uma linha, um objeto JSON. O que o pedido carrega vai como campo próprio."""

    CAMPOS = ("rota", "metodo", "status", "ms", "usuario", "status_code")

    def format(self, record):
        linha = {
            "t": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "pedido": getattr(record, "pedido", "-"),
            "msg": redigir(record.getMessage()),
        }
        for campo in self.CAMPOS:
            if hasattr(record, campo):
                linha[campo] = getattr(record, campo)
        if record.exc_info:
            linha["exc"] = redigir(self.formatException(record.exc_info))
        return json.dumps(linha, ensure_ascii=False, default=str)


def _enviar_email(assunto: str, corpo: str) -> bool:
    """O e-mail de alerta, pelo SMTP configurado. Sem destinatário, só avisa no log."""
    from django.conf import settings
    from django.core.mail import send_mail

    destino = getattr(settings, "NUTRIPLAN_ALERTA_EMAIL", "")
    if not destino:
        logging.getLogger("nutriplan").warning("alerta de 5xx sem destinatário (NUTRIPLAN_ALERTA_EMAIL vazio): %s", assunto)
        return False
    try:
        send_mail(assunto, corpo, None, [destino], fail_silently=True)
        return True
    except Exception:  # o alerta nunca pode derrubar quem já está caindo
        logging.getLogger("nutriplan").exception("falha ao enviar o alerta de 5xx")
        return False


def _enviar_em_thread(assunto: str, corpo: str) -> None:
    threading.Thread(target=_enviar_email, args=(assunto, corpo), daemon=True).start()


class AlertaDe5xx(logging.Handler):
    """Conta 5xx numa janela deslizante e manda UM e-mail quando passa do limite.

    `limite` é POR PROCESSO: cada worker do gunicorn tem o seu contador. Com
    dois workers e limite 3, uma rajada de 4 erros num worker (ou ~8 espalhados)
    dispara. `silencio` evita a avalanche: depois de um alerta, o próximo só em
    30 minutos — o e-mail diz "n erros em 5 min", não é um por erro.
    """

    def __init__(self, limite=3, janela=300, silencio=1800, enviar=None, relogio=None, level=logging.ERROR):
        super().__init__(level=level)
        self.limite, self.janela, self.silencio = int(limite), int(janela), int(silencio)
        self.enviar = enviar or _enviar_em_thread
        self.relogio = relogio or time.monotonic
        self.erros = deque()
        self.ultimo_alerta = None
        self.alertas = 0

    def emit(self, record):
        status = getattr(record, "status_code", 500)
        if not (500 <= int(status) < 600):
            return
        agora = self.relogio()
        pedido = getattr(record, "pedido", "-")
        self.erros.append((agora, redigir(record.getMessage())[:120], pedido))
        while self.erros and agora - self.erros[0][0] > self.janela:
            self.erros.popleft()
        if len(self.erros) <= self.limite:
            return
        if self.ultimo_alerta is not None and agora - self.ultimo_alerta < self.silencio:
            return
        self.ultimo_alerta = agora
        self.alertas += 1
        try:
            self.enviar(*self._mensagem())
        except Exception:  # nunca a partir de um handler de log
            self.handleError(record)

    def _mensagem(self):
        n = len(self.erros)
        assunto = "[NutriPlan] %d erros 5xx em %d min" % (n, self.janela // 60)
        linhas = ["%d respostas 5xx nos últimos %d minutos neste processo (limite %d)." % (n, self.janela // 60, self.limite), ""]
        linhas += ["- %s [pedido %s]" % (msg, pedido) for _, msg, pedido in list(self.erros)[-10:]]
        linhas += ["", "Runbook: CLAUDE.md, \"Runbook de incidente\" — scripts/incidente.py diagnostico."]
        return assunto, "\n".join(linhas)


def configuracao(debug: bool, json_: bool = None, acesso_ligado: bool = True, limite_5xx: int = 3) -> dict:
    """O dicionário de `LOGGING`.

    Em produção o destino é a saída padrão, e não arquivo: o Render captura
    stdout e o disco do plano gratuito é efêmero — log em arquivo desaparece
    no próximo deploy, que é justamente quando alguém iria procurá-lo.

    `json_` (padrão: fora de DEBUG) troca o formato por `FormatoJSON`;
    `acesso_ligado` desliga o log de acesso (a suíte não precisa de duas mil
    linhas de `GET ... -> 200`); `limite_5xx` é o gatilho do e-mail.
    """
    nivel = "DEBUG" if debug else "INFO"
    if json_ is None:
        json_ = not debug
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
            "json": {"()": "config.observabilidade.FormatoJSON"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if json_ else "nutriplan",
                "filters": ["pedido"],
            },
            # O alerta de 5xx mora no logger do Django que registra o 500, e
            # só nele: é ali que o `status_code` chega como campo do registro.
            "alerta_5xx": {
                "()": "config.observabilidade.AlertaDe5xx",
                "level": "ERROR",
                "limite": limite_5xx,
                "filters": ["pedido"],
            },
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
        "loggers": {
            # O que interessa de verdade: 5xx com traceback e endpoint.
            "django.request": {
                "handlers": ["console", "alerta_5xx"],
                "level": "ERROR",
                "propagate": False,
            },
            "nutriplan.acesso": {
                "handlers": ["console"],
                "level": "INFO" if acesso_ligado else "WARNING",
                "propagate": False,
            },
            # SQL fica de fora mesmo em DEBUG: consulta com parâmetro carrega
            # e-mail e peso, e um log de dado de saúde é dado de saúde.
            "django.db.backends": {"level": "WARNING", "propagate": False},
            "nutriplan": {"handlers": ["console"], "level": nivel, "propagate": False},
        },
    }
