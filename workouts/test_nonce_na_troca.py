# -*- coding: utf-8 -*-
"""O `<script>` recriado sem recarga continua valendo sob a CSP (24/09/2026).

MEDIDO no Chromium, conta de QA, servidor local com a CSP de produção:

| momento                              | `<script>` no `<main>` | com nonce |
|--------------------------------------|-----------------------:|----------:|
| carga inicial                        |                      3 |     **3** |
| depois de UMA série sem recarga      |                      3 |     **0** |

A CSP de 22/09/2026 é `script-src 'self' 'nonce-…'` **sem** `unsafe-inline`.
A troca do `<main>` recria cada `<script>` com `document.createElement` — que
é o que os faz rodar, porque `innerHTML` não executa script —, e o elemento
novo não herda nonce nenhum. Sob a política, o navegador recusa os três em
SILÊNCIO: atributo de evento e script sem nonce não dão erro visível, ficam
lá sem fazer nada.

O que a pessoa via, da primeira série em diante: "ver vídeo" na tela sem
abrir vídeo nenhum, os degraus de carga (−2,5 / +2,5) mortos e o relógio de
descanso congelado no número que o servidor mandou.

E por que isso passou despercebido: **a própria troca mora no `<main>`**.
Sem o nonce ela morria junto, o "Concluir série" seguinte voltava a ser um
POST com recarga — e a recarga consertava tudo. O defeito se apagava a cada
duas séries.

Não dá para copiar o nonce do nó `velho`: ele veio do HTML BUSCADO e carrega
o nonce DAQUELA resposta. Quem o navegador exige é o nonce DESTA página, e
ele é capturado em `document.currentScript.nonce` enquanto o script executa —
por isso a captura é de topo, e não dentro de um callback.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)
AGORA = RAIZ / "templates" / "workouts" / "agora.html"


def sem_comentarios(texto):
    """Este repositório comenta muito, e o comentário cita o nome da coisa
    que a asserção procura — ler o arquivo cru faria tudo "existir"."""
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


class OScriptRecriadoLevaONonceDaPaginaTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.codigo = sem_comentarios(AGORA.read_text(encoding="utf-8"))

    def test_a_pagina_guarda_o_proprio_nonce_no_topo_do_script(self):
        """`document.currentScript` é `null` dentro de qualquer callback: a
        captura tem de acontecer enquanto o script ainda executa."""
        self.assertRegex(
            self.codigo,
            r"var NONCE_DA_PAGINA\s*=\s*\(document\.currentScript\s*&&\s*"
            r"document\.currentScript\.nonce\)",
            "sem guardar o nonce desta resposta não há o que devolver aos "
            "scripts recriados",
        )
        # E a captura vem ANTES da troca, que é quem a consome.
        self.assertLess(
            self.codigo.index("NONCE_DA_PAGINA ="),
            self.codigo.index('createElement("script")'),
        )

    def test_a_troca_devolve_o_nonce_a_cada_script_recriado(self):
        recriacao = self.codigo[self.codigo.index('createElement("script")'):]
        recriacao = recriacao[:recriacao.index("velho.replaceWith(novo)")]
        self.assertIn(
            "novo.nonce = NONCE_DA_PAGINA", recriacao,
            "o script recriado sem nonce é recusado calado pela CSP",
        )

    def test_o_nonce_do_html_buscado_nao_e_copiado_como_atributo(self):
        """Ele é o nonce de OUTRA resposta. Copiá-lo é pior que não copiar
        nada: parece certo na inspeção e o navegador recusa igual."""
        recriacao = self.codigo[self.codigo.index('createElement("script")'):]
        recriacao = recriacao[:recriacao.index("velho.replaceWith(novo)")]
        self.assertRegex(
            recriacao, r'a\.name\s*!==\s*"nonce"',
            "ao copiar os atributos do nó velho, o `nonce` dele fica de fora",
        )


class NinguemMaisRecriaScriptSemONonceTests(SimpleTestCase):
    """A régua que vale na PRÓXIMA tela que trocar HTML por fetch.

    `config/test_csp.py` já varre `templates/` exigindo `nonce="{{ csp_nonce }}"`
    em todo `<script>` inline — mas ele lê o TEMPLATE, e um script criado em
    tempo de execução não passa por lá. É este o buraco que esta classe fecha.
    """

    def test_toda_recriacao_de_script_atribui_um_nonce(self):
        alvos = list((RAIZ / "templates").rglob("*.html"))
        alvos += list((RAIZ / "static" / "js").rglob("*.js"))
        faltando = []
        for caminho in alvos:
            codigo = sem_comentarios(caminho.read_text(encoding="utf-8"))
            for m in re.finditer(r'createElement\(\s*["\']script["\']\s*\)', codigo):
                # A janela é generosa de propósito: o que importa é que a
                # atribuição do nonce ande junto da criação.
                janela = codigo[m.start():m.start() + 800]
                if ".nonce" not in janela:
                    faltando.append("%s:%d" % (
                        caminho.relative_to(RAIZ),
                        codigo[:m.start()].count("\n") + 1,
                    ))
        self.assertEqual(
            faltando, [],
            "script criado em tempo de execução sem nonce não roda sob a CSP, "
            "e não dá erro visível: %s" % faltando,
        )
