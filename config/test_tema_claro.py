# -*- coding: utf-8 -*-
"""O Ferro (escuro) é a base do NutriPlan, e o Papel (claro) é a preferência.

Três inversões na história do arquivo, e a razão de cada uma: o app nasceu
escuro-primeiro; em 12/09/2026 o `:root` virou claro (a identidade das
auditorias) com o escuro sob `prefers-color-scheme: dark`; em 16/09/2026 a
direção CORTE (`docs/briefs/design/DIRECAO-ESCOLHIDA.md`) decidiu o
contrário — luz baixa de academia como padrão, o claro DERIVADO para quem
prefere claro no sistema —, e o `:root` passou a ligar o Ferro
(`--bg: var(--ferro-bg)`), com o Papel sob `prefers-color-scheme: light`.

Por que isso precisa de teste próprio, e não só do contraste: os dois
regimes têm os mesmos nomes de token, então inverter os dois de volta por
acidente — um `git checkout` parcial, uma resolução de conflito — deixa o
CSS válido, o contraste passando nos dois, e o app claro para quem nunca
pediu. O nome do arquivo ficou (é o que o hook e os relatórios citam); o
que ele prende é QUEM É A BASE.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from config.tests import REGIME_FERRO, REGIME_PAPEL, _contraste, _tokens

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


def _bloco_root(css):
    inicio = css.index(":root {")
    fim = css.index("\n}\n", inicio)
    return css[inicio:fim]


class OFerroEABaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # SEM COMENTÁRIOS: o comentário que explica a inversão cita os dois
        # valores de `--bg` por extenso, e uma busca ingênua acharia o claro
        # no lugar errado. É a armadilha que o `CLAUDE.md` registra.
        cls.css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)
        cls.cru = CSS.read_text(encoding="utf-8")

    def test_o_root_liga_o_ferro(self):
        root = _bloco_root(self.css)
        self.assertIn("--bg: var(--ferro-bg);", root)
        self.assertIn("--brand: var(--ferro-brand);", root)
        self.assertIn("--folha: var(--ferro-folha);", root)
        self.assertIn("color-scheme: dark light;", root)
        # E o Ferro é o da direção: papel escuro, lima, osso.
        ferro = _tokens(self.cru, REGIME_FERRO)
        self.assertEqual(ferro["--bg"], "#10120e")
        self.assertEqual(ferro["--brand"], "#c7f24a")
        self.assertEqual(ferro["--text"], "#f6f3ea")

    def test_o_papel_mora_na_preferencia_clara_e_o_escuro_nao_e_mais_excecao(self):
        self.assertIn("@media (prefers-color-scheme: light)", self.css)
        self.assertNotIn("@media (prefers-color-scheme: dark)", self.css)
        claro = self.css.split("@media (prefers-color-scheme: light)", 1)[1]
        claro = claro[: claro.index("\n}\n")]
        self.assertIn("--bg: var(--papel-bg);", claro)
        self.assertIn("--brand: var(--papel-brand);", claro)
        self.assertIn("--folha:", claro)
        papel = _tokens(self.cru, REGIME_PAPEL)
        self.assertEqual(papel["--bg"], "#f6f3ea")
        self.assertEqual(papel["--brand"], "#3f5a00", "no claro a ação é OLIVA — a lima não é texto sobre osso")
        self.assertEqual(papel["--text"], "#14180a")

    def test_a_moldura_do_navegador_acompanha_a_base(self):
        """`theme-color` e manifesto pintam a barra de status e a tela de
        abertura ANTES da página. Divergir do fundo real produz uma emenda
        visível de meio segundo toda vez que o app abre — e já aconteceu.
        A trava lê o `--bg` de cada regime no CSS em vez de repetir o hex:
        assim uma troca de paleta não faz deste teste uma segunda cópia."""
        ferro = _tokens(self.cru, REGIME_FERRO)
        papel = _tokens(self.cru, REGIME_PAPEL)
        self.assertEqual(settings.PWA_THEME_COLOR, ferro["--bg"])
        self.assertEqual(settings.PWA_BACKGROUND_COLOR, ferro["--bg"])
        self.assertEqual(settings.PWA_LIGHT_COLOR, papel["--bg"])

    def test_a_folha_e_legivel_como_objeto_grafico_nos_dois_regimes(self):
        """3:1 contra a trilha vazia do anel (WCAG 1.4.11), medido nos dois."""
        for rotulo, escopo in (("escuro", REGIME_FERRO), ("claro", REGIME_PAPEL)):
            tokens = _tokens(self.cru, escopo)
            for fundo in ("--surface", "--surface-2", "--bg"):
                with self.subTest(regime=rotulo, fundo=fundo):
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
