"""O DESIGN.md é derivado da direção C; se um token entrar na direção e não
no contrato, o Claude Design desenha sem ele — e inventa."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

DESIGN_DIR = Path(settings.BASE_DIR) / "docs" / "briefs" / "design"


class DesignMdTests(SimpleTestCase):
    def test_todo_token_da_direcao_c_esta_no_contrato(self):
        direcao = (DESIGN_DIR / "direcao-c-mesa-e-ferro.md").read_text(encoding="utf-8")
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        tabela = direcao.split("## 2. Cor", 1)[1].split("**A regra de três.**", 1)[0]
        tokens = re.findall(r"^\| `(--[\w-]+)` \|", tabela, re.M)
        self.assertGreaterEqual(len(tokens), 20, "a tabela da direção C não foi lida")
        faltando = [t for t in tokens if f"`{t}`" not in contrato]
        self.assertEqual(faltando, [], f"tokens da direção C fora do DESIGN.md: {faltando}")

    def test_o_contrato_diz_o_que_nunca_muda_e_o_que_o_app_nao_faz(self):
        contrato = (DESIGN_DIR / "DESIGN.md").read_text(encoding="utf-8")
        for secao in ("## O que NUNCA muda entre Mesa e Ferro", "## O que este app não faz", "## Componentes que já existem"):
            self.assertIn(secao, contrato)
