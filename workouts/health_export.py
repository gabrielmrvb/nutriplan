"""Exportação do treino para o app Saúde do iPhone e o Health Connect.

**O limite, primeiro.** Uma PWA não escreve no HealthKit. Não existe API web
para isso: o HealthKit é framework nativo do iOS e o Safari não o expõe a
página nenhuma. O Health Connect do Android tem a mesma característica — API
nativa, sem porta web. Qualquer coisa que prometesse "sincronizar com o Apple
Saúde" direto do navegador estaria mentindo.

O que dá para fazer, e é o que está aqui, é a camada que um invólucro nativo
consumiria e que já serve sozinha: o cálculo dos números (minutos ativos e
gasto estimado) e a saída num formato que os aplicativos de importação leem.

TCX porque é o formato que todo importador aceita — HealthFit, Health Auto
Export, Strava, Garmin. A pessoa exporta e abre no app de importação; o
invólucro nativo, quando existir, chama `resumo_da_sessao()` e passa direto ao
HealthKit sem tocar em arquivo.

**Sobre o gasto calórico.** MET 3,5, que é o valor do compêndio de Ainsworth
para musculação de esforço leve a moderado — e não os 6,0 de "vigoroso". A
escolha é a mesma já tomada no cálculo do TDEE deste app: a fórmula do MET
trata a hora inteira como esforço contínuo, quando metade dela é descanso entre
séries. Errar para baixo faz a pessoa comer um pouco menos do que poderia;
errar para cima faz ela não emagrecer e concluir que o app não funciona.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone as tz
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils import timezone

from .models import ExerciseLog, TrainingSession

#: MET da musculação de esforço leve a moderado (Ainsworth 2011, código 02054).
MET_MUSCULACAO = Decimal("3.5")

#: A duração vem da MESMA conta da ficha (`segundos_da_sessao`, "a única
#: conta de duração do projeto"): série a série, com aquecimento, descanso e
#: troca. Até 20/09/2026 este módulo tinha uma segunda fórmula (série × 40 s
#: + descanso médio + 45 s por troca), e o painel mostrava "42 minutos
#: estimado" ao lado do cartão da mesma sessão dizendo "~59 min" — visto na
#: auditoria em produção daquele dia.
from .models import segundos_da_sessao  # noqa: E402


@dataclass
class ResumoDaSessao:
    """O que um treino rendeu, no vocabulário dos apps de saúde."""

    data: object
    minutos: int
    kcal: int
    series: int
    exercicios: int
    volume_kg: Decimal
    inicio: object
    fim: object

    @property
    def tem_dados(self) -> bool:
        return self.series > 0


#: "Ninguém informou a escolha" é diferente de "não há escolha hoje": o
#: painel passa `None` quando a pessoa ainda não escolheu, e isso não pode
#: virar uma consulta a mais.
NAO_INFORMADA = object()


def _duracao_estimada(logs, linhas, descanso_padrao: int) -> int:
    """Quanto tempo o que foi FEITO levou, em segundos — pela conta única.

    Estimativa e não medição: o app não cronometra a sessão inteira, só as
    séries anotadas. Cada exercício com série vira um item `(séries feitas,
    descanso, é composto)` na ordem da ficha (os que a ficha não lista vão
    ao fim, na ordem em que apareceram), e `segundos_da_sessao` faz o resto —
    com aquecimento, descanso e troca. Fechar a ficha inteira dá, por
    construção, o mesmo número que o cartão da sessão promete.
    """
    descanso_por_exercicio = {linha.exercise_id: linha.rest_seconds for linha in linhas}
    ordem = {linha.exercise_id: posicao for posicao, linha in enumerate(linhas)}
    feitas = {}
    for log in logs:
        item = feitas.setdefault(log.exercise_id, [0, log.exercise])
        item[0] += 1
    itens = []
    for exercise_id, (series, exercicio) in sorted(
        feitas.items(), key=lambda par: ordem.get(par[0], len(ordem) + par[1][0])
    ):
        descanso = descanso_por_exercicio.get(exercise_id, descanso_padrao)
        itens.append((series, descanso, exercicio.is_compound))
    return segundos_da_sessao(itens)


def resumo_da_sessao(user, dia=None, sessao=None, escolha=NAO_INFORMADA) -> ResumoDaSessao:
    """Consolida o treino de um dia a partir das cargas registradas.

    A fonte é o `ExerciseLog` e não a ficha: a ficha é o que estava previsto, e
    o que foi feito é o que se exporta. Quem fez quatro dos seis exercícios não
    deve mandar seis para o app de saúde.

    `sessao` e `escolha` são a sessão de hoje e a escolha do dia quando quem
    chama JÁ AS TEM — o painel carrega as duas antes de pedir o resumo. Sem
    isso o resumo refazia a consulta da sessão, a da escolha e a do descanso
    (o painel tem `exercises` em prefetch): três consultas a mais no dia em
    que há série registrada, e foi o que estourou o orçamento de
    `plans.test_stress` — só nesse dia (17/09/2026).
    """
    dia = dia or timezone.localdate()
    logs = list(
        ExerciseLog.objects.filter(user=user, date=dia).select_related("exercise")
    )

    if not logs:
        return ResumoDaSessao(
            data=dia, minutos=0, kcal=0, series=0, exercicios=0,
            volume_kg=Decimal("0"), inicio=None, fim=None,
        )

    exercicios = {log.exercise_id for log in logs}
    volume = sum(
        (log.weight_kg or Decimal("0")) * (log.reps or 0) for log in logs
    )

    # O descanso de cada exercício vem da ficha ativa do dia, quando existe;
    # para exercício fora dela (ou sem ficha), 90 segundos, que é a mediana
    # das prescrições do catálogo.
    if sessao is None:
        from .services import get_active_routine, sessao_do_dia

        sessao = sessao_do_dia(get_active_routine(user), dia)
    descanso = 90
    if sessao:
        # O descanso médio é o da OPÇÃO do dia (a escolhida, senão a 1):
        # somar as duas opções mediria uma sessão que ninguém faz.
        if escolha is NAO_INFORMADA:
            from .services import escolha_do_dia

            escolha = escolha_do_dia(user, dia)
        # A opção do dia (ficha única): a pinada, senão a variação do ciclo —
        # o painel já a calculou em `preparar_dia` (`opcao_do_dia`).
        opcao = getattr(sessao, "opcao_do_dia", None)
        if opcao is None:
            from .services import opcao_do_dia

            opcao = opcao_do_dia(user, sessao, dia, escolha=escolha)
        # Em Python sobre o prefetch, e não `.filter(opcao=...)`: o filtro
        # abre consulta nova mesmo com `exercises` já carregado.
        todas = list(sessao.exercises.all())
        linhas = [i for i in todas if i.opcao == opcao] or todas
        if linhas:
            descanso = round(sum(i.rest_seconds for i in linhas) / len(linhas))
    else:
        linhas = []

    segundos = _duracao_estimada(logs, linhas, descanso)
    minutos = max(1, round(segundos / 60))

    peso = getattr(getattr(user, "profile", None), "current_weight", None)
    kcal = 0
    if peso:
        # kcal = MET × 3,5 ml/kg/min × peso ÷ 200 × minutos
        kcal = int(MET_MUSCULACAO * Decimal("3.5") * Decimal(peso)
                   / Decimal("200") * minutos)

    # O horário real não é registrado; o começo vem da ficha quando ela tem
    # horário, e das 18h quando não tem. É estimativa, e o TCX aceita — o que
    # importa para o app de saúde é a duração e a data.
    inicio_hora = (sessao.start_time if sessao and sessao.start_time else time(18, 0))
    inicio = timezone.make_aware(datetime.combine(dia, inicio_hora))

    return ResumoDaSessao(
        data=dia,
        minutos=minutos,
        kcal=kcal,
        series=len(logs),
        exercicios=len(exercicios),
        volume_kg=Decimal(volume).quantize(Decimal("1")),
        inicio=inicio,
        fim=inicio + timedelta(minutes=minutos),
    )


def tcx(resumo: ResumoDaSessao, titulo="Treino de força") -> str:
    """O treino em TCX, que é o que os importadores de saúde leem.

    Sport="Other" porque o TCX só conhece Running, Biking e Other — musculação
    cai no terceiro, e é assim que o HealthFit e o Health Auto Export a
    convertem para "Traditional Strength Training" no HealthKit.
    """
    if not resumo.tem_dados:
        raise ValueError("Nenhuma série registrada nesse dia.")

    # `datetime.timezone.utc`, e não `django.utils.timezone.utc`: o segundo
    # deixou de existir no Django 5.
    inicio = resumo.inicio.astimezone(tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase
    xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
    xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Activities>
    <Activity Sport="Other">
      <Id>{inicio}</Id>
      <Lap StartTime="{inicio}">
        <TotalTimeSeconds>{resumo.minutos * 60}</TotalTimeSeconds>
        <DistanceMeters>0</DistanceMeters>
        <Calories>{resumo.kcal}</Calories>
        <Intensity>Active</Intensity>
        <TriggerMethod>Manual</TriggerMethod>
      </Lap>
      <Notes>{escape(titulo)} — {resumo.series} séries, {resumo.exercicios} exercícios, {resumo.volume_kg} kg de volume total. Exportado do NutriPlan.</Notes>
      <Creator xsi:type="Device_t">
        <Name>NutriPlan</Name>
        <UnitId>0</UnitId>
        <ProductID>0</ProductID>
      </Creator>
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""
