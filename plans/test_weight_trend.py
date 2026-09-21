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

from accounts.models import Goal, WeightEntry

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

    def test_the_raise_never_pushes_the_target_above_the_safety_ceiling(self):
        """O teto é simétrico ao piso: o pedido manual também não fura o
        limite de segurança, do outro lado — para quem EMAGRECE ou MANTÉM,
        que é para quem `target_kcal` aplica o teto automático.

        Homem de 105 kg, 180 cm, 30 anos, rotina ativa, 4 treinos, cortando:
        meta automática 2 707. "Somar 150" pediria 2 857, e o teto segura
        em 2 800 com o aviso.
        """
        from decimal import Decimal as D

        from accounts.models import ActivityLevel, Goal, Sex

        from .calculations import PlanInputs, SAFE_MAX_KCAL, calculate

        base = dict(
            sex=Sex.MALE,
            weight_kg=D("105"),
            height_cm=180,
            age_years=30,
            activity_level=ActivityLevel.ACTIVE,
            goal=Goal.CUT,
            session_minutes=(60,) * 4,
        )
        sem_ajuste = calculate(PlanInputs(**base))
        com_aumento = calculate(PlanInputs(**base, kcal_adjustment=150))

        # Controle: a meta automática está abaixo do teto e o pedido passa
        # dele — senão o teste passaria sem o teto ter feito nada.
        self.assertEqual(sem_ajuste.target_kcal, 2707)
        self.assertGreater(sem_ajuste.target_kcal + 150, SAFE_MAX_KCAL)

        self.assertEqual(com_aumento.target_kcal, SAFE_MAX_KCAL)
        self.assertIn("teto de segurança", com_aumento.notes)

    def test_o_teto_manual_nao_corta_quem_ganha_massa(self):
        """Achado da revisão final da Fase 3 (17/09/2026), CRÍTICO.

        `target_kcal` só aplica o teto de 2 800 a CUT e MAINTAIN — "superávit
        alto é gordura ganha, não risco de segurança" (`SafetyCapTests`). O
        teto do ajuste MANUAL valia para qualquer objetivo, e o perfil de
        referência da avaliação (BULK, meta automática 2 859) pedia "Somar
        150", esperava 3 009 e recebia 2 800 — CINQUENTA E NOVE kcal a MENOS
        do que tinha antes de pedir mais, com a mensagem "parou no teto de
        segurança". O teto manual passa a ESPELHAR `target_kcal`: BULK e
        RECOMP não têm teto manual, como não têm teto automático.
        """
        from decimal import Decimal as D

        from accounts.models import ActivityLevel, Goal, Sex

        from .calculations import PlanInputs, calculate

        referencia = dict(
            sex=Sex.MALE,
            weight_kg=D("82.5"),
            height_cm=178,
            age_years=30,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            session_minutes=(60,) * 5,
        )
        sem_ajuste = calculate(PlanInputs(**referencia))
        com_aumento = calculate(PlanInputs(**referencia, kcal_adjustment=150))

        self.assertEqual(sem_ajuste.target_kcal, 2859)
        self.assertEqual(com_aumento.target_kcal, 3009)
        self.assertEqual(com_aumento.notes, "")

    def test_recomp_acima_do_teto_tambem_nao_recebe_aviso(self):
        """RECOMP fica do lado de BULK: sem teto automático, sem teto manual,
        e sem o aviso de "passou de 2 800" — esse aviso só faz sentido quando
        o teto TERIA se aplicado (CUT/MAINTAIN acima de 120 kg)."""
        from decimal import Decimal as D

        from accounts.models import ActivityLevel, Goal, Sex

        from .calculations import PlanInputs, calculate

        base = dict(
            sex=Sex.MALE,
            weight_kg=D("95"),
            height_cm=185,
            age_years=25,
            activity_level=ActivityLevel.ACTIVE,
            goal=Goal.RECOMP,
            session_minutes=(60,) * 5,
        )
        sem_ajuste = calculate(PlanInputs(**base))
        com_aumento = calculate(PlanInputs(**base, kcal_adjustment=150))

        self.assertGreater(com_aumento.target_kcal, 2800)
        self.assertEqual(com_aumento.target_kcal, sem_ajuste.target_kcal + 150)
        self.assertNotIn("2800", com_aumento.notes)
        self.assertNotIn("teto", com_aumento.notes)

    def test_o_teto_manual_nao_corta_abaixo_da_tmb_em_peso_extremo(self):
        """Achado em revisão adversarial, lendo `plans/calculations.py`.

        Homem de 200 kg, 200 cm, 20 anos: a TMB sozinha já passa de 3.100
        kcal, acima do teto de segurança de 2.800. Antes da correção, o
        `elif pedido > teto` do ajuste manual não conhecia essa exceção — a
        mesma que `target_kcal` já aplica acima de 120 kg — e cortava a meta
        de quem está GANHANDO massa e só pediu "Somar 150 kcal" para 2.800,
        mais de 1.000 kcal ABAIXO da própria taxa de repouso. Era o exato
        problema que o piso, três linhas acima no código, existe para
        impedir.
        """
        from decimal import Decimal as D

        from accounts.models import ActivityLevel, Goal, Sex

        from .calculations import PlanInputs, calculate

        base = dict(
            sex=Sex.MALE,
            weight_kg=D("200"),
            height_cm=200,
            age_years=20,
            activity_level=ActivityLevel.SEDENTARY,
            goal=Goal.BULK,
            session_minutes=(),
        )
        sem_ajuste = calculate(PlanInputs(**base))
        com_ajuste = calculate(PlanInputs(**base, kcal_adjustment=150))

        self.assertGreaterEqual(com_ajuste.target_kcal, sem_ajuste.bmr_kcal)
        # O aumento pedido precisa aparecer em cima do que `target_kcal` já
        # tinha dado — não só "não cair abaixo da TMB", que um teto travado
        # exatamente no piso também cumpriria sem deixar o pedido surtir
        # efeito nenhum.
        self.assertEqual(com_ajuste.target_kcal, sem_ajuste.target_kcal + 150)

    def test_quem_emagrece_acima_de_120_kg_e_avisado_que_o_teto_nao_se_aplicou(self):
        """O único ramo do bloco que ficou sem teste na onda final.

        Emagrecer acima de 120 kg é o caso em que o teto de 2.800 TERIA se
        aplicado e a exceção de peso extremo o desligou: o ajuste manual
        vale inteiro E a pessoa lê por quê ("o seu peso realmente sustenta um
        gasto alto"). Para quem ganha massa esse aviso não existe — não há
        teto a explicar — e o teste vizinho de RECOMP garante isso."""
        from decimal import Decimal as D

        from accounts.models import ActivityLevel, Goal, Sex

        from .calculations import PlanInputs, calculate

        base = dict(
            sex=Sex.MALE,
            weight_kg=D("200"),
            height_cm=200,
            age_years=20,
            activity_level=ActivityLevel.SEDENTARY,
            goal=Goal.CUT,
            session_minutes=(),
        )
        sem_ajuste = calculate(PlanInputs(**base))
        com_ajuste = calculate(PlanInputs(**base, kcal_adjustment=150))

        self.assertGreater(sem_ajuste.target_kcal, 2800)
        self.assertEqual(com_ajuste.target_kcal, sem_ajuste.target_kcal + 150)
        self.assertIn("não se aplicou", com_ajuste.notes)
        self.assertNotIn("parou no teto", com_ajuste.notes)

    def test_quem_ganha_massa_ouve_aumentar_nao_cortar(self):
        """Sugerir corte para quem quer GANHAR massa e empacou seria o app
        remando contra o objetivo da própria pessoa."""
        self.user.profile.goal = Goal.BULK
        self.user.profile.save()
        self.user.weight_entries.all().delete()
        for semana in range(4):
            registrar_semana(self.user, semana, [100, 100, 100])

        self.assertEqual(weight_trend.analisar(self.user).sugestao, "aumentar")

    def test_quem_corta_ouve_cortar(self):
        """CONTROLE: o padrão (CUT) continua pedindo corte, não os dois."""
        self.user.weight_entries.all().delete()
        for semana in range(4):
            registrar_semana(self.user, semana, [100, 100, 100])

        self.assertEqual(weight_trend.analisar(self.user).sugestao, "cortar")

    def test_quem_mantem_nao_ouve_nada(self):
        """Estabilidade É a meta de quem mantém — não há o que sugerir."""
        self.user.profile.goal = Goal.MAINTAIN
        self.user.profile.save()
        self.user.weight_entries.all().delete()
        for semana in range(4):
            registrar_semana(self.user, semana, [100, 100, 100])

        t = weight_trend.analisar(self.user)
        self.assertIsNone(t.sugestao)
        self.assertFalse(t.sugerir_recalibragem)

    def test_quem_recompoe_tambem_nao_ouve_nada(self):
        """RECOMP também não tem corte nem aumento sugerido: o déficit
        pequeno já é a prescrição inteira do objetivo."""
        self.user.profile.goal = Goal.RECOMP
        self.user.profile.save()
        self.user.weight_entries.all().delete()
        for semana in range(4):
            registrar_semana(self.user, semana, [100, 100, 100])

        self.assertIsNone(weight_trend.analisar(self.user).sugestao)

    def test_the_view_accepts_aumentar_and_raises_the_target(self):
        antes = self.user.profile.kcal_adjustment

        self.client.post(reverse("plans:recalibrate"), {"acao": "aumentar"})

        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.kcal_adjustment, antes + weight_trend.AJUSTE_KCAL
        )
        self.assertIsNotNone(self.user.profile.recalibrated_at)

    def test_prefiro_esperar_fala_de_proteina_para_quem_ganha_massa(self):
        """"Somar uns 20 minutos de caminhada" é conselho de CORTE: gastar mais
        para quem quer GANHAR massa e empacou é o app remando contra o
        objetivo da própria pessoa (revisão final da Fase 3, 17/09/2026).
        Para BULK a mensagem fala do que destrava o ganho — proteína e as
        refeições do dia sendo batidas."""
        self.user.profile.goal = Goal.BULK
        self.user.profile.save(update_fields=["goal"])

        resposta = self.client.post(
            reverse("plans:recalibrate"), {"acao": "dispensar"}, follow=True
        )

        self.assertContains(resposta, "meta de proteína")
        self.assertNotContains(resposta, "caminhada")

    def test_prefiro_esperar_continua_sugerindo_caminhada_para_os_outros_objetivos(self):
        """CONTROLE por objetivo: CUT, MAINTAIN e RECOMP ficam com a frase de
        antes — cada um num POST próprio, para o teste de BULK não passar
        por acidente de fixture."""
        for goal in (Goal.CUT, Goal.MAINTAIN, Goal.RECOMP):
            with self.subTest(goal=goal):
                self.user.profile.goal = goal
                self.user.profile.recalibrated_at = None
                self.user.profile.save(update_fields=["goal", "recalibrated_at"])

                resposta = self.client.post(
                    reverse("plans:recalibrate"), {"acao": "dispensar"}, follow=True
                )

                self.assertContains(resposta, "20 minutos de caminhada")
                self.assertNotContains(resposta, "meta de proteína")

    def test_the_view_ignores_an_unknown_acao(self):
        """Uma ação inventada não pode aplicar ajuste nenhum — nem cortar,
        nem aumentar, nem dispensar. `acao` vem de um POST, e o servidor não
        confia nele: uma versão anterior tratava qualquer valor desconhecido
        como "dispensar" e gravava `recalibrated_at` mesmo assim, o que
        silenciaria o aviso de recalibragem sem a pessoa ter respondido nada."""
        antes = self.user.profile.kcal_adjustment
        antes_recalibrado = self.user.profile.recalibrated_at

        self.client.post(reverse("plans:recalibrate"), {"acao": "girar_polegares"})

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.kcal_adjustment, antes)
        self.assertEqual(self.user.profile.recalibrated_at, antes_recalibrado)


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
