"""As perguntas que o painel faz ao banco — e o orçamento que elas respeitam.

Regra desta camada: cada TELA do painel fica abaixo de 15 consultas, medido em
`analytics/test_painel_orcamento.py`, e o custo NÃO cresce com o volume de
eventos (os índices `(name, ts)`, `(user, ts)`, `(anon_id, ts)` seguram o GROUP
BY). Teste de carga: 100k eventos, tela em < 2 s local.

A PESSOA é a mesma chave em todo lugar: o usuário quando identificado, senão o
`anon_id`. Uma pessoa em dez toques conta como uma; uma logada e uma anônima
contam como duas.

Bruto vive 90 dias; para períodos além disso o painel lê `DailyAggregate`
(`serie_de_agregado`). Enquanto a base é nova, tudo cabe no bruto.
"""
from datetime import timedelta

from django.db.models import CharField, Count, F, Min, Value
from django.db.models.functions import Coalesce, Cast, TruncDate, TruncWeek
from django.utils import timezone

from accounts.models import Pilar

from .models import DailyAggregate, Event

#: A chave de pessoa: user_id (como texto) ou, se anônimo, o anon_id.
PESSOA = Coalesce(Cast("user_id", CharField(max_length=40)), "anon_id")


def _inicio(dias):
    return timezone.now() - timedelta(days=dias)


# ---------------------------------------------------------------- visão geral

def ativos(dias):
    """Pessoas distintas com pelo menos um evento na janela (DAU/WAU/MAU)."""
    return (
        Event.objects.filter(ts__gte=_inicio(dias))
        .aggregate(n=Count(PESSOA, distinct=True))["n"]
        or 0
    )


def eventos_por_dia(dias):
    return list(
        Event.objects.filter(ts__gte=_inicio(dias))
        .annotate(dia=TruncDate("ts"))
        .values("dia")
        .annotate(n=Count("id"))
        .order_by("dia")
    )


def top_eventos(dias, limite=12):
    return list(
        Event.objects.filter(ts__gte=_inicio(dias))
        .values("name")
        .annotate(n=Count("id"), pessoas=Count(PESSOA, distinct=True))
        .order_by("-n")[:limite]
    )


def top_rotas(dias, limite=10):
    return list(
        Event.objects.filter(ts__gte=_inicio(dias), name="tela.vista")
        .exclude(route="")
        .values("route")
        .annotate(n=Count("id"))
        .order_by("-n")[:limite]
    )


def erros_js(dias, limite=10):
    inicio = _inicio(dias)
    total = Event.objects.filter(ts__gte=inicio, name="erro.js").count()
    principais = list(
        Event.objects.filter(ts__gte=inicio, name="erro.js")
        .values(msg=F("props__mensagem"), rota=F("props__rota"))
        .annotate(n=Count("id"))
        .order_by("-n")[:limite]
    )
    return total, principais


# ------------------------------------------------------------------- explorar

#: Atributos de usuário que o filtro entende, mapeados para o caminho ORM.
ATRIBUTOS = {
    "equipamento": "user__profile__equipamento",
    "objetivo": "user__profile__objetivo",
    "tema": "theme",
    "pwa": "pwa",
    "dispositivo": "device",
}


def explorar(nome, dias, filtros=None, agrupar=None):
    """Conta um evento na janela, com filtros por propriedade e por atributo do
    usuário, opcionalmente AGRUPADO por uma propriedade. Uma consulta."""
    qs = Event.objects.filter(name=nome, ts__gte=_inicio(dias))
    for chave, valor in (filtros or {}).items():
        if chave in ATRIBUTOS:
            qs = qs.filter(**{ATRIBUTOS[chave]: valor})
        else:  # propriedade do evento
            qs = qs.filter(**{f"props__{chave}": valor})
    if agrupar:
        return list(
            qs.values(valor=F(f"props__{agrupar}"))
            .annotate(n=Count("id"), pessoas=Count(PESSOA, distinct=True))
            .order_by("-n")
        )
    return list(
        qs.annotate(dia=TruncDate("ts"))
        .values("dia")
        .annotate(n=Count("id"), pessoas=Count(PESSOA, distinct=True))
        .order_by("dia")
    )


