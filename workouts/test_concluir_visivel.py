"""O botão "Concluir série" nunca fica atrás da tabbar.

Medido em 14/09/2026 antes desta regra (`medir_cta.sh`, conta de QA com o
poster e a instrução de esforço na tela): o botão nascia em y=589-637 em
todas as larguras; a 320×568 a tabbar começa em 489 e a 375×667 em 588 — o
botão mais tocado da tela ficava fora da dobra ou debaixo da navegação
(UX P1-08, TREINO UX-CTA-320). Três receitas disputaram a correção —
recolher a dica num `<details>`, ajustar espaçamento, ou fixar o bloco —, e
só a terceira garante a dobra em todas as larguras com a frase de sugestão
mais longa.

O bloco Carga/Reps/Concluir é `position: sticky` no rodapé do viewport,
ACIMA da tabbar (`bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom))`)
e no degrau `--camada-flutuante` — abaixo de `--camada-navegacao`, que é a
regra de produto que `test_nada_cobre_a_barra_de_navegacao` guarda: nada
cobre a barra de baixo. Sabotagem que precisa ficar vermelha: trocar o
degrau por `--camada-navegacao`, ou tirar o `sticky`.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


def bloco(css, seletor):
    """As declarações do PRIMEIRO bloco cujo seletor é exatamente `seletor`.

    Sem os comentários: este arquivo comenta muito, e o comentário cita o
    nome da coisa que a asserção procura (CLAUDE.md, "Testes").
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    m = re.search(r"(?m)^" + re.escape(seletor) + r"\s*\{(.*?)\}", css, re.S)
    assert m, "bloco não encontrado: " + seletor
    return m.group(1)


class ConcluirSerieVisivelTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")
        self.regra = bloco(self.css, ".registro--agora")

    def test_o_bloco_de_registro_gruda_no_rodape_acima_da_tabbar(self):
        self.assertIn("position: sticky", self.regra)
        self.assertRegex(
            self.regra,
            r"bottom:\s*calc\(var\(--tabbar-h\)\s*\+\s*env\(safe-area-inset-bottom\)",
        )

    def test_o_bloco_fica_no_degrau_flutuante_e_nunca_no_da_navegacao(self):
        self.assertIn("z-index: var(--camada-flutuante)", self.regra)
        self.assertNotIn("--camada-navegacao", self.regra)

    def test_o_body_nao_e_o_conteiner_de_rolagem(self):
        """`overflow-x: hidden` no `body` além do `html` fazia do body o
        contêiner de rolagem de todo `sticky` — e o body é tão alto quanto o
        conteúdo, então nada grudava. Medido em 14/09/2026: a `.app-bar`
        (`sticky; top: 0`) em y=-300 com `scrollY=300`. O `html` trava a
        rolagem horizontal sozinho."""
        self.assertIn("overflow-x: hidden", bloco(self.css, "html"))
        self.assertNotIn("overflow", bloco(self.css, "body"))

    def test_o_bloco_tem_fundo_para_o_conteudo_nao_vazar_por_baixo(self):
        """Grudado, o bloco passa por cima do que rola: sem fundo opaco a
        anatomia e a carga anterior apareceriam através dos campos."""
        self.assertRegex(self.regra, r"background:\s*var\(--surface\)")
