# -*- coding: utf-8 -*-
"""A CSP existe, é estrita no script, e nenhum `<script>` inline fica de fora.

ACHADO DE SEGURANÇA da auditoria de 22/09/2026: o app não mandava
`Content-Security-Policy` em rota nenhuma. CSP não conserta XSS; ela limita
o estrago de um que exista — e num app que guarda peso, altura e histórico
de treino esse limite vale o trabalho.

O teste que mais importa aqui é o de VARREDURA: ele lê `templates/` e cobra
que todo `<script>` inline carregue `nonce="{{ csp_nonce }}"`. Sem ele, o
próximo `<script>` inline escrito neste repositório simplesmente não roda em
produção, e ninguém descobre até a tela quebrar.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

TEMPLATES = Path(settings.BASE_DIR, "templates")
#: `{% comment %}…{% endcomment %}` e `{# … #}`: este repositório comenta
#: muito, e os comentários CITAM as tags de que falam.
COMENTARIO = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}", re.S)
ABERTURA = re.compile(r"<script\b[^>]*>", re.I)


def sem_comentarios(texto: str) -> str:
    return COMENTARIO.sub("", texto)


class APoliticaChegaNaRespostaTests(TestCase):
    def test_toda_tela_manda_a_politica(self):
        for rota in ("/", reverse("accounts:login"), reverse("ajuda:index")):
            with self.subTest(rota=rota):
                politica = self.client.get(rota).headers.get("Content-Security-Policy", "")
                self.assertIn("default-src 'self'", politica)
                self.assertIn("frame-ancestors 'none'", politica)

    def test_o_script_nao_aceita_inline(self):
        """`'unsafe-inline'` em `script-src` é o que transforma a política em
        enfeite — é exatamente o que um XSS injetado usaria."""
        politica = self.client.get("/").headers["Content-Security-Policy"]
        script = [d for d in politica.split("; ") if d.startswith("script-src")][0]
        self.assertNotIn("unsafe-inline", script)
        self.assertNotIn("unsafe-eval", script)
        self.assertIn("nonce-", script)

    def test_o_nonce_muda_a_cada_resposta(self):
        """Nonce repetido é nonce nenhum: bastaria ler o HTML de uma página
        para escrever um `<script>` que passa na próxima."""
        um = self.client.get("/").headers["Content-Security-Policy"]
        outro = self.client.get("/").headers["Content-Security-Policy"]
        self.assertNotEqual(um, outro)

    def test_o_script_da_pagina_leva_o_nonce_do_cabecalho(self):
        resposta = self.client.get("/")
        nonce = re.search(r"'nonce-([^']+)'", resposta.headers["Content-Security-Policy"]).group(1)
        html = resposta.content.decode("utf-8")
        for tag in ABERTURA.findall(sem_comentarios(html)):
            if "src=" in tag:
                continue
            self.assertIn(nonce, tag, "script inline sem o nonce desta resposta: %s" % tag[:120])

    def test_a_casca_nativa_nao_recebe_a_politica(self):
        """O Capacitor injeta a própria ponte no WebView e não conhece o nosso
        nonce. A marca é do User-Agent de QUEM PEDE — um XSS no navegador da
        vítima não muda o User-Agent dela, então isto não é uma porta."""
        resposta = self.client.get("/", headers={"user-agent": "Mozilla/5.0 NutriPlanNativo/1.0"})
        self.assertNotIn("Content-Security-Policy", resposta.headers)


class NenhumScriptInlineFicaDeForaTests(TestCase):
    """A varredura: a régua que vale para o `<script>` que ainda não existe."""

    def _arquivos(self):
        return sorted(TEMPLATES.rglob("*.html"))

    def test_todo_script_inline_de_template_leva_o_nonce(self):
        faltando = []
        for arquivo in self._arquivos():
            texto = sem_comentarios(arquivo.read_text(encoding="utf-8"))
            for tag in ABERTURA.findall(texto):
                if "src=" in tag or "csp_nonce" in tag:
                    continue
                faltando.append("%s: %s" % (arquivo.relative_to(TEMPLATES), tag[:80]))
        self.assertEqual(faltando, [], "script inline sem nonce (não vai rodar em produção): %s" % faltando)

    def test_nenhum_atributo_de_evento_inline(self):
        """`onclick=` e parentes param de funcionar com a política ligada, e
        param em SILÊNCIO: o botão fica lá e não faz nada. Quatro existiam
        quando a CSP entrou (403 de CSRF, Perfil, gestão e a tela offline) e
        viraram ouvinte."""
        atributo = re.compile(r"\son(click|submit|change|input|load|error|focus|blur)\s*=", re.I)
        achados = []
        for arquivo in self._arquivos():
            texto = sem_comentarios(arquivo.read_text(encoding="utf-8"))
            for linha, conteudo in enumerate(texto.splitlines(), 1):
                if atributo.search(conteudo):
                    achados.append("%s:%d" % (arquivo.relative_to(TEMPLATES), linha))
        self.assertEqual(achados, [], "handler inline não roda sob CSP: %s" % achados)
