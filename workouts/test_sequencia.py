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
from django.urls import reverse

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

    def test_feita_de_outro_plano_conta_na_sequencia_e_nao_na_opcao(self):
        """Escolha que aponta para a sessão de um plano antigo (remontado)
        ENTRA na sequência do plano atual: a letra segue da última feita.

        O CONTRATO MUDOU em 28/09/2026 (B4 do caça-bugs de 27/09). Este teste
        dizia "feito sob plano antigo não conta" (`feitas == []`, recomenda
        A), e era exatamente o defeito: remontar a ficha zerava a sequência —
        A de novo no dia seguinte a A, e a tira marcando `pulado` os dias
        treinados. A presença é da pessoa, não da ficha. Só a `contagem`
        (a opção da ficha legada) continua por plano."""
        antigo = self.plan
        TrainingPlan.objects.filter(pk=antigo.pk).update(is_active=False)
        novo = services.create_routine(self.user)
        fazer(self.user, antigo, "A", SEGUNDA)  # feito sob o plano antigo
        seq = services.sequencia_do_treino(self.user, novo)
        self.assertEqual(seq.feitas, [(SEGUNDA, "A")])
        self.assertEqual(seq.recomendada(), "B")
        self.assertEqual(seq.contagem("A"), 0)

    def test_a_leitura_e_uma_consulta_so(self):
        fazer(self.user, self.plan, "A", SEGUNDA)
        with self.assertNumQueries(1):
            seq = services.sequencia_do_treino(self.user, self.plan, sessoes=self.linhas)
            # materializa (a query roda aqui dentro)
            _ = seq.recomendada(), seq.contagem("A")


class ALetraDeHojePorPresencaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("hoje@exemplo.com")
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def test_sem_historico_hoje_e_a_primeira_letra_vestida_no_dia(self):
        sessao = services.sessao_do_dia(self.plan, QUINTA, self.linhas, user=self.user)
        self.assertEqual(sessao.label, "A")
        self.assertEqual(sessao.weekday, QUINTA.weekday())  # vestida no dia de hoje
        self.assertEqual(sessao.data, QUINTA)
        self.assertEqual(services.letra_do_dia(self.plan, QUINTA, self.linhas, user=self.user), "A")

    def test_o_caso_do_dono_pulou_a_quarta_e_hoje_recomenda_c(self):
        """A na segunda, B na terça, NADA na quarta. Hoje (quinta) o
        recomendado é C — continua de onde parou, não a A que o calendário
        daria (posição 3)."""
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "B", SEGUNDA + timedelta(days=1))
        sessao = services.sessao_do_dia(self.plan, QUINTA, self.linhas, user=self.user)
        self.assertEqual(sessao.label, "C")

    def test_a_escolha_do_dia_vence_a_recomendacao(self):
        """A pessoa escolheu fazer B hoje, mesmo que o recomendado fosse A."""
        linha_b = next(s for s in self.linhas if s.label == "B")
        services.registrar_escolha(self.user, linha_b, 1, dia=QUINTA)
        sessao = services.sessao_do_dia(self.plan, QUINTA, self.linhas, user=self.user)
        self.assertEqual(sessao.label, "B")

    def test_plano_customizado_fica_preso_ao_dia_da_semana(self):
        """Ficha ajustada à mão: a pessoa arranjou os dias, e a presença não
        remexe nisso — a letra é a da linha do dia da semana."""
        from django.utils import timezone as _tz
        TrainingPlan.objects.filter(pk=self.plan.pk).update(customized_at=_tz.now())
        self.plan.refresh_from_db()
        # quinta é a 2ª ocorrência de A nas linhas [A,B,C,A,B] -> label A
        sessao = services.sessao_do_dia(self.plan, QUINTA, user=self.user)
        self.assertEqual(sessao.label, "A")
        self.assertFalse(services.usa_presenca(self.plan))


class AProjecaoDaSemanaTests(TestCase):
    """A tira da semana vira PROJEÇÃO (24/09/2026): dia passado feito mostra a
    letra feita, hoje mostra a recomendada, o futuro segue o ciclo a partir
    daí, e dia de treino pulado fica marcado."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("tira@exemplo.com")
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def _tira(self, hoje):
        return [
            (None if s.projecao == "pulado" else s.label, s.projecao)
            for s in services.sessoes_da_semana(self.plan, hoje, self.linhas, user=self.user)
        ]

    def test_plano_fresco_semana_1_e_a_b_c_a_b(self):
        tira = self._tira(SEGUNDA)
        self.assertEqual([l for l, _ in tira], ["A", "B", "C", "A", "B"])
        self.assertEqual([e for _, e in tira], ["hoje", "futuro", "futuro", "futuro", "futuro"])

    def test_plano_fresco_semana_2_ainda_e_a_b_c_a_b(self):
        """Nada feito: o calendário NÃO avança o ciclo — a semana 2 ainda
        começa em A. Era o que a rotação por posição fazia (começava em C)."""
        self.assertEqual([l for l, _ in self._tira(SEGUNDA + timedelta(days=7))], ["A", "B", "C", "A", "B"])

    def test_o_caso_do_dono_pulou_a_quarta(self):
        """A na segunda (feito), B na terça (feito), quarta PULADA, e hoje
        (quinta) recomenda C — continua de onde parou —, sexta projeta A."""
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "B", SEGUNDA + timedelta(days=1))
        self.assertEqual(
            self._tira(QUINTA),
            [("A", "feito"), ("B", "feito"), (None, "pulado"), ("C", "hoje"), ("A", "futuro")],
        )

    def test_a_escolha_de_hoje_aparece_na_tira_no_lugar_da_recomendada(self):
        linha_b = next(s for s in self.linhas if s.label == "B")
        services.registrar_escolha(self.user, linha_b, linha_b.opcoes[0], dia=SEGUNDA)
        tira = self._tira(SEGUNDA)
        self.assertEqual(tira[0], ("B", "hoje"))
        # o futuro segue a partir de B: C, A, B, C
        self.assertEqual([l for l, _ in tira], ["B", "C", "A", "B", "C"])


class ApresencaNaoRemontaAFichaTests(TestCase):
    """A presença é LEITURA (24/09/2026): usar o app não altera
    `SessionExercise` nem `customized_at`, e a ficha continua válida — o
    retrato das linhas é o mesmo antes e depois (como test_gluteo)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("nao-remonta@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def _retrato(self):
        from workouts.models import SessionExercise

        return sorted(
            (se.session_id, se.exercise_id, se.opcao, se.sets)
            for se in SessionExercise.objects.filter(session__plan=self.plan)
        )

    def test_usar_o_app_por_presenca_nao_muda_as_linhas_nem_invalida(self):
        antes = self._retrato()
        fazer(self.user, self.plan, "A", SEGUNDA)
        fazer(self.user, self.plan, "B", SEGUNDA + timedelta(days=1))
        self.client.force_login(self.user)
        self.client.get(reverse("workouts:routine"))
        self.client.get(reverse("workouts:now"))
        services.estado_do_treino(self.user)  # recomenda C, veste em memória
        self.plan.refresh_from_db()
        self.assertIsNone(self.plan.customized_at)
        self.assertEqual(self._retrato(), antes, "nenhuma linha da ficha mudou")
        self.assertFalse(services.rotina_invalida(self.plan, self.user))
