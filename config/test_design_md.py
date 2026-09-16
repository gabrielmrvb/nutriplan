"""O DESIGN.md é o contrato visual. Até 16/09/2026 ele derivava da direção C
(Mesa & Ferro); desde a escolha da direção CORTE (`DIRECAO-ESCOLHIDA.md`)
ele é reescrito a partir dela e a direção C sobrevive só na seção
"Mantido da spec anterior". Os NOMES dos tokens do app não mudam com a
direção — é o que deixa os testes de contraste e as catracas de pé —, então
todo token que a direção C nomeava continua tendo de aparecer no contrato."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

DESIGN_DIR = Path(settings.BASE_DIR) / "docs" / "briefs" / "design"


class DesignMdTests(SimpleTestCase):
    def test_todo_token_do_app_esta_no_contrato(self):
        direcao = (DESIGN_DIR / "direcao-c-mesa-e-ferro.md").read_text(encoding="utf-8")
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        tabela = direcao.split("## 2. Cor", 1)[1].split("**A regra de três.**", 1)[0]
        tokens = re.findall(r"^\| `(--[\w-]+)` \|", tabela, re.M)
        self.assertGreaterEqual(len(tokens), 20, "a tabela da direção C não foi lida")
        faltando = [t for t in tokens if f"`{t}`" not in contrato]
        self.assertEqual(faltando, [], f"tokens do app fora do DESIGN.md: {faltando}")

    def test_o_contrato_diz_o_que_nunca_muda_e_o_que_o_app_nao_faz(self):
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        for secao in ("## Dois regimes, e o escuro é a base", "## O recorte — os raios", "## O que este app não faz", "## Componentes que já existem", "## Mantido da spec anterior"):
            self.assertIn(secao, contrato)

    def test_o_contrato_e_a_escolha_dizem_a_mesma_direcao(self):
        """`DIRECAO-ESCOLHIDA.md` decide; o DESIGN.md obedece. Se alguém
        trocar a escolha sem reescrever o contrato (ou o contrário), os dois
        arquivos param de dizer o mesmo nome."""
        escolha = (DESIGN_DIR / "DIRECAO-ESCOLHIDA.md").read_text(encoding="utf-8")
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        nome = re.search(r"# Direção escolhida: \*\*([A-ZÇÃ]+)\*\*", escolha).group(1)
        self.assertIn(f"direção **{nome}**", contrato)
        self.assertIn("--corte: 0 20px 0 20px", contrato)
