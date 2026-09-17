"""O export do Claude Design vem com dump aninhado, artefato interno e uploads
(visto no Reel "Parte 2/2"). A triagem classifica por padrão de nome e
extensão — não por uma lista fixa que envelhece —, e nenhum arquivo fica
sem classe.

O zip real ainda não existe (16/09/2026): tudo aqui roda contra árvores
SINTÉTICAS, montadas a partir da listagem do Finder do vídeo e de uma
estrutura Vite (`src/` + `index.html`) que o export pode trazer em vez dela.
Quando o zip chegar, o Step 5 da Task 8 roda o script de verdade e amplia
`classificar` com teste — nunca editando o `.md` à mão.
"""
import contextlib
import importlib
import io
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


def _plantar(raiz, relativos):
    for rel in relativos:
        alvo = raiz / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(b"x" * 10)
    return raiz


def _arvore(tmp):
    """A listagem do Finder do vídeo 2, mais um arquivo que ninguém previu."""
    return _plantar(Path(tmp) / "design-system-export", (
        "_adherence.oxlintrc.json", "_ds_bundle.js", "_ds_manifest.json", ".thumbnail",
        "readme.md", "SKILL.md", "styles.css", "thumbnail.html",
        "tokens/colors.json", "guidelines/typography.md",
        "components/button/index.html", "ui_kits/admin/preview.html",
        "NutriPlan - Hoje (standalone).html",
        "design-system-export/tokens/colors.json",
        "uploads/hoje-claro.png", "assets/icon-192.png", "misterio.xyz",
    ))


def _arvore_vite(tmp):
    """Estrutura que a documentação NÃO prevê: `src/` e `index.html` na raiz.

    Sem `.js` de propósito — script fora de `_ds_` é leitura humana, e a
    régua desta árvore é "zero incerto"."""
    return _plantar(Path(tmp) / "export-vite", (
        "index.html",
        "src/tokens.css", "src/design-tokens.json", "src/guidelines/spacing.md",
        "src/components/Button.html", "src/assets/logo.svg", "src/fonts/Inter.woff2",
    ))


