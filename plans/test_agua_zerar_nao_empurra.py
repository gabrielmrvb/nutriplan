"""Zerar a água não empurra o número para duas linhas; nenhum par de alvos se toca.

UX P1-04 (14/09/2026), medido a 320 e 390: abrir "zerar" renderizava a
confirmação "apagar a água de hoje" DENTRO da linha do cabeçalho, ao lado
de "0 / 3000 ml", e o número colapsava em duas linhas. Junto vieram dois
alvos que se tocavam (MOB-11: "desfazer" e "zerar" sobrepostos em 3 px —
os `.btn-link` têm margem horizontal negativa, e ela entrava no vão) e os
três botões de água com 6,4 px de folga (MOB-13).

As regras são de CSS, e o teste as lê no arquivo:

- o cabeçalho quebra linha e a confirmação aberta ocupa a linha inteira;
- o número não quebra nunca (`white-space: nowrap`);
- os links do cabeçalho não avançam sobre o vão (sem margem horizontal
  negativa), então os 8 px de `gap` são 8 px de verdade;
- os três botões de água têm o vão da escala, e não um número solto.

Sabotagem que precisa ficar vermelha: tirar o `nowrap`, tirar o
`flex-wrap`, ou voltar o `gap: .4rem`.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


def regra(css, seletor):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?:^|\})\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", css)
    assert m, "regra não encontrada: " + seletor
    return m.group(1)


class ZerarNaoEmpurraONumeroTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")

    def test_o_numero_nunca_quebra(self):
        self.assertIn("white-space: nowrap", regra(self.css, ".agua__valor"))

    def test_a_confirmacao_aberta_ganha_a_linha_inteira(self):
        self.assertIn("flex-wrap: wrap", regra(self.css, ".agua__topo"))
        aberta = regra(self.css, ".agua__zerar[open]")
        self.assertRegex(aberta, r"flex(?:-basis)?:\s*(?:1 0 )?100%")

    def test_os_links_do_cabecalho_nao_avancam_sobre_o_vao(self):
        """`.btn-link` tem `margin: -.75rem -.35rem` para o alvo de 44px não
        mover o layout; aqui a metade horizontal sai, senão dois links com
        8 px de vão se tocam por 3 px."""
        self.assertIn("margin-inline: 0", regra(self.css, ".agua__zerar .btn-link"))

    def test_os_botoes_de_agua_tem_o_vao_da_escala(self):
        botoes = regra(self.css, ".agua__botoes")
        self.assertRegex(botoes, r"gap:\s*var\(--espaco-3\)")
        self.assertNotIn(".4rem", botoes)