# --------------------------------------------------------------------- funil

def funil(passos, dias):
    """Conversão por etapa de uma sequência de eventos, na ORDEM do tempo.

    Uma consulta traz (pessoa, evento, primeiro_ts) da janela; o passo a passo
    é em Python, sobre no máximo tantas linhas quantas pessoas × passos — cabe
    na memória para a escala deste app. Devolve, por etapa, quantas pessoas
    chegaram e o tempo MEDIANO desde a etapa anterior.
    """
    linhas = (
        Event.objects.filter(name__in=passos, ts__gte=_inicio(dias))
        .values("name")
        .annotate(pessoa=PESSOA)
        .values("pessoa", "name")
        .annotate(t=Min("ts"))
    )
    # por pessoa: {evento: primeiro_ts}
    por_pessoa = {}
    for linha in linhas:
        por_pessoa.setdefault(linha["pessoa"], {})[linha["name"]] = linha["t"]

    resultado = []
    anterior_ok = None  # conjunto de pessoas que chegaram na etapa anterior
    for i, passo in enumerate(passos):
        deltas = []
        chegaram = set()
        for pessoa, tempos in por_pessoa.items():
            if passo not in tempos:
                continue
            if i == 0:
                chegaram.add(pessoa)
            elif pessoa in anterior_ok:
                t_ant = por_pessoa[pessoa][passos[i - 1]]
                if tempos[passo] >= t_ant:
                    chegaram.add(pessoa)
                    deltas.append((tempos[passo] - t_ant).total_seconds())
        resultado.append(
            {
                "evento": passo,
                "pessoas": len(chegaram),
                "mediana_s": _mediana(deltas) if i > 0 else None,
            }
        )
        anterior_ok = chegaram
    return resultado


def _mediana(valores):
    if not valores:
        return None
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return (ordenados[meio - 1] + ordenados[meio]) / 2


# ------------------------------------------------------------------ retenção

def retencao(semanas=8):
    """Coorte por semana de cadastro × semanas retornando.

    Duas consultas (cadastros e atividade), matriz em Python. A semana de
    cadastro vem do evento `conta.criada`; o retorno é qualquer evento.
    """
    limite = timezone.now() - timedelta(weeks=semanas)
    cadastros = (
        Event.objects.filter(name="conta.criada", ts__gte=limite)
        .annotate(pessoa=PESSOA, semana=TruncWeek("ts"))
        .values("pessoa", "semana")
    )
    coorte = {}  # pessoa -> semana de cadastro
    semana_de = {}
    for linha in cadastros:
        coorte[linha["pessoa"]] = linha["semana"]
        semana_de.setdefault(linha["semana"], set()).add(linha["pessoa"])

    if not coorte:
        return []

    atividade = (
        Event.objects.filter(ts__gte=limite, user__isnull=False)
        .annotate(pessoa=PESSOA, semana=TruncWeek("ts"))
        .values("pessoa", "semana")
        .distinct()
    )
    ativos_por_pessoa = {}
    for linha in atividade:
        ativos_por_pessoa.setdefault(linha["pessoa"], set()).add(linha["semana"])

    linhas = []
    for semana in sorted(semana_de):
        pessoas = semana_de[semana]
        base = len(pessoas)
        celulas = []
        for k in range(semanas):
            alvo = semana + timedelta(weeks=k)
            voltaram = sum(
                1 for p in pessoas if alvo in ativos_por_pessoa.get(p, ())
            )
            celulas.append(
                {"k": k, "n": voltaram, "pct": round(100 * voltaram / base) if base else 0}
            )
        linhas.append({"semana": semana, "base": base, "celulas": celulas})
    return linhas


# ------------------------------------------------------------------ usuário

def linha_do_tempo(chave, limite=200):
    """Todos os eventos de um usuário, por id (pk do usuário ou anon_id)."""
    from django.db.models import Q

    filtro = Q(anon_id=chave)
    if str(chave).isdigit():
        filtro |= Q(user_id=int(chave))
    return list(
        Event.objects.filter(filtro).order_by("-ts")[:limite]
    )


