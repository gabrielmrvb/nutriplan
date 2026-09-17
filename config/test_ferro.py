"""Ferro é UM bloco de valores com DOIS gatilhos (direção C §1).

Os valores moram uma vez em `:root`, como `--ferro-*`; o bloco do tema
escuro e o `body.modo-foco` só ligam `--bg: var(--ferro-bg)` e companhia.
Duplicar a lista de valores é como uma segunda paleta nasce sem ninguém
decidir — e este teste é a trava."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
ESCURO = "prefers-color-scheme: dark) {" + chr(10) + "  :root {"
FOCO = "body.modo-foco {"


def ler_bloco(css, escopo):
    trecho = css.split(escopo, 1)[1].split(chr(10) + "}", 1)[0] if escopo == ":root {" else css.split(escopo, 1)[1].split("}", 1)[0]
    return dict(re.findall(r"^\s*(--[\w-]+):\s*([^;]+);", trecho, re.M))


class FerroTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")
        self.raiz = ler_bloco(self.css, ":root {")
        self.escuro = ler_bloco(self.css, ESCURO)
        self.foco = ler_bloco(self.css, FOCO)

    def test_os_valores_de_ferro_existem_uma_vez_no_root(self):
        ferro = {k for k in self.raiz if k.startswith("--ferro-")}
        self.assertGreaterEqual(len(ferro), 20)
        for nome in ("--ferro-bg", "--ferro-surface", "--ferro-text", "--ferro-brand", "--ferro-folha"):
            self.assertIn(nome, ferro)

    def test_os_dois_gatilhos_ligam_os_mesmos_tokens_e_so_por_var(self):
        self.assertEqual(set(self.escuro) - {"color-scheme"}, set(self.foco) - {"color-scheme"})
        for bloco, rotulo in ((self.escuro, "escuro"), (self.foco, "modo-foco")):
            for nome, valor in bloco.items():
                if nome == "color-scheme":
                    continue
                with self.subTest(gatilho=rotulo, token=nome):
                    self.assertEqual(valor.strip(), "var(--ferro-" + nome[2:] + ")")
                    self.assertIn("--ferro-" + nome[2:], self.raiz)

    def test_nenhum_ferro_sem_dono(self):
        """Todo `--ferro-x` liga um `--x` que existe em Mesa."""
        for nome in (k for k in self.raiz if k.startswith("--ferro-")):
            with self.subTest(token=nome):
                self.assertIn("--" + nome[len("--ferro-"):], self.raiz)

    def test_o_modo_foco_declara_o_esquema_escuro(self):
        """Sem `color-scheme: dark`, campo e rolagem nativos ficam claros no Ferro."""
        trecho = self.css.split(FOCO, 1)[1].split("}", 1)[0]
        self.assertIn("color-scheme: dark;", trecho)
