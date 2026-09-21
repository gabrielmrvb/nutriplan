"""A leitura de um lote de eventos — pura, sem banco e sem request.

Separada da view por um motivo prático: dá para testar a validação inteira
(nome fora do catálogo, timestamp do futuro, propriedade gigante) sem subir uma
requisição. A view só junta isto com o contexto do request e grava.

O que ela recusa e por quê:

- **nome fora do catálogo** — o evento some. Analytics aceita lixo do cliente e
  vira lixo; a taxonomia fechada é a defesa. Um nome errado não derruba o lote
  inteiro (o resto é bom), só aquele evento.
- **timestamp absurdo** — relógio do cliente adiantado escreveria um evento no
  futuro, invisível para "e hoje?". Fora de ±2 dias, cai para a hora do
  servidor.
- **propriedade grande demais ou aninhada** — corta. props é para rótulos
  curtos ("opcao": "almoço"), não para despejar objeto.
"""
import json
from datetime import timedelta, datetime, timezone as dt_timezone

from django.utils import timezone

from . import catalogo

MAX_EVENTOS_POR_LOTE = 50
MAX_CHAVES_POR_PROP = 20
MAX_TAMANHO_PROP = 2000  # bytes do JSON das props
JANELA_DO_TS = timedelta(days=2)


def parse_lote(corpo):
    """bytes/str do corpo -> dict. Levanta ValueError no que não for objeto."""
    if isinstance(corpo, (bytes, bytearray)):
        corpo = corpo.decode("utf-8", errors="replace")
    dados = json.loads(corpo)
    if not isinstance(dados, dict):
        raise ValueError("o lote precisa ser um objeto JSON")
    return dados


def eventos_validos(dados, *, agora=None):
    """Devolve a lista de eventos normalizados, com o contexto do lote aplicado.

    Nome inválido é descartado silenciosamente (o resto do lote vale). Devolve
    no máximo MAX_EVENTOS_POR_LOTE.
    """
    agora = agora or timezone.now()
    brutos = dados.get("events")
    if not isinstance(brutos, list):
        return []

    contexto = {
        "session_id": _texto(dados.get("session_id"), 36),
        "device": _texto(dados.get("device"), 12),
        "width": _inteiro(dados.get("width"), 2000),
        "theme": _texto(dados.get("theme"), 8),
        "pwa": bool(dados.get("pwa")),
        "app_version": _texto(dados.get("app_version"), 20),
    }

    saida = []
    for bruto in brutos[:MAX_EVENTOS_POR_LOTE]:
        if not isinstance(bruto, dict):
            continue
        nome = bruto.get("name")
        if not isinstance(nome, str) or not catalogo.existe(nome):
            continue
        saida.append(
            {
                "name": nome,
                "props": _props(bruto.get("props")),
                "route": _texto(bruto.get("route"), 200),
                "referrer": _texto(bruto.get("referrer"), 300),
                "ts": _quando(bruto.get("ts"), agora),
                **contexto,
            }
        )
    return saida


def _texto(valor, limite):
    if valor is None:
        return ""
    return str(valor)[:limite]


def _inteiro(valor, teto):
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return min(n, teto)


def _quando(valor, agora):
    """ms do cliente -> datetime. Fora de ±2 dias, usa a hora do servidor."""
    try:
        quando = datetime.fromtimestamp(int(valor) / 1000, tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return agora
    if abs(quando - agora) > JANELA_DO_TS:
        return agora
    return quando


def _props(valor):
    """Mantém só rótulos curtos e escalares. Corta o que for grande ou aninhado."""
    if not isinstance(valor, dict):
        return {}
    limpo = {}
    for chave, item in list(valor.items())[:MAX_CHAVES_POR_PROP]:
        if not isinstance(chave, str):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            limpo[chave[:64]] = item if not isinstance(item, str) else item[:200]
    # Um teto de tamanho total, para uma propriedade não inflar a linha.
    if len(json.dumps(limpo, ensure_ascii=False).encode("utf-8")) > MAX_TAMANHO_PROP:
        return {}
    return limpo