# ------------------------------------------------------------- longo prazo

def serie_de_agregado(nome, dias):
    """Para períodos além dos 90 dias do bruto: lê o DailyAggregate."""
    inicio = timezone.localdate() - timedelta(days=dias)
    return list(
        DailyAggregate.objects.filter(name=nome, prop_key="", day__gte=inicio)
        .values("day", "count", "users")
        .order_by("day")
    )


# ---------------------------------------------------------- funil de entrada
#
# A PERGUNTA É "ONDE A PESSOA DESISTE", e ela só tem resposta com os passos
# NOMEADOS e na ordem do produto. `funil()` acima é genérico — recebe nomes de
# evento e devolve o total da janela; aqui a lista é fechada, três passos são
# o MESMO evento com propriedade diferente (as etapas do cadastro), e o
# resultado vem por COORTE de dia ou de semana. Coorte, e não "eventos do
# dia": quem abriu a landing na segunda e treinou na quarta desistiu — ou não
# — daquela segunda, e contar a série de quarta como conversão de quarta faz
# a taxa de um dia depender do movimento do dia anterior.
#
#: Cada passo é `(chave, rótulo, nome do evento, filtro de propriedade)`.
PASSOS_DE_ENTRADA = (
    ("landing", "Abriu a landing", "site.landing_vista", {}),
    ("cadastro", "Começou o cadastro", "onboarding.iniciado", {}),
    ("etapa1", "Etapa 1 · sobre você", "onboarding.etapa_concluida", {"props__etapa": 1}),
    ("etapa2", "Etapa 2 · objetivo e rotina", "onboarding.etapa_concluida", {"props__etapa": 2}),
    ("etapa3", "Etapa 3 · personalização", "onboarding.etapa_concluida", {"props__etapa": 3}),
    ("refeicao", "1ª refeição registrada", "dieta.refeicao_registrada", {}),
    ("serie", "1ª série registrada", "treino.serie_concluida", {}),
)

GRANULARIDADES = {"dia": TruncDate, "semana": TruncWeek}


def funil_de_entrada(dias=30, por="dia"):
    """O funil de entrada por coorte de dia ou de semana.

    UMA consulta por passo (sete, fixas — não crescem com o volume nem com o
    número de coortes), e a matriz é montada em Python sobre `pessoas ×
    passos`. Cada pessoa entra na coorte do seu PRIMEIRO passo alcançado, e só
    conta num passo se o tempo dele veio DEPOIS do anterior — a mesma régua de
    ordem que `funil()` já aplica.

    Devolve `(coortes, total)`: cada coorte é `{quando, base, etapas}` e cada
    etapa traz `pessoas`, `pct_do_topo` e `pct_do_anterior`. A segunda é a que
    responde a pergunta — "de quem chegou aqui, quantos passaram?" —, e é ela
    que a tela destaca.
    """
    inicio = _inicio(dias)
    # {chave do passo: {pessoa: primeiro_ts}}
    quando = {}
    for chave, _rotulo, nome, filtro in PASSOS_DE_ENTRADA:
        linhas = (
            Event.objects.filter(name=nome, ts__gte=inicio, **filtro)
            .annotate(pessoa=PESSOA)
            .values("pessoa")
            .annotate(t=Min("ts"))
        )
        quando[chave] = {linha["pessoa"]: linha["t"] for linha in linhas}

    chaves = [p[0] for p in PASSOS_DE_ENTRADA]
    todas = set()
    for mapa in quando.values():
        todas |= set(mapa)
    # A COORTE é o PRIMEIRO passo que a pessoa alcançou, e a data dele. Quem
    # entrou direto pelo cadastro (link compartilhado, sem passar pela
    # landing) não fica de fora do funil: ela entra pela etapa em que
    # apareceu, e as etapas acima dela ficam zeradas naquela coorte — que é a
    # verdade, e não um buraco.
    coorte_de = {}
    for pessoa in todas:
        primeiro = next((c for c in chaves if pessoa in quando[c]), None)
        if primeiro is not None:
            coorte_de[pessoa] = quando[primeiro][pessoa]

    baldes = {}
    for pessoa, instante in coorte_de.items():
        baldes.setdefault(_balde(instante, por), set()).add(pessoa)

    coortes = [
        _linha_do_funil(rotulo, pessoas, quando, chaves)
        for rotulo, pessoas in sorted(baldes.items())
    ]
    total = _linha_do_funil(None, set(coorte_de), quando, chaves)
    return coortes, total


