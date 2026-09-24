# -*- coding: utf-8 -*-
"""SEQUÊNCIA POR PRESENÇA (decisão do dono, 24/09/2026).

"Qual treino é hoje" deixou de sair da POSIÇÃO no calendário (doutrina de
17/09, substituída) e passa a sair da SEQUÊNCIA REALIZADA: o recomendado é a
letra seguinte à ÚLTIMA FEITA (série registrada). Faltar um dia não avança
nada — quem pulou a quarta faz o treino de quarta na quinta, como na
academia. A pessoa pode escolher outra letra; a escolha do dia vence.

`sequencia_do_treino` é a leitura única — UMA consulta — de que letra_do_dia,
a opção da letra, a tira-projeção e o aviso de repetição derivam.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from accounts.models import DuracaoTreino, TrainingDay
from config import relogio
from plans.tests import create_complete_user
from workouts import services
from workouts.models import EscolhaDeTreino, ExerciseLog, TrainingPlan

SEGUNDA = date(2026, 9, 14)  # uma segunda-feira
QUINTA = SEGUNDA + timedelta(days=3)


def _pessoa(email, dias=5):
    user = create_complete_user(
        email=email, experiencia="intermediario", split_preference="two",
        split_preference_confirmada=True, duracao_treino=DuracaoTreino.PADRAO,
    )
    TrainingDay.objects.filter(user=user).delete()
    for d in range(dias):
        TrainingDay.objects.create(user=user, weekday=d, duration_min=60)
    return user


def fazer(user, plan, letra, dia, series=1):
    """Registra `letra` como FEITA em `dia`: a escolha do dia + `series`
    ExerciseLog. É o que "presença" mede."""
    linhas = list(plan.sessions.prefetch_related("exercises__exercise"))
    sessao = next(s for s in linhas if s.label == letra)
    ex = sessao.exercises.all()[0].exercise
    EscolhaDeTreino.objects.update_or_create(
        user=user, date=dia, defaults={"session": sessao, "opcao": 1}
    )
    for n in range(1, series + 1):
        ExerciseLog.objects.create(
            user=user, exercise=ex, date=dia, set_number=n,
            weight_kg=Decimal("40"), reps=10,
        )
    return sessao


def escolher_sem_serie(user, plan, letra, dia):
    """Uma escolha do dia SEM série — encerrou com zero, ou só abriu."""
    sessao = next(s for s in plan.sessions.all() if s.label == letra)
    EscolhaDeTreino.objects.update_or_create(
        user=user, date=dia, defaults={"session": sessao, "opcao": 1}
    )
    return sessao


class ASequenciaRealizadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("seq@exemplo.com")
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def _seq(self):
        return services.sequencia_do_treino(self.user, self.plan, sessoes=self.linhas)

    def test_sem_serie_recomenda_a_primeira_letra_do_ciclo(self):
        seq = self._seq()
        self.assertEqual(seq.feitas, [])
        self.assertEqual(seq.recomendada(), "A")
        self.assertIsNone(seq.ultima_letra())

    def test_apos_a_e_b_feitas_recomenda_c(self):
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "B", SEGUNDA + timedelta(days=1))
        seq = self._seq()
        self.assertEqual(seq.ultima_letra(), "B")
        self.assertEqual(seq.recomendada(), "C")
        self.assertEqual(seq.contagem("A"), 1)
        self.assertEqual(seq.contagem("C"), 0)

    def test_a_ultima_feita_manda_mesmo_fora_de_ordem(self):
        """A seg, depois C ter (pulou B). A última feita é C, então o
        recomendado é A — não D, não a contagem."""
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "C", SEGUNDA + timedelta(days=1))
        self.assertEqual(self._seq().recomendada(), "A")

    def test_escolha_sem_serie_nao_conta_como_feita(self):
        """Encerrou o treino com zero série: não avança o ciclo."""
        escolher_sem_serie(self.user, self.plan, "A", SEGUNDA)
        seq = self._seq()
        self.assertEqual(seq.feitas, [])
        self.assertEqual(seq.recomendada(), "A")

    def test_feita_de_outro_plano_nao_conta(self):
        """Escolha que aponta para a sessão de um plano antigo (remontado)
        não entra na sequência do plano atual."""
        antigo = self.plan
        TrainingPlan.objects.filter(pk=antigo.pk).update(is_active=False)
        novo = services.create_routine(self.user)
        fazer(self.user, antigo, "A", SEGUNDA)  # feito sob o plano antigo
        seq = services.sequencia_do_treino(self.user, novo)
        self.assertEqual(seq.feitas, [])
        self.assertEqual(seq.recomendada(), "A")

    def test_a_leitura_e_uma_consulta_so(self):
        fazer(self.user, self.plan, "A", SEGUNDA)
        with self.assertNumQueries(1):
            seq = services.sequencia_do_treino(self.user, self.plan, sessoes=self.linhas)
            # materializa (a query roda aqui dentro)
            _ = seq.recomendada(), seq.contagem("A")
