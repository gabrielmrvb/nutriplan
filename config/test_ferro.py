"""Dois regimes escritos UMA vez cada, e três gatilhos que só ligam (CORTE).

Os valores moram no `:root`, como `--ferro-*` (escuro, o padrão) e
`--papel-*` (claro, o derivado). Quem liga: o próprio `:root` liga o Ferro
(`--bg: var(--ferro-bg)`), `@media (prefers-color-scheme: light)` liga o
Papel e `:root.modo-foco` — classe que o servidor escreve no `<html>` —
liga o Ferro de volta por cima da preferência: a execução do treino nasce
escura sempre. No `<html>` porque `--glass`/`--glow`/`--halo` são receitas
de `var()` do `:root` e resolvem onde são declaradas. Duplicar a lista de valores é
como uma segunda paleta nasce sem ninguém decidir; um `--ferro-x` sem o
`--papel-x` é cor que vaza inteira para o claro. Este arquivo é a trava
das duas coisas. Até 16/09/2026 a base era a clara (Mesa) e o Ferro o
derivado; a inversão é a decisão da direção escolhida (`DESIGN.md`,
"Dois regimes, e o escuro é a base")."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
RAIZ = ":root {"
CLARO = "prefers-color-scheme: light) {" + chr(10) + "  :root {"
FOCO = ":root.modo-foco {"


def ler_bloco(css, escopo):
    fecha = chr(10) + "}" if escopo == RAIZ else "}"
    trecho = css.split(escopo, 1)[1].split(fecha, 1)[0]
    return dict(re.findall(r"^\s*(--[\w-]+|color-scheme):\s*([^;]+);", trecho, re.M))


class FerroTests(SimpleTestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding="utf-8")
        self.raiz = ler_bloco(self.css, RAIZ)
        self.claro = ler_bloco(self.css, CLARO)
        self.foco = ler_bloco(self.css, FOCO)
        self.ferro = {k[len("--ferro-"):] for k in self.raiz if k.startswith("--ferro-")}
        self.papel = {k[len("--papel-"):] for k in self.raiz if k.startswith("--papel-")}

    def test_os_valores_dos_dois_regimes_existem_uma_vez_no_root(self):
        self.assertGreaterEqual(len(self.ferro), 20)
        for nome in ("bg", "surface", "text", "brand", "folha", "fio"):
            self.assertIn(nome, self.ferro)
        self.assertEqual(self.ferro, self.papel, "todo --ferro-x tem o seu --papel-x, e vice-versa")

    def test_o_root_liga_o_ferro_e_so_por_var(self):
        """A base é o escuro: cada token de cor do `:root` é `var(--ferro-x)`."""
        ligados = {k: v for k, v in self.raiz.items() if v.strip().startswith("var(--ferro-")}
        self.assertEqual(set(ligados), {"--" + n for n in self.ferro})
        for nome, valor in ligados.items():
            with self.subTest(token=nome):
                self.assertEqual(valor.strip(), "var(--ferro-" + nome[2:] + ")")
        self.assertIn("color-scheme: dark light;", self.css.split(RAIZ, 1)[1].split(chr(10) + "}", 1)[0])

    def test_o_claro_liga_o_papel_e_o_modo_foco_liga_o_ferro_na_mesma_lista(self):
        self.assertEqual(set(self.claro) - {"color-scheme"}, {"--" + n for n in self.papel})
        self.assertEqual(set(self.foco) - {"color-scheme"}, {"--" + n for n in self.ferro})
        for bloco, prefixo, rotulo in ((self.claro, "papel", "claro"), (self.foco, "ferro", "modo-foco")):
            for nome, valor in bloco.items():
                if nome == "color-scheme":
                    continue
                with self.subTest(gatilho=rotulo, token=nome):
                    self.assertEqual(valor.strip(), "var(--%s-%s)" % (prefixo, nome[2:]))

    def test_nenhum_valor_de_regime_sem_dono(self):
        """Todo `--ferro-x`/`--papel-x` liga um `--x` que o `:root` declara."""
        for nome in self.ferro | self.papel:
            with self.subTest(token=nome):
                self.assertIn("--" + nome, self.raiz)

    def test_os_gatilhos_declaram_o_esquema_certo(self):
        """Sem `color-scheme`, campo e rolagem nativos ficam na cor errada:
        o Papel precisa de `light`, o modo-foco de `dark`."""
        self.assertEqual(self.claro.get("color-scheme"), "light")
        self.assertEqual(self.foco.get("color-scheme"), "dark")

    def test_nenhum_hex_fora_das_duas_listas_nos_gatilhos(self):
        for bloco, rotulo in ((self.claro, "claro"), (self.foco, "modo-foco")):
            hex_solto = [k for k, v in bloco.items() if "#" in v or "rgb" in v]
            self.assertEqual(hex_solto, [], f"{rotulo} escreve cor por extenso: {hex_solto}")
