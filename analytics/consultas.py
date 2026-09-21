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
