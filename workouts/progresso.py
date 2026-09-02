"""O que a tela de progresso pode afirmar sobre o treino.

Duas perguntas, e as duas se respondem só com o que a pessoa registrou:

  "eu tenho treinado?"      -> em quantos dias houve série anotada
  "eu fiquei mais forte?"   -> a carga máxima por exercício, antes e agora

O que este módulo NÃO calcula, e por quê:

VOLUME TOTAL. "12.400 kg no mês" é o exemplo de métrica sem ação: o número não
muda a próxima série. Progressão de carga por exercício muda — ela diz onde
subir.

ADERÊNCIA AO PLANO. `TrainingDay` guarda os dias que a pessoa DECLAROU, e
`ExerciseLog` os dias em que ela anotou série. A distância entre os dois é
comportamento, e tratar declaração como comportamento é o erro que a régua de
frequência deste projeto existe para impedir. Os dois números aparecem lado a
lado, sem virar uma porcentagem que finge medir compromisso.
"""
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from .models import ExerciseLog

#: Oito semanas: o mesmo horizonte da tendência de peso. Duas telas do mesmo
#: app medindo janelas diferentes convidam a comparações que não valem.
SEMANAS = 8

#: Quantos exercícios cabem na tela sem virar planilha. Os mais recentes.
EXERCICIOS_NA_TELA = 6


def _inicio_da_semana(dia):
    """Segunda-feira. A semana do app começa na segunda, como no resto dele."""
    return dia - timedelta(days=dia.weekday())


def dias_treinados(user, hoje=None, semanas=SEMANAS) -> list:
    """Por semana: em quantos DIAS houve série anotada.

    Dias e não séries. Quem faz cinco exercícios num dia registra dezenas de
    linhas, e contar linhas transformaria um dia em uma semana movimentada.
    """
    hoje = hoje or timezone.localdate()
    primeira = _inicio_da_semana(hoje) - timedelta(weeks=semanas - 1)

    datas = (
        ExerciseLog.objects.filter(user=user, date__gte=primeira)
        # `order_by()` vazio ANTES do `distinct()`, e não é estilo: o
        # `Meta.ordering` do model é `["-date", "set_number"]`, e o Django põe
        # as colunas de ordenação no SELECT. Com `set_number` lá dentro, cada
        # série vira uma linha distinta e o "distinct" passa a não distinguir
        # nada — cinco séries num dia contavam como cinco dias.
        .order_by()
        .values_list("date", flat=True)
        .distinct()
    )
    por_semana = {}
    for data in datas:
        por_semana[_inicio_da_semana(data)] = por_semana.get(
            _inicio_da_semana(data), 0
        ) + 1

    return [
        {"inicio": primeira + timedelta(weeks=n), "dias": por_semana.get(
            primeira + timedelta(weeks=n), 0
        )}
        for n in range(semanas)
    ]


def progressao_de_carga(user, hoje=None, semanas=SEMANAS) -> list:
    """Por exercício: a maior carga do começo da janela e a de agora.

    Compara o PRIMEIRO registro da janela com o ÚLTIMO, e não o máximo de tudo
    com o máximo de tudo: o segundo devolveria "seu recorde é seu recorde",
    que é verdade e não é evolução.

    Exercício que aparece uma vez só fica de fora — com um ponto não há reta, e
    mostrar "60 kg → 60 kg" para quem treinou uma vez sugere estagnação onde
    houve uma sessão.
    """
    hoje = hoje or timezone.localdate()
    inicio = _inicio_da_semana(hoje) - timedelta(weeks=semanas - 1)

    linhas = (
        ExerciseLog.objects.filter(user=user, date__gte=inicio)
        .values("exercise_id", "exercise__name", "date")
        .annotate(carga=Max("weight_kg"))
        .order_by("exercise_id", "date")
    )

    por_exercicio = {}
    for linha in linhas:
        if not linha["carga"]:
            # Peso corporal grava ZERO, não nulo — a coluna é `NOT NULL` com
            # mínimo 0. Sem esta guarda, flexão e barra apareceriam como
            # "0 kg → 0 kg", que lê como estagnação e é ausência de carga.
            # Elas contam como treino em `dias_treinados`; aqui não há o que
            # comparar, e inventar um número seria inventar o progresso.
            continue
        registro = por_exercicio.setdefault(
            linha["exercise_id"],
            {"nome": linha["exercise__name"], "primeiro": None, "ultimo": None,
             "primeira_data": None, "ultima_data": None, "sessoes": 0},
        )
        if registro["primeiro"] is None:
            registro["primeiro"] = linha["carga"]
            registro["primeira_data"] = linha["date"]
        registro["ultimo"] = linha["carga"]
        registro["ultima_data"] = linha["date"]
        registro["sessoes"] += 1

    resultado = [
        {**dados, "delta": dados["ultimo"] - dados["primeiro"]}
        for dados in por_exercicio.values()
        if dados["sessoes"] >= 2
    ]
    resultado.sort(key=lambda d: (d["ultima_data"], d["delta"]), reverse=True)
    return resultado[:EXERCICIOS_NA_TELA]
