# -*- coding: utf-8 -*-
"""A adaptação da carga é LEITURA pura, e o estado dela tem nome (T2.1).

Este módulo não toca no banco, não lê o relógio e não fala com a rede: ele
recebe o que a tela já carregou (`load_history`, uma consulta) e devolve uma
`Progressao` — o número que o campo abre e a frase que fica ao lado dele. A
pureza é textual e tem teste (`workouts/test_adaptacao.py`): nada de
`django.db`, `timezone` ou `requests` aqui dentro. É o que permite provar a
regra com dublês em memória e simular um ano de treino sem uma consulta.

A regra é a dupla progressão de 13/09/2026 (ACSM 2009: +2–10% ao fechar a
faixa; Plotkin 2022: reps com carga fixa ≈ carga; degrau declarado baixo e
por isso ABSOLUTO — a menor anilha), agora com o estado NOMEADO:

- `SUBIR`  — todas as séries prescritas da última data fecharam `rep_max`
             NA MESMA carga (a maior daquela data). O degrau é 2,5 kg no
             tronco e 5 na perna, arredondado ao múltiplo de 2,5 acima;
- `MANTER` — a faixa não fechou, e a razão diz onde: em que série faltou
             quanto, ou que série foi feita mais leve. 60/60/55 com todas as
             reps no topo NÃO sobe: a terceira série não fechou a 60. O campo
             abre com 60 — a maior —, e a frase cita o mesmo 60 (frase ==
             campo, `MUDA_CARGA` diz quem muda o número);
- `None`   — não há o que dizer: sem histórico, histórico incompleto (menos
             séries anotadas que prescritas), série anotada HOJE (hoje
             manda), peso do corpo ou segundos (não há anilha).

`ajuste(item, sessoes, ultimo_registro, hoje)` recebe as últimas sessões do
exercício (até `SESSOES_LIDAS` datas, da mais recente para trás) e o último
registro antes de hoje: em T2.1 só a mais recente decide; `sessoes` e
`hoje` já chegam para as regras de RETOMAR e ESTAGNADO (T2.3), que leem
o intervalo entre datas e a sequência sem avanço.
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

#: `Measure.REPS` e os três grupos que sobem de 5 em 5, escritos aqui para o
#: módulo não importar os modelos; `test_adaptacao` confere que batem.
REPS = "reps"
GRUPOS_INFERIORES = frozenset({"quads", "hamstrings", "calves"})

#: A menor anilha: todo degrau e todo arredondamento saem dela.
DEGRAU_MINIMO = Decimal("2.5")
DEGRAU_INFERIOR = Decimal("5")

#: Quantas datas `load_history` entrega ao módulo. Dez cabem numa consulta
#: que a tela já faz e cobrem as regras de retomada e estagnação.
SESSOES_LIDAS = 10


class Estado(StrEnum):
    """O que a adaptação decidiu. `StrEnum`: `str(Estado.SUBIR) == "subir"`,
    que é o que o template imprime e o que os testes de 13/09 comparam."""

    SUBIR = "subir"
    MANTER = "manter"


#: Os estados em que o NÚMERO do campo muda. `MANTER` fala, mas não muda; é
#: por isso que a frase de "manter" cita a carga que o campo já tem.
MUDA_CARGA = frozenset({Estado.SUBIR})


@dataclass(frozen=True)
class Progressao:
    """O que a adaptação decidiu para a PRÓXIMA sessão de um exercício."""

    estado: Estado
    valor: Decimal     # a carga a abrir no campo
    razao: str         # a frase que a tela mostra ao lado


def _degrau(item) -> Decimal:
    return DEGRAU_INFERIOR if item.exercise.muscle_group in GRUPOS_INFERIORES else DEGRAU_MINIMO


def _arredonda_para_cima(valor: Decimal) -> Decimal:
    """Múltiplo de 2,5 para cima: 61 + 2,5 = 63,5 vira 65."""
    resto = valor % DEGRAU_MINIMO
    return valor - resto + DEGRAU_MINIMO if resto else valor


def _kg(valor: Decimal) -> str:
    """"60", "62,5" — sem zeros à direita e com vírgula, como a tela."""
    return format(valor.normalize(), "f").replace(".", ",")


def ajuste(item, sessoes, ultimo_registro, hoje):
    """A `Progressao` do exercício para a sessão que vai começar, ou `None`.

    `item` traz `sets`, `rep_min`, `rep_max`, `measure`, `exercise.sem_carga`,
    `exercise.muscle_group` e `load["hoje"]`; `sessoes` é a lista
    `[(data, {serie: registro})]` da mais recente para trás, cada registro
    com `weight_kg` e `reps`; `ultimo_registro` é o registro mais recente
    antes de `hoje` (ou `None`).
    """
    if (getattr(item, "load", None) or {}).get("hoje"):
        return None
    if item.measure != REPS or item.exercise.sem_carga:
        return None
    if not sessoes:
        return None
    _data, anterior = sessoes[0]
    if len(anterior) < item.sets:
        return None
    numeros = sorted(anterior)[: item.sets]
    series = [anterior[n] for n in numeros]
    if any(s.weight_kg is None for s in series):
        return None
    maior = max(s.weight_kg for s in series)

    # Série feita mais leve que a maior do dia não fechou a faixa NAQUELA
    # carga — 60/60/55 mantém 60, e diz por quê.
    mais_leves = [(n, s.weight_kg) for n, s in zip(numeros, series) if s.weight_kg < maior]
    faltas = [
        (n, item.rep_max - (s.reps or 0))
        for n, s in zip(numeros, series)
        if (s.reps or 0) < item.rep_max
    ]
    if not faltas and not mais_leves:
        alvo = _arredonda_para_cima(maior + _degrau(item))
        return Progressao(
            Estado.SUBIR, alvo,
            "fechou %d×%d na última vez" % (item.sets, item.rep_max),
        )
    if faltas:
        numero, quanto = faltas[0]
        return Progressao(
            Estado.MANTER, maior,
            "faltaram %d rep%s na série %d para subir" % (quanto, "" if quanto == 1 else "s", numero),
        )
    numero, peso = mais_leves[0]
    return Progressao(
        Estado.MANTER, maior,
        "a série %d foi a %s kg — feche %s kg nas %d para subir" % (numero, _kg(peso), _kg(maior), item.sets),
    )
