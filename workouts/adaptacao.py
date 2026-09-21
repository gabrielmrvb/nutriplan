# -*- coding: utf-8 -*-
"""A adaptação da carga é LEITURA pura, e o estado dela tem nome (T2.1, T2.3).

Este módulo não toca no banco, não lê o relógio e não fala com a rede: ele
recebe o que a tela já carregou (`load_history`, uma consulta) e devolve uma
`Progressao` — o número que o campo abre e a frase que fica ao lado dele. A
pureza é textual e tem teste (`workouts/test_adaptacao.py`): nada de
`django.db`, `timezone` ou `requests` aqui dentro. É o que permite provar a
regra com dublês em memória e simular um ano de treino sem uma consulta.

A regra é a dupla progressão de 13/09/2026 (ACSM 2009: +2–10% ao fechar a
faixa; Plotkin 2022: reps com carga fixa ≈ carga; degrau declarado baixo e
por isso ABSOLUTO — a menor anilha), com o estado NOMEADO:

- `SUBIR`    — todas as séries prescritas da referência fecharam `rep_max`
               NA MESMA carga (a maior daquela data). O degrau é 2,5 kg no
               tronco e 5 na perna, arredondado ao múltiplo de 2,5 acima;
- `MANTER`   — a faixa não fechou, e a razão diz onde: em que série faltou
               quanto, ou que série foi feita mais leve. 60/60/55 com todas
               as reps no topo NÃO sobe: a terceira série não fechou a 60.
               O campo abre com 60 — a maior —, e a frase cita o mesmo 60
               (frase == campo, `MUDA_CARGA` diz quem muda o número);
- `RETOMAR`  — (T2.3) `DIAS_PARA_RETOMAR` (21) dias ou mais sem NENHUMA
               série deste exercício: mesma carga, SUBIR suspenso mesmo com
               a faixa fechada, reps no piso, e a frase pede para confirmar
               a carga; a partir de `DIAS_PARA_RETOMAR_MAIS_LEVE` (28) ela
               acrescenta "comece mais leve se precisar" — o app NÃO propõe
               número menor (decisão C2-A do brief de 13/09: DESCER fica
               fora). 21 vem de Hwang 2017 (duas semanas sem perda) e
               Bosquet 2013 ("significativo a partir da terceira semana");
- `ESTAGNADO` — (T2.3) três sessões completas seguidas (≤ 27 dias entre
               elas) na MESMA carga máxima, nenhuma fechou a faixa, e o
               total de repetições da última não passou o da primeira por
               mais de `REPS_DE_RUIDO` (1; Mitter 2022: uma rep é ruído de
               medição). "Manter e dizer": o campo abre com a mesma carga e a
               frase diz que são três treinos sem ganhar repetição —
               nenhum RESET, nenhum número menor;
- `ESTAGNADO_PERSISTENTE` — a trava escrita desde já para o dia em que um
               RESET existir (C2-B): o mesmo platô depois de um recomeço
               (uma sessão mais leve seguida da volta à mesma carga em ≤ 56
               dias) é só frase, nunca outro RESET em cadeia;
- `None`     — não há o que dizer: sem histórico, sem sessão COMPLETA
               (menos séries anotadas que prescritas) nas últimas
               `DATAS_DA_REFERENCIA` datas, série anotada HOJE (hoje manda),
               peso do corpo ou segundos (não há anilha).

Precedência, fixa: hoje manda > sem anilha > sem referência completa >
RETOMAR > SUBIR > ESTAGNADO(_PERSISTENTE) > MANTER. Uma razão por estado.

`ajuste(item, sessoes, ultimo_registro, hoje)` recebe as últimas sessões do
exercício (até `SESSOES_LIDAS` datas, da mais recente para trás) e o último
registro antes de hoje. A referência é a primeira sessão COMPLETA entre as
quatro mais recentes; o intervalo da retomada é contado do ÚLTIMO REGISTRO,
de qualquer série — uma sessão parcial há 5 dias com a completa há 20 não é
pausa. Os dias (21, 28, 27, 56) e o "+1" são calibração [HIPOTÉTICA] do
brief; `medir_progressao` (T2.4) é o que vai revê-los com dado.
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

#: `Measure.REPS` e os três grupos que sobem de 5 em 5, escritos aqui para o
#: módulo não importar os modelos; `test_adaptacao` confere que batem.
REPS = "reps"
GRUPOS_INFERIORES = frozenset({"quads", "hamstrings", "glutes", "calves"})

#: A menor anilha: todo degrau e todo arredondamento saem dela.
DEGRAU_MINIMO = Decimal("2.5")
DEGRAU_INFERIOR = Decimal("5")

#: Quantas datas `load_history` entrega ao módulo. Dez cabem numa consulta
#: que a tela já faz e cobrem as regras de retomada e estagnação.
SESSOES_LIDAS = 10

#: A referência (a sessão que decide SUBIR/MANTER) é a primeira COMPLETA
#: entre estas datas mais recentes; a estagnação lê as três primeiras
#: completas entre estas.
DATAS_DA_REFERENCIA = 4
DATAS_DA_ESTAGNACAO = 6

#: RETOMAR: dias sem série deste exercício. Hwang 2017 dá duas semanas sem
#: perda; Bosquet 2013, "significativo a partir da terceira semana" — 21, e
#: não 15 (que freava sem evidência). A partir de 28 a frase acrescenta
#: "comece mais leve se precisar".
DIAS_PARA_RETOMAR = 21
DIAS_PARA_RETOMAR_MAIS_LEVE = 28

#: ESTAGNADO: três sessões completas seguidas, com no máximo 27 dias entre
#: uma e a seguinte (mais que isso é pausa, não platô), na mesma carga, sem
#: fechar, e sem ganhar mais de 1 repetição no total (Mitter 2022).
SESSOES_PARA_ESTAGNAR = 3
DIAS_ENTRE_SESSOES_DO_PLATO = 27
REPS_DE_RUIDO = 1

#: A trava do RESET em cadeia: um recomeço (sessão mais leve seguida da
#: volta à mesma carga) dentro deste prazo torna o platô PERSISTENTE.
DIAS_DO_RECOMECO = 56


class Estado(StrEnum):
    """O que a adaptação decidiu. `StrEnum`: `str(Estado.SUBIR) == "subir"`,
    que é o que os testes de 13/09 comparam; o que a TELA imprime é
    `Progressao.rotulo`, o verbo — "estagnado" não é verbo."""

    SUBIR = "subir"
    MANTER = "manter"
    RETOMAR = "retomar"
    ESTAGNADO = "estagnado"
    ESTAGNADO_PERSISTENTE = "estagnado_persistente"


#: Os estados em que o NÚMERO do campo muda. `MANTER` fala, mas não muda; é
#: por isso que a frase de "manter" cita a carga que o campo já tem.
#: RETOMAR e ESTAGNADO também não mudam: o campo abre com a carga de sempre,
#: a CONFIRMAR.
MUDA_CARGA = frozenset({Estado.SUBIR})

#: Os estados em que as repetições sugeridas voltam ao PISO da faixa: carga
#: nova (a dupla progressão) e retomada (Bosquet 2013: o que se perde
#: primeiro é a resistência de força — fechar a faixa de novo é o teste).
REPS_NO_PISO = frozenset({Estado.SUBIR, Estado.RETOMAR})

#: O verbo que a tela mostra ao lado do número — "Sugestão: manter 60 kg".
#: ESTAGNADO é "manter e dizer": o verbo é manter; a frase é que muda.
ROTULO = {
    Estado.SUBIR: "subir",
    Estado.MANTER: "manter",
    Estado.RETOMAR: "retomar",
    Estado.ESTAGNADO: "manter",
    Estado.ESTAGNADO_PERSISTENTE: "manter",
}


@dataclass(frozen=True)
class Progressao:
    """O que a adaptação decidiu para a PRÓXIMA sessão de um exercício."""

    estado: Estado
    valor: Decimal     # a carga a abrir no campo
    razao: str         # a frase que a tela mostra ao lado

    @property
    def rotulo(self) -> str:
        return ROTULO[self.estado]


def _degrau(item) -> Decimal:
    return DEGRAU_INFERIOR if item.exercise.muscle_group in GRUPOS_INFERIORES else DEGRAU_MINIMO


def _arredonda_para_cima(valor: Decimal) -> Decimal:
    """Múltiplo de 2,5 para cima: 61 + 2,5 = 63,5 vira 65."""
    resto = valor % DEGRAU_MINIMO
    return valor - resto + DEGRAU_MINIMO if resto else valor


def _kg(valor: Decimal) -> str:
    """"60", "62,5" — sem zeros à direita e com vírgula, como a tela."""
    return format(valor.normalize(), "f").replace(".", ",")


def _series(registros, sets):
    """As `sets` primeiras séries anotadas, na ordem: [(número, registro)]."""
    return [(n, registros[n]) for n in sorted(registros)[:sets]]


def sessao_completa(registros, sets) -> bool:
    """Pelo menos `sets` séries anotadas, todas com carga — a definição de
    "sessão completa" que a referência e a estagnação usam."""
    if len(registros) < sets:
        return False
    return all(r.weight_kg is not None for _, r in _series(registros, sets))


def _maior(registros, sets) -> Decimal:
    return max(r.weight_kg for _, r in _series(registros, sets))


def _fechou(item, registros) -> bool:
    """Todas as séries prescritas com `rep_max` NA MAIOR carga do dia."""
    maior = _maior(registros, item.sets)
    return all(
        r.weight_kg == maior and (r.reps or 0) >= item.rep_max
        for _, r in _series(registros, item.sets)
    )


def _total(registros, sets):
    """A soma das repetições das séries prescritas, ou `None` se alguma não
    foi anotada — sem número não há como medir avanço (T2.3: reps `None`
    numa das três sessões é MANTER, não estagnação)."""
    reps = [r.reps for _, r in _series(registros, sets)]
    if any(r is None for r in reps):
        return None
    return sum(reps)


def _intervalo(sessoes, ultimo_registro, hoje):
    """Dias desde a ÚLTIMA série deste exercício (qualquer série, completa
    ou não), ou `None` quando não dá para saber (load antigo sem data)."""
    ultima = getattr(ultimo_registro, "date", None) or sessoes[0][0]
    if ultima is None or hoje is None:
        return None
    return (hoje - ultima).days


def _estagnacao(item, sessoes, maior):
    """O platô: três completas seguidas na mesma carga, nenhuma fechou, sem
    ganhar mais de `REPS_DE_RUIDO` repetições da primeira à última."""
    completas = [
        (d, r) for d, r in sessoes[:DATAS_DA_ESTAGNACAO] if sessao_completa(r, item.sets)
    ][:SESSOES_PARA_ESTAGNAR]
    if len(completas) < SESSOES_PARA_ESTAGNAR:
        return None
    datas = [d for d, _ in completas]
    if any(d is None for d in datas):
        return None
    if any((datas[i] - datas[i + 1]).days > DIAS_ENTRE_SESSOES_DO_PLATO for i in range(len(datas) - 1)):
        return None
    if any(_maior(r, item.sets) != maior for _, r in completas):
        return None
    if any(_fechou(item, r) for _, r in completas):
        return None
    totais = [_total(r, item.sets) for _, r in completas]
    if any(t is None for t in totais):
        return None
    if totais[0] > totais[-1] + REPS_DE_RUIDO:
        return None
    frase = "três treinos em %s kg sem ganhar repetição" % _kg(maior)
    if _houve_recomeco(item, sessoes, maior, datas[-1]):
        return Progressao(
            Estado.ESTAGNADO_PERSISTENTE, maior,
            "de novo %s — a carga já recomeçou uma vez; mantenha" % frase,
        )
    return Progressao(Estado.ESTAGNADO, maior, frase)


def _houve_recomeco(item, sessoes, maior, antes_de):
    """Antes do platô houve uma sessão mais leve seguida da volta à MESMA
    carga em até `DIAS_DO_RECOMECO` dias? É o rastro de um RESET (ou de um
    recomeço à mão) — a trava contra RESET em cadeia, escrita antes de
    existir RESET."""
    anteriores = [
        (d, r) for d, r in sessoes
        if d is not None and d < antes_de and sessao_completa(r, item.sets)
    ]
    # `sessoes` vem da mais recente para trás; a volta (mesma carga) é mais
    # recente que a sessão leve, e o próprio platô conta como volta.
    voltas = [antes_de] + [d for d, r in anteriores if _maior(r, item.sets) == maior]
    for data_leve, registros in anteriores:
        if _maior(registros, item.sets) >= maior:
            continue
        if any(0 < (volta - data_leve).days <= DIAS_DO_RECOMECO for volta in voltas):
            return True
    return False


def ajuste(item, sessoes, ultimo_registro, hoje):
    """A `Progressao` do exercício para a sessão que vai começar, ou `None`.

    `item` traz `sets`, `rep_min`, `rep_max`, `measure`, `exercise.sem_carga`,
    `exercise.muscle_group` e `load["hoje"]`; `sessoes` é a lista
    `[(data, {serie: registro})]` da mais recente para trás, cada registro
    com `weight_kg` e `reps`; `ultimo_registro` é o registro mais recente
    antes de `hoje` (ou `None`); `hoje` é a data da sessão que vai começar.
    """
    if (getattr(item, "load", None) or {}).get("hoje"):
        return None
    if item.measure != REPS or item.exercise.sem_carga:
        return None
    if not sessoes:
        return None
    referencia = next(
        ((d, r) for d, r in sessoes[:DATAS_DA_REFERENCIA] if sessao_completa(r, item.sets)), None
    )
    if referencia is None:
        return None
    _data, anterior = referencia
    numeros_e_series = _series(anterior, item.sets)
    maior = _maior(anterior, item.sets)

    # RETOMAR vence SUBIR: depois de três semanas parado, fechar a faixa da
    # última vez não é licença para subir — é para confirmar.
    dias = _intervalo(sessoes, ultimo_registro, hoje)
    if dias is not None and dias >= DIAS_PARA_RETOMAR_MAIS_LEVE:
        return Progressao(
            Estado.RETOMAR, maior,
            "%d dias sem este exercício: confirme a carga — comece mais leve se precisar" % dias,
        )
    if dias is not None and dias >= DIAS_PARA_RETOMAR:
        return Progressao(
            Estado.RETOMAR, maior,
            "%d dias sem este exercício: confirme a carga hoje" % dias,
        )

    # Série feita mais leve que a maior do dia não fechou a faixa NAQUELA
    # carga — 60/60/55 mantém 60, e diz por quê.
    mais_leves = [(n, s.weight_kg) for n, s in numeros_e_series if s.weight_kg < maior]
    faltas = [
        (n, item.rep_max - (s.reps or 0))
        for n, s in numeros_e_series
        if (s.reps or 0) < item.rep_max
    ]
    if not faltas and not mais_leves:
        alvo = _arredonda_para_cima(maior + _degrau(item))
        return Progressao(
            Estado.SUBIR, alvo,
            "fechou %d×%d na última vez" % (item.sets, item.rep_max),
        )
    plato = _estagnacao(item, sessoes, maior)
    if plato is not None:
        return plato
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