class InventarioTests(SimpleTestCase):
    def setUp(self):
        self.m = importlib.import_module("scripts.inventariar_export")

    def test_classifica_por_padrao(self):
        c = self.m.classificar
        self.assertEqual(c("_ds_bundle.js"), "interno")
        self.assertEqual(c(".thumbnail"), "interno")
        self.assertEqual(c("uploads/hoje-claro.png"), "interno")
        self.assertEqual(c("design-system-export/tokens/colors.json"), "interno")
        self.assertEqual(c("_adherence.oxlintrc.json"), "tokens")
        self.assertEqual(c("tokens/colors.json"), "tokens")
        self.assertEqual(c("guidelines/typography.md"), "tokens")
        self.assertEqual(c("readme.md"), "tokens")
        self.assertEqual(c("styles.css"), "tokens")
        self.assertEqual(c("components/button/index.html"), "referencia")
        self.assertEqual(c("NutriPlan - Hoje (standalone).html"), "referencia")
        self.assertEqual(c("assets/icon-192.png"), "referencia")
        self.assertEqual(c("misterio.xyz"), "incerto")

    def test_pasta_desconhecida_classifica_pela_extensao(self):
        """A documentação lista as pastas do vídeo; o zip pode trazer outras.
        Fora delas, a extensão decide — e o que não dá para decidir por
        extensão fica `incerto`, em vez de ganhar uma classe por palpite."""
        c = self.m.classificar
        self.assertEqual(c("src/components/Button.html"), "referencia")
        self.assertEqual(c("src/assets/logo.svg"), "referencia")
        self.assertEqual(c("src/fonts/Inter.woff2"), "referencia")
        self.assertEqual(c("src/tokens.css"), "tokens")
        self.assertEqual(c("src/design-tokens.json"), "tokens")
        self.assertEqual(c("src/guidelines/spacing.md"), "tokens")
        self.assertEqual(c("src/app.css"), "incerto")
        self.assertEqual(c("src/main.js"), "incerto")
        self.assertEqual(c("bin/instalador.exe"), "incerto")
        self.assertEqual(c("src\\tokens.css"), "tokens")

    def test_arvore_vite_classifica_sem_incerto(self):
        with tempfile.TemporaryDirectory() as tmp:
            itens = self.m.inventariar(_arvore_vite(tmp))
            self.assertEqual(len(itens), 7)
            self.assertEqual([i["caminho"] for i in itens if i["classe"] == "incerto"], [])
            self.m.exigir_tudo_classificado(itens)  # não levanta

    def test_inventaria_tudo_e_escreve_o_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore(tmp)
            itens = self.m.inventariar(raiz)
            self.assertEqual(len(itens), 17)
            self.assertTrue(all(len(i["sha256"]) == 64 for i in itens))
            destino = Path(tmp) / "inventario.md"
            self.m.escrever_md(itens, destino, origem="teste")
            md = destino.read_text(encoding="utf-8")
            self.assertIn("| `misterio.xyz` |", md)
            self.assertIn("incerto", md)
            self.assertIn("**17** arquivos", md)

    def test_estrito_recusa_incerto(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore(tmp)
            with self.assertRaises(SystemExit):
                self.m.exigir_tudo_classificado(self.m.inventariar(raiz))

    def test_estrito_nomeia_todo_incerto_e_o_padrao_so_lista(self):
        """Controle positivo com um `.exe`: ele cai em `incerto`, e o modo
        estrito falha nomeando CADA um — não só o primeiro —, sem traceback
        (é `SystemExit` com texto, que o Python imprime e encerra com 1). Sem
        `--estrito` o mesmo inventário termina em 0: o padrão é listar."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _plantar(_arvore(tmp), ("bin/instalador.exe",))
            saida = Path(tmp) / "inventario.md"
            terminal = io.StringIO()
            with contextlib.redirect_stdout(terminal):
                codigo = self.m.main([str(raiz), "--saida", str(saida)])
            self.assertEqual(codigo, 0)
            self.assertIn("| `bin/instalador.exe` |", terminal.getvalue())
            self.assertIn("incerto", terminal.getvalue())
            self.assertTrue(saida.is_file())

            saida.unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as parada:
                    self.m.main([str(raiz), "--estrito", "--saida", str(saida)])
            mensagem = str(parada.exception.code)
            self.assertIn("bin/instalador.exe", mensagem)
            self.assertIn("misterio.xyz", mensagem)
            self.assertNotIsInstance(parada.exception.code, int)
            self.assertTrue(saida.is_file(), "o estrito recusa DEPOIS de listar")

    def test_pasta_vazia_avisa_e_sai_com_2(self):
        """Um export que veio vazio (zip errado, pasta errada) não pode virar
        um `.md` dizendo "0 arquivos" com cara de trabalho feito."""
        with tempfile.TemporaryDirectory() as tmp:
            vazia = Path(tmp) / "vazia"
            vazia.mkdir()
            saida = Path(tmp) / "inventario.md"
            erro = io.StringIO()
            with contextlib.redirect_stderr(erro):
                codigo = self.m.main([str(vazia), "--saida", str(saida)])
            self.assertEqual(codigo, 2)
            self.assertIn("inventário vazio", erro.getvalue())
            self.assertFalse(saida.exists())


class OZipRealTests(SimpleTestCase):
    """16/09/2026: os dois zips chegaram e a árvore documentada estava certa —
    mas extraída em SUBPASTAS (`design-system/`, `telas/`), com `components/`
    em React (`.jsx`, `.d.ts`, `.prompt.md`), `ui_kits/pwa/*.jsx`, uma pasta
    `reference/` e uma cópia do sistema em `telas/_ds/`. A primeira rodada do
    `--estrito` reprovou com 49 incertos, todos `.jsx`/`.d.ts`, porque a pasta
    conhecida só era lida no primeiro nível. Esta é a árvore real, reduzida."""

    REAL = (
        "nutriplan-design-system.zip",
        "nutriplan-telas.zip",
        "design-system/SKILL.md",
        "design-system/_adherence.oxlintrc.json",
        "design-system/_ds_bundle.js",
        "design-system/_ds_manifest.json",
        "design-system/.thumbnail",
        "design-system/thumbnail.html",
        "design-system/readme.md",
        "design-system/styles.css",
        "design-system/assets/icones.svg",
        "design-system/assets/telas/hoje-claro.png",
        "design-system/components/core/Button.jsx",
        "design-system/components/core/Button.d.ts",
        "design-system/components/core/Button.prompt.md",
        "design-system/css/base.css",
        "design-system/guidelines/cores/agir-e-feito.html",
        "design-system/reference/DESIGN.md",
        "design-system/tokens/colors.css",
        "design-system/ui_kits/pwa/Hoje.jsx",
        "design-system/ui_kits/pwa/index.html",
        "design-system/uploads/app.css",
        "telas/Hoje.html",
        "telas/_ds/nutriplan-design-system-abc/tokens/colors.css",
        "telas/_ds/nutriplan-design-system-abc/_ds_bundle.js",
        "telas/assets/icones.svg",
    )

    def test_a_arvore_real_classifica_sem_incerto(self):
        m = importlib.import_module("scripts.inventariar_export")
        classes = {rel: m.classificar(rel) for rel in self.REAL}
        incertos = [r for r, c in classes.items() if c == "incerto"]
        self.assertEqual(incertos, [])
        self.assertEqual(classes["design-system/components/core/Button.jsx"], "referencia")
        self.assertEqual(classes["design-system/ui_kits/pwa/Hoje.jsx"], "referencia")
        self.assertEqual(classes["design-system/tokens/colors.css"], "tokens")
        self.assertEqual(classes["design-system/reference/DESIGN.md"], "tokens")
        self.assertEqual(classes["design-system/css/base.css"], "tokens")
        self.assertEqual(classes["telas/Hoje.html"], "referencia")
        # A cópia do sistema dentro do projeto das telas é duplicata, inteira.
        self.assertEqual(classes["telas/_ds/nutriplan-design-system-abc/tokens/colors.css"], "interno")
        self.assertEqual(classes["nutriplan-telas.zip"], "interno")
        self.assertEqual(classes["design-system/uploads/app.css"], "interno")
        # O terceiro zip (as três direções, canvas `.dc.html`) traz o runtime
        # do canvas ao lado dos arquivos: é o irmão do `_ds_bundle.js`.
        self.assertEqual(m.classificar("direcoes/support.js"), "interno")
        self.assertEqual(m.classificar("direcoes/Direcao1-a.dc.html"), "referencia")

    def test_um_arquivo_estranho_continua_incerto(self):
        """Controle positivo: abrir a pasta conhecida em qualquer nível não
        pode ter transformado a triagem em "tudo é referência"."""
        m = importlib.import_module("scripts.inventariar_export")
        self.assertEqual(m.classificar("design-system/scripts/build.py"), "incerto")
        self.assertEqual(m.classificar("telas/misterio.xyz"), "incerto")
