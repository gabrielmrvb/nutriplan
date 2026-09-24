# -*- coding: utf-8 -*-
"""A janela do Progresso NUNCA é maior que a vida da conta.

MEDIDO em produção (e6194b7) numa conta de TRÊS DIAS, que é o estado em que
todo mundo vê esta tela na primeira semana: 24 linhas de semana, sete delas
começando em 03/08 — antes de a conta existir —, dezoito "—" e "0,0 km". As
séries eram fixas em oito semanas (`SEMANAS = 8` em `workouts/progresso.py`,
`semanas=8` em `tracking.agua_por_semana`), e "buraco na série é informação"
só vale para buraco DENTRO da série: fora dela é ruído que afirma ausência
onde não havia nem app.

Este módulo prende a regra única do item 6: o recorte começa no máximo em
`primeiro_dia_da_conta`, e tudo que a tela desenha sai dele.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from plans import evolucao
from plans.tests import create_complete_user


def _nasceu_em(user, dia):
    """Reescreve a data de cadastro para o dia local pedido."""
    user.date_joined = timezone.make_aware(
        timezone.datetime.combine(dia, timezone.datetime.min.time())
    ) + timedelta(hours=9)
    user.save(update_fields=["date_joined"])
    return user


class AJanelaNuncaPrecedeOCadastroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="janela@exemplo.com")

    def test_a_conta_de_tres_dias_pede_um_mes_e_recebe_tres_dias(self):
        hoje = date(2026, 9, 23)
        _nasceu_em(self.user, hoje - timedelta(days=2))
        janela = evolucao.janela(self.user, "mes", hoje=hoje)
        self.assertEqual(janela.inicio, hoje - timedelta(days=2))
        self.assertEqual(janela.fim, hoje)
        self.assertEqual(len(evolucao.dias_da_janela(janela)), 3)
        self.assertTrue(janela.truncada, "a janela foi cortada pelo cadastro")

    def test_a_conta_velha_recebe_o_periodo_inteiro(self):
        hoje = date(2026, 9, 23)
        _nasceu_em(self.user, hoje - timedelta(days=400))
        janela = evolucao.janela(self.user, "mes", hoje=hoje)
        self.assertEqual(janela.inicio, hoje - timedelta(days=29))
        self.assertEqual(len(evolucao.dias_da_janela(janela)), 30)
        self.assertFalse(janela.truncada)

    def test_nenhuma_semana_comeca_antes_do_cadastro(self):
        """A regra que a tela quebrava: `semanas` devolvia oito, sempre."""
        hoje = date(2026, 9, 23)  # quarta
        nasceu = hoje - timedelta(days=2)  # segunda 21/09
        _nasceu_em(self.user, nasceu)
        for periodo in evolucao.PERIODOS:
            with self.subTest(periodo=periodo):
                semanas = evolucao.semanas_da_janela(
                    evolucao.janela(self.user, periodo, hoje=hoje)
                )
                self.assertTrue(semanas, "sempre existe a semana corrente")
                for semana in semanas:
                    self.assertGreaterEqual(
                        semana.fim, nasceu,
                        "semana que termina antes do cadastro não existiu",
                    )
                self.assertEqual(len(semanas), 1, "três dias são UMA semana")

    def test_os_tres_periodos_existem_e_o_padrao_e_o_mes(self):
        self.assertEqual(evolucao.PERIODOS, ("semana", "mes", "trimestre"))
        self.assertEqual(evolucao.PADRAO, "mes")
        self.assertEqual(evolucao.periodo_valido("trimestre"), "trimestre")

    def test_periodo_desconhecido_cai_no_padrao_em_vez_de_quebrar(self):
        """`?p=` é parâmetro de URL: qualquer pessoa digita qualquer coisa."""
        for entrada in ("", None, "ontem", "../../etc", "90"):
            with self.subTest(entrada=entrada):
                self.assertEqual(evolucao.periodo_valido(entrada), evolucao.PADRAO)

    def test_a_semana_parcial_do_cadastro_e_marcada(self):
        """A semana em que a conta nasceu não teve sete dias, e dizer a média
        dela como se tivesse seria a mesma mentira da média de água sobre
        sete dias — a que `agua_por_semana` já documenta."""
        hoje = date(2026, 9, 23)  # quarta
        _nasceu_em(self.user, hoje - timedelta(days=2))  # segunda
        semana = evolucao.semanas_da_janela(
            evolucao.janela(self.user, "trimestre", hoje=hoje)
        )[0]
        self.assertEqual(semana.dias, 3, "segunda, terça e quarta")
        self.assertTrue(semana.parcial)


class OMapaDoDiaTemOsTresEstadosTests(TestCase):
    """O heatmap existe para distinguir três coisas que a lista de semanas
    somava numa só: o dia treinado, o dia de DESCANSO COMBINADO (que é o
    plano, e não falha — a régua da ofensiva já dizia isso) e o dia previsto
    em que não houve série."""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import TrainingDay

        cls.user = create_complete_user(email="mapa@exemplo.com")
        TrainingDay.objects.filter(user=cls.user).delete()
        for weekday in (0, 2, 4):  # segunda, quarta, sexta
            TrainingDay.objects.create(user=cls.user, weekday=weekday, duration_min=60)

    def _mapa(self, hoje):
        _nasceu_em(self.user, hoje - timedelta(days=6))
        return {
            d.data: d
            for d in evolucao.mapa_de_treino(
                self.user, evolucao.janela(self.user, "semana", hoje=hoje)
            )
        }

    def test_dia_combinado_sem_serie_e_faltou_e_dia_livre_e_descanso(self):
        from decimal import Decimal

        from workouts.models import Exercise, ExerciseLog

        hoje = date(2026, 9, 23)  # quarta
        segunda = date(2026, 9, 21)
        exercicio = Exercise.objects.create(
            name="Supino de teste", muscle_group="chest", padrao="pressao_de_peito",
            equipment="barbell", is_active=True,
        )
        ExerciseLog.objects.create(
            user=self.user, exercise=exercicio, date=segunda, set_number=1,
            weight_kg=Decimal("40"), reps=10,
        )
        mapa = self._mapa(hoje)
        self.assertEqual(mapa[segunda].estado, evolucao.FEITO)
        self.assertEqual(mapa[date(2026, 9, 22)].estado, evolucao.DESCANSO, "terça é livre")
        self.assertEqual(mapa[hoje].estado, evolucao.FALTOU, "quarta é combinada e vazia")

    def test_o_mapa_tem_exatamente_os_dias_da_janela(self):
        hoje = date(2026, 9, 23)
        dias = [d.data for d in self._mapa(hoje).values()]
        self.assertEqual(len(dias), 7)
        self.assertEqual(min(dias), hoje - timedelta(days=6))
        self.assertEqual(max(dias), hoje)


class ATendenciaDoPesoTests(TestCase):
    """O tile do peso precisa responder a 1, a 2 e a N pesagens — e as três
    respostas são diferentes. Com uma só não há tendência nenhuma, e inventar
    uma seta para cima ou para baixo seria afirmar direção a partir de um
    ponto."""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import WeightEntry

        cls.user = create_complete_user(email="tendencia@exemplo.com")
        # O fixture já nasce com UMA pesagem (o motor precisa dela para
        # calcular a meta). Estes testes contam pesagens, então a limpeza é o
        # que faz "uma pesagem" querer dizer uma.
        WeightEntry.objects.filter(user=cls.user).delete()

    def _pesar(self, dia, kg):
        from decimal import Decimal

        from accounts.models import WeightEntry

        WeightEntry.objects.update_or_create(
            user=self.user, date=dia, defaults={"weight_kg": Decimal(str(kg))}
        )

    def _tile(self, hoje):
        _nasceu_em(self.user, hoje - timedelta(days=29))
        return evolucao.tile_de_peso(
            self.user, evolucao.janela(self.user, "mes", hoje=hoje)
        )

    def test_sem_pesagem_o_tile_convida_e_nao_afirma_direcao(self):
        tile = self._tile(date(2026, 9, 23))
        self.assertIsNone(tile.variacao)
        self.assertEqual(tile.direcao, evolucao.SEM_DIRECAO)

    def test_uma_pesagem_mostra_o_valor_e_continua_sem_direcao(self):
        hoje = date(2026, 9, 23)
        self._pesar(hoje - timedelta(days=3), 72.5)
        tile = self._tile(hoje)
        self.assertEqual(tile.valor, "72,50")
        self.assertIsNone(tile.variacao)
        self.assertEqual(tile.direcao, evolucao.SEM_DIRECAO)

    def test_duas_pesagens_ja_dao_direcao(self):
        hoje = date(2026, 9, 23)
        self._pesar(hoje - timedelta(days=20), 74.0)
        self._pesar(hoje - timedelta(days=1), 73.5)
        tile = self._tile(hoje)
        self.assertEqual(tile.direcao, evolucao.CAINDO)
        self.assertEqual(tile.variacao, -0.5)

    def test_n_pesagens_comparam_a_primeira_com_a_ultima_do_periodo(self):
        hoje = date(2026, 9, 23)
        for n, kg in enumerate((75.0, 74.2, 73.8, 73.1)):
            self._pesar(hoje - timedelta(days=21 - n * 7), kg)
        tile = self._tile(hoje)
        self.assertEqual(tile.variacao, -1.9)
        self.assertEqual(tile.direcao, evolucao.CAINDO)
        self.assertEqual(len(tile.pontos), 4, "a linha desenha todas as pesagens")

    def test_a_media_movel_so_nasce_com_tres_pesagens(self):
        hoje = date(2026, 9, 23)
        self._pesar(hoje - timedelta(days=10), 75.0)
        self._pesar(hoje - timedelta(days=5), 74.0)
        self.assertEqual(self._tile(hoje).media_movel, (), "duas não fazem média")
        self._pesar(hoje - timedelta(days=1), 73.5)
        self.assertTrue(self._tile(hoje).media_movel, "três, sim")


class OPainelInteiroTests(TestCase):
    """`reunir()` monta a tela toda, e o custo dela não cresce com o período.

    É a propriedade que o orçamento de `plans/test_stress.py` protege: trocar
    "Semana" por "3 meses" multiplica os DIAS desenhados por treze, e não
    pode multiplicar as consultas por nada.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = create_complete_user(email="painel@exemplo.com")

    def _reunir(self, periodo):
        from plans import services

        _nasceu_em(self.user, date(2026, 9, 23) - timedelta(days=120))
        plano = services.get_active_plan(self.user)
        return evolucao.reunir(
            self.user, periodo, hoje=date(2026, 9, 23), plano=plano
        )

    def test_o_painel_traz_quatro_tiles_e_quatro_areas(self):
        painel = self._reunir("mes")
        self.assertEqual(len(painel["tiles"]), 4)
        self.assertEqual(
            [a.chave for a in painel["areas"]], ["dieta", "treino", "agua", "corrida"]
        )
        self.assertEqual([p["chave"] for p in painel["periodos"]], list(evolucao.PERIODOS))

    def test_o_mes_e_o_trimestre_custam_as_MESMAS_consultas(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as semana:
            self._reunir("semana")
        with CaptureQueriesContext(connection) as trimestre:
            self._reunir("trimestre")
        self.assertEqual(
            len(semana.captured_queries), len(trimestre.captured_queries),
            "o custo tem de ser do NÚMERO DE ÁREAS, nunca do tamanho da janela",
        )

    def test_as_barras_cobrem_exatamente_as_semanas_da_janela(self):
        painel = self._reunir("mes")
        semanas = evolucao.semanas_da_janela(painel["janela"])
        for area in painel["areas"]:
            with self.subTest(area=area.chave):
                self.assertEqual(len(area.barras), len(semanas))

    def test_o_mapa_de_cada_area_cobre_exatamente_os_dias_da_janela(self):
        painel = self._reunir("mes")
        dias = len(evolucao.dias_da_janela(painel["janela"]))
        for area in painel["areas"]:
            with self.subTest(area=area.chave):
                self.assertEqual(len(area.mapa), dias)
