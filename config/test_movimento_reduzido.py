# -*- coding: utf-8 -*-
"""`prefers-reduced-motion` respeitado em TODA animação (21/09/2026).

`config/test_movimento.py` prende os três caminhos que animam por JS e o bloco
universal do CSS. Este arquivo é a régua SISTEMÁTICA — a que continua valendo
quando alguém escreve a próxima animação:

* CSS: o bloco universal (`*, *::before, *::after` a `.01ms`) existe e é o
  primeiro bloco reduzido do arquivo; e TODO seletor com `animation-delay`
  fora dos blocos reduzidos tem o atraso zerado (ou a animação desligada)
  dentro de um bloco reduzido — `.01ms` de duração não zera o atraso, e um
  cartão com `fill: both` fica invisível enquanto espera;
* JS: toda chamada a `.animate(`, `requestAnimationFrame(` ou rolagem
  `smooth` — em `static/js/*.js` e nos `<script>` dos templates — tem um
  gate `reduzido()`/`prefers-reduced-motion` ao alcance (nas 45 linhas
  acima, o corpo da função que anima);
* HTML: nenhum `<animate>`/`<animateTransform>` SMIL (o SMIL ignora a
  preferência) e nenhum `autoplay` escrito no HTML — o vídeo do exercício
  nasce no toque, por JS, e continua sendo o único.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
JANELA = 45


def sem_comentarios_css(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def blocos_reduzidos(css):
    """[(inicio, fim, corpo)] de cada `@media (prefers-reduced-motion: reduce) { ... }`."""
    saida = []
    for m in re.finditer(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{", css):
        nivel, i = 1, m.end()
        while nivel and i < len(css):
            nivel += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        saida.append((m.start(), i, css[m.end():i - 1]))
    return saida


def fora_dos_reduzidos(css):
    partes, cursor = [], 0
    for inicio, fim, _ in blocos_reduzidos(css):
        partes.append(css[cursor:inicio])
        cursor = fim
    partes.append(css[cursor:])
    return "".join(partes)


def regras(css):
    """[(seletor, corpo)] das regras de primeiro nível (e dentro de @media que não são reduzidos)."""
    return [(s.strip(), c) for s, c in re.findall(r"([^{}@;]+?)\s*\{([^{}]*)\}", css)]


class OCssRespeitaAPreferenciaTests(SimpleTestCase):
    def test_o_bloco_universal_e_o_primeiro_e_zera_duracao_e_transicao(self):
        css = sem_comentarios_css(CSS)
        primeiro = blocos_reduzidos(css)[0][2]
        self.assertRegex(primeiro, r"\*,\s*\*::before,\s*\*::after\s*\{[^}]*animation-duration:\s*\.01ms\s*!important")
        self.assertRegex(primeiro, r"transition-duration:\s*\.01ms\s*!important")

    def test_todo_atraso_de_animacao_e_zerado_para_quem_pediu_menos_movimento(self):
        css = sem_comentarios_css(CSS)
        reduzido = "\n".join(corpo for _, _, corpo in blocos_reduzidos(css))
        neutralizados = set()
        for seletor, corpo in regras(reduzido):
            if re.search(r"animation-delay:\s*0s|animation:\s*none", corpo):
                neutralizados.update(s.strip() for s in seletor.split(","))
        faltam = []
        for seletor, corpo in regras(fora_dos_reduzidos(css)):
            atraso = re.search(r"animation-delay:\s*([^;]+)", corpo)
            if not atraso or atraso.group(1).strip() in ("0s", "0", "0ms"):
                continue
            for s in (x.strip() for x in seletor.split(",")):
                if s not in neutralizados and not any(s.startswith(n) or n.startswith(s) for n in neutralizados):
                    faltam.append(s)
        self.assertEqual(faltam, [], "seletores com animation-delay sem saída em prefers-reduced-motion")

    def test_nenhuma_rolagem_suave_sem_saida(self):
        css = sem_comentarios_css(CSS)
        if "scroll-behavior: smooth" in fora_dos_reduzidos(css):
            reduzido = "\n".join(corpo for _, _, corpo in blocos_reduzidos(css))
            self.assertIn("scroll-behavior: auto", reduzido)


class OJavaScriptRespeitaAPreferenciaTests(SimpleTestCase):
    GATILHOS = re.compile(r"\.animate\(|requestAnimationFrame\(|behavior:\s*[\"']smooth[\"']")
    GATE = re.compile(r"reduzido\(\)|prefers-reduced-motion")

    def _fontes(self):
        for arquivo in sorted((RAIZ / "static" / "js").glob("*.js")):
            yield arquivo, arquivo.read_text(encoding="utf-8")
        for arquivo in sorted((RAIZ / "templates").rglob("*.html")):
            texto = arquivo.read_text(encoding="utf-8")
            for bloco in re.findall(r"<script\b[^>]*>(.*?)</script>", texto, re.S):
                yield arquivo, bloco

    def test_toda_animacao_por_js_tem_o_gate_ao_alcance(self):
        sem_gate, vistos = [], 0
        for arquivo, texto in self._fontes():
            linhas = texto.splitlines()
            for i, linha in enumerate(linhas):
                if not self.GATILHOS.search(linha) or linha.lstrip().startswith(("*", "//", "/*")):
                    continue
                vistos += 1
                # A janela para na função NOMEADA que contém a chamada
                # (`  function x(`): o gate da função vizinha não vale — a
                # sanfona de fechar passaria sem gate por estar a 40 linhas
                # da de abrir.
                inicio = max(0, i - JANELA)
                for j in range(i, inicio - 1, -1):
                    if re.match(r"^\s{0,2}function \w+\(", linhas[j]):
                        inicio = j
                        break
                janela = "\n".join(linhas[inicio:i + 1])
                if not self.GATE.search(janela):
                    sem_gate.append("%s:%d %s" % (arquivo.relative_to(RAIZ), i + 1, linha.strip()[:70]))
        self.assertGreater(vistos, 0, "controle positivo: existe animação por JS no app")
        self.assertEqual(sem_gate, [], "animação por JS sem `reduzido()`/prefers-reduced-motion ao alcance")

    def test_o_gate_le_a_preferencia_do_navegador(self):
        pwa = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")
        self.assertIn('matchMedia("(prefers-reduced-motion: reduce)").matches', pwa)


class OHtmlNaoAnimaPorContaPropriaTests(SimpleTestCase):
    def test_sem_smil_e_sem_autoplay_escrito_no_html(self):
        for arquivo in sorted((RAIZ / "templates").rglob("*.html")):
            texto = arquivo.read_text(encoding="utf-8")
            with self.subTest(arquivo=str(arquivo.relative_to(RAIZ))):
                self.assertNotRegex(texto, r"<animate(Transform|Motion)?\b", "SMIL ignora prefers-reduced-motion")
                self.assertNotRegex(texto, r"<(video|audio)\b[^>]*\bautoplay\b", "autoplay escrito no HTML anima sem perguntar")
