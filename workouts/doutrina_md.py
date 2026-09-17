# -*- coding: utf-8 -*-
"""O leitor GENÉRICO de tabela markdown — extraído de `workouts/doutrina.py`
em 17/09/2026, quando `workouts/doutrina_corrida.py` precisou da mesma leitura
para `CORRIDA.md`.

Nada aqui sabe o que é treino nem o que é corrida: só sabe ler uma tabela
`| a | b | c |` e uma célula `a–b` ou inteira. Os dois documentos — TREINO.md
e CORRIDA.md — têm o VOCABULÁRIO das colunas diferente; a FORMA da tabela é a
mesma, e é só essa forma que este módulo entende.
"""
import re

_FAIXA = re.compile(r"^\s*(\d+)\s*(?:[–\-]\s*(\d+))?\s*$")


def faixa(texto):
    """`"24"` -> `(24, 24)`; `"8–12"` -> `(8, 12)`. Erra alto de propósito:
    célula sem número é defeito no documento, não valor ausente."""
    m = _FAIXA.match(texto)
    if not m:
        raise ValueError("célula sem número: %r" % texto)
    minimo = int(m.group(1))
    maximo = int(m.group(2)) if m.group(2) else minimo
    return (minimo, maximo)


def tabelas(texto):
    """Toda tabela markdown do documento, indexada pela tupla do cabeçalho."""
    tabelas = {}
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()
        if linha.startswith("|") and i + 1 < len(linhas) and re.match(r"^\|[\s\-:|]+\|$", linhas[i + 1].strip()):
            cabecalho = tuple(c.strip() for c in linha.strip("|").split("|"))
            corpo = []
            i += 2
            while i < len(linhas) and linhas[i].strip().startswith("|"):
                celulas = [c.strip() for c in linhas[i].strip().strip("|").split("|")]
                corpo.append(dict(zip(cabecalho, celulas)))
                i += 1
            tabelas[cabecalho] = corpo
            continue
        i += 1
    return tabelas
