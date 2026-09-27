"""A corrida entra na conta — o item 2 da missão "quem entra não desiste".

A persona 3 do relatório de experiência corre 5 km três vezes por semana e
não faz musculação. O app calculava a meta dela como a de quem não treina:
`calculations.activity_factor` conta SESSÕES por semana, e sessões eram só
`TrainingDay` — os dias de academia. Zero dias, piso da faixa.

Quatro coisas aqui, e a terceira é a que evita o defeito novo:

1. a corrida vira SESSÃO no fator de atividade — três corridas movem a
   pessoa dentro da faixa exatamente como três musculações;
2. os MINUTOS continuam fora da conta, e isso é decisão escrita: somar
   caloria por minuto de esforço depende de um número que ninguém sabe de
   cabeça, e infla a meta de quem mais precisa dela apertada;
3. **quem declara a corrida deixa de receber o crédito do dia**, porque o
   gasto já está na meta de todo dia — somar os dois contaria o mesmo
   esforço duas vezes. Quem NÃO declarou continua recebendo, exatamente
   como antes;
4. a meta de ÁGUA do dia sobe meio litro quando houve corrida; a ofensiva
   continua medindo pela meta base, de propósito.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Corrida as CorridaPerfil
from accounts.models import FULL_TRAINING_WEEK, TrainingDay
from plans import services, tracking, weight_trend
from plans.calculations import PlanInputs, activity_factor, calculate
from plans.tests import create_complete_user
from workouts.models import Corrida

BASE = dict(
    sex="F", weight_kg=Decimal("62"), height_cm=165, age_years=34,
    activity_level="light", goal="maintain",
)


class OFatorDeAtividadeContaACorridaTests(TestCase):
    def test_quem_so_corre_sai_do_piso_da_faixa(self):
        piso = activity_factor("light", 0, 0)
        correndo = activity_factor("light", 0, 3)
        self.assertGreater(correndo, piso)

    def test_tres_corridas_valem_tres_musculacoes(self):
        """Sessão é sessão. A faixa existe para acomodar a frequência, e o
        corpo não pergunta se o esforço foi com barra ou na rua."""
        self.assertEqual(activity_factor("light", 0, 3), activity_factor("light", 3, 0))
        self.assertEqual(activity_factor("moderate", 1, 2), activity_factor("moderate", 3, 0))

    def test_quem_nao_respondeu_recebe_exatamente_o_de_antes(self):
        """A pergunta nova não mexe em conta nenhuma de quem já tem conta:
        zero corridas é o que toda linha do banco tem hoje."""
        for nivel in ("sedentary", "light", "moderate"):
            for dias in range(0, 6):
                with self.subTest(nivel=nivel, dias=dias):
                    self.assertEqual(
                        activity_factor(nivel, dias, 0), activity_factor(nivel, dias)
                    )

    def test_o_teto_da_faixa_continua_sendo_o_teto(self):
        """Cinco musculações mais três corridas não passam do topo — a faixa
        é uma faixa, e somar sessões não pode furá-la."""
        teto = activity_factor("light", FULL_TRAINING_WEEK, 0)
        self.assertEqual(activity_factor("light", FULL_TRAINING_WEEK, 3), teto)
        self.assertEqual(activity_factor("light", 3, 9), teto)

    def test_a_meta_de_quem_corre_e_maior_que_a_de_quem_nao_faz_nada(self):
        sedentaria = calculate(PlanInputs(**BASE))
        corredora = calculate(PlanInputs(**BASE, corrida_dias=3))
        self.assertGreater(corredora.target_kcal, sedentaria.target_kcal)

    def test_os_minutos_nao_entram_na_conta(self):
        """Decisão escrita: a conta usa a FREQUÊNCIA. Quem corre 20 minutos e
        quem corre 60 recebem a mesma meta — e é por isso que o campo de
        minutos diz para que serve."""
        curta = calculate(PlanInputs(**BASE, corrida_dias=3, corrida_minutos=20))
        longa = calculate(PlanInputs(**BASE, corrida_dias=3, corrida_minutos=60))
        self.assertEqual(curta.target_kcal, longa.target_kcal)


class ACorridaEEntradaDoPlanoTests(TestCase):
    """Mudar a corrida no Perfil faz nascer estimativa nova, como mudar os
    dias de academia já fazia."""

    def setUp(self):
        self.user = create_complete_user(email="corrida-plano@exemplo.com")
        perfil = self.user.profile
        perfil.corrida = CorridaPerfil.SIM
        perfil.corrida_dias = 3
        perfil.save(update_fields=["corrida", "corrida_dias"])
        self.plano = services.sync_active_plan(self.user)

    def test_o_retrato_guarda_as_corridas(self):
        self.assertEqual(self.plano.corrida_dias, 3)

    def test_mudar_a_frequencia_invalida_o_plano(self):
        self.assertTrue(services.plan_is_current(self.plano, self.user))
        perfil = self.user.profile
        perfil.corrida_dias = 5
        perfil.save(update_fields=["corrida_dias"])
        self.user.refresh_from_db()
        self.assertFalse(services.plan_is_current(self.plano, self.user))

    def test_responder_nao_zera_a_entrada(self):
        perfil = self.user.profile
        perfil.corrida = CorridaPerfil.NAO
        perfil.save(update_fields=["corrida"])
        self.user.refresh_from_db()
        self.assertEqual(services.build_inputs(self.user).corrida_dias, 0)


class ACorridaNaoEntraDuasVezesTests(TestCase):
    """O crédito do dia e a meta não podem contar o mesmo esforço."""

    def setUp(self):
        self.hoje = timezone.localdate()

    def _com_corrida(self, *, declarou):
        user = create_complete_user(email="duplo-%s@exemplo.com" % declarou)
        if declarou:
            perfil = user.profile
            perfil.corrida = CorridaPerfil.SIM
            perfil.corrida_dias = 3
            perfil.save(update_fields=["corrida", "corrida_dias"])
        plano = services.sync_active_plan(user)
        Corrida.objects.create(
            user=user,
            comecou_em=timezone.now() - timedelta(hours=2),
            duracao_s=1800,
            distancia_m=5000,
        )
        return tracking.day_summary(user, plano, self.hoje)

    def test_quem_declarou_nao_ganha_o_gasto_por_cima(self):
        resumo = self._com_corrida(declarou=True)
        self.assertEqual(resumo["gasto_corrida_kcal"], 0)
        self.assertTrue(resumo["corrida_ja_na_meta"])

    def test_quem_nao_declarou_continua_ganhando(self):
        """CONTROLE POSITIVO: o crédito não sumiu do app — ele saiu de quem
        já o tem na meta de todo dia."""
        resumo = self._com_corrida(declarou=False)
        self.assertGreater(resumo["gasto_corrida_kcal"], 0)
        self.assertFalse(resumo["corrida_ja_na_meta"])


class AMetaDeAguaSobeNoDiaDeCorridaTests(TestCase):
    def test_meio_litro_a_mais_quando_correu(self):
        base = weight_trend.hidratacao_ml(Decimal("70"))
        self.assertEqual(
            weight_trend.hidratacao_do_dia_ml(Decimal("70"), correu=True),
            base + weight_trend.EXTRA_POR_CORRIDA_ML,
        )

    def test_sem_corrida_a_meta_e_a_de_sempre(self):
        base = weight_trend.hidratacao_ml(Decimal("70"))
        self.assertEqual(weight_trend.hidratacao_do_dia_ml(Decimal("70")), base)

    def test_o_teto_diario_continua_valendo(self):
        """Ninguém recebe meta de doze litros porque correu."""
        alto = weight_trend.hidratacao_do_dia_ml(Decimal("200"), correu=True)
        self.assertLessEqual(alto, weight_trend.TETO_DIARIO_ML)


class AOfensivaContaACorridaComoTreinoTests(TestCase):
    """Já era verdade antes desta missão (a régua é "moveu-se", não "fez a
    letra"), e fica preso: a corrida de hoje fecha o treino do dia."""

    def test_o_dia_de_treino_fecha_com_uma_corrida(self):
        from plans import streaks

        user = create_complete_user(email="ofensiva-corrida@exemplo.com")
        hoje = timezone.localdate()
        TrainingDay.objects.filter(user=user).delete()
        TrainingDay.objects.create(user=user, weekday=hoje.weekday(), duration_min=60)
        import workouts.services as treino

        treino.create_routine(user)
        Corrida.objects.create(
            user=user,
            comecou_em=timezone.now() - timedelta(hours=1),
            duracao_s=1800,
            distancia_m=5000,
        )
        ofensiva = streaks.para_a_tela(user, hoje=hoje)
        self.assertNotIn("treino", ofensiva.falta_hoje)
