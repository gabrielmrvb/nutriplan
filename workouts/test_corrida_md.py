# -*- coding: utf-8 -*-
"""Cada número de `docs/briefs/corrida/CORRIDA.md` tem um teste aqui — como
`workouts/test_treino_md.py` cobra o `TREINO.md`.

Duas metades. A primeira prova que `workouts/doutrina_corrida.py` devolve o
que está escrito no documento (o leitor não inventa) — com um SEGUNDO parser,
de regex, que não é o `workouts/doutrina_md.py` que o motor usa, para o teste
não confiar no que ele testa. A segunda prova que o modelo e a tela obedecem:
`PlanoDeCorrida.semana_atual`, `sessoes_feitas`, e o cartão da semana em
`/treino/corridas/`.
"""
import re
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import doutrina_corrida
from workouts.corrida import FATOR_KCAL_POR_KG_KM
from workouts.models import Corrida, PlanoDeCorrida
from workouts.tests import create_user

RAIZ = Path(__file__).resolve().parent.parent
DOC = RAIZ / "docs" / "briefs" / "corrida" / "CORRIDA.md"


def _linhas_da_tabela(texto, cabecalho):
    """As linhas de uma tabela do documento, por um segundo parser — regex e
    não `workouts/doutrina_md.py` — para o teste não confiar no que testa."""
    bloco = re.search(re.escape(cabecalho) + r"\n\|[-|: ]+\|\n((?:\|.*\|\n?)+)", texto)
    assert bloco, "tabela não encontrada: %s" % cabecalho
    return [
        [c.strip() for c in linha.strip().strip("|").split("|")]
        for linha in bloco.group(1).strip().splitlines()
    ]


class OLeitorDevolveOQueEstaEscritoTests(SimpleTestCase):
    def setUp(self):
        self.texto = DOC.read_text(encoding="utf-8")

    def test_tabela_de_planos_tem_quatro_combinacoes(self):
        linhas = _linhas_da_tabela(self.texto, "| plano | nivel | semanas | sessoes_por_semana |")
        self.assertEqual(len(linhas), 4)
        planos = doutrina_corrida.planos()
        for plano, nivel, semanas, sessoes_por_semana in linhas:
            with self.subTest(plano=plano, nivel=nivel):
                self.assertEqual(
                    planos[(plano, nivel)],
                    {"semanas": int(semanas), "sessoes_por_semana": int(sessoes_por_semana)},
                )
        self.assertEqual({l[0] for l in linhas}, {"5k", "10k"})
        self.assertEqual({l[1] for l in linhas}, {"iniciante", "intermediario"})

    def test_96_sessoes_com_descricao_e_minutos_positivos(self):
        """4 planos × 8 semanas × 3 sessões — e cada linha do documento bate
        com o que `doutrina_corrida.sessoes` devolve para aquela semana."""
        linhas = _linhas_da_tabela(self.texto, "| plano | nivel | semana | sessao | descricao | minutos |")
        self.assertEqual(len(linhas), 96)
        vistas = set()
        for plano, nivel, semana, sessao, descricao, minutos in linhas:
            chave = (plano, nivel, int(semana), int(sessao))
            vistas.add(chave)
            with self.subTest(chave=chave):
                self.assertTrue(descricao.strip())
                self.assertGreater(int(minutos), 0)
                sessoes_da_semana = doutrina_corrida.sessoes(plano, nivel, int(semana))
                encontrada = next(s for s in sessoes_da_semana if s["sessao"] == int(sessao))
                self.assertEqual(encontrada["descricao"], descricao)
                self.assertEqual(encontrada["minutos"], int(minutos))
        # Nenhuma chave repetida: as 96 linhas cobrem exatamente as 96 células
        # (4 planos x 8 semanas x 3 sessões), sem duplicata nem buraco.
        self.assertEqual(len(vistas), 96)

    def test_fator_kcal_bate_com_o_motor(self):
        """`workouts/corrida.py::FATOR_KCAL_POR_KG_KM` e o documento não podem
        divergir em silêncio — é a mesma conta em dois lugares."""
        fator = doutrina_corrida.fator_kcal()
        self.assertIsInstance(fator, Decimal)
        self.assertEqual(fator, FATOR_KCAL_POR_KG_KM)
        linhas = _linhas_da_tabela(self.texto, "| medida | valor |")
        gasto = {medida: valor for medida, valor in linhas}
        self.assertEqual(Decimal(gasto["fator_kcal_por_kg_km"].replace(",", ".")), fator)

    def test_o_documento_cita_couch_to_5k_e_higdon(self):
        self.assertIn("Couch to 5K", self.texto)
        self.assertIn("Higdon", self.texto)


