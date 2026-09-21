# -*- coding: utf-8 -*-
"""O andaime da NERVURA (17/09/2026): traço, nervura, CTA inclinado, ponta.

Quatro tokens que nasceram com o consumidor no mesmo commit, e as regras
que a direção impõe aos componentes: o botão primário é inclinado por um
pseudo-elemento (o botão em si continua retângulo — área de toque e anel
de foco inteiros), contorno e quieto pintam a mesma borda de `--traco`, o
chip é caixa de contorno em caixa alta, a aba ativa não enche, a barra de
progresso termina na ponta de folha, e a nervura é decoração atrás do
texto do prato e acima do título — nunca o único sinal de estado.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.test_design_system import CSS, sem_comentarios


def _regra(css, seletor, contendo=None):
    """O corpo da regra `seletor {…}`; com `contendo`, a primeira que tem
    aquele texto (um seletor pode ter mais de uma regra no arquivo)."""
    for casou in re.finditer(r"(?:^|\n)" + re.escape(seletor) + r"\s*\{([^}]*)\}", css):
        if contendo is None or contendo in casou.group(1):
            return casou.group(1)
    return None


class OsTokensDoAndaimeTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))
        self.raiz = self.css.split(":root {", 1)[1].split("\n}", 1)[0]

    def test_os_quatro_tokens_existem_com_os_valores_do_contrato(self):
        for token, valor in (("--traco", "2px"), ("--nervura", "-14deg"),
                             ("--inclinado", "polygon(0 0, 100% 0, 100% 74%, 0 100%)"),
                             ("--ponta", "polygon(0 100%, 100% 0, 100% 100%)")):
            with self.subTest(token=token):
                achado = re.search(r"^\s*%s:\s*([^;]+);" % re.escape(token), self.raiz, re.M)
                self.assertIsNotNone(achado, f"{token} sumiu do :root")
                self.assertEqual(achado.group(1).strip(), valor)

    def test_cada_token_tem_consumidor(self):
        fora = self.css.split("\n}", 1)[1]
        for token, minimo in (("--traco", 5), ("--nervura", 1), ("--inclinado", 1), ("--ponta", 1)):
            with self.subTest(token=token):
                self.assertGreaterEqual(fora.count("var(%s)" % token), minimo, f"{token} sem consumidor")


class OBotaoPrimarioEInclinadoTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_a_inclinacao_mora_no_pseudo_elemento_e_nao_no_botao(self):
        """`clip-path` no botão cortaria o anel de foco e a área de toque; no
        `::before` de fundo, o retângulo de 52 px continua inteiro."""
        fundo = _regra(self.css, ".btn--primary::before")
        self.assertIsNotNone(fundo, "o fundo inclinado sumiu")
        self.assertIn("clip-path: var(--inclinado)", fundo)
        self.assertIn("background: var(--brand)", fundo)
        self.assertIn("z-index: var(--camada-fundo)", fundo)
        botao = _regra(self.css, ".btn--primary")
        self.assertIsNotNone(botao)
        self.assertNotIn("clip-path", botao)
        self.assertIn("isolation: isolate", botao)
        self.assertIn("background: transparent", botao)

    def test_o_primario_fala_em_caixa_alta_condensada_e_o_pequeno_nao(self):
        botao = _regra(self.css, ".btn--primary")
        self.assertIn("var(--font-display)", botao)
        self.assertIn("text-transform: uppercase", botao)
        self.assertIn("font-size: var(--texto-xl)", botao, "a display nunca abaixo de 20 px")
        pequeno = _regra(self.css, ".btn--primary.btn--sm")
        self.assertIsNotNone(pequeno, "o primário pequeno (44 px) precisa voltar ao texto")
        self.assertIn("var(--font)", pequeno)
        self.assertIn("var(--texto-md)", pequeno, "e sem valor cru — a catraca")

    def test_o_halo_do_primario_fica(self):
        """Decisão do dono (16/09): o halo de hover/foco é sinal de estado e
        fica — mesmo com o preenchimento inclinado, o anel traça o retângulo
        inteiro, que é a área de toque."""
        regra = re.search(r"\.btn--primary:hover,\s*\.btn--primary:active,\s*\.btn--primary:focus-visible\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(regra)
        self.assertIn("var(--halo)", regra.group(1))

    def test_contorno_quieto_e_campo_pintam_o_traco(self):
        for sel in (".btn--ghost", ".btn--quiet", ".field-input", ".chip"):
            with self.subTest(seletor=sel):
                corpo = _regra(self.css, sel, contendo="border:")
                self.assertIsNotNone(corpo, sel)
                self.assertRegex(corpo, r"border:\s*var\(--traco\) solid var\(--fio-forte\)")
        base = _regra(self.css, ".btn")
        self.assertIn("border: var(--traco) solid transparent", base, "os três botões têm a mesma altura empilhados")


class OBotaoNaoParteAPalavraTests(SimpleTestCase):
    """Auditoria em produção de 20/09/2026, painel do treino a 1280 px: o
    primário "COMPARTILHAR O QUE JÁ FIZ" saía "COMPARTILHA / R O QUE JÁ FIZ"
    — a regra global `overflow-wrap: anywhere` (para nome de alimento e de
    exercício não estourar a tela) vale para `button`, e no grid de duas
    colunas de `.resumo__acoes` a palavra em display a 20 px não cabia. Um
    botão nunca parte uma palavra: o rótulo quebra entre palavras, e o
    primário daquele grid ocupa a linha inteira, como já ocupa a 390."""

    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_o_botao_quebra_entre_palavras_e_nunca_dentro_delas(self):
        btn = _regra(self.css, ".btn", contendo="inline-flex")
        self.assertIsNotNone(btn)
        self.assertIn("overflow-wrap: normal", btn)

    def test_o_primario_do_resumo_ocupa_a_linha_inteira_do_grid(self):
        regra = _regra(self.css, ".resumo__acoes .btn--primary")
        self.assertIsNotNone(regra, ".resumo__acoes .btn--primary precisa de regra própria")
        self.assertIn("grid-column: 1 / -1", regra)


class AAbaAPontaEANervuraTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))

    def test_a_aba_ativa_nao_enche(self):
        corpo = _regra(self.css, ".tabbar__item.is-active")
        self.assertIsNotNone(corpo)
        self.assertIn("color: var(--brand)", corpo)
        self.assertIn("background: transparent", corpo)
        self.assertIn("var(--traco) 0 var(--brand)", corpo, "a régua em cima é o que marca a aba")

    def test_a_barra_termina_na_ponta_de_folha(self):
        ponta = _regra(self.css, ".progress__fill::after")
        self.assertIsNotNone(ponta)
        self.assertIn("clip-path: var(--ponta)", ponta)
        self.assertIn("background: inherit", ponta, "a ponta é da cor da barra — proteína, carbo, gordura")
        trilha = _regra(self.css, ".progress")
        self.assertIn("overflow: visible", trilha, "com hidden a ponta some")

    def test_a_faixa_do_demo_abre_espaco_para_a_nervura_do_titulo(self):
        """A nervura do título sobe 100 px × sen 14° ≈ 24 px acima do `h1`
        (`.page-head h1::after`, `bottom: 100%`, `min(32%, 100px)`). No
        `/demo/` a faixa "Ambiente de demonstração … Saiba mais" fica logo
        acima do título com 16 px de margem, e a ponta da régua encostava
        no sublinhado de "Saiba mais" (visto em produção, 17/09/2026). A
        faixa é página PÚBLICA, não decoração: a margem tem de passar da
        subida da nervura com folga: MEDIDO no navegador em 18/09/2026, com
        32 px a ponta cai exatamente na base da caixa do link (folga 0);
        com 40 px (24 + 16) sobram 8 px."""
        faixa = _regra(self.css, ".demo-aviso")
        self.assertIsNotNone(faixa)
        self.assertRegex(faixa, r"margin:\s*0 0 calc\(var\(--espaco-7\) \+ var\(--espaco-6\)\)")

    def test_a_nervura_e_decoracao_atras_do_texto(self):
        corpo = _regra(self.css, ".page-head h1::after,\n.today-hero::after")
        self.assertIsNotNone(corpo, "a nervura sumiu do prato e do título")
        self.assertIn("transform: rotate(var(--nervura))", corpo)
        self.assertIn("pointer-events: none", corpo)
        self.assertIn("z-index: var(--camada-fundo)", corpo)
        self.assertIn("height: var(--traco)", corpo)
        donos = _regra(self.css, ".page-head h1,\n.today-hero")
        self.assertIsNotNone(donos)
        self.assertIn("isolation: isolate", donos, "sem contexto próprio o z-index cai atrás da página")
        # Nenhum template conta com ela: é `::after`, sem markup.
        for arquivo in (Path(settings.BASE_DIR) / "templates" / "plans" / "today.html",):
            self.assertNotIn("nervura", arquivo.read_text(encoding="utf-8"))
