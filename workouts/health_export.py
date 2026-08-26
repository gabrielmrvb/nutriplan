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

#: Segundos por série, para estimar a duração de uma sessão a partir do que foi
#: registrado. É a mesma constante que a ficha usa para prever o tempo.
from .models import SEGUNDOS_ENTRE_EXERCICIOS, SEGUNDOS_POR_SERIE  # noqa: E402


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


def _duracao_estimada(series: int, exercicios: int, descanso_medio: int) -> int:
    """Quanto tempo aquele volume levou, em segundos.

    Estimativa e não medição: o app não cronometra a sessão inteira, só as
    séries anotadas. Contar o descanso entre séries é o que aproxima do tempo
    real — sem ele, um treino de uma hora exportaria como dezoito minutos.
    """
    segundos = series * SEGUNDOS_POR_SERIE
    segundos += max(series - exercicios, 0) * descanso_medio
    segundos += max(exercicios - 1, 0) * SEGUNDOS_ENTRE_EXERCICIOS
    return segundos


def resumo_da_sessao(user, dia=None) -> ResumoDaSessao:
    """Consolida o treino de um dia a partir das cargas registradas.

    A fonte é o `ExerciseLog` e não a ficha: a ficha é o que estava previsto, e
    o que foi feito é o que se exporta. Quem fez quatro dos seis exercícios não
    deve mandar seis para o app de saúde.
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

    # O descanso médio vem da ficha ativa do dia, quando existe; sem ela, 90
    # segundos, que é a mediana das prescrições do catálogo.
    sessao = TrainingSession.objects.filter(
        plan__user=user, plan__is_active=True, weekday=dia.weekday()
    ).first()
    descanso = 90
    if sessao:
        prescritos = list(sessao.exercises.values_list("rest_seconds", flat=True))
        if prescritos:
            descanso = round(sum(prescritos) / len(prescritos))

    segundos = _duracao_estimada(len(logs), len(exercicios), descanso)
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
