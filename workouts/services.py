"""Monta a rotina de treino da semana a partir dos dias que a pessoa informou.

Duas decisões concentram a inteligência daqui, e as duas são de treinamento,
não de programação:

1. **A divisão vem da frequência, não do gosto.** Dividir o corpo em quatro
   dias para quem treina duas vezes por semana significa cada músculo ser
   treinado a cada duas semanas — a pior forma de organizar treino que existe.
   A regra é: quanto menos dias, mais cada sessão precisa cobrir.

2. **Acima de quatro dias a divisão não cresce, ela repete.** Quem treina cinco
   ou seis vezes roda o ABC de novo (A, B, C, A, B, ...). Inventar um quinto e
   um sexto dia de "braço" e "ombro" preenche a semana e não adiciona estímulo;
   repetir o ciclo dá a cada grupo muscular duas sessões na semana, que é o que
   a literatura mostra render mais que uma.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    ExerciseLog,
    SessionExercise,
    Split,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplate,
)


class NoTrainingDays(Exception):
    """A pessoa não marcou nenhum dia de treino — não há rotina a montar."""


#: Divisão escolhida por quantidade de dias na semana. Cinco dias ou mais
#: caem no ABC e o ciclo se repete ao longo da semana.
SPLIT_BY_FREQUENCY = {
    1: Split.FULL,
    2: Split.AB,
    3: Split.ABC,
    4: Split.ABCD,
}
DEFAULT_SPLIT = Split.ABC

SPLIT_NOTE = {
    Split.FULL: (
        "Com um treino por semana, o corpo inteiro entra na mesma sessão — é o que "
        "dá algum estímulo a cada grupo muscular. Se conseguir abrir um segundo dia, "
        "o resultado muda de patamar."
    ),
    Split.AB: (
        "Dois treinos por semana: superior e inferior. Cada grupo muscular é treinado "
        "uma vez, então priorize os exercícios do começo da ficha — são eles que "
        "carregam o resultado."
    ),
    Split.ABC: (
        "Empurrar, puxar e pernas. É a divisão mais eficiente para quem treina de três "
        "a seis vezes: com quatro dias ou mais o ciclo recomeça, e cada grupo muscular "
        "acaba treinado duas vezes na semana."
    ),
    Split.ABCD: (
        "Quatro treinos, um foco por dia. Volume por sessão é menor, então dá para "
        "puxar mais carga em cada exercício sem estender o treino."
    ),
}


def split_for(days_per_week: int) -> str:
    """A divisão que faz sentido para essa frequência."""
    return SPLIT_BY_FREQUENCY.get(days_per_week, DEFAULT_SPLIT)


def templates_for(split: str) -> list:
    """Os dias da divisão, em ordem, já com os exercícios pré-carregados."""
    return list(
        WorkoutTemplate.objects.filter(split=split, is_active=True)
        .order_by("order")
        .prefetch_related("items__exercise")
    )


def build_sessions(plan, training_days, templates) -> list:
    """Casa cada dia de treino da pessoa com um dia da divisão, em ordem.

    O `%` é o que faz a divisão repetir quando a pessoa treina mais dias do que
    a divisão tem letras: cinco dias num ABC viram A, B, C, A, B.
    """
    sessions = []
    for index, day in enumerate(training_days):
        template = templates[index % len(templates)]
        sessions.append(
            TrainingSession(
                plan=plan,
                weekday=day.weekday,
                label=template.label,
                name=template.name,
                focus=template.focus,
                start_time=day.start_time,
                duration_min=day.duration_min,
                order=index,
            )
        )
    return sessions


@transaction.atomic
def create_routine(user) -> TrainingPlan:
    """Cria a rotina ativa da pessoa, aposentando a anterior.

    A ordem dentro da transação importa pelo mesmo motivo do plano alimentar: o
    banco tem índice único parcial de uma rotina ativa por usuário, então a
    antiga precisa ser desativada antes de a nova entrar.
    """
    training_days = list(user.training_days.order_by("weekday"))
    if not training_days:
        raise NoTrainingDays("Nenhum dia de treino cadastrado.")

    split = split_for(len(training_days))
    templates = templates_for(split)
    if not templates:
        raise NoTrainingDays(f"A divisão {split} não está no catálogo.")

    TrainingPlan.objects.filter(user=user, is_active=True).update(is_active=False)
    plan = TrainingPlan.objects.create(
        user=user,
        is_active=True,
        split=split,
        days_per_week=len(training_days),
        notes=SPLIT_NOTE.get(split, ""),
    )

    sessions = build_sessions(plan, training_days, templates)
    TrainingSession.objects.bulk_create(sessions)

    by_label = {template.label: template for template in templates}
    exercises = []
    for session in sessions:
        for item in by_label[session.label].items.all():
            exercises.append(
                SessionExercise(
                    session=session,
                    exercise=item.exercise,
                    sets=item.sets,
                    rep_min=item.rep_min,
                    rep_max=item.rep_max,
                    measure=item.measure,
                    rest_seconds=item.rest_seconds,
                    order=item.order,
                )
            )
    SessionExercise.objects.bulk_create(exercises)
    return plan


def get_active_routine(user):
    return TrainingPlan.objects.filter(user=user, is_active=True).first()


def routine_is_current(plan, user) -> bool:
    """A rotina ativa ainda corresponde aos dias de treino de hoje?

    Compara o conjunto (dia da semana, horário, duração) — mudou qualquer coisa
    aí, a ficha é remontada. Sem o horário e a duração na comparação, trocar o
    treino da manhã para a noite deixaria a ficha dizendo o horário errado.
    """
    if plan is None or not plan.sessions.exists():
        return False
    if plan.split != split_for(user.training_days.count()):
        return False
    if plan.sessions.filter(exercises__exercise__is_active=False).exists():
        # Exercício aposentado no catálogo: a ficha manda fazer o que saiu do ar.
        return False

    atual = {
        (day.weekday, day.start_time, day.duration_min)
        for day in user.training_days.all()
    }
    na_ficha = {
        (session.weekday, session.start_time, session.duration_min)
        for session in plan.sessions.all()
    }
    return atual == na_ficha


def sync_active_routine(user) -> tuple:
    """Garante uma rotina coerente com os dias de treino atuais.

    Devolve (rotina, mudou). Chamada na entrada da tela, como o plano alimentar:
    enquanto nada muda é só uma comparação de conjuntos em memória.
    """
    plan = get_active_routine(user)
    if routine_is_current(plan, user):
        return plan, False
    return create_routine(user), True


def has_training_days(user) -> bool:
    return user.training_days.exists()


# --------------------------------------------------------------------------
# Registro de carga
# --------------------------------------------------------------------------

def record_load(user, exercise, weight_kg, set_number=1, reps=None, day=None):
    """Anota a carga de uma série. Anotar de novo corrige em vez de duplicar."""
    day = day or timezone.localdate()
    log, _ = ExerciseLog.objects.update_or_create(
        user=user,
        exercise=exercise,
        date=day,
        set_number=set_number,
        defaults={"weight_kg": Decimal(str(weight_kg)), "reps": reps},
    )
    return log


def load_history(user, exercises, day=None) -> dict:
    """Cargas de hoje e a comparação com o último treino, por exercício.

    Devolve, por exercício:

        {
          "hoje":     {série: log},            # o que preencher no formulário
          "anterior": {série: log},            # o mesmo dia de treino passado
          "melhor_hoje": Decimal|None,         # série mais pesada de hoje
          "melhor_anterior": Decimal|None,
          "delta": Decimal|None,               # subiu ou não subiu
          "data_anterior": date|None,
        }

    A comparação é entre as séries MAIS PESADAS de cada dia, e não série a série:
    a ordem em que a pessoa anota varia (às vezes a pesada é a primeira, às vezes
    a última), e o que responde "evoluí?" é o topo do dia.

    Tudo sai de uma consulta só — a tela mostra isso para vinte exercícios de
    uma vez, e vinte consultas por página é o caminho curto para a tela lenta.
    """
    day = day or timezone.localdate()
    ids = [exercise.pk for exercise in exercises]
    if not ids:
        return {}

    por_exercicio = {}
    logs = ExerciseLog.objects.filter(user=user, exercise_id__in=ids).order_by(
        "exercise_id", "-date", "set_number"
    )
    for log in logs:
        por_exercicio.setdefault(log.exercise_id, []).append(log)

    resultado = {}
    for exercise_id, registros in por_exercicio.items():
        hoje = {log.set_number: log for log in registros if log.date == day}
        anteriores = [log for log in registros if log.date < day]
        data_anterior = anteriores[0].date if anteriores else None
        anterior = {
            log.set_number: log for log in anteriores if log.date == data_anterior
        }

        melhor_hoje = max((l.weight_kg for l in hoje.values()), default=None)
        melhor_anterior = max((l.weight_kg for l in anterior.values()), default=None)
        resultado[exercise_id] = {
            "hoje": hoje,
            "anterior": anterior,
            "melhor_hoje": melhor_hoje,
            "melhor_anterior": melhor_anterior,
            "data_anterior": data_anterior,
            "delta": (melhor_hoje - melhor_anterior)
            if (melhor_hoje is not None and melhor_anterior is not None)
            else None,
        }
    return resultado
