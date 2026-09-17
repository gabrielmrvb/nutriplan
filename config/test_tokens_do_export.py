"""A spec ganha; a comparação existe para que a diferença fique escrita.

O export do Claude Design ainda não chegou (16/09/2026), então estes testes
montam a árvore que a documentação do produto descreve — `styles.css` com um
`:root`, `tokens/*.css|json`, `_ds_manifest.json`, `components/`,
`guidelines/`, `readme.md`, `SKILL.md` — e provam três coisas que o script
precisa fazer antes de ver o zip de verdade: ler custom property de CSS e
JSON nas duas formas que o mercado usa (plana e W3C/DTCG), comparar cor sem
caixa e com `#abc` expandido, e NUNCA morrer num arquivo estranho — JSON
quebrado vira linha de "não lidos", árvore sem token vira código 2.

Os valores da direção C são lidos do `app.css` real dentro do teste: quando
um token da Mesa mudar de valor, o teste acompanha em vez de apodrecer.
"""
import contextlib
import importlib
import io
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)
BRAND_PROPOSTO = "#0d6d42"


def _modulo():
    return importlib.import_module("scripts.tokens_do_export")


def _arvore_documentada(tmp, styles_css, colors_json='{"--novo-do-export": "#123456"}'):
    """A estrutura que o Claude Design exporta, com o conteúdo que cada teste pede."""
    raiz = Path(tmp) / "design-system-export"
    arquivos = {
        "styles.css": styles_css,
        "tokens/colors.css": ":root {\n  --chip-bg: #dff0e6;\n}\n",
        "tokens/colors.json": colors_json,
        "_ds_manifest.json": '{"name": "NutriPlan", "version": 1, "colors": {"--bg": "#000000"}}',
        "components/button/index.html": '<style>.btn { background: var(--brand); --btn-x: #ff0000; }</style><button class="btn">Ok</button>',
        "guidelines/typography.md": "# Tipografia\n\nCorpo em `system-ui`, 16px.\n",
        "readme.md": "# NutriPlan\n\n```css\n--text: #141f1a;\n```\n",
        "SKILL.md": "---\nname: nutriplan\n---\nUse `--brand` para o CTA.\n",
        "uploads/hoje-claro.css": ":root { --bg: #000000; }",
        "design-system-export/tokens/colors.json": '{"--bg": "#000000"}',
    }
    for rel, texto in arquivos.items():
        alvo = raiz / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
    return raiz


