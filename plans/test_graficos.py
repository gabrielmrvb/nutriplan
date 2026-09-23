# -*- coding: utf-8 -*-
"""A geometria dos gráficos — um sistema só, e ele cabe na caixa.

Três formas para a tela inteira (linha, colunas, mapa) em vez das três
gramáticas que existiam para a MESMA pergunta. O que estes testes prendem é
o que quebra em silêncio num gráfico: ponto fora do viewBox (some sem erro),
divisão por zero numa série constante, e a barra de valor zero que não
desenha nada e some da série.
"""
from datetime import date, timedelta

from django.test import SimpleTestCase

from plans import graficos


class ALinhaCabeNaCaixaTests(SimpleTestCase):
    def _pontos(self, valores):
        base = date(2026, 9, 1)
        return [(base + timedelta(days=n * 7), v) for n, v in enumerate(valores)]

    def test_todo_ponto_fica_dentro_do_viewbox(self):
        """Ponto fora do viewBox não dá erro: ele simplesmente não aparece."""
        linha = graficos.linha(self._pontos([74.8, 74.1, 73.9, 72.5, 72.6]))
        for ponto in linha.pontos:
            self.assertGreaterEqual(ponto.x, 0)
            self.assertLessEqual(ponto.x, graficos.LARGURA)
            self.assertGreaterEqual(ponto.y, 0)
            self.assertLessEqual(ponto.y, graficos.ALTURA)

    def test_serie_constante_nao_divide_por_zero_e_fica_no_meio(self):
        linha = graficos.linha(self._pontos([70.0, 70.0, 70.0]))
        # O meio da ÁREA DE DESENHO, e não do viewBox: as margens são
        # assimétricas (o eixo de baixo leva data e pede mais respiro).
        util = graficos.ALTURA - graficos.MARGEM_TOPO - graficos.MARGEM_BASE
        meio = graficos.MARGEM_TOPO + util / 2
        for ponto in linha.pontos:
            self.assertAlmostEqual(ponto.y, meio, delta=1)

    def test_um_ponto_so_e_marcado_como_unico_e_vai_para_o_centro(self):
        """Com uma pesagem não há linha; a tela diz o que falta em vez de
        desenhar um segmento de tamanho zero."""
        linha = graficos.linha(self._pontos([72.5]))
        self.assertTrue(linha.unico)
        self.assertEqual(len(linha.pontos), 1)
        self.assertAlmostEqual(linha.pontos[0].x, graficos.LARGURA / 2, delta=20)
        self.assertEqual(len(linha.eixo_x), 1, "um ponto, uma data no eixo")

    def test_o_caminho_comeca_com_M_e_tem_um_L_por_ponto_seguinte(self):
        linha = graficos.linha(self._pontos([74.0, 73.0, 72.0]))
        self.assertTrue(linha.caminho.startswith("M "))
        self.assertEqual(linha.caminho.count("L"), 2)

    def test_a_media_movel_vira_um_segundo_caminho(self):
        pontos = self._pontos([74.0, 73.0, 72.0])
        linha = graficos.linha(pontos, media=pontos)
        self.assertTrue(linha.caminho_media)
        self.assertEqual(len(linha.media), 3)

    def test_sem_ponto_nenhum_a_linha_e_vazia_e_nao_explode(self):
        linha = graficos.linha([])
        self.assertEqual(linha.caminho, "")
        self.assertEqual(linha.pontos, ())


class AsColunasTests(SimpleTestCase):
    def _itens(self, valores):
        return [("s%d" % n, v, str(v), n == len(valores) - 1)
                for n, v in enumerate(valores)]

    def test_a_barra_mais_alta_usa_a_altura_util_inteira(self):
        colunas = graficos.colunas(self._itens([2, 5, 9]))
        util = graficos.ALTURA - graficos.MARGEM_TOPO - graficos.MARGEM_BASE
        self.assertAlmostEqual(colunas.barras[-1].altura, util, delta=0.5)

    def test_barra_de_zero_vira_um_fio_e_nao_some(self):
        """Semana de valor zero ACONTECEU — ela é diferente de semana que não
        existiu, e é a janela que decide quais existem."""
        colunas = graficos.colunas(self._itens([0, 4]))
        self.assertGreater(colunas.barras[0].altura, 0)

    def test_toda_barra_fica_dentro_da_caixa(self):
        colunas = graficos.colunas(self._itens([1, 7, 3, 9, 2, 5]))
        for barra in colunas.barras:
            self.assertGreaterEqual(barra.x, 0)
            self.assertLessEqual(barra.x + barra.largura, graficos.LARGURA)
            self.assertGreaterEqual(barra.y, 0)
            self.assertLessEqual(barra.y + barra.altura, graficos.ALTURA)

    def test_a_ultima_semana_e_marcada_como_atual(self):
        colunas = graficos.colunas(self._itens([1, 2, 3]))
        self.assertTrue(colunas.barras[-1].atual)
        self.assertFalse(colunas.barras[0].atual)

    def test_serie_toda_zerada_nao_divide_por_zero(self):
        colunas = graficos.colunas(self._itens([0, 0, 0]))
        self.assertEqual(len(colunas.barras), 3)


class OMapaEmGradeTests(SimpleTestCase):
    def _dias(self, primeiro, quantos):
        from plans import evolucao

        return [
            evolucao.DiaDoMapa(data=primeiro + timedelta(days=n),
                               estado=evolucao.SEM_REGISTRO)
            for n in range(quantos)
        ]

    def test_uma_coluna_por_semana_e_sete_linhas_por_coluna(self):
        mapa = graficos.mapa(self._dias(date(2026, 8, 24), 21))  # 3 semanas cheias
        self.assertEqual(mapa.semanas, 3)
        for coluna in mapa.colunas:
            self.assertEqual(len(coluna), 7)

    def test_a_semana_parcial_do_cadastro_deixa_buracos_no_topo(self):
        """A conta nasceu numa quarta: segunda e terça da primeira coluna são
        `None`, e é isso que faz o mapa dizer 'aqui começou' sem texto."""
        mapa = graficos.mapa(self._dias(date(2026, 9, 23), 3))  # quarta
        self.assertEqual(mapa.semanas, 1)
        self.assertIsNone(mapa.colunas[0][0], "segunda não existiu")
        self.assertIsNone(mapa.colunas[0][1], "terça não existiu")
        self.assertIsNotNone(mapa.colunas[0][2], "quarta existiu")
        self.assertEqual(mapa.colunas[0][2].y, 2 * (mapa.lado + mapa.vao), "a quarta é a terceira linha")

    def test_a_caixa_do_mapa_acompanha_o_numero_de_semanas(self):
        mapa = graficos.mapa(self._dias(date(2026, 8, 24), 28))
        self.assertEqual(mapa.semanas, 4)
        self.assertEqual(mapa.largura, 4 * (mapa.lado + mapa.vao) - mapa.vao)
        self.assertEqual(mapa.altura, 7 * (mapa.lado + mapa.vao) - mapa.vao)

    def test_sem_dia_nenhum_o_mapa_e_vazio(self):
        self.assertEqual(graficos.mapa([]).colunas, ())
