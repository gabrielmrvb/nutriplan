"""A ofensiva: quantos dias seguidos a pessoa cumpriu o combinado.

O que a torna honesta é o que ela decide NÃO cobrar.

**Dia de descanso não quebra treino.** A rotina prevê três dias por semana; se
o contador exigisse treino todo dia, a sequência morreria toda quarta-feira e
o número viraria ruído. Num dia sem treino previsto, treino está cumprido por
definição — descansar É o plano.

**O dia de hoje nunca quebra.** Às sete da manhã ninguém almoçou, treinou nem
bebeu três litros. Um contador que zerasse ao amanhecer seria um contador que
pune por acordar cedo. Hoje só ENTRA na conta quando já está cumprido; enquanto
não está, ele é o dia em risco, e é sobre ele que o aviso fala.

**Sem meta, sem cobrança.** Quem não tem plano alimentar não é reprovado em
dieta. Metas que a pessoa não tem não podem quebrar a sequência dela.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from workouts.models import ExerciseLog, TrainingPlan

from .models import HydrationLog, MealLog, MealStatus

#: Quanto da meta calórica conta como dia cumprido. Oitenta por cento das
#: refeições marcadas como feitas — não 100%: exigir perfeição de um contador
#: de constância é a forma mais rápida de a pessoa desistir dele.
ADESAO_MINIMA_PCT = 80

#: E pelo menos três refeições marcadas. Sem piso, um dia com uma única
#: refeição marcada daria 100% de aderência e passaria — premiando quem esqueceu
#: de usar o app em vez de quem seguiu o plano.
REFEICOES_MINIMAS = 3

#: Da meta de água. Noventa por cento porque a meta já é estimativa (35 ml/kg),
#: e cobrar o número cheio de uma estimativa é falsa precisão.
HIDRATACAO_MINIMA_PCT = 90

#: Até onde olhar para trás. Uma sequência de um ano é possível e a consulta
#: precisa de um teto.
DIAS_NO_HISTORICO = 400


@dataclass
class Dia:
    """Um dia e o que ele cumpriu."""

    data: object
    treino: bool
    dieta: bool
    agua: bool
    #: Havia treino previsto? Muda a leitura de `treino=True`.
    treino_previsto: bool

    @property
    def completo(self) -> bool:
        return self.treino and self.dieta and self.agua

    @property
    def pendencias(self) -> list:
        faltando = []
        if not self.treino:
            faltando.append("treino")
        if not self.dieta:
            faltando.append("dieta")
        if not self.agua:
            faltando.append("água")
        return faltando


@dataclass
class Ofensiva:
    dias: int
    recorde: int
    #: O dia de hoje já está fechado?
    hoje_completo: bool
    #: O que falta hoje para a sequência continuar.
    falta_hoje: list
    ultimo_dia: object = None

    @property
    def em_risco(self) -> bool:
        """Tem sequência viva e hoje ainda não fechou."""
        return self.dias > 0 and not self.hoje_completo

    @property
    def mensagem(self) -> str:
        """O texto do topo do painel.

        Muda com o tamanho da sequência porque a mesma frase repetida por
        quarenta dias deixa de ser lida. E nunca é ríspida: o contador existe
        para dar vontade de voltar, não para cobrar.
        """
        if self.dias == 0:
            return "Comece hoje: cumpra treino, dieta e água e a contagem começa."
        if self.em_risco:
            falta = ", ".join(self.falta_hoje)
            return f"Falta {falta} para manter a sequência hoje."
        if self.dias == 1:
            return "Primeiro dia fechado. O segundo é o que costuma escapar."
        if self.dias < 7:
            return f"{self.dias} dias seguidos. Uma semana está logo ali."
        if self.dias < 30:
            return f"{self.dias} dias seguidos. Isso já é rotina, não esforço."
        return f"{self.dias} dias seguidos. Você virou outra pessoa nesse intervalo."


def _dias_de_treino(user) -> set:
    """Os dias da semana em que há treino previsto (0 = segunda)."""
    plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
    if plano is None:
        return set()
    return set(plano.sessions.values_list("weekday", flat=True))


def calcular(user, hoje=None, meta_agua_ml=None) -> Ofensiva:
    """Percorre os dias de trás para frente até achar o primeiro furo."""
    hoje = hoje or timezone.localdate()
    inicio = hoje - timedelta(days=DIAS_NO_HISTORICO)
    previstos = _dias_de_treino(user)

    # --------------------------------------------------------- treino
    treinou = set(
        ExerciseLog.objects.filter(user=user, date__gte=inicio).values_list(
            "date", flat=True
        )
    )

    # ---------------------------------------------------------- dieta
    dieta_ok = set()
    for linha in (
        MealLog.objects.filter(user=user, date__gte=inicio)
        .values("date")
        .annotate(
            feitas=Count("pk", filter=Q(status=MealStatus.DONE)),
            marcadas=Count("pk", filter=~Q(status=MealStatus.PENDING)),
        )
    ):
        marcadas = linha["marcadas"] or 0
        if marcadas < REFEICOES_MINIMAS:
            continue
        if linha["feitas"] * 100 / marcadas >= ADESAO_MINIMA_PCT:
            dieta_ok.add(linha["date"])

    # ----------------------------------------------------------- água
    agua_ok = set()
    if meta_agua_ml:
        alvo = meta_agua_ml * HIDRATACAO_MINIMA_PCT / 100
        agua_ok = {
            linha["date"]
            for linha in HydrationLog.objects.filter(
                user=user, date__gte=inicio
            ).values("date").annotate(total=Sum("ml"))
            if (linha["total"] or 0) >= alvo
        }

    def avaliar(data) -> Dia:
        previsto = data.weekday() in previstos
        return Dia(
            data=data,
            # Descansar é o plano nos dias sem treino previsto.
            treino=(data in treinou) if previsto else True,
            # Sem plano alimentar não há meta de dieta para cobrar.
            dieta=(data in dieta_ok) if _tem_plano(user) else True,
            agua=(data in agua_ok) if meta_agua_ml else True,
            treino_previsto=previsto,
        )

    dia_de_hoje = avaliar(hoje)

    # Hoje só entra quando já está fechado. Enquanto não está, a contagem
    # começa em ontem — e hoje é o dia em risco.
    sequencia = 0
    cursor = hoje if dia_de_hoje.completo else hoje - timedelta(days=1)
    limite = hoje - timedelta(days=DIAS_NO_HISTORICO)
    ultimo = None
    while cursor >= limite:
        dia = avaliar(cursor)
        if not dia.completo:
            break
        if ultimo is None:
            ultimo = cursor
        sequencia += 1
        cursor -= timedelta(days=1)

    return Ofensiva(
        dias=sequencia,
        recorde=max(sequencia, _recorde(user, hoje, previstos, treinou, dieta_ok,
                                        agua_ok, meta_agua_ml)),
        hoje_completo=dia_de_hoje.completo,
        falta_hoje=dia_de_hoje.pendencias,
        ultimo_dia=ultimo,
    )


def _tem_plano(user) -> bool:
    # Import tardio: `services` importa `models`, e subir isto para o topo
    # fecharia o ciclo.
    from .services import get_active_plan

    if not hasattr(user, "_streak_tem_plano"):
        user._streak_tem_plano = get_active_plan(user) is not None
    return user._streak_tem_plano


def _recorde(user, hoje, previstos, treinou, dieta_ok, agua_ok, meta_agua_ml) -> int:
    """A maior sequência já feita, para a atual ter contra o que se medir."""
    tem_plano = _tem_plano(user)
    melhor = atual = 0
    cursor = hoje - timedelta(days=DIAS_NO_HISTORICO)
    while cursor <= hoje:
        previsto = cursor.weekday() in previstos
        completo = (
            ((cursor in treinou) if previsto else True)
            and ((cursor in dieta_ok) if tem_plano else True)
            and ((cursor in agua_ok) if meta_agua_ml else True)
        )
        if completo:
            atual += 1
            melhor = max(melhor, atual)
        else:
            atual = 0
        cursor += timedelta(days=1)
    return melhor
