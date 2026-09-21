# -*- coding: utf-8 -*-
"""O leitor do `CHANGELOG.md` — "O que mudou", para gente.

O `BACKLOG.md` é o caderno de engenharia (por que cada decisão foi tomada,
o que ficou medido) e não serve para quem usa o app. O `CHANGELOG.md` é
outro documento, com outra régua: uma seção por dia (`## AAAA-MM-DD`), um
item por mudança que a pessoa VÊ (`- **Título.** Uma frase.`), sem nome de
arquivo, sem número de PR. Este módulo só lê — e lê pouco de propósito:
título em negrito, `código` e o resto escapado. Markdown inteiro seria uma
dependência para renderizar três marcas.
"""
import html
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

_SECAO = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$")
_ITEM = re.compile(r"^- (.+)$")


def _inline(texto: str) -> str:
    """Escapa tudo e devolve só duas marcas: `**negrito**` e `` `código` ``."""
    partes = []
    for i, trecho in enumerate(re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", texto)):
        if not trecho:
            continue
        if i % 2 == 0:
            partes.append(html.escape(trecho))
        elif trecho.startswith("**"):
            partes.append("<strong>%s</strong>" % html.escape(trecho[2:-2]))
        else:
            partes.append("<code>%s</code>" % html.escape(trecho[1:-1]))
    return "".join(partes)


def ler(texto: str) -> list:
    """`[{"data": date, "itens": [html, ...]}, ...]` na ordem do arquivo
    (o mais recente primeiro — é assim que o arquivo é escrito, e o teste
    cobra). Linha que não é seção nem item é ignorada."""
    secoes = []
    for linha in texto.splitlines():
        m = _SECAO.match(linha)
        if m:
            secoes.append({"data": date.fromisoformat(m.group(1)), "itens": []})
            continue
        m = _ITEM.match(linha)
        if m and secoes:
            secoes[-1]["itens"].append(_inline(m.group(1).strip()))
    return secoes


@lru_cache(maxsize=1)
def _carregar(marca):
    return ler(ARQUIVO.read_text(encoding="utf-8"))


def mudancas() -> list:
    """As seções do arquivo, relidas quando ele muda (a marca é o mtime)."""
    try:
        marca = ARQUIVO.stat().st_mtime_ns
    except OSError:
        return []
    return _carregar(marca)
