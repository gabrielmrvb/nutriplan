"""Estado vazio não grita: a PALAVRA sai da fonte de número (24/09/2026).

Na Home, cada cartão de área tem um `painel__valor` — e ele nasceu para
número: display (Big Shoulders), 900, caixa alta, tracking negativo,
`--texto-2xl`. Quatro desses valores são PALAVRA: "Descanso", "Sem ficha",
"Nenhuma ainda" e "Sem pesagem". Na varredura de 24/09/2026 o cartão de
Corrida sem corrida apareceu com "NENHUMA AINDA" em manchete de 72 px — um
estado vazio gritando, contra os outros 16 do app, que são texto normal.

A correção é a mesma que a branch da Home (#138) já escolheu, e a classe é a
DELA, copiada verbatim: `painel__valor--palavra` mantém o degrau de
hierarquia e troca a família — fonte de texto, peso 700, `--texto-lg`. Usar
o mesmo nome é o que faz as duas branches mergearem sem briga.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATE = Path(settings.BASE_DIR) / "templates" / "plans" / "today.html"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

#: `<p class="painel__valor…">…</p>` — o conteúdo inteiro, para separar o que
#: é número (`{{ ... }}`) do que é palavra escrita no template.
VALOR = re.compile(r'<p class="(painel__valor[^"]*)"[^>]*>(.*?)</p>', re.S)


class OValorDePalavraNaoUsaAFonteDoNumeroTests(SimpleTestCase):
    def test_todo_valor_escrito_a_mao_leva_o_modificador(self):
        """A régua é o CONTEÚDO: valor que vem do banco (`{{ ... }}`) é
        número e fica na display; valor escrito no template é palavra."""
        marcacao = TEMPLATE.read_text(encoding="utf-8")
        palavras = []
        for classes, conteudo in VALOR.findall(marcacao):
            if "{{" in conteudo:
                continue
            palavras.append((conteudo.strip(), classes))

        self.assertTrue(palavras, "nenhum valor de palavra achado — o regex envelheceu?")
        for texto, classes in palavras:
            with self.subTest(texto=texto):
                self.assertIn("painel__valor--palavra", classes)

    def test_o_numero_continua_na_display(self):
        """O contrapeso: nenhum valor que VEM DO BANCO pode ter ganhado o
        modificador junto — senão a correção teria tirado a display dos
        números, que é onde ela ganha o app."""
        marcacao = TEMPLATE.read_text(encoding="utf-8")
        for classes, conteudo in VALOR.findall(marcacao):
            if "{{" not in conteudo:
                continue
            with self.subTest(conteudo=conteudo.strip()[:40]):
                self.assertNotIn("painel__valor--palavra", classes)

    def test_a_regra_troca_a_familia_e_mantem_o_degrau(self):
        css = CSS.read_text(encoding="utf-8")
        regra = re.search(r"\.painel__valor--palavra\s*\{([^}]*)\}", css)
        self.assertIsNotNone(regra, "a classe precisa existir no CSS")
        corpo = regra.group(1)
        self.assertIn("var(--font)", corpo)
        self.assertNotIn("--font-display", corpo)
