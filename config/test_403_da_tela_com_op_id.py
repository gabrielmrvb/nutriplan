"""O 403 de CSRF de um formulário que carrega `op_id` — água, série,
refeição, corrida — enviado PELA TELA tem de ser a página em português, e
não o JSON de "replay preservado".

Achado da Fase 0 da missão Capacitor (22/09/2026), MEDIDO no staging com o
agent-browser: a corrida enviada com token velho (a mesma conta entrou de
novo noutra aba) devolvia a tela inteira em
`{"code": "replay_offline_csrf_expirado", ...}` — o texto cru, sem botão
de voltar, e o digitado perdido. `falha_de_csrf` decidia "é replay" só por
`op_id` no corpo, e o caminho ONLINE carimba o mesmo `op_id` (é o que faz
toque duplo e botão voltar corrigirem em vez de duplicar). O que distingue
a DRENAGEM é o cabeçalho `X-NutriPlan-Replay` (fila.js e sw.js mandam) —
e, para o cliente publicado antes dele, o fato de ser `fetch`: um envio
de formulário pela pessoa é NAVEGAÇÃO (`Sec-Fetch-Dest: document`, ou
`Accept: text/html` em navegador sem Sec-Fetch).
"""
from django.test import Client, TestCase

from accounts.replay import CODIGO_CSRF_VELHO, CODIGO_SEM_DONO, STATUS_PRESERVA
from plans.tests import create_complete_user


class OFormularioComOpIdEnviadoPelaTelaTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="tela@exemplo.com")
        self.c = Client(enforce_csrf_checks=True)
        self.c.force_login(self.user)

    def _post(self, **cabecalhos):
        return self.c.post(
            "/agua/",
            {"ml": "250", "op_id": "op-da-pagina", "csrfmiddlewaretoken": "token-velho-de-outra-aba"},
            **cabecalhos,
        )

    def test_a_navegacao_do_navegador_ve_a_pagina_em_portugues(self):
        resposta = self._post(HTTP_SEC_FETCH_DEST="document", HTTP_ACCEPT="text/html,application/xhtml+xml")
        self.assertEqual(resposta.status_code, 403)
        html = resposta.content.decode()
        self.assertIn("não pôde ser confirmado", html)
        # A saída é `history.back()` — mas desde a CSP (22/09/2026) ele mora
        # no ouvinte de `pwa.js`, e o HTML só traz o marcador: atributo
        # `onclick=` não roda com a política ligada, e não roda em silêncio.
        self.assertIn("data-voltar", html)
        self.assertNotIn("replay_offline_csrf_expirado", html)

    def test_navegador_sem_sec_fetch_e_reconhecido_pelo_accept(self):
        resposta = self._post(HTTP_ACCEPT="text/html,application/xhtml+xml,*/*;q=0.8")
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("não pôde ser confirmado", resposta.content.decode())

    def test_a_drenagem_da_fila_continua_preservada(self):
        """Controle: o `fetch` da fila (cabeçalho de replay) e o cliente
        publicado (`fetch` sem o cabeçalho, sem Accept de documento) continuam
        recebendo a resposta que não os faz apagar o item."""
        for cabecalhos in ({"HTTP_X_NUTRIPLAN_REPLAY": "1", "HTTP_SEC_FETCH_DEST": "empty"},
                           {"HTTP_X_REQUESTED_WITH": "fetch"},
                           {"HTTP_SEC_FETCH_DEST": "empty", "HTTP_ACCEPT": "*/*"}):
            with self.subTest(cabecalhos=cabecalhos):
                resposta = self._post(**cabecalhos)
                self.assertEqual(resposta.status_code, STATUS_PRESERVA)
                # com o cabeçalho de replay e sem dono, quem responde é a
                # barreira (antes do CSRF); os outros dois chegam ao CSRF
                self.assertIn(resposta.json()["code"], (CODIGO_CSRF_VELHO, CODIGO_SEM_DONO))


class ASessaoQueVenceuComOFormularioAbertoTests(TestCase):
    """A outra cara do mesmo achado: sessão vencida, formulário com `op_id`
    enviado pela tela. A barreira de replay via `op_id` sem sessão e
    respondia o JSON de "preservado" — a pessoa recebia um texto técnico em
    vez do redirect para entrar (e o rascunho devolve o digitado depois)."""

    def test_a_navegacao_sem_sessao_vai_para_o_login_como_qualquer_formulario(self):
        c = Client()
        resposta = c.post("/agua/", {"ml": "250", "op_id": "op-da-pagina"},
                          HTTP_SEC_FETCH_DEST="document", HTTP_ACCEPT="text/html")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/entrar/", resposta["Location"])

    def test_o_fetch_da_fila_sem_sessao_continua_preservado(self):
        c = Client()
        resposta = c.post("/agua/", {"ml": "250", "op_id": "op-da-fila"},
                          HTTP_X_NUTRIPLAN_REPLAY="1", HTTP_SEC_FETCH_DEST="empty")
        self.assertEqual(resposta.status_code, STATUS_PRESERVA)
