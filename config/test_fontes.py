# -*- coding: utf-8 -*-
"""Duas fontes próprias, com regra de uso e gate de tamanho (CORTE, T3.2).

Big Shoulders Display é a DISPLAY e Archivo é o TEXTO (`DESIGN.md`,
"Tipografia" — NERVURA, 17/09/2026; foram Bodoni Moda e Karla na CORTE). O
que este arquivo prende: os dois `.woff2` existem em `static/fonts/` e
cabem no gate de 260 KB; o `@font-face` de cada uma tem `font-display:
swap` e o `unicode-range` do latin; `--font` abre com Archivo e
`--font-display` com Big Shoulders Display; a display SÓ aparece em regra
cujo tamanho é herói (≥ 20 px: `--texto-xl` para cima, ou o `1.42rem` do
nome), em caixa alta 800 nos títulos e 900 nos números; só os pesos do
contrato (400 · 500 · 600 · 700 no texto, 800 · 900 na display); a licença OFL está ao
lado dos arquivos; o service worker pré-cacheia as duas; e, quando o
fontTools está instalado (`requirements-dev.txt`), as tabelas confirmam
eixo variável e `tnum` — número tabular é o que faz a coluna de carga
alinhar, e uma fonte sem ele passaria em todo teste visual e desalinharia
em produção.
"""
import re
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.test_design_system import CSS, sem_comentarios

FONTES = Path(settings.BASE_DIR) / "static" / "fonts"
ARQUIVOS = ("big-shoulders-display-latin.woff2", "archivo-latin.woff2")
GATE = 260 * 1024

#: Tamanhos que valem como herói para a display (≥ 20 px). `1.42rem` é o
#: nome da refeição/do exercício (22,7 px) e `1.6rem` o número do anel na
#: tela de 22rem (25,6 px) — valores crus que já existiam.
TAMANHOS_DE_HEROI = ("var(--texto-xl)", "var(--texto-2xl)", "var(--texto-3xl)", "var(--texto-heroi)", "var(--texto-display)", "1.42rem", "1.6rem", "min(var(--texto-2xl)")


def _regras(css):
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield m.group(1).strip(), m.group(2)


class OsArquivosTests(SimpleTestCase):
    def test_existem_e_cabem_no_gate(self):
        total = 0
        for nome in ARQUIVOS:
            arquivo = FONTES / nome
            with self.subTest(arquivo=nome):
                self.assertTrue(arquivo.is_file(), arquivo)
                self.assertGreater(arquivo.stat().st_size, 10_000, "arquivo vazio ou truncado")
            total += arquivo.stat().st_size
        self.assertLessEqual(total, GATE, f"as fontes somam {total} bytes; o gate é {GATE}")

    def test_a_licenca_esta_ao_lado(self):
        for nome in ("OFL-big-shoulders-display.txt", "OFL-archivo.txt"):
            with self.subTest(arquivo=nome):
                texto = (FONTES / nome).read_text(encoding="utf-8")
                self.assertIn("SIL Open Font License, Version 1.1", texto)
        self.assertIn("Big Shoulders", (FONTES / "OFL-big-shoulders-display.txt").read_text(encoding="utf-8"))
        self.assertIn("Archivo", (FONTES / "OFL-archivo.txt").read_text(encoding="utf-8"))

    def test_nenhum_arquivo_alem_dos_declarados(self):
        """A pasta é fechada: a itálica da Bodoni ficou de fora de propósito
        (sem consumidor), e um terceiro arquivo entra por aqui, com teste."""
        extras = sorted(p.name for p in FONTES.iterdir() if p.suffix == ".woff2" and p.name not in ARQUIVOS)
        self.assertEqual(extras, [])


