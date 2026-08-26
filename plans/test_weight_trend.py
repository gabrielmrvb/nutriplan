"""Testes da média semanal de peso e da recalibragem.

O que estes testes defendem é uma decisão de produto, não um cálculo: o app
não pode reagir ao peso do dia. Ele oscila com sal, com o carboidrato de
ontem, com o intestino e com a hora da pesagem — um a dois quilos que não são
gordura. Quem olha o número do dia desiste na primeira quinta-feira em que a
balança sobe.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry

from . import weight_trend
from .tests import CatalogFixture, create_complete_user


def registrar(user, dias_atras, peso):
    return WeightEntry.objects.create(
        user=user,
        date=timezone.localdate() - timedelta(days=dias_atras),
        weight_kg=Decimal(str(peso)),
    )


def registrar_semana(user, semanas_atras, pesos):
    """Grava pesagens dentro de uma semana de CALENDÁRIO, não de sete dias.

    Contar "sete dias atrás" atravessa a segunda-feira e espalha os registros
    por duas semanas — foi assim que a primeira versão destes testes achou
    três semanas onde deveria haver duas. A semana do módulo começa na
    segunda, então o teste precisa começar lá também.
    """
    hoje = timezone.localdate()
    segunda = hoje - timedelta(days=hoje.weekday()) - timedelta(weeks=semanas_atras)
    for dia, peso in enumerate(pesos):
        WeightEntry.objects.create(
            user=user,
            date=segunda + timedelta(days=dia),
            weight_kg=Decimal(str(peso)),
        )


class MediaSemanalTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="peso@exemplo.com")
        self.user.weight_entries.all().delete()

    def test_a_single_weighing_is_not_a_trend(self):
        """Com uma semana só não há do que comparar, e dizer isso é melhor que
        desenhar um gráfico de um ponto."""
        registrar(self.user, 0, 100)

        t = weight_trend.analisar(self.user)

        self.assertIsNone(t.variacao_semanal)
        self.assertFalse(t.sugerir_recalibragem)
        self.assertEqual(t.faltam_registros, 1)

    def test_the_week_average_smooths_the_daily_noise(self):
        """Sete pesagens viram um número.

        Os valores abaixo variam 1,4 kg dentro da mesma semana — o tipo de
        oscilação que faz alguém achar que engordou numa terça. A média não se
        mexe com isso.
        """
        registrar_semana(self.user, 1, [100.2, 101.1, 100.4, 99.9, 100.6, 101.3, 100.5])
        registrar_semana(self.user, 0, [99.8, 100.4, 99.5, 99.2, 100.1, 99.6, 99.4])

        t = weight_trend.analisar(self.user)

        self.assertEqual(len(t.semanas), 2)
        self.assertEqual(t.semanas[0].registros, 7)
        # A média cai cerca de 0,86 kg, apesar de dias isolados subirem.
        self.assertLess(t.variacao_semanal, Decimal("-0.5"))
        self.assertEqual(t.direcao, "perdendo")

    def test_two_flat_weeks_are_not_enough_to_change_the_diet(self):
        """Duas semanas iguais acontecem por acaso o tempo todo. Mexer na dieta
        a cada oscilação é ajustar o volante a cada buraco da estrada."""
        for semana in range(3):
            registrar_semana(self.user, semana, [100, 100, 100])

        t = weight_trend.analisar(self.user)

        self.assertEqual(t.semanas_paradas, 2)
        self.assertFalse(t.sugerir_recalibragem)

    def test_three_flat_weeks_ask_for_a_decision(self):
        for semana in range(4):
            registrar_semana(self.user, semana, [100, 100, 100])

        t = weight_trend.analisar(self.user)

        self.assertEqual(t.semanas_paradas, 3)
        self.assertTrue(t.sugerir_recalibragem)
        self.assertEqual(t.direcao, "estável")

    def test_losing_slowly_is_not_stagnation(self):
        """Cento e cinquenta gramas por semana é pouco, mas é movimento — e
        avisar quem está progredindo devagar faria a pessoa cortar comida sem
        precisar."""
        # `semana` conta para trás: 3 é a mais antiga, e é a mais pesada.
        for semana in range(4):
            peso = 100 - (3 - semana) * 0.3
            registrar_semana(self.user, semana, [peso, peso, peso])

        t = weight_trend.analisar(self.user)

        self.assertFalse(t.sugerir_recalibragem)
        self.assertEqual(t.direcao, "perdendo")

    def test_the_week_starts_on_monday_and_does_not_slide(self):
        """Semana fixa e não janela móvel: assim a média de uma semana não muda
        quando a pessoa registra hoje o peso de ontem, e duas telas abertas em
        horas diferentes mostram o mesmo número."""
        hoje = timezone.localdate()
        segunda = hoje - timedelta(days=hoje.weekday())

        self.assertEqual(weight_trend._inicio_da_semana(segunda), segunda)
        self.assertEqual(weight_trend._inicio_da_semana(segunda + timedelta(days=6)), segunda)
        self.assertEqual(
            weight_trend._inicio_da_semana(segunda + timedelta(days=7)),
            segunda + timedelta(days=7),
        )


class HidratacaoTests(TestCase):
    def test_the_target_scales_with_body_weight(self):
        """Trinta e cinco mililitros por quilo. Para 102 kg dá 3,5 L — dentro
        da faixa esperada para alguém desse porte treinando cinco vezes."""
        self.assertEqual(weight_trend.hidratacao_ml(102), 3500)
        self.assertEqual(weight_trend.hidratacao_ml(60), 2000)

    def test_the_target_lands_on_half_litres(self):
        """Ninguém mede 3.570 ml. A pessoa enche uma garrafa, e a meta precisa
        caber em garrafas."""
        for peso in range(45, 145, 7):
            with self.subTest(peso=peso):
                self.assertEqual(weight_trend.hidratacao_ml(peso) % 500, 0)


class RecalibragemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user(email="recalibra@exemplo.com")
        self.client.force_login(self.user)

    def test_cutting_lowers_the_target_by_the_agreed_amount(self):
        antes = self.user.profile.kcal_adjustment

        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})

        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.kcal_adjustment, antes - weight_trend.AJUSTE_KCAL
        )
        self.assertIsNotNone(self.user.profile.recalibrated_at)

    def test_choosing_to_move_more_changes_no_calories(self):
        """"Prefiro me mexer mais" não é botão decorativo: aumentar o gasto é
        resposta legítima, e às vezes melhor que comer menos."""
        self.client.post(reverse("plans:recalibrate"), {"acao": "dispensar"})

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.kcal_adjustment, 0)
        # Mas a resposta fica registrada, para não perguntar de novo semana que vem.
        self.assertIsNotNone(self.user.profile.recalibrated_at)

    def test_the_cut_never_pushes_the_target_below_resting_burn(self):
        """A trava vence o pedido manual.

        Comer abaixo do gasto de repouso não acelera nada: derruba o treino e
        come músculo. Um corte de 150 kcal repetido muitas vezes acabaria lá
        se ninguém segurasse.
        """
        from decimal import Decimal as D

        from accounts.models import ActivityLevel, Goal, Sex

        from .calculations import PlanInputs, calculate

        base = dict(
            sex=Sex.FEMALE,
            weight_kg=D("52"),
            height_cm=158,
            age_years=30,
            activity_level=ActivityLevel.SEDENTARY,
            goal=Goal.CUT,
            session_minutes=(60,) * 3,
        )
        sem_corte = calculate(PlanInputs(**base))
        com_corte = calculate(PlanInputs(**base, kcal_adjustment=-1200))

        self.assertGreaterEqual(com_corte.target_kcal, sem_corte.bmr_kcal)
        self.assertIn("mínimo seguro", com_corte.notes)
