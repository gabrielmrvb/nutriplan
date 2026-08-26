"""A aba de monitoramento: o que o aluno fez, em números comparáveis.

Três leituras, e só três. A tentação num painel profissional é mostrar tudo que
o banco tem; o efeito é que o profissional não olha nada. Aqui ficam as
perguntas que mudam a conduta da semana: o peso está indo para onde deveria, a
pessoa está comendo o que foi combinado, e o treino está progredindo.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from plans import weight_trend
from plans.models import MealLog, MealStatus
from workouts.models import ExerciseLog

#: Duas semanas de dieta. Sete dias pega a semana corrente e não dá comparação;
#: trinta vira parede de números.
DIAS_DE_DIETA = 14
#: Oito sessões de treino é o bastante para a linha de volume ter forma.
SESSOES_NO_HISTORICO = 8

#: Margem em que o dia conta como "dentro da meta". Dez por cento de 2.500 kcal
#: são 250 — a diferença entre uma colher de azeite a mais ou a menos, que não
#: é desvio de dieta nenhum.
MARGEM_META = Decimal("0.10")


@dataclass
class DiaDeDieta:
    data: object
    kcal: int
    meta: int
    marcadas: int
    cumpridas: int

    @property
    def desvio_pct(self) -> int:
        if not self.meta:
            return 0
        return int((self.kcal - self.meta) * 100 / self.meta)

    @property
    def situacao(self) -> str:
        """"dentro", "abaixo" ou "acima" — é o que a pílula do dia pinta."""
        if not self.meta or not self.marcadas:
            return "vazio"
        limite = self.meta * MARGEM_META
        if abs(self.kcal - self.meta) <= limite:
            return "dentro"
        return "abaixo" if self.kcal < self.meta else "acima"


@dataclass
class Sessao:
    data: object
    exercicios: int
    series: int
    volume_kg: Decimal
    #: Diferença de volume para a sessão anterior. `None` na primeira.
    delta: object = None


def grafico_de_peso(student, meta_kg=None) -> dict:
    """Média semanal contra a meta, pronta para virar barras na tela.

    A altura de cada barra é relativa à faixa do período, e não ao zero: numa
    escala que começa no zero, oitenta e dois quilos e oitenta e cinco são a
    mesma barra, e o gráfico inteiro não diz nada.
    """
    tendencia = weight_trend.analisar(student)
    semanas = tendencia.semanas
    if not semanas:
        return {"tem_dados": False, "semanas": [], "tendencia": tendencia}

    valores = [s.media for s in semanas]
    if meta_kg is not None:
        valores = valores + [Decimal(meta_kg)]
    piso, teto = min(valores), max(valores)
    faixa = teto - piso

    linhas = []
    for semana in semanas:
        if faixa > 0:
            # 12% de piso: uma barra de altura zero parece dado faltando.
            altura = 12 + int((semana.media - piso) / faixa * 76)
        else:
            altura = 50
        linhas.append(
            {
                "inicio": semana.inicio,
                "media": semana.media,
                "delta": semana.delta,
                "registros": semana.registros,
                "altura": altura,
            }
        )

    meta_altura = None
    if meta_kg is not None and faixa > 0:
        meta_altura = 12 + int((Decimal(meta_kg) - piso) / faixa * 76)

    return {
        "tem_dados": True,
        "semanas": linhas,
        "tendencia": tendencia,
        "meta_kg": meta_kg,
        "meta_altura": meta_altura,
        "piso": piso,
        "teto": teto,
    }


def dieta(student, plan, dias=DIAS_DE_DIETA) -> dict:
    """Dias dentro da meta contra dias fora, nos últimos `dias`."""
    if plan is None:
        return {"dias": [], "dentro": 0, "abaixo": 0, "acima": 0, "total": 0}

    hoje = timezone.localdate()
    desde = hoje - timedelta(days=dias - 1)

    linhas = (
        MealLog.objects.filter(user=student, date__gte=desde)
        .values("date")
        .annotate(
            kcal=Sum("kcal", filter=Q(status=MealStatus.DONE)),
            cumpridas=Count("pk", filter=Q(status=MealStatus.DONE)),
            marcadas=Count("pk", filter=~Q(status=MealStatus.PENDING)),
        )
        .order_by("-date")
    )

    dias_lidos = [
        DiaDeDieta(
            data=linha["date"],
            kcal=int(linha["kcal"] or 0),
            meta=plan.target_kcal,
            marcadas=linha["marcadas"] or 0,
            cumpridas=linha["cumpridas"] or 0,
        )
        for linha in linhas
    ]

    contagem = {"dentro": 0, "abaixo": 0, "acima": 0}
    for dia in dias_lidos:
        if dia.situacao in contagem:
            contagem[dia.situacao] += 1

    return {
        "dias": dias_lidos,
        "total": sum(contagem.values()),
        **contagem,
    }


def treinos(student, limite=SESSOES_NO_HISTORICO) -> list:
    """Volume por sessão: séries × repetições × carga, do mais recente ao mais antigo.

    Volume é a métrica que responde "está progredindo?" melhor que carga
    máxima: subir de 3×10 com 60 kg para 4×10 com 58 kg é progresso, e a carga
    máxima diria que caiu.

    Séries sem repetição anotada entram com zero no volume em vez de sumir da
    contagem — some do total de carga, não do total de séries, que é o que
    diz se a pessoa apareceu.
    """
    linhas = (
        ExerciseLog.objects.filter(user=student)
        .values("date")
        .annotate(
            exercicios=Count("exercise", distinct=True),
            series=Count("pk"),
            volume=Sum(F("weight_kg") * F("reps")),
        )
        .order_by("-date")[:limite]
    )

    sessoes = [
        Sessao(
            data=linha["date"],
            exercicios=linha["exercicios"],
            series=linha["series"],
            volume_kg=(linha["volume"] or Decimal("0")).quantize(Decimal("1")),
        )
        for linha in linhas
    ]

    # A comparação é com a sessão anterior no tempo, então percorre de trás
    # para frente — a lista já vem do mais recente para o mais antigo.
    for i in range(len(sessoes) - 1):
        anterior = sessoes[i + 1].volume_kg
        if anterior:
            sessoes[i].delta = sessoes[i].volume_kg - anterior

    return sessoes
