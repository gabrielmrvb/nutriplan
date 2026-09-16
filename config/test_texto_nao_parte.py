# -*- coding: utf-8 -*-
"""Rótulo não parte dentro da palavra, número não parte nem é cortado.

Medido em produção em 16/09/2026 (avaliação, B23/B24/B25/B26/B33), a 390 px:

- "Experiên/cia" no resumo da etapa 3, "Dia/s", "Quinta-/feira", "Entrou/como"
  e o e-mail "exampl/e.com" no Perfil, "Na sua/ficha" e "1:20 / min" no
  detalhe do exercício, e "×1,4" numa linha com "5" na outra em "Entender
  minhas metas" — um fator de atividade que lê como número errado;
- "/140" saindo "/14C" nos macros da Home, com o zero cortado pela metade.

Causa dos primeiros: a regra global `overflow-wrap: anywhere` (que existe
para nome de alimento e de exercício não estourar a tela) dentro de
`.data-list > div { display: flex }` com `dt` e `dd` encolhíveis — o flex
espreme o rótulo abaixo da largura da palavra e o `anywhere` corta onde
couber. Causa do último: `overflow: hidden` no número com `letter-spacing`
negativo — a tinta da última cifra passa da caixa e é cortada.

A guarda é sobre a DECLARAÇÃO, pela mesma razão do teste da corrida em
`test_design_system`: o sintoma não rola a tela e `scrollWidth` não acusa. O
que se pode cobrar do CSS é o mecanismo — a linha quebra entre rótulo e valor
(`flex-wrap`), o rótulo não parte (`overflow-wrap: normal`) e o número não é
cortado (sem `overflow: hidden`). A medida visual fica com o QA de navegador,
que fez as capturas da avaliação e refaz as mesmas depois.
"""
import re

from django.test import SimpleTestCase

from config.test_design_system import CSS, sem_comentarios


def _regra(css, seletor):
    casou = re.search(r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", css)
    return casou.group(1) if casou else None


class RotuloDaListaDeDadosNaoParteTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_a_linha_da_lista_quebra_entre_rotulo_e_valor(self):
        corpo = _regra(self.css, ".data-list > div")
        self.assertIsNotNone(corpo, "a regra .data-list > div sumiu")
        self.assertIn("flex-wrap: wrap", corpo)

    def test_o_rotulo_nao_parte_dentro_da_palavra(self):
        corpo = _regra(self.css, ".data-list dt")
        self.assertIsNotNone(corpo, "a regra .data-list dt sumiu")
        self.assertIn("overflow-wrap: normal", corpo)
        # E mede o próprio conteúdo: é o `flex-basis: auto` que faz o valor
        # descer de linha em vez de o rótulo encolher.
        self.assertRegex(corpo, r"flex:\s*1 1 auto")

    def test_o_valor_continua_a_direita_e_pode_descer_de_linha(self):
        corpo = _regra(self.css, ".data-list dd")
        self.assertIsNotNone(corpo)
        self.assertIn("text-align: right", corpo)
        self.assertRegex(corpo, r"margin:\s*0 0 0 auto")

    def test_a_regra_global_de_quebra_continua_para_nome_comprido(self):
        """Controle: a saída NÃO é tirar o `anywhere` global — nome de alimento
        e de exercício precisam dele para não estourar a tela."""
        self.assertRegex(
            self.css, r"h1, h2, h3, p, li, dt, dd, span, strong, b, a, button, label \{\s*overflow-wrap: anywhere"
        )

