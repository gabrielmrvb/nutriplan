"""Zerar a água não empurra o número, e nenhum par de alvos se toca.

UX P1-04 (14/09/2026), medido a 320 e 390: abrir "zerar" renderizava a
confirmação "apagar a água de hoje" DENTRO da linha do cabeçalho do cartão de
água, ao lado de "0 / 3000 ml", e o número colapsava em duas linhas. Junto
vieram dois alvos que se tocavam (MOB-11: "desfazer" e "zerar" sobrepostos em
3 px — os `.btn-link` têm margem horizontal negativa, e ela entrava no vão) e
os três botões de água com 6,4 px de folga (MOB-13).

EM 22/09/2026 O CARTÃO VIROU DUAS COISAS, e este arquivo foi atrás delas:

- o número mora numa CÉLULA do painel da Hoje (`.painel__valor`, com o
  denominador em `.painel__de`), e os três passos são uma linha que QUEBRA
  (`.painel .agua__botoes`) — é o que mantém a grade em 2×2 no celular com os
  alvos em 44 px (medido: 50 px de botão a 320, 65 a 390);
- "desfazer" e "zerar" moram na tela de Hidratação, ao lado da lista de goles
  que eles mexem, em `.agua__acoes`. É lá que a confirmação aberta pode
  empurrar vizinho, e é lá que os dois `.btn-link` ficam lado a lado.

O defeito de P1-04 deixou de ser possível por ESTRUTURA — o zerar não divide
mais linha com o número —, e o de MOB-11 continua possível e continua medido.

Sabotagem que precisa ficar vermelha: tirar o `flex-wrap` de `.agua__acoes`
ou do painel, tirar o `flex: 1 0 100%` da confirmação aberta, ou devolver a
margem horizontal ao `.btn-link` de `.agua__acoes`.
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

    def test_a_confirmacao_aberta_ganha_a_linha_inteira(self):
        self.assertIn("flex-wrap: wrap", regra(self.css, ".agua__acoes"))
        aberta = regra(self.css, ".agua__acoes > [open]")
        self.assertRegex(aberta, r"flex(?:-basis)?:\s*(?:1 0 )?100%")

    def test_os_links_das_acoes_nao_avancam_sobre_o_vao(self):
        """`.btn-link` tem `margin: -.75rem -.35rem` para o alvo de 44px não
        mover o layout; aqui a metade horizontal sai, senão dois links com
        8 px de vão se tocam por 3 px."""
        self.assertIn("margin-inline: 0", regra(self.css, ".agua__acoes .btn-link"))

    def test_os_botoes_de_agua_tem_o_vao_da_escala(self):
        """Dois vãos, os dois da escala: o da tela de Hidratação (onde a linha
        tem largura sobrando) e o da célula do painel, que é menor porque a
        célula tem ~138 px úteis a 390 e os três alvos de 44 px precisam
        caber. Número solto é o que não entra."""
        for seletor in (".agua__botoes", ".painel .agua__botoes"):
            botoes = regra(self.css, seletor)
            self.assertRegex(botoes, r"gap:\s*var\(--espaco-[13]\)", seletor)
            self.assertNotIn(".4rem", botoes)

    def test_os_tres_passos_quebram_em_vez_de_espremer(self):
        """Na célula do painel eles não cabem em três colunas a 390 px, e o
        que NÃO pode acontecer é espremer abaixo de 44 px — a régua de toque
        deste projeto. A linha quebra, e o terceiro cresce e ocupa a linha:
        numa grade de duas colunas ele ficaria com metade e um buraco ao lado
        (medido a 320: 50 px de botão e 50 px de vazio)."""
        self.assertIn("flex-wrap: wrap", regra(self.css, ".painel .agua__botoes"))
        self.assertIn("flex: 1 1 2.75rem", regra(self.css, ".painel .agua__botoes > form"))
        self.assertIn("min-height: 2.75rem", regra(self.css, ".painel .agua__botao"))