def _balde(instante, por):
    """A chave da coorte: a data (dia) ou a segunda-feira daquela semana."""
    data = timezone.localtime(instante).date()
    if por == "semana":
        return data - timedelta(days=data.weekday())
    return data


def _linha_do_funil(quando_rotulo, pessoas, quando, chaves):
    etapas = []
    chegaram_antes = None
    base = 0
    for i, chave in enumerate(chaves):
        if i == 0:
            chegaram = {p for p in pessoas if p in quando[chave]}
            base = len(chegaram)
        else:
            chegaram = {
                p for p in chegaram_antes
                if p in quando[chave] and quando[chave][p] >= quando[chaves[i - 1]][p]
            }
        anterior = len(chegaram_antes) if chegaram_antes is not None else len(chegaram)
        etapas.append(
            {
                "chave": chave,
                "pessoas": len(chegaram),
                "pct_do_topo": round(100 * len(chegaram) / base) if base else 0,
                "pct_do_anterior": round(100 * len(chegaram) / anterior) if anterior else 0,
            }
        )
        chegaram_antes = chegaram
    return {"quando": quando_rotulo, "base": base, "etapas": etapas}


# ---------------------------------------------------------- uso por área
#
#: Que evento conta como REGISTRO em cada pilar. É a lista que responde "o que
#: a base usa de fato" — e ela é de REGISTRO, não de visita: abrir a tela de
#: água não é beber água.
#: A CHAVE é o `value` de `accounts.models.Pilar`, e não um slug próprio: o
#: nome de cada área mora em `Pilar.label` e em nenhum outro lugar
#: (`CLAUDE.md`, "Uma área, um nome"). A primeira versão desta tabela usava
#: "alimentacao"/"hidratacao" e a tela escrevia `capfirst` em cima —
#: "Alimentacao" e "Hidratacao", sem acento, um TERCEIRO vocabulário para as
#: mesmas cinco áreas. `dieta` continuar valendo "Alimentação" é exatamente a
#: separação que `Pilar` existe para manter.
EVENTOS_DA_AREA = {
    Pilar.DIETA.value: ("dieta.refeicao_registrada", "dieta.pulou", "dieta.comeu_outra_coisa"),
    Pilar.TREINO.value: ("treino.serie_concluida",),
    Pilar.HIDRATACAO.value: ("agua.registrada",),
    Pilar.PROGRESSO.value: ("progresso.peso_registrado",),
    Pilar.CORRIDA.value: ("corrida.registrada",),
}


def nome_da_area(valor: str) -> str:
    """O nome de tela de uma área, do único lugar onde ele é escrito."""
    return Pilar(valor).label

#: Todo evento de registro, achatado — a régua de "voltou" da retenção e o
#: denominador do uso por área saem da MESMA lista, de propósito: duas
#: definições de "usou o app" é como duas telas passam a discordar.
EVENTOS_DE_REGISTRO = tuple(
    nome for nomes in EVENTOS_DA_AREA.values() for nome in nomes
)


# ------------------------------------------------------- retenção D1/D7/D30
#
#: Os degraus que a pergunta "a pessoa volta?" usa. Dia, e não semana: a
#: `retencao()` acima responde por SEMANA de retorno, que é a curva de longo
#: prazo; D1/D7/D30 é a régua de produto — voltou no dia seguinte, na semana,
#: no mês.
DEGRAUS_DE_RETENCAO = (1, 7, 30)


