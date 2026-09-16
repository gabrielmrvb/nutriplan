# -*- coding: utf-8 -*-
"""Servidor lento não é rede caída — e a tela tem de dizer qual dos dois é.

Medido em produção em 16/09/2026 (avaliação, B6): o service worker tem
`PACIENCIA_MS = 3000` na navegação. Quando o servidor passa de três segundos
— e no plano gratuito ele passa: cold start, Neon acordando —, o worker
decide sozinho e em silêncio:

- rota em cache → entrega a CÓPIA VELHA sem aviso nenhum. A Home das 07:23
  saiu do cache com o saldo de antes, e a pessoa não tinha como saber;
- rota fora do cache → entrega o shell "Você está sem conexão", com o
  cabeçalho anônimo "Entrar / Criar conta", a uma sessão logada e online.

Três correções, uma por frase:

1. a página em cache avisa que pode estar desatualizada — o worker guarda a
   URL que serviu do cache, a página pergunta "de onde vim?" ao carregar, e o
   worker responde; quando a rede finalmente responde, ele avisa de novo e a
   faixa oferece "Atualizar";
2. o shell distingue "sem conexão" de "servidor acordando": com
   `navigator.onLine`, ele sonda `/saude/vivo/` (zero consulta) e recarrega
   sozinho quando o servidor responde;
3. o shell não oferece "Entrar" nem "Criar conta": ele é pré-cacheado sem
   identidade de propósito, e esses dois botões mentem para quem está logado.
"""
import re
from pathlib import Path

from django.test import TestCase

from plans.tests import create_complete_user
from push.test_cache_privado import sem_comentarios

RAIZ = Path(__file__).resolve().parent.parent


class OWorkerDizDeOndeAPaginaVeioTests(TestCase):
    def setUp(self):
        self.sw = sem_comentarios(self.client.get("/sw.js").content.decode())
        self.pwa = sem_comentarios((RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8"))

    def test_o_worker_registra_a_pagina_servida_do_cache_nos_dois_caminhos(self):
        """Paciência esgotada E rede caída: os dois entregam cache, os dois
        precisam marcar — com motivos diferentes, porque a frase é diferente."""
        self.assertIn("servidaDoCache(", self.sw)
        self.assertIn('"demora"', self.sw)
        self.assertIn('"sem-rede"', self.sw)

    def test_o_worker_responde_de_onde_a_pagina_veio(self):
        self.assertIn('"de-onde-vim"', self.sw)
        self.assertIn('"pagina-do-cache"', self.sw)

    def test_o_worker_avisa_quando_a_rede_responde_depois_do_cache(self):
        self.assertIn('"pagina-nova-disponivel"', self.sw)

    def test_a_pagina_pergunta_e_mostra_a_faixa(self):
        self.assertIn('"de-onde-vim"', self.pwa)
        self.assertIn('"pagina-do-cache"', self.pwa)
        self.assertIn('"pagina-nova-disponivel"', self.pwa)
        self.assertIn("data-aviso-cache", self.pwa)

    def test_toda_tela_traz_a_faixa_escondida(self):
        create_complete_user(email="cache@exemplo.com")
        self.client.login(username="cache@exemplo.com", password="senha-bem-forte-123")
        html = self.client.get("/").content.decode()
        self.assertRegex(html, r'<[a-z]+ class="flash[^"]*"[^>]*data-aviso-cache[^>]*hidden')
        self.assertIn("Atualizar", html)


class OShellDistingueServidorAcordandoDeSemConexaoTests(TestCase):
    def setUp(self):
        self.html = self.client.get("/offline/").content.decode()

    def test_o_shell_sonda_o_servidor_com_a_rota_sem_consulta(self):
        """`/saude/vivo/`, e não `/saude/`: a sonda roda a cada poucos segundos
        enquanto o servidor acorda, e `/saude/` consulta o banco."""
        self.assertIn("/saude/vivo/", self.html)
        self.assertNotIn('"/saude/"', self.html)

    def test_o_shell_tem_as_duas_frases_e_recarrega_sozinho(self):
        self.assertIn("Você está sem conexão", self.html)
        self.assertIn("acordando", self.html)
        self.assertIn("location.reload()", self.html)

    def test_o_shell_nao_oferece_entrar_nem_criar_conta(self):
        """Pré-cacheado sem identidade de propósito — e por isso não pode
        fingir que a pessoa é anônima: 'Entrar / Criar conta' para quem está
        logado é mentira, e sem rede os dois botões não levam a lugar nenhum."""
        cabecalho = self.html.split("<main", 1)[0]
        self.assertNotIn("Criar conta", cabecalho)
        self.assertNotIn(">Entrar<", cabecalho)
        # Controle positivo: a tela de entrada, que é anônima de verdade,
        # continua sem os botões pelo motivo dela (tela_de_entrada), e a
        # capa do demo, anônima e NÃO shell, continua com eles.
        demo = self.client.get("/demo/").content.decode().split("<main", 1)[0]
        self.assertIn("Criar conta", demo)


class OShellNaoApagaOCacheDePaginasTests(TestCase):
    """Achado durante o QA de B6 no navegador (16/09/2026): o shell sai com
    `data-autenticado="0"` — sem identidade de propósito —, e a "segunda
    camada" de `pwa.js` lê isso como "tela aberta sem sessão" e APAGA o cache
    de páginas. Ou seja: todo cold start em que o worker entregava o shell
    jogava fora as cópias que a pessoa logada tinha, e a próxima tela virava
    shell também. O shell não é prova de que a sessão acabou; ele só diz que
    o servidor não respondeu a tempo."""

    def test_o_shell_se_declara_shell_no_body(self):
        html = self.client.get("/offline/").content.decode()
        self.assertRegex(html, r"<body[^>]*data-shell-offline=\"1\"")
        normal = self.client.get("/conta/entrar/").content.decode()
        self.assertNotRegex(normal, r"<body[^>]*data-shell-offline=\"1\"")

    def test_a_segunda_camada_pula_o_shell(self):
        pwa = sem_comentarios((RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8"))
        segunda = pwa.split("limparPaginas();", 1)[0].rsplit("if (", 1)[1]
        self.assertIn('autenticado === "0"', segunda)
        self.assertIn("shellOffline", segunda)
