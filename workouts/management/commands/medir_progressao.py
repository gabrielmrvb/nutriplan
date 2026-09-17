# -*- coding: utf-8 -*-
"""O instrumento da adaptação: SÓ LEITURA, sobre o histórico de todo mundo.

T2.4 (17/09/2026). Os dias de RETOMAR (21/28), o prazo do platô (27), o
"+1" de ruído e o próprio hábito de parar em `rep_max` são calibração
[HIPOTÉTICA] — a literatura dá os dias (Bosquet 2013) e o ruído (Mitter
2022), não o corte. Este comando conta o que acontece de verdade, para os
números serem revistos com dado:

- ABERTURAS por estado: para cada (pessoa, exercício, data com série), o
  que `adaptacao.ajuste` diria ao abrir a sessão — com as até dez datas
  anteriores, sem a série do dia (a mesma leitura da tela);
- REPETIÇÕES em relação a `rep_max`: a distribuição de `reps − rep_max`
  na última série de cada dia, e a fração que PAROU EXATAMENTE em
  `rep_max` — o sinal de que a faixa está sendo lida como teto (é o que
  a frase do T2.2, "mesmo passando de N", existe para mudar);
- RETOMAR SEM PAUSA: quantas retomadas são de exercício abandonado com a
  pessoa treinando OUTROS exercícios no intervalo — não é volta de férias,
  é troca de ficha, e a frase "N dias sem este exercício" cabe menos;
- INTERVALO entre sessões do mesmo exercício, em semanas.

Duas consultas fixas — as linhas de prescrição ativas e os registros —,
nunca uma por pessoa ou por exercício: é para rodar sobre produção
inteira. Nada é gravado; `workouts/test_instrumento.py` cobra as duas
coisas.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from workouts import adaptacao
from workouts.models import ExerciseLog, Measure, SessionExercise


class _Item:
    """O que `ajuste` lê de uma linha da ficha, sem a linha."""

    def __init__(self, sets, rep_min, rep_max, grupo, sem_carga):
        self.sets, self.rep_min, self.rep_max = sets, rep_min, rep_max
        self.measure, self.load = Measure.REPS, {}

        class _Ex:
            pass

        self.exercise = _Ex()
        self.exercise.muscle_group = grupo
        self.exercise.sem_carga = sem_carga


class Command(BaseCommand):
    help = "Mede, sem escrever nada, o que a adaptação da carga vem dizendo — por estado, por reps e por intervalo."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=365, help="janela de histórico (padrão 365)")

    def handle(self, *args, **options):
        inicio = timezone.localdate() - timedelta(days=options["dias"])

        # 1) A prescrição ATIVA por (pessoa, exercício): sets e faixa. Uma
        #    linha por par basta — quando a mesma pessoa tem o exercício em
        #    duas letras, a primeira vale (é medição, não prescrição).
        prescricao = {}
        linhas = (
            SessionExercise.objects.filter(session__plan__is_active=True, measure=Measure.REPS)
            .values_list(
                "session__plan__user_id", "exercise_id", "sets", "rep_min", "rep_max",
                "exercise__muscle_group", "exercise__equipment",
            )
            .order_by("session__plan__user_id", "exercise_id", "session__order", "order")
        )
        for user_id, exercise_id, sets, rep_min, rep_max, grupo, equipamento in linhas:
            prescricao.setdefault((user_id, exercise_id), _Item(sets, rep_min, rep_max, grupo, equipamento == "bodyweight"))

        # 2) Os registros da janela, uma consulta, agrupados em memória.
        registros = (
            ExerciseLog.objects.filter(date__gte=inicio)
            .values_list("user_id", "exercise_id", "date", "set_number", "weight_kg", "reps")
            .order_by("user_id", "exercise_id", "date", "set_number")
        )
        por_par = defaultdict(lambda: defaultdict(dict))
        datas_da_pessoa = defaultdict(set)
        for user_id, exercise_id, dia, serie, peso, reps in registros:
            por_par[(user_id, exercise_id)][dia][serie] = _Registro(peso, reps)
            datas_da_pessoa[user_id].add(dia)

        estados = Counter()
        delta_reps = Counter()
        paradas_exatas = 0
        ultimas_series = 0
        retomar_sem_pausa = 0
        intervalos = Counter()
        for (user_id, exercise_id), por_data in por_par.items():
            item = prescricao.get((user_id, exercise_id))
            if item is None or item.exercise.sem_carga:
                continue
            datas = sorted(por_data)
            for i, dia in enumerate(datas):
                anteriores = datas[max(0, i - adaptacao.SESSOES_LIDAS):i][::-1]
                sessoes = [(d, por_data[d]) for d in anteriores]
                ultimo = por_data[anteriores[0]][max(por_data[anteriores[0]])] if anteriores else None
                p = adaptacao.ajuste(item, sessoes, ultimo, dia)
                estados[str(p.estado) if p else "sem sugestão"] += 1
                if anteriores:
                    gap = (dia - anteriores[0]).days
                    intervalos[min(gap // 7, 8)] += 1
                    if p is not None and p.estado is adaptacao.Estado.RETOMAR:
                        treinou_no_meio = any(
                            anteriores[0] < d < dia for d in datas_da_pessoa[user_id]
                        )
                        retomar_sem_pausa += treinou_no_meio
                # A última série do dia em relação ao topo da faixa.
                series = por_data[dia]
                ultima = series[max(series)]
                if ultima.reps is not None:
                    ultimas_series += 1
                    delta_reps[max(-6, min(ultima.reps - item.rep_max, 6))] += 1
                    paradas_exatas += ultima.reps == item.rep_max

        total = sum(estados.values())
        self.stdout.write("janela: %d dias · pares pessoa×exercício: %d · aberturas: %d" % (options["dias"], len(por_par), total))
        self.stdout.write("estados por abertura:")
        for estado, n in estados.most_common():
            self.stdout.write("  %-22s %6d  %5.1f%%" % (estado, n, 100.0 * n / total if total else 0))
        retomadas = estados.get("retomar", 0)
        self.stdout.write(
            "retomar sem pausa (a pessoa treinou outros exercícios no intervalo): %d de %d retomadas"
            % (retomar_sem_pausa, retomadas)
        )
        self.stdout.write(
            "paradas exatas em rep_max (última série do dia): %d de %d (%.1f%%)"
            % (paradas_exatas, ultimas_series, 100.0 * paradas_exatas / ultimas_series if ultimas_series else 0)
        )
        self.stdout.write("reps − rep_max na última série (−6…+6, extremos agrupados):")
        for delta in sorted(delta_reps):
            self.stdout.write("  %+d: %d" % (delta, delta_reps[delta]))
        self.stdout.write("intervalo desde a última sessão do exercício (semanas; 8 = 8+):")
        for semanas in sorted(intervalos):
            self.stdout.write("  %d: %d" % (semanas, intervalos[semanas]))


class _Registro:
    __slots__ = ("weight_kg", "reps")

    def __init__(self, weight_kg, reps):
        self.weight_kg, self.reps = weight_kg, reps
