# -*- coding: utf-8 -*-
"""Teclado aberto recolhe a barra de abas; um flutuante por vez (decisão do
dono, 20/09/2026).

Dois achados da auditoria de 20/09, os dois no rodapé do celular:

1. com o teclado aberto sobram ~450 px a 390, e a barra de abas fixa ocupa
   68 deles — medido em Progresso, Lista e Corrida manual;
2. três camadas fixas podem se empilhar na mesma borda: o convite de
   instalação, o toast de conquista e a barra.

A resposta mora em dois arquivos que o navegador executa e o teste só lê —
o comportamento de verdade é provado no navegador (agent-browser, no PR).
O que se prende aqui é a ESTRUTURA: o gancho existe e escreve a classe
certa, a classe recolhe a barra e o convite, e o convite cede ao toast.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
JS = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8")


def _sem_comentarios(texto):
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"^\s*//.*$", "", texto, flags=re.M)


class TecladoAbertoRecolheABarraTests(SimpleTestCase):
    def test_o_foco_num_campo_que_abre_teclado_marca_o_corpo(self):
        js = _sem_comentarios(JS)
        self.assertIn('document.addEventListener("focusin"', js)
        self.assertIn('document.addEventListener("focusout"', js)
        self.assertIn('classList.add("teclado-aberto")', js)
        self.assertIn('classList.remove("teclado-aberto")', js)

    def test_so_campo_de_texto_conta(self):
        """Botão, rádio, caixa e `range` recebem foco e não abrem teclado; a
        barra não pode sumir quando a pessoa toca num rádio do onboarding."""
        js = _sem_comentarios(JS)
        inicio = js.index("var ABRE_TECLADO")
        corpo = js[inicio:js.index('document.addEventListener("focusin"', inicio)]
        self.assertIn("TEXTAREA", corpo)
        for tipo in ("text", "search", "email", "number", "password", "tel", "url"):
            self.assertIn(tipo, corpo)
        for tipo in ("radio", "checkbox", "range", "submit"):
            self.assertNotIn(tipo, corpo)

    def test_a_classe_recolhe_a_barra_e_o_convite(self):
        css = _sem_comentarios(CSS)
        barra = re.search(r"\.teclado-aberto \.tabbar \{([^}]*)\}", css)
        self.assertIsNotNone(barra, ".teclado-aberto .tabbar precisa existir")
        self.assertIn("transform: translateY(", barra.group(1))
        self.assertIn("var(--mov-estado) var(--ease)", barra.group(1), "a volta anima com o token de estado e a curva da casa, não com número solto")
        convite = re.search(r"\.teclado-aberto \.install \{([^}]*)\}", css)
        self.assertIsNotNone(convite)
        self.assertIn("display: none", convite.group(1))
        # e o container devolve o respiro que reservava para a barra
        self.assertRegex(css, r"\.teclado-aberto \.container \{[^}]*padding-bottom: var\(--espaco-")


class UmFlutuantePorVezTests(SimpleTestCase):
    def test_o_convite_de_instalacao_cede_ao_toast_de_conquista(self):
        """`horaRuim()` já recusava a execução e o vídeo; agora também recusa
        enquanto um `.conquista` está na tela — o toast é a notícia, o
        convite espera a próxima página."""
        js = _sem_comentarios(JS)
        inicio = js.index("function horaRuim()")
        corpo = js[inicio:js.index("function mostrar()", inicio)]
        self.assertIn('querySelector(".conquista")', corpo)
        self.assertIn("data-sem-convite", corpo)
        self.assertIn("dialog[open]", corpo)