class OFontFaceTests(SimpleTestCase):
    def setUp(self):
        self.css = sem_comentarios(CSS.read_text(encoding="utf-8"))
        self.faces = re.findall(r"@font-face\s*\{([^}]*)\}", self.css)

    def test_as_duas_familias_com_swap_e_latin(self):
        self.assertEqual(len(self.faces), 2, "uma @font-face por família — variável, um arquivo por família")
        familias = {re.search(r'font-family:\s*"([^"]+)"', f).group(1) for f in self.faces}
        self.assertEqual(familias, {"Big Shoulders Display", "Archivo"})
        for face in self.faces:
            with self.subTest(face=face.strip()[:40]):
                self.assertIn("font-display: swap", face)
                self.assertRegex(face, r'src:\s*url\("\.\./fonts/[a-z-]+\.woff2"\)\s*format\("woff2"\)')
                self.assertIn("unicode-range: U+0000-00FF", face)
                self.assertRegex(face, r"font-weight:\s*100 900", "peso variável, um arquivo por família")

    def test_os_tokens_de_familia(self):
        raiz = self.css.split(":root {", 1)[1].split("\n}", 1)[0]
        self.assertRegex(raiz, r'--font:\s*"Archivo",\s*system-ui')
        self.assertRegex(raiz, r'--font-display:\s*"Big Shoulders Display",')
        self.assertNotIn("fonts.googleapis.com", self.css)

    def test_a_display_so_aparece_em_regra_de_heroi(self):
        """Bodoni nunca abaixo de 20 px: toda regra que a pede declara um
        tamanho de herói na mesma regra (ou é a segunda regra do mesmo
        seletor, que herda o tamanho da primeira)."""
        com_display = [(sel, corpo) for sel, corpo in _regras(self.css) if "var(--font-display)" in corpo]
        self.assertGreaterEqual(len(com_display), 8, "a display sumiu dos heróis")
        seletores = {sel for sel, _ in com_display}
        tamanhos = {}
        for sel, corpo in _regras(self.css):
            fs = re.search(r"font-size:\s*([^;]+);", corpo)
            if fs and sel in seletores:
                tamanhos.setdefault(sel, []).append(fs.group(1).strip())
        for sel in sorted(seletores):
            with self.subTest(seletor=sel):
                self.assertIn(sel, tamanhos, "regra de display sem tamanho declarado em regra nenhuma")
                for tamanho in tamanhos[sel]:
                    self.assertTrue(tamanho.startswith(TAMANHOS_DE_HEROI), f"{sel}: {tamanho} é menor que herói")

    def test_os_titulos_e_os_nomes_sao_display_em_caixa_alta(self):
        """A Big Shoulders é feita para caixa alta: título e nome vão em
        `uppercase` e 800; o número herói em 900."""
        for sel in ("h1", ".hoje__nome", ".agora__titulo", ".agora__nome", ".series__titulo"):
            with self.subTest(seletor=sel):
                regras = [corpo for s, corpo in _regras(self.css) if s == sel]
                self.assertTrue(any("var(--font-display)" in c for c in regras), f"{sel} não é display")
                self.assertTrue(any("text-transform: uppercase" in c for c in regras), f"{sel} não é caixa alta")
                self.assertTrue(any("font-weight: 800" in c for c in regras), f"{sel} não é 800")
        for sel in (".ring__value", ".curva__valor", ".tile__value", ".recompensa__numero"):
            with self.subTest(seletor=sel):
                regras = [corpo for s, corpo in _regras(self.css) if s == sel]
                self.assertTrue(any("var(--font-display)" in c and "font-weight: 900" in c for c in regras), f"{sel} não é display 900")

    def test_coluna_de_numeros_e_texto_tabular(self):
        """A Big Shoulders não tem `tnum` (dígitos proporcionais, medido): a
        lista de pesagens — uma COLUNA de números — fica em Archivo."""
        regras = [corpo for s, corpo in _regras(self.css) if s == ".pesagem__media"]
        self.assertTrue(regras)
        self.assertTrue(all("var(--font-display)" not in c for c in regras), ".pesagem__media voltou para a display")
        self.assertTrue(any("var(--font)" in c for c in regras))

    def test_o_filho_pequeno_do_heroi_volta_para_a_fonte_de_texto(self):
        """Herdar é o caminho que a régua das regras não vê: `.series__faixa`
        ("6-10 reps", 12,8 px) mora DENTRO do "SÉRIE 2 DE 4" e herdava a
        Big Shoulders — visto na captura da execução em 17/09/2026. Todo
        filho pequeno de um herói declara a fonte de texto de volta."""
        for sel in (".series__faixa",):
            with self.subTest(seletor=sel):
                regras = [corpo for s, corpo in _regras(self.css) if s == sel]
                self.assertTrue(regras, f"{sel} sem regra")
                self.assertTrue(any(re.search(r"font-family:\s*var\(--font\)", c) for c in regras), f"{sel} herda a display")

    def test_so_os_pesos_do_contrato(self):
        # Um valor só, seguido de `;`: o `100 900` do @font-face é faixa, não peso.
        pesos = sorted({int(p) for p in re.findall(r"font-weight:\s*(\d+)\s*;", self.css)})
        # Archivo 400/500/600/700, Big Shoulders 800/900 (DESIGN.md, "Tipografia");
        # 400 é o padrão do navegador e não precisa ser escrito.
        self.assertTrue(pesos and set(pesos) <= {400, 500, 600, 700, 800, 900}, pesos)


class OServiceWorkerPreCacheiaTests(SimpleTestCase):
    def test_as_duas_fontes_entram_no_shell(self):
        from django.test import Client

        fonte = Client().get("/sw.js").content.decode()
        for nome in ARQUIVOS:
            with self.subTest(arquivo=nome):
                self.assertIn("fonts/" + nome, fonte)


try:
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover — o CI instala só requirements.txt
    TTFont = None


@unittest.skipIf(TTFont is None, "fontTools não instalado (requirements-dev)")
class AsTabelasDasFontesTests(SimpleTestCase):
    """Medido com fontTools, quando ele existe: eixo de peso variável nas
    duas; `tnum` na Archivo — a Big Shoulders NÃO tem, e é por isso que a
    display só serve ao número solto (`test_coluna_de_numeros_e_texto_tabular`)."""

    def _fonte(self, nome):
        return TTFont(str(FONTES / nome))

    def test_eixos_e_tnum(self):
        for nome, tnum in (("big-shoulders-display-latin.woff2", False), ("archivo-latin.woff2", True)):
            with self.subTest(fonte=nome):
                fonte = self._fonte(nome)
                self.assertEqual({a.axisTag for a in fonte["fvar"].axes}, {"wght"})
                feats = {fr.FeatureTag for fr in fonte["GSUB"].table.FeatureList.FeatureRecord}
                self.assertEqual("tnum" in feats, tnum, "a regra da coluna existe porque isto é verdade; se mudar, revise a regra")

    def test_cobrem_o_portugues(self):
        for nome in ARQUIVOS:
            cmap = self._fonte(nome).getBestCmap()
            faltam = [c for c in "ãçéíóúâêôàüÃÇÉÍÓÚÂÊÔÀ0123456789,.–—%×" if ord(c) not in cmap]
            with self.subTest(fonte=nome):
                self.assertEqual(faltam, [])
