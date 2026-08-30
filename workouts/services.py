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

from accounts.models import SplitPreference

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
# De três dias em diante, sempre ABC.
#
# O ciclo se repete para preencher a semana: cinco dias viram A, B, C, A, B, e
# seis viram A, B, C, A, B, C. Isso dá de uma a duas sessões por grupo na
# semana — mais que qualquer divisão de quatro ou cinco letras entrega, porque
# lá cada grupo aparece uma vez só.
#
# ABCD e ABCDE existiram aqui e foram retirados. O motivo declarado é o
# clássico por sinergia: peito e costas são antagonistas e não dividem o dia,
# empurrar fica junto de empurrar, puxar junto de puxar.
SPLIT_BY_FREQUENCY = {
    1: Split.FULL,
    2: Split.AB,
    3: Split.ABC,
    4: Split.ABC,
    5: Split.ABC,
    6: Split.ABC,
    7: Split.ABC,
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
        "A divisão clássica por sinergia: empurrar num dia, puxar no outro, "
        "pernas no terceiro. Peito e costas nunca caem no mesmo treino — são "
        "antagonistas, e treinar um cansa o outro pela metade. O ciclo "
        "recomeça para preencher a semana, então quem treina cinco vezes faz "
        "A, B, C, A, B e alguns grupos recebem duas sessões."
    ),
    Split.ABCDE: (
        "Cinco treinos: o ciclo de quatro mais um dia para o que sobra de fora "
        "dele. Somando as séries da semana no ABCD, posterior de coxa e "
        "panturrilha ficam bem abaixo da faixa em que o ganho aparece — o "
        "quinto dia existe para fechar essa conta, não para adicionar treino "
        "por adicionar."
    ),
    Split.ABCD: (
        "Quatro treinos, um foco por dia: peito e tríceps, costas e bíceps, ombro e "
        "perna, e um dia para trapézio, antebraço e core. Volume por sessão é menor, "
        "então dá para puxar mais carga em cada exercício sem estender o treino. O "
        "dia dos complementares fica longe do de costas de propósito — trapézio e "
        "antebraço trabalham junto no puxe, e chegar neles cansado tira do treino "
        "de costas justamente a pegada que ele precisa."
    ),
}


#: (preferência, dias mínimos) -> divisão.
#:
#: A frequência continua mandando, e a preferência escolhe DENTRO do que ela
#: comporta. Não é diplomacia entre dois campos: uma divisão de cinco dias com
#: duas sessões por semana deixa três quintos do corpo sem treinar nenhuma vez,
#: porque as últimas letras nunca chegam. A preferência não cria dias.
#:
#: Lido por linha — cada uma desce para a divisão mais próxima que cabe:
#:   UM     cinco dias viram peito / costas / pernas / ombros / braços; com
#:          quatro cai no ABCD, com três no ABC, e assim por diante.
#:   DOIS   quatro dias: peito+tríceps, costas+bíceps, pernas+ombros e um dia
#:          de complementares. É a divisão mais comum de academia.
#:   TRES   o ABC de sempre: empurrar, puxar e pernas, em três dias.
SPLIT_BY_PREFERENCE = {
    SplitPreference.UM: (
        (5, Split.ABCDE), (4, Split.ABCD), (3, Split.ABC), (2, Split.AB), (1, Split.FULL),
    ),
    SplitPreference.DOIS: (
        (4, Split.ABCD), (3, Split.ABC), (2, Split.AB), (1, Split.FULL),
    ),
    SplitPreference.TRES: ((3, Split.ABC), (2, Split.AB), (1, Split.FULL)),
}


def _preferencia_de(user) -> str:
    """A preferência de divisão desta pessoa, ou nada.

    `getattr` em vez de `user.profile` porque a ficha pode ser montada num
    caminho em que o perfil ainda não existe — e ali a ausência de preferência
    é a resposta certa, não um erro: `split_for` cai na tabela por frequência,
    que é o que o app fazia antes da pergunta existir.
    """
    profile = getattr(user, "profile", None)
    return getattr(profile, "split_preference", None)