class TokensDoExportTests(SimpleTestCase):
    def setUp(self):
        self.m = _modulo()
        self.spec = self.m._spec()
        # Se a Mesa um dia adotar exatamente o verde proposto aqui, o teste
        # da "uma diferença" passaria a medir zero — melhor ele dizer isso.
        self.assertNotEqual(self.spec["--brand"].lower(), BRAND_PROPOSTO, "escolha outro valor proposto")

    # --- Task 11, Step 1, ao pé da letra ---------------------------------

    def test_extrai_custom_properties_de_css_json_e_md(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "tokens").mkdir()
            (raiz / "styles.css").write_text(":root{--bg:#f5f3ee;--brand:#0d6d42}", encoding="utf-8")
            (raiz / "tokens" / "colors.json").write_text('{"--brand": "#0d6d42", "--novo": "#123456"}', encoding="utf-8")
            (raiz / "guidelines").mkdir()
            (raiz / "guidelines" / "cores.md").write_text("Texto em `--text: #141f1a` e nada mais.\n", encoding="utf-8")
            (raiz / "uploads").mkdir()
            (raiz / "uploads" / "x.css").write_text(":root{--bg:#000000}", encoding="utf-8")  # interno: ignorado
            achados = m.extrair(raiz)
        self.assertEqual(achados["--bg"], {"#f5f3ee"})
        self.assertEqual(achados["--brand"], {"#0d6d42"})
        self.assertIn("--novo", achados)
        self.assertEqual(achados["--text"], {"#141f1a"}, "o .md das guidelines também é fonte de token")

    def test_compara_e_lista_so_as_diferencas(self):
        m = self.m
        difs = m.comparar({"--bg": {"#f5f3ee"}, "--brand": {"#0d6d42"}, "--novo": {"#123456"}}, {"--bg": "#f5f3ee", "--brand": "#0c6b40"})
        self.assertEqual(difs, [("--brand", "#0d6d42", "#0c6b40"), ("--novo", "#123456", "(não existe na spec)")])

    # --- N8: a árvore documentada contra a Mesa real ----------------------

    def test_arvore_sintetica_produz_exatamente_uma_diferenca_nomeada(self):
        """`--bg` igual à Mesa, `--brand` diferente, um `--ferro-*` que não
        conta e um token só do export: a tabela de diferenças tem UMA linha
        de token da direção, e ela se chama `--brand`."""
        m = self.m
        styles = ":root {\n  --bg: %s;\n  --brand: %s;\n  --ferro-bg: #000000;\n}\n" % (self.spec["--bg"], BRAND_PROPOSTO)
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore_documentada(tmp, styles)
            leitura = m.ler_export(raiz)
            rel = m.relatorio(leitura, self.spec)
            difs = m.comparar(leitura.encontrados, self.spec)

        so_da_direcao = [d for d in difs if d[2] != "(não existe na spec)"]
        self.assertEqual(so_da_direcao, [("--brand", BRAND_PROPOSTO, self.spec["--brand"])])

        por_token = {linha["token"]: linha for linha in rel["linhas"]}
        self.assertEqual(por_token["--bg"]["estado"], "igual")
        self.assertEqual(por_token["--brand"]["estado"], "diferente")
        self.assertEqual(por_token["--brand"]["export"], [BRAND_PROPOSTO])
        self.assertEqual(por_token["--text"]["estado"], "igual", "veio do bloco de código do readme.md")
        self.assertEqual(por_token["--surface"]["estado"], "ausente")
        self.assertEqual(rel["resumo"]["diferentes"], 1)
        self.assertEqual(rel["ignorados"], ["--ferro-bg"])
        novos = dict(rel["novos"])
        self.assertIn("--novo-do-export", novos)
        self.assertIn("--chip-bg", novos, "tokens/colors.css é fonte de token")
        self.assertIn("--btn-x", novos, "HTML de componente é referência e também é lido")
        # interno não entra: manifesto, uploads e export aninhado dizem #000000 para --bg
        self.assertNotIn("#000000", por_token["--bg"]["export"])

    def test_json_w3c_e_prefixo_color_mapeiam_para_o_token_da_direcao(self):
        """`--color-bg` no CSS e `color.brand.value` no JSON são os nomes que
        o mercado usa; a direção diz `--bg` e `--brand`. O mapeamento é
        aplicado E escrito, para ninguém ter de adivinhar quem casou com quem."""
        m = self.m
        w3c = json.dumps({"color": {"brand": {"$value": BRAND_PROPOSTO, "$type": "color"}, "surface": {"value": "#FFF"}}})
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore_documentada(tmp, ":root { --color-bg: %s; }" % self.spec["--bg"].upper(), colors_json=w3c)
            rel = m.relatorio(m.ler_export(raiz), self.spec)
        por_token = {linha["token"]: linha for linha in rel["linhas"]}
        self.assertEqual(por_token["--bg"]["estado"], "igual")
        self.assertEqual(por_token["--brand"]["estado"], "diferente")
        self.assertEqual(por_token["--surface"]["estado"], "igual", "#FFF é #ffffff")
        self.assertEqual(sorted(rel["mapeamento"]), [("--color-bg", "--bg"), ("--color-brand", "--brand"), ("--color-surface", "--surface")])
        self.assertEqual(rel["nao_lidos"], [])

    def test_cor_e_comparada_sem_caixa_e_com_hex_curto_expandido(self):
        """`#F5F3EE` e `#f5f3ee` são a mesma cor; `#FFF` é `#ffffff`. Um
        comparador que olhasse a string crua acusaria diferença onde não há —
        e é essa a sabotagem que este teste existe para pegar."""
        m = self.m
        encontrados = {"--bg": {self.spec["--bg"].upper()}, "--surface": {"#FFF"}, "--fio": {"RGBA(20,31,26,0.1)"}}
        difs = m.comparar(encontrados, {"--bg": self.spec["--bg"], "--surface": "#ffffff", "--fio": "rgba(20, 31, 26, .10)"})
        self.assertEqual(difs, [])
        self.assertEqual(m.normalizar_cor("#ABC"), "#aabbcc")
        self.assertEqual(m.normalizar_cor("#0C6B40"), "#0c6b40")
        self.assertNotEqual(m.normalizar_cor("#0c6b40"), m.normalizar_cor("#0d6d42"))

    def test_varios_valores_para_o_mesmo_token_viram_misto_e_entram_nas_diferencas(self):
        """Um export com `--bg` igual num arquivo e diferente noutro está
        propondo algo — listar só o "igual" esconderia a proposta."""
        m = self.m
        difs = m.comparar({"--bg": {"#f5f3ee", "#000000"}}, {"--bg": "#f5f3ee"})
        self.assertEqual(difs, [("--bg", "#000000 / #f5f3ee", "#f5f3ee")])

    # --- controles positivos: o script não morre em árvore ruim -----------

    def test_arvore_sem_token_nenhum_termina_com_codigo_2_e_diz_isso(self):
        m = self.m
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "design-system-export"
            (raiz / "components").mkdir(parents=True)
            (raiz / "readme.md").write_text("# Sem token nenhum\n", encoding="utf-8")
            (raiz / "components" / "index.html").write_text("<p>oi</p>", encoding="utf-8")
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                codigo = m.main([str(raiz)])
        self.assertEqual(codigo, 2)
        self.assertIn("nenhum token lido", saida.getvalue())

    def test_pasta_inexistente_termina_com_codigo_2_sem_traceback(self):
        m = self.m
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = m.main([str(RAIZ / "nao-existe-esta-pasta")])
        self.assertEqual(codigo, 2)
        self.assertIn("não existe", erro.getvalue() + saida.getvalue())

    def test_json_malformado_entra_em_nao_lidos_com_o_nome_do_arquivo(self):
        """Um JSON quebrado ou de forma estranha não derruba a leitura dos
        outros arquivos — vira linha nomeada, para alguém abrir."""
        m = self.m
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore_documentada(tmp, ":root { --bg: %s; }" % self.spec["--bg"], colors_json='{"--brand": ')
            (raiz / "tokens" / "lista.json").write_text('["#000000", "#ffffff"]', encoding="utf-8")
            leitura = m.ler_export(raiz)
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                codigo = m.main([str(raiz)])
        arquivos = [rel for rel, _ in leitura.nao_lidos]
        self.assertEqual(arquivos, ["tokens/colors.json", "tokens/lista.json"])
        self.assertIn("JSON inválido", dict(leitura.nao_lidos)["tokens/colors.json"])
        self.assertEqual(leitura.encontrados["--bg"], {self.spec["--bg"]})
        self.assertEqual(codigo, 0)
        self.assertIn("tokens/colors.json", saida.getvalue())
        self.assertIn("Não lidos", saida.getvalue())

    def test_pasta_mae_do_export_extraido_e_aceita(self):
        """Quem extrai o zip e passa a pasta de cima (a que contém
        `design-system-export/`) não pode receber "nenhum token lido"."""
        m = self.m
        with tempfile.TemporaryDirectory() as tmp:
            _arvore_documentada(tmp, ":root { --bg: %s; }" % self.spec["--bg"])
            self.assertEqual(m.raiz_efetiva(Path(tmp)), Path(tmp) / "design-system-export")
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                codigo = m.main([tmp])
        self.assertEqual(codigo, 0)
        self.assertIn("| `--bg` |", saida.getvalue())

    # --- o markdown e a spec -------------------------------------------------

    def test_markdown_tem_as_cinco_secoes_e_a_tabela_da_task_11(self):
        m = self.m
        styles = ":root { --bg: %s; --brand: %s; }" % (self.spec["--bg"], BRAND_PROPOSTO)
        with tempfile.TemporaryDirectory() as tmp:
            raiz = _arvore_documentada(tmp, styles, colors_json='{"color": {"novo": {"value": "#123456"}}}')
            md = m.escrever_md(m.relatorio(m.ler_export(raiz), self.spec), origem="teste")
            destino = Path(tmp) / "saida.md"
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                codigo = m.main([str(raiz), "--saida", str(destino)])
            gravado = destino.read_text(encoding="utf-8")
        self.assertEqual(codigo, 0)
        for secao in ("## Token a token", "## Só as diferenças", "## Novos no export", "## Nomes traduzidos", "## Não lidos"):
            with self.subTest(secao=secao):
                self.assertIn(secao, md)
        self.assertIn("| token | proposto pelo Claude Design | spec (direção C) | motivo |", md)
        self.assertIn("| `--brand` | `%s` | `%s` | |" % (BRAND_PROPOSTO, self.spec["--brand"]), md)
        self.assertIn("| `--color-novo` | `#123456` |", md)
        self.assertIn("**diferente**", md)
        self.assertIn("ausente", md)
        self.assertIn("## Token a token", gravado, "--saida grava o mesmo markdown")
        self.assertNotIn("## Token a token", saida.getvalue(), "com --saida o terminal recebe só o resumo")

    def test_spec_e_a_mesa_do_root_sem_ferro_e_cobre_os_hex_que_a_suite_le(self):
        """`_spec()` lê o `:root` real. Ferro mora no mesmo bloco como
        `--ferro-*` e é o OUTRO regime — fora. E todo hex que
        `config.tests._tokens` enxerga ali está aqui com o mesmo valor: são
        duas leituras da mesma régua, e esta ainda pega o `rgba()` do fio."""
        from config.tests import _tokens
        spec = self.spec
        for nome in ("--bg", "--surface", "--text", "--brand", "--agua", "--fio"):
            with self.subTest(token=nome):
                self.assertIn(nome, spec)
        self.assertTrue(spec["--fio"].startswith("rgba("))
        self.assertFalse([n for n in spec if n.startswith("--ferro-")])
        css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
        for nome, valor in _tokens(css, ":root {").items():
            if nome.startswith("--ferro-"):
                continue
            with self.subTest(token=nome):
                self.assertEqual(spec.get(nome), valor)
        self.assertEqual(list(spec)[0], "--bg", "a ordem é a do :root, e o linho abre a paleta")

    def test_classificacao_e_a_da_triagem_da_task_8(self):
        """Task 8 e Task 11 precisam concordar sobre o que é interno, e a
        forma de concordar é ser a MESMA função — uma cópia local divergiria
        na primeira pasta nova que a triagem aprendesse a classificar."""
        inventario = importlib.import_module("scripts.inventariar_export")
        self.assertIs(self.m.classificar, inventario.classificar)
        # e a leitura obedece: `interno` fora, `incerto` dentro (um `src/theme.css`
        # não previsto é exatamente onde um export de estrutura estranha guardaria token)
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "src").mkdir()
            (raiz / "src" / "theme.css").write_text(":root { --brand: %s; }" % BRAND_PROPOSTO, encoding="utf-8")
            (raiz / "_ds_bundle.css").write_text(":root { --bg: #000000; }", encoding="utf-8")
            achados = self.m.extrair(raiz)
        self.assertEqual(inventario.classificar("src/theme.css"), "incerto")
        self.assertEqual(achados, {"--brand": {BRAND_PROPOSTO}})