def retencao_por_coorte(semanas=8, degraus=DEGRAUS_DE_RETENCAO):
    """Coortes por SEMANA DE CADASTRO × D1 / D7 / D30.

    "Voltou" é ter REGISTRADO alguma coisa — uma refeição, uma série, um copo
    d'água — no dia D depois do cadastro, e não "abriu o app": abrir sem
    registrar é curiosidade, não retenção. Por isso a atividade sai de
    `EVENTOS_DE_REGISTRO`, a mesma lista que o uso por área usa.

    Duas consultas, matriz em Python. Coorte cuja janela ainda não fechou (o
    D30 de quem se cadastrou ontem) vem com `None` em vez de 0 — zero seria a
    tela afirmando que ninguém voltou de um prazo que ainda não chegou.
    """
    limite = timezone.now() - timedelta(weeks=semanas)
    cadastros = (
        Event.objects.filter(name="conta.criada", ts__gte=limite)
        .annotate(pessoa=PESSOA)
        .values("pessoa")
        .annotate(t=Min("ts"))
    )
    nasceu = {
        linha["pessoa"]: timezone.localtime(linha["t"]).date() for linha in cadastros
    }
    if not nasceu:
        return []

    atividade = (
        Event.objects.filter(name__in=EVENTOS_DE_REGISTRO, ts__gte=limite)
        .annotate(pessoa=PESSOA, dia=TruncDate("ts"))
        .values("pessoa", "dia")
        .distinct()
    )
    dias_de = {}
    for linha in atividade:
        dias_de.setdefault(linha["pessoa"], set()).add(linha["dia"])

    hoje = timezone.localdate()
    por_semana = {}
    for pessoa, dia in nasceu.items():
        por_semana.setdefault(dia - timedelta(days=dia.weekday()), []).append(pessoa)

    linhas = []
    for semana in sorted(por_semana):
        pessoas = por_semana[semana]
        celulas = []
        for d in degraus:
            # A janela fechou? O D7 de uma coorte de segunda só fecha no
            # domingo seguinte; enquanto não fechar, a célula é `None`.
            fechou = all(nasceu[p] + timedelta(days=d) <= hoje for p in pessoas)
            voltaram = sum(
                1 for p in pessoas
                if (nasceu[p] + timedelta(days=d)) in dias_de.get(p, ())
            )
            celulas.append(
                {
                    "d": d,
                    "n": voltaram if fechou else None,
                    "pct": (
                        round(100 * voltaram / len(pessoas))
                        if fechou and pessoas else None
                    ),
                }
            )
        linhas.append({"semana": semana, "base": len(pessoas), "celulas": celulas})
    return linhas


def uso_por_area(semanas=8):
    """Registros e pessoas por área, semana a semana.

    UMA consulta: `(semana, evento, pessoa) -> contagem`. O mapa de evento
    para área é aplicado em Python — são cinco áreas e sete eventos, e um
    `CASE WHEN` no SQL seria a mesma tabela escrita duas vezes.

    A pessoa vem na consulta de propósito: somar as pessoas distintas de dois
    eventos da MESMA área contaria duas vezes quem fez os dois, então a área
    junta os conjuntos antes de medir o tamanho.
    """
    limite = timezone.now() - timedelta(weeks=semanas)
    linhas = (
        Event.objects.filter(name__in=EVENTOS_DE_REGISTRO, ts__gte=limite)
        .annotate(pessoa=PESSOA, semana=TruncWeek("ts"))
        .values("semana", "name", "pessoa")
        .annotate(n=Count("pk"))
    )
    area_de = {
        nome: area for area, nomes in EVENTOS_DA_AREA.items() for nome in nomes
    }
    acumulado = {}
    for linha in linhas:
        semana = linha["semana"]
        semana = timezone.localtime(semana).date() if timezone.is_aware(semana) else semana
        balde = acumulado.setdefault(
            (semana, area_de[linha["name"]]), {"registros": 0, "pessoas": set()}
        )
        balde["registros"] += linha["n"]
        balde["pessoas"].add(linha["pessoa"])

    return [
        {
            "semana": semana,
            "areas": [
                {
                    "area": area,
                    "registros": acumulado.get((semana, area), {}).get("registros", 0),
                    "pessoas": len(acumulado.get((semana, area), {}).get("pessoas", ())),
                }
                for area in EVENTOS_DA_AREA
            ],
        }
        for semana in sorted({chave[0] for chave in acumulado})
    ]