def split_for(days_per_week: int, preference: str = None) -> str:
    """A divisão que faz sentido para essa frequência e essa preferência.

    Sem preferência, cai na tabela por frequência — é o caminho de quem tem
    plano anterior à pergunta existir, e devolve exatamente o que devolvia.
    """
    if not preference:
        return SPLIT_BY_FREQUENCY.get(days_per_week, DEFAULT_SPLIT)

    escala = SPLIT_BY_PREFERENCE.get(preference)
    if escala is None:
        return SPLIT_BY_FREQUENCY.get(days_per_week, DEFAULT_SPLIT)

    for minimo, divisao in escala:
        if days_per_week >= minimo:
            return divisao
    # Zero dias de treino não é uma frequência — é ausência dela. Quem chega
    # aqui não tem ficha para montar, e o corpo inteiro é a resposta menos
    # errada se alguém montar mesmo assim.
    return Split.FULL


def preferencia_muda_a_divisao(dias_por_semana: int) -> bool:
    """A pergunta de divisão altera alguma coisa nessa frequência?

    NÃO é uma regra escrita à mão — é lida da própria `SPLIT_BY_PREFERENCE`,
    rodando `split_for` para cada preferência e vendo se sobra mais de uma
    resposta. O dia em que a tabela mudar, o onboarding acompanha sozinho.

    Hoje isso responde `False` para 0, 1, 2 e 3 dias e `True` de 4 em diante:
    quem treina três vezes recebe ABC pelas três preferências, porque a
    divisão não pode inventar dias que a semana não tem. Perguntar ali é pedir
    uma escolha que o app vai ignorar — e o onboarding fica um passo mais
    longo em troca de nada.
    """
    respostas = {split_for(dias_por_semana, p) for p in SPLIT_BY_PREFERENCE}
    return len(respostas) > 1


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

    split = split_for(len(training_days), _preferencia_de(user))
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
    if plan.sessions.filter(exercises__exercise__is_active=False).exists():
        # Exercício aposentado no catálogo: a ficha manda fazer o que saiu do
        # ar. Vale inclusive para ficha ajustada — aqui o gerador não está
        # desfazendo a escolha da pessoa, está avisando que o catálogo mudou
        # embaixo dela.
        return False
    # A prescrição do catálogo mudou embaixo da ficha?
    #
    # `sets`, faixa de repetições e descanso são copiados do modelo quando a
    # ficha nasce, e ficavam congelados: mudar o descanso padrão no catálogo não
    # chegava a quem já tinha ficha. A pessoa continuava vendo "3 min" numa
    # versão do app que passou a prescrever 1:20.
    prescrito = {
        (i.exercise_id, i.sets, i.rep_min, i.rep_max, i.rest_seconds)
        for template in templates_for(plan.split)
        for i in template.items.all()
    }
    na_ficha = {
        (i.exercise_id, i.sets, i.rep_min, i.rep_max, i.rest_seconds)
        # Uma consulta, e não uma por sessão: esta função roda na entrada de
        # toda visita à tela de treino.
        for i in SessionExercise.objects.filter(session__plan=plan)
    }
    # Ficha ajustada à mão fica de fora: ali a divergência é a escolha da
    # pessoa, e remontar apagaria justamente o que ela mudou.
    if not plan.is_customized and not na_ficha <= prescrito:
        return False

    if plan.is_customized:
        # Ficha ajustada à mão não é remontada pelo gerador. A pessoa trocou
        # aqueles exercícios por um motivo — joelho, equipamento ocupado,
        # preferência — e mudar o horário de terça-feira não é motivo para
        # descartar a escolha e voltar ao modelo do catálogo.
        return True
    if plan.split != split_for(user.training_days.count(), _preferencia_de(user)):
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
