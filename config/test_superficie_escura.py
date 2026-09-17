# -*- coding: utf-8 -*-
"""No tema escuro, o que é botão tem cara de botão e o que é trilha aparece.

Revisão visual da avaliação de 16/09/2026 (U28), medida no pixel:
`--surface-2` escuro (#121a18) sobre `--surface` (#0d1413) dava **1,05:1**.
Tudo o que se pintava com essa dupla sumia: "Pulei" e "Comi outra coisa"
(`.btn--quiet`, sem borda) viravam texto solto sem cara de botão; o anel de
calorias a 0 % e o de treino não tinham trilha (1,07 e 1,1:1); as barras dos
sete dias da Hidratação ficavam invisíveis. O contraste de TEXTO passava — o
que faltava era o de componente (WCAG 1.4.11).

Três correções, cada uma com a sua guarda aqui:

1. `--surface-2` e `--surface-3` do escuro sobem — e, a cada paleta, sobem
   de novo pela mesma régua: no Ferro da direção C, sobre `--surface`
   #161d1a o #1d2622 dava 1,10:1 (ficou #243029); na CORTE (16/09/2026),
   sobre #1a1d17 o #22261e da direção dava 1,11 e ficou #292d25 (1,22),
   com a terceira em #33382d — mantendo a ordem das camadas e o texto
   legível sobre elas (`config.tests.ContrastTests` cobra 4,5:1 e a
   margem de 5,0 para `--text-mute`);
2. `.btn--quiet` ganha borda, como `.btn--ghost` já tem: a affordance do botão
   não pode depender de um preenchimento que o tema escuro apaga;
3. trilha de progresso — o resto do anel e o fundo das barras — usa
   `--fio` (o hairline; chamava-se `--border` até a direção C), que é
   translúcido e desenha sobre qualquer superfície, em vez de `--surface-2`,
   que é uma superfície e some sobre a outra.
"""
import re

from django.test import SimpleTestCase

from config.tests import REGIME_FERRO, _contraste, _luminancia, _tokens
from config.test_design_system import CSS, sem_comentarios


def _regra(css, seletor):
    casou = re.search(r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", css)
    return casou.group(1) if casou else None


class SuperficiesDoEscuroTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")
        # CORTE (16/09/2026): o escuro é a base — o próprio `:root`.
        self.escuro = _tokens(self.css, REGIME_FERRO)

    def test_a_segunda_superficie_se_distingue_da_primeira(self):
        razao = _contraste(self.escuro["--surface-2"], self.escuro["--surface"])
        self.assertGreaterEqual(razao, 1.2, "surface-2 sobre surface dá %.2f:1 — some" % razao)

    def test_as_camadas_continuam_em_ordem(self):
        """bg < surface < surface-2 < surface-3 em luminância: cada camada
        acima é um pouco mais clara, como no claro."""
        nomes = ("--bg", "--surface", "--surface-2", "--surface-3")
        lums = [_luminancia(self.escuro[n]) for n in nomes]
        self.assertEqual(lums, sorted(lums), dict(zip(nomes, lums)))


class BotaoQuietoTemCaraDeBotaoTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_o_quiet_tem_borda_como_o_ghost(self):
        corpo = _regra(self.css, ".btn--quiet")
        self.assertIsNotNone(corpo, "a regra .btn--quiet sumiu")
        self.assertRegex(corpo, r"border:\s*1px solid var\(--fio-forte\)")


class TrilhaDeProgressoAparecemTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_o_resto_do_anel_e_desenhado_com_a_borda(self):
        corpo = _regra(self.css, ".ring")
        self.assertIsNotNone(corpo)
        self.assertIn("var(--fio) 0)", corpo)
        self.assertNotIn("var(--surface-2) 0)", corpo)

    def test_as_barras_de_semana_e_de_historico_usam_a_borda(self):
        for seletor in (".semana__barra", ".history-row__bar"):
            corpo = _regra(self.css, seletor)
            self.assertIsNotNone(corpo, seletor)
            self.assertIn("background: var(--fio)", corpo, seletor)
