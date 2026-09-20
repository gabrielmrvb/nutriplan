"""O resumo da sessão de hoje: séries, minutos ativos e gasto estimado.

Até 20/09/2026 este módulo também gerava o TCX de `/treino/exportar/saude.tcx`
— a ponte para o Apple Saúde e o Health Connect, que nenhuma PWA escreve
direto. A exportação SAIU por decisão do dono (auditoria de 20/09: nenhum
uso, e a segunda fórmula de duração morava aqui). O que fica é o que o
painel de treino lê para dizer "N séries · M minutos": `resumo_da_sessao`.
O nome do arquivo fica até o PR da duração (`fix/duracao-do-resumo`, parte
A da auditoria) entrar; renomeá-lo antes seria conflito sem ganho.

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


#: "Ninguém informou a escolha" é diferente de "não há escolha hoje": o
#: painel passa `None` quando a pessoa ainda não escolheu, e isso não pode
#: virar uma consulta a mais.
NAO_INFORMADA = object()


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

    # O descanso médio vem da ficha ativa do dia, quando existe; sem ela, 90
    # segundos, que é a mediana das prescrições do catálogo.
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
        linhas = list(sessao.exercises.all())
        prescritos = [i.rest_seconds for i in linhas if i.opcao == opcao] or [
            i.rest_seconds for i in linhas
        ]
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
