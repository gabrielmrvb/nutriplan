# -*- coding: utf-8 -*-
"""O tema claro é o padrão do NutriPlan, e o escuro é a preferência.

O app nasceu escuro-primeiro: o `:root` trazia grafite e verde vivo, e o claro
era exceção sob `@media (prefers-color-scheme: light)`. A identidade decidida
nas auditorias é a clara — fundo `#f4f6f5`, verde `#0c6b40`, folha `#43A11B`
—, e ela já EXISTIA como bloco de exceção com exatamente esses valores. O que
este arquivo prende é quem é a base: um `:root` claro, com o escuro embaixo de
`prefers-color-scheme: dark`.

Por que isso precisa de teste próprio, e não só do contraste: os dois blocos
têm os mesmos nomes de token, então inverter os dois de volta por acidente —
um `git checkout` parcial, uma resolução de conflito — deixa o CSS válido, o
contraste passando nos dois temas, e o app escuro para quem nunca pediu.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


def _bloco_root(css):
    inicio = css.index(":root {")
    fim = css.index("\n}\n", inicio)
    return css[inicio:fim]


class OClaroEOPadraoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # SEM COMENTÁRIOS: o comentário que explica a inversão cita os dois
        # valores de `--bg` por extenso, e uma busca ingênua acharia o escuro
        # no lugar errado. É a armadilha que o `CLAUDE.md` registra.
        cls.css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)

    def test_o_root_declara_a_paleta_clara(self):
        root = _bloco_root(self.css)
        self.assertIn("--bg: #f5f3ee;", root)
        self.assertIn("--brand: #0c6b40;", root)
        self.assertIn("--folha: #3f9718;", root.lower())
        self.assertIn("color-scheme: light dark;", root)

    def test_o_escuro_mora_na_preferencia_e_o_claro_nao_e_mais_excecao(self):
        self.assertIn("@media (prefers-color-scheme: dark)", self.css)
        escuro = self.css.split("@media (prefers-color-scheme: dark)", 1)[1]
        escuro = escuro[: escuro.index("\n}\n")]
        # MESA & FERRO (15/09/2026): o bloco escuro não carrega mais hex — ele
        # liga `var(--ferro-*)`, e o valor mora uma vez no `:root`. `_tokens`
        # resolve o `var()` para continuar provando a IDENTIDADE, e não só a
        # indireção.
        self.assertIn("--bg: var(--ferro-bg);", escuro)
        self.assertIn("--brand: var(--ferro-brand);", escuro)
        self.assertIn("--folha:", escuro)
        self.assertNotIn("@media (prefers-color-scheme: light)", self.css)

        from config.tests import _tokens
        tokens = _tokens(
            CSS.read_text(encoding="utf-8"),
            "prefers-color-scheme: dark) {" + chr(10) + "  :root {",
        )
        self.assertEqual(tokens["--bg"], "#0e1412")
        self.assertEqual(tokens["--brand"], "#22c98a")

    def test_a_moldura_do_navegador_acompanha_a_base(self):
        """`theme-color` e manifesto pintam a barra de status e a tela de
        abertura ANTES da página. Divergir do fundo real produz uma emenda
        visível de meio segundo toda vez que o app abre — e já aconteceu.
        A trava lê o `--bg` de cada tema no CSS em vez de repetir o hex:
        assim a Mesa & Ferro (15/09/2026) troca a paleta sem que este teste
        vire uma segunda cópia dela."""
        from config.tests import _tokens
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        claro = _tokens(css, ":root {")
        escuro = _tokens(css, "prefers-color-scheme: dark) {" + chr(10) + "  :root {")
        self.assertEqual(settings.PWA_THEME_COLOR, claro["--bg"])
        self.assertEqual(settings.PWA_BACKGROUND_COLOR, claro["--bg"])
        self.assertEqual(settings.PWA_DARK_COLOR, escuro["--bg"])

    def test_a_folha_e_legivel_como_objeto_grafico_nos_dois_temas(self):
        """3:1 contra a trilha vazia do anel (WCAG 1.4.11), medido — e não o
        #43a11b da spec, que dá 2,93:1 no claro. "Próximo de" foi levado a
        sério: o valor escolhido é o vizinho mais próximo que passa."""
        from config.tests import _contraste, _tokens

        claro = _tokens(self.css, ":root {")
        escuro = _tokens(self.css, "prefers-color-scheme: dark) {" + chr(10) + "  :root {")
        for rotulo, tokens in (("claro", claro), ("escuro", escuro)):
            for fundo in ("--surface", "--surface-2", "--bg"):
                with self.subTest(tema=rotulo, fundo=fundo):
                    self.assertGreaterEqual(
                        _contraste(tokens["--folha"], tokens[fundo]), 3.0,
                        "%s: --folha sobre %s" % (rotulo, fundo),
                    )

    def test_a_folha_tem_papel_e_nao_e_o_verde_de_acao(self):
        """`--folha` é o verde do que FOI FEITO; `--brand` é o do que SE FAZ.

        Um token que só existe no `:root` é decoração. Ele precisa aparecer
        em regra de estado concluído — e NÃO no botão principal, senão os
        dois verdes viram um só e a tela perde a distinção que justificou o
        segundo.
        """
        fora_do_root = self.css[self.css.index("\n}\n", self.css.index(":root {")):]
        usos = re.findall(r"^[^\n{]*\{[^}]*var\(--folha\)", fora_do_root, re.M)
        self.assertGreaterEqual(len(usos), 4, "a folha só existe declarada")
        for regra in usos:
            self.assertNotIn(".btn--primary", regra.split("{", 1)[0])
