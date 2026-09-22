# -*- coding: utf-8 -*-
"""A cópia local do que o Brevo sabe sobre as caixas: quem BLOQUEOU e quem
ABRIU.

Duas leituras da API v3 (`api-key` de `settings.BREVO_API_KEY`; sem chave,
nada roda e o motivo fica no log — o app continua igual):

* `GET /v3/smtp/blockedContacts` — hard bounce, spam, bloqueio. Vira
  `EmailBloqueado`, e `enviar()` recusa antes de gravar linha;
* `GET /v3/smtp/statistics/events?event=opened` — quem abriu algum e-mail
  nosso. Vira `EmailAberto`, a prova de caixa viva enquanto o cadastro não
  verifica e-mail.

Só GET, por construção (`_get`), como `scripts/render_api.py`: este módulo
nunca escreve no Brevo. A chave nunca é impressa nem entra em argumento.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone as tz

from django.conf import settings
from django.utils import timezone

from .models import EmailAberto, EmailBloqueado

logger = logging.getLogger("nutriplan.avisos")

API = "https://api.brevo.com/v3"
PAGINA = 100
#: Quantos dias de eventos "abriu" a sincronização olha: o Brevo guarda 90.
DIAS_DE_EVENTOS = 90
#: Entre uma sincronização e outra dentro da rodada de e-mails (`jobs`): a
#: lista muda devagar e o Brevo já não reenvia para hard bounce sozinho.
HORAS_ENTRE_SINCRONIZACOES = 12


def configurado() -> bool:
    return bool(getattr(settings, "BREVO_API_KEY", ""))


def _get(caminho, params):
    url = API + caminho + "?" + urllib.parse.urlencode(params)
    pedido = urllib.request.Request(url, method="GET", headers={
        "api-key": settings.BREVO_API_KEY, "accept": "application/json", "User-Agent": "nutriplan-avisos",
    })
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        return json.loads(resposta.read() or b"{}")


def _quando(texto):
    """`2026-09-21T13:35:00.000+00:00` (ou `Z`) → aware; ilegível → None."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(tz.utc)
    except ValueError:
        return None


def _paginado(caminho, params, chave):
    offset = 0
    while True:
        dados = _get(caminho, {**params, "limit": PAGINA, "offset": offset})
        itens = dados.get(chave) or []
        for item in itens:
            yield item
        if len(itens) < PAGINA:
            return
        offset += PAGINA


def sincronizar_bloqueados() -> int:
    novos = 0
    for contato in _paginado("/smtp/blockedContacts", {"sort": "desc"}, "contacts"):
        email = (contato.get("email") or "").strip().lower()
        if not email:
            continue
        motivo = ((contato.get("reason") or {}).get("code") or "")[:40]
        _, criado = EmailBloqueado.objects.update_or_create(
            email=email, defaults={"motivo": motivo, "bloqueado_em": _quando(contato.get("blockedAt"))},
        )
        novos += criado
    return novos


def sincronizar_abertos() -> int:
    novos = 0
    primeira = {}
    for evento in _paginado("/smtp/statistics/events", {"event": "opened", "days": DIAS_DE_EVENTOS}, "events"):
        email = (evento.get("email") or "").strip().lower()
        quando = _quando(evento.get("date"))
        if not email:
            continue
        if email not in primeira or (quando and primeira[email] and quando < primeira[email]):
            primeira[email] = quando
    for email, quando in primeira.items():
        registro, criado = EmailAberto.objects.get_or_create(email=email, defaults={"primeira_abertura": quando})
        if not criado and quando and (registro.primeira_abertura is None or quando < registro.primeira_abertura):
            registro.primeira_abertura = quando
            registro.save(update_fields=["primeira_abertura"])
        novos += criado
    return novos


def sincronizar() -> dict:
    """Devolve o que entrou; sem chave ou com a API fora, devolve o motivo e
    NÃO levanta — quem chama (o build, a rodada) segue."""
    if not configurado():
        return {"pulado": "BREVO_API_KEY ausente"}
    try:
        bloqueados = sincronizar_bloqueados()
        abertos = sincronizar_abertos()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("sincronização com o Brevo falhou: %s", exc)
        return {"falhou": str(exc)[:120]}
    return {
        "bloqueados_novos": bloqueados, "abertos_novos": abertos,
        "bloqueados": EmailBloqueado.objects.count(), "abertos": EmailAberto.objects.count(),
    }


_ultima = {"em": None}


def sincronizar_se_vencido(now=None) -> dict:
    """A rodada de e-mails chama isto: uma sincronização a cada
    `HORAS_ENTRE_SINCRONIZACOES` por processo — a memória é do processo,
    como a pausa do `push/tarefas`, e some no restart (custa um GET a mais)."""
    now = now or timezone.now()
    if _ultima["em"] and (now - _ultima["em"]).total_seconds() < HORAS_ENTRE_SINCRONIZACOES * 3600:
        return {"pulado": "sincronizado há menos de %dh" % HORAS_ENTRE_SINCRONIZACOES}
    resultado = sincronizar()
    if "falhou" not in resultado:
        _ultima["em"] = now
    return resultado
