"""Testes da média semanal de peso e da recalibragem.

O que estes testes defendem é uma decisão de produto, não um cálculo: o app
não pode reagir ao peso do dia. Ele oscila com sal, com o carboidrato de
ontem, com o intestino e com a hora da pesagem — um a dois quilos que não são
gordura. Quem olha o número do dia desiste na primeira quinta-feira em que a
balança sobe.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
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


class ConvitePesagemTests(TestCase):
    """Quando o painel convida a pessoa a se pesar.

    A decisão de produto é duas pesagens por semana, em dias diferentes, sem
    dias obrigatórios. O que estes testes defendem é o "duas": pedir mais
    transforma acompanhamento em cobrança diária, e quem se sente cobrado para
    de se pesar — o app perde a série inteira, que é o insumo da tendência e
    da recalibragem.

    As datas são fixas de propósito. Contar "ontem" atravessa a segunda-feira
    quando o teste roda numa segunda, e aí o registro cai na semana passada
    sem ninguém perceber: o teste passaria a medir outra coisa dependendo do
    dia em que a suíte roda.
    """

    #: Quarta-feira. A semana dela vai de 24/08 (segunda) a 30/08 (domingo).
    QUARTA = date(2026, 8, 26)
    SEGUNDA = date(2026, 8, 24)

    def setUp(self):
        self.user = create_complete_user(email="convite@exemplo.com")
        # `create_complete_user` já grava a pesagem de hoje: sem limpar, todo
        # cenário começaria com o convite desligado.
        self.user.weight_entries.all().delete()

    def _pesar(self, dia, peso="82.4"):
        WeightEntry.objects.create(user=self.user, date=dia, weight_kg=Decimal(peso))

    def test_a_week_with_no_weighing_gets_the_invitation(self):
        self.assertTrue(weight_trend.convidar_a_pesar(self.user, hoje=self.QUARTA))

    def test_one_earlier_weighing_in_the_week_still_gets_the_invitation(self):
        """Uma pesagem não faz média. O convite continua até a segunda."""
        self._pesar(self.SEGUNDA)

        self.assertTrue(weight_trend.convidar_a_pesar(self.user, hoje=self.QUARTA))

    def test_two_weighings_in_the_week_end_the_invitation(self):
        """Atingido o alvo, o app para de pedir. Não existe terceira pesagem
        solicitada, e é isso que separa acompanhamento de cobrança."""
        self._pesar(self.SEGUNDA)
        self._pesar(self.SEGUNDA + timedelta(days=1))

        self.assertFalse(weight_trend.convidar_a_pesar(self.user, hoje=self.QUARTA))

    def test_weighing_today_ends_the_invitation_even_below_the_target(self):
        """Uma na semana e ela é de hoje: o convite some mesmo faltando a
        segunda. Insistir seria pedir a segunda pesagem no mesmo dia — que a
        unicidade por (usuário, dia) recusaria de qualquer forma."""
        self._pesar(self.QUARTA)

        self.assertFalse(weight_trend.convidar_a_pesar(self.user, hoje=self.QUARTA))

    def test_the_next_week_starts_the_count_over(self):
        """Semana nova, contagem nova. Sem compensação da semana anterior:
        quem não pesou não deve nada a ninguém."""
        self._pesar(self.SEGUNDA)
        self._pesar(self.SEGUNDA + timedelta(days=1))

        semana_seguinte = self.QUARTA + timedelta(days=7)
        self.assertTrue(weight_trend.convidar_a_pesar(self.user, hoje=semana_seguinte))

    def test_the_week_starts_on_the_same_monday_the_average_uses(self):
        """Sábado e domingo pertencem à semana que passou, e é a mesma
        fronteira da média. Duas definições de semana no mesmo assunto seria o
        app dizendo que a contagem virou enquanto a média ainda não."""
        self._pesar(self.SEGUNDA - timedelta(days=2))  # sábado anterior
        self._pesar(self.SEGUNDA - timedelta(days=1))  # domingo anterior

        self.assertEqual(weight_trend._inicio_da_semana(self.QUARTA), self.SEGUNDA)
        self.assertTrue(weight_trend.convidar_a_pesar(self.user, hoje=self.QUARTA))

    def test_the_invitation_does_not_come_from_faltam_registros(self):
        """`faltam_registros` responde outra pergunta, e este teste é a prova.

        Ele conta o total acumulado enquanto o histórico tem menos de duas
        semanas, e zera para sempre depois. Quem tem meses de pesagens tem
        `faltam_registros == 0` para sempre — se o convite dependesse dele,
        nunca mais apareceria para justamente quem usa o app há mais tempo.
        """
        for semanas_atras in (1, 2, 3):
            base = self.SEGUNDA - timedelta(weeks=semanas_atras)
            self._pesar(base)
            self._pesar(base + timedelta(days=3))

        self.assertEqual(weight_trend.analisar(self.user).faltam_registros, 0)
        self.assertTrue(weight_trend.convidar_a_pesar(self.user, hoje=self.QUARTA))

    def test_two_weighings_land_on_different_days_without_a_rule_for_it(self):
        """"Em dias diferentes" não precisa de regra própria.

        A unicidade por (usuário, dia) já impede duas pesagens no mesmo dia,
        então duas na semana caem necessariamente em dias distintos. É a mesma
        garantia que transforma "registrar de novo hoje" em correção, e não em
        linha nova — por isso a escrita usa `update_or_create`.
        """
        self._pesar(self.SEGUNDA, "82.4")
        WeightEntry.objects.update_or_create(
            user=self.user, date=self.SEGUNDA, defaults={"weight_kg": Decimal("81.9")}
        )

        entries = self.user.weight_entries.filter(date=self.SEGUNDA)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().weight_kg, Decimal("81.90"))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._pesar(self.SEGUNDA, "80.0")
