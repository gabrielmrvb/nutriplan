# -*- coding: utf-8 -*-
"""A curva de peso diz DE QUANTO A QUANTO e DE QUANDO A QUANDO.

A auditoria de UX de 22/09/2026 leu o gráfico do Progresso como "uma linha
reta sem eixo", e a leitura estava certa sobre o que se vê: o SVG desenhava a
polilinha e nada mais. A escala é a do próprio período — decisão antiga e
correta, porque ancorar em zero acha o peso humano numa reta horizontal — e é
exatamente por isso que ela precisa ser DITA: sem os dois extremos em quilos,
a mesma inclinação serve para 200 g e para 4 kg de variação.

O que este arquivo prende:

- o eixo existe e é o que está DESENHADO (o piso e o teto da caixa), e não o
  menor e o maior peso: com variação abaixo do piso de 0,4 kg os dois deixam
  de coincidir, e imprimir o menor/maior ali afirmaria uma amplitude que a
  linha não tem;
- o período existe, e as datas acompanham os pontos — um `zip` sobre as
  semanas cruas desalinharia a primeira data assim que uma semana sem média
  fosse descartada da curva;
- os pontos saem com PONTO decimal. O app é pt-BR com `USE_L10N`, e
  `{{ marca.x }}` de um float sai "42,9": atributo inválido em SVG, que o
  navegador descarta em silêncio. Medido em 22/09/2026 — os oito pontos
  empilhados na origem, todos no mesmo pixel.
"""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from plans.views import _curva_de_peso


def semanas(*medias, inicio=date(2026, 8, 3)):
    """Semanas como `weight_trend.Semana`: o que a curva recebe de verdade."""
    return [
        SimpleNamespace(
            inicio=inicio + timedelta(weeks=i),
            media=None if m is None else Decimal(str(m)),
            registros=3,
            delta=None,
        )
        for i, m in enumerate(medias)
    ]


class OEixoDaCurvaTests(SimpleTestCase):
    def test_o_eixo_traz_o_piso_e_o_teto_em_quilos(self):
        curva = _curva_de_peso(semanas(76.2, 77.1, 78.0))

        self.assertEqual(curva["piso"], 76.2)
        self.assertEqual(curva["teto"], 78.0)

    def test_com_variacao_minima_o_eixo_diz_a_CAIXA_e_nao_os_pesos(self):
        """O piso de 0,4 kg impede que ruído de balança vire montanha — e o
        eixo tem de dizer o que foi DESENHADO, senão ele promete uma amplitude
        que a linha não tem. Com 100 g de variação, a caixa continua 0,4."""
        curva = _curva_de_peso(semanas(80.0, 80.1))

        self.assertEqual(curva["piso"], 80.0)
        self.assertEqual(curva["teto"], 80.4)

    def test_o_periodo_sai_das_pontas(self):
        curva = _curva_de_peso(semanas(76.2, 77.1, 78.0))

        self.assertEqual(curva["de"], date(2026, 8, 3))
        self.assertEqual(curva["ate"], date(2026, 8, 17))

    def test_a_semana_sem_media_nao_desalinha_as_datas(self):
        """A data acompanha o PONTO, e não a posição na lista de semanas.

        A semana sem pesagem sai da curva (não há o que desenhar), e a lista
        de datas tem de sair junto: `[s.inicio for s in semanas]` continuaria
        com uma data a mais e dataria as pontas com a semana errada.

        O caso que separa as duas implementações é a semana sem média NO FIM
        — sabotagem medida em 22/09/2026: com o buraco no MEIO as duas dão o
        mesmo "de" e "até", e o teste passava verde com a lista errada.
        """
        curva = _curva_de_peso(semanas(76.2, 77.1, None))

        self.assertEqual(len(curva["marcas"]), 2)
        self.assertEqual(curva["de"], date(2026, 8, 3))
        self.assertEqual(curva["ate"], date(2026, 8, 10), "datou a ponta com a semana vazia")

        # E o buraco no MEIO continua coberto, pelo número de pontos.
        do_meio = _curva_de_peso(semanas(76.2, None, 78.0))
        self.assertEqual(len(do_meio["marcas"]), 2)
        self.assertEqual(do_meio["ate"], date(2026, 8, 17))

    def test_um_ponto_por_semana_medida(self):
        curva = _curva_de_peso(semanas(76.2, 77.1, 78.0, 78.4))

        self.assertEqual(len(curva["marcas"]), 4)

    def test_as_coordenadas_usam_PONTO_decimal(self):
        """O defeito medido: `USE_L10N` renderiza float com vírgula, e um
        `cx="42,9"` é descartado pelo navegador — os oito pontos empilhados
        na origem. Por isso a coordenada nasce STRING, como `pontos` já
        nascia."""
        curva = _curva_de_peso(semanas(76.2, 77.1, 78.0))

        for marca in curva["marcas"]:
            for eixo in ("x", "y"):
                with self.subTest(eixo=eixo, valor=marca[eixo]):
                    self.assertIsInstance(marca[eixo], str)
                    self.assertNotIn(",", marca[eixo])
                    float(marca[eixo])  # levanta se não for número

    def test_menos_de_dois_pontos_nao_e_curva(self):
        """CONTROLE POSITIVO dos de cima: sem dois pontos não há eixo nenhum
        para conferir, e desenhar uma linha de um ponto afirmaria tendência
        onde não há."""
        self.assertIsNone(_curva_de_peso(semanas(80.0)))
        self.assertIsNone(_curva_de_peso([]))