class QuandoUmaLinhaFaltaTests(SimpleTestCase):
    """`carregar()` valida na leitura, como `workouts/doutrina.py::carregar`
    valida o TREINO.md: uma sessão faltando não pode virar uma semana
    incompleta descoberta por quem estiver correndo — o boot (ou o primeiro
    acesso à tela) reprova com `ValueError`."""

    def test_uma_sessao_faltando_derruba_o_carregar_com_valueerror(self):
        texto = DOC.read_text(encoding="utf-8")
        linha_removida = "| 5k | iniciante | 1 | 1 | 8 × (1 min corrida + 1,5 min caminhada) | 25 |\n"
        self.assertIn(linha_removida, texto, "a linha esperada mudou — atualize a sabotagem")
        texto_incompleto = texto.replace(linha_removida, "", 1)
        self.assertNotIn(linha_removida, texto_incompleto)

        original = doutrina_corrida.DOCUMENTO
        doutrina_corrida.carregar.cache_clear()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp = Path(tmp_dir) / "CORRIDA.md"
                tmp.write_text(texto_incompleto, encoding="utf-8")
                doutrina_corrida.DOCUMENTO = tmp
                with self.assertRaises(ValueError):
                    doutrina_corrida.carregar()
        finally:
            doutrina_corrida.DOCUMENTO = original
            doutrina_corrida.carregar.cache_clear()

        # O documento de verdade volta a carregar normalmente depois.
        self.assertEqual(len(doutrina_corrida.planos()), 4)


class OSemanaAtualTests(SimpleTestCase):
    """`semana_atual`: 1 a 8, `None` depois — não bate no banco, então
    `SimpleTestCase` basta."""

    def _plano(self, comecou_em):
        return PlanoDeCorrida(plano="5k", nivel="iniciante", comecou_em=comecou_em, ativo=True)

    def test_o_dia_em_que_comecou_e_semana_1(self):
        inicio = date(2026, 1, 5)
        plano = self._plano(inicio)
        self.assertEqual(plano.semana_atual(inicio), 1)

    def test_sete_dias_depois_e_semana_2(self):
        inicio = date(2026, 1, 5)
        plano = self._plano(inicio)
        self.assertEqual(plano.semana_atual(inicio + timedelta(days=7)), 2)

    def test_quarenta_e_nove_dias_ainda_e_a_oitava_semana(self):
        inicio = date(2026, 1, 5)
        plano = self._plano(inicio)
        self.assertEqual(plano.semana_atual(inicio + timedelta(days=49)), 8)

    def test_cinquenta_e_seis_dias_ja_concluiu(self):
        """56 dias = a 9ª semana de calendário: o plano só tem 8."""
        inicio = date(2026, 1, 5)
        plano = self._plano(inicio)
        self.assertIsNone(plano.semana_atual(inicio + timedelta(days=56)))


class OSessoesFeitasTests(TestCase):
    """`sessoes_feitas` conta as corridas (GPS ou à mão) entre o início da
    semana atual e hoje — não filtra por origem nem por distância."""

    def setUp(self):
        self.pessoa = create_user(email="plano-sessoes@exemplo.com")

    def _corrida_em(self, dia):
        momento = timezone.make_aware(datetime.combine(dia, time(12, 0)))
        Corrida.objects.create(
            user=self.pessoa,
            op_id="corrida-%s" % dia.isoformat(),
            origem=Corrida.Origem.MANUAL,
            comecou_em=momento,
            terminou_em=momento + timedelta(minutes=20),
            distancia_m=3000,
            duracao_s=1200,
        )

    def test_conta_so_as_corridas_da_semana_atual(self):
        hoje = timezone.localdate()
        inicio_do_plano = hoje - timedelta(days=2)
        plano = PlanoDeCorrida.objects.create(
            user=self.pessoa, plano="5k", nivel="iniciante", comecou_em=inicio_do_plano, ativo=True,
        )
        self._corrida_em(inicio_do_plano)  # dentro da semana atual
        self._corrida_em(hoje)  # também dentro
        self._corrida_em(inicio_do_plano - timedelta(days=5))  # ANTES do plano começar
        self.assertEqual(plano.sessoes_feitas(hoje), 2)

    def test_sem_plano_em_andamento_e_zero(self):
        """Depois da 8ª semana `semana_atual` é `None`, e não há "semana
        atual" para contar — `sessoes_feitas` devolve 0 em vez de estourar."""
        hoje = timezone.localdate()
        plano = PlanoDeCorrida.objects.create(
            user=self.pessoa, plano="5k", nivel="iniciante",
            comecou_em=hoje - timedelta(days=60), ativo=True,
        )
        self._corrida_em(hoje)
        self.assertEqual(plano.sessoes_feitas(hoje), 0)


class OCartaoDoPlanoNaTelaTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="plano-tela@exemplo.com")
        self.client.force_login(self.pessoa)

    def test_mostra_semana_1_de_8_e_as_tres_sessoes(self):
        PlanoDeCorrida.objects.create(
            user=self.pessoa, plano="5k", nivel="iniciante",
            comecou_em=timezone.localdate(), ativo=True,
        )
        html = self.client.get(reverse("workouts:corridas")).content.decode()
        self.assertIn("Semana 1 de 8", html)
        self.assertIn("8 × (1 min corrida + 1,5 min caminhada)", html)
        # As três sessões da semana viram três `<li class="corrida-plano__sessao...">`.
        self.assertEqual(html.count('class="corrida-plano__sessao'), 3)

    def test_sem_plano_convida_a_escolher(self):
        html = self.client.get(reverse("workouts:corridas")).content.decode()
        self.assertIn("Quer um plano?", html)
        self.assertIn(reverse("workouts:corrida_plano"), html)

    def test_a_pagina_do_plano_lista_as_quatro_opcoes(self):
        html = self.client.get(reverse("workouts:corrida_plano")).content.decode()
        for rotulo in ("5K iniciante", "5K intermediário", "10K iniciante", "10K intermediário"):
            self.assertIn(rotulo, html)


class EscolherTrocarEEncerrarOPlanoTests(TestCase):
    def setUp(self):
        self.pessoa = create_user(email="plano-escolha@exemplo.com")
        self.client.force_login(self.pessoa)

    def test_escolher_um_plano_cria_um_ativo(self):
        r = self.client.post(reverse("workouts:corrida_plano"), {"plano": "5k", "nivel": "iniciante"})
        self.assertEqual(r.status_code, 302)
        plano = PlanoDeCorrida.objects.get(user=self.pessoa, ativo=True)
        self.assertEqual((plano.plano, plano.nivel, plano.comecou_em), ("5k", "iniciante", timezone.localdate()))

    def test_escolher_outro_plano_desativa_o_anterior(self):
        anterior = PlanoDeCorrida.objects.create(
            user=self.pessoa, plano="5k", nivel="iniciante",
            comecou_em=timezone.localdate() - timedelta(days=10), ativo=True,
        )
        r = self.client.post(reverse("workouts:corrida_plano"), {"plano": "10k", "nivel": "intermediario"})
        self.assertEqual(r.status_code, 302)
        anterior.refresh_from_db()
        self.assertFalse(anterior.ativo)
        ativos = PlanoDeCorrida.objects.filter(user=self.pessoa, ativo=True)
        self.assertEqual(ativos.count(), 1)
        self.assertEqual((ativos.first().plano, ativos.first().nivel), ("10k", "intermediario"))

    def test_encerrar_desativa_sem_criar_outro(self):
        plano = PlanoDeCorrida.objects.create(
            user=self.pessoa, plano="5k", nivel="iniciante", comecou_em=timezone.localdate(), ativo=True,
        )
        r = self.client.post(reverse("workouts:corrida_plano"), {"encerrar": "1"})
        self.assertEqual(r.status_code, 302)
        plano.refresh_from_db()
        self.assertFalse(plano.ativo)
        self.assertEqual(PlanoDeCorrida.objects.filter(user=self.pessoa).count(), 1)

    def test_plano_invalido_nao_cria_nada(self):
        r = self.client.post(reverse("workouts:corrida_plano"), {"plano": "42k", "nivel": "iniciante"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(PlanoDeCorrida.objects.filter(user=self.pessoa).count(), 0)
