# -*- coding: utf-8 -*-
"""O leitor do `docs/briefs/corrida/CORRIDA.md` — a doutrina do plano de corrida.

O DOCUMENTO É A FONTE; este módulo só lê. Cada sessão que a tela de corrida
mostra — descrição e minutos, por plano, nível e semana — sai das tabelas do
CORRIDA.md, lidas UMA vez do disco. `workouts/test_corrida_md.py` cobra que o
que está escrito é o que este módulo entrega, com um segundo parser — como
`workouts/test_treino_md.py` cobra `workouts/doutrina.py`.

O parser de tabela markdown é o mesmo dos dois documentos:
`workouts/doutrina_md.py`, extraído de `workouts/doutrina.py` para não copiar
a leitura de `| a | b | c |` uma segunda vez.
"""
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from .doutrina_md import tabelas

DOCUMENTO = Path(__file__).resolve().parent.parent / "docs" / "briefs" / "corrida" / "CORRIDA.md"


#: ESTE ARQUIVO É CÓDIGO, no mesmo sentido que `workouts/doutrina.py` é:
#: `carregar()` valida na importação (via `PlanoDeCorridaView` e
#: `HistoricoDeCorridasView`, que chamam `planos()`/`sessoes()` no primeiro
#: request) que as 96 linhas existem — um CORRIDA.md com uma linha faltando
#: derruba a tela de corrida em vez de mostrar uma semana incompleta em
#: silêncio.
@lru_cache(maxsize=1)
def carregar():
    """As três tabelas do documento, uma vez por processo."""
    texto = DOCUMENTO.read_text(encoding="utf-8")
    tabs = tabelas(texto)

    por_plano = {}
    for linha in tabs[("plano", "nivel", "semanas", "sessoes_por_semana")]:
        por_plano[(linha["plano"], linha["nivel"])] = {
            "semanas": int(linha["semanas"]),
            "sessoes_por_semana": int(linha["sessoes_por_semana"]),
        }

    por_sessao = {}
    for linha in tabs[("plano", "nivel", "semana", "sessao", "descricao", "minutos")]:
        chave = (linha["plano"], linha["nivel"], int(linha["semana"]), int(linha["sessao"]))
        por_sessao[chave] = {
            "descricao": linha["descricao"],
            "minutos": int(linha["minutos"]),
        }

    gasto = {linha["medida"]: linha["valor"] for linha in tabs[("medida", "valor")]}
    if "fator_kcal_por_kg_km" not in gasto:
        raise ValueError("CORRIDA.md sem a linha fator_kcal_por_kg_km na tabela Gasto")
    # Vírgula decimal, como todo número de tela do app — `faixa()` só entende
    # inteiro e faixa de inteiro, então o fator é lido à parte.
    fator = Decimal(gasto["fator_kcal_por_kg_km"].replace(",", "."))

    # A MESMA VALIDAÇÃO EAGER de `workouts/doutrina.py`: uma linha faltando na
    # tabela Sessões não pode virar uma semana incompleta descoberta em
    # produção — o boot (ou o primeiro acesso à tela de corrida) já reprova.
    faltam = [
        (plano, nivel, semana, sessao)
        for (plano, nivel), dados in por_plano.items()
        for semana in range(1, dados["semanas"] + 1)
        for sessao in range(1, dados["sessoes_por_semana"] + 1)
        if (plano, nivel, semana, sessao) not in por_sessao
    ]
    if faltam:
        raise ValueError("CORRIDA.md sem sessão para %s" % faltam)

    return {"planos": por_plano, "sessoes": por_sessao, "fator_kcal": fator}


def planos() -> dict:
    """`{("5k", "iniciante"): {"semanas": 8, "sessoes_por_semana": 3}, ...}`,
    uma entrada por combinação de plano e nível."""
    return carregar()["planos"]


def sessoes(plano, nivel, semana) -> list:
    """As sessões da semana, na ordem 1, 2, 3 — `[{"sessao", "descricao", "minutos"}, ...]`."""
    dados_do_plano = carregar()["planos"].get((plano, nivel))
    if dados_do_plano is None:
        raise ValueError("CORRIDA.md sem o plano %s" % ((plano, nivel),))
    todas = carregar()["sessoes"]
    saida = []
    for numero in range(1, dados_do_plano["sessoes_por_semana"] + 1):
        chave = (plano, nivel, semana, numero)
        dados = todas.get(chave)
        if dados is None:
            raise ValueError("CORRIDA.md sem sessão para %s" % (chave,))
        saida.append({"sessao": numero, **dados})
    return saida


def fator_kcal() -> Decimal:
    """O mesmo fator que `workouts/corrida.py::FATOR_KCAL_POR_KG_KM` usa —
    os dois precisam bater, e `test_corrida_md.py` cobra."""
    return carregar()["fator_kcal"]
