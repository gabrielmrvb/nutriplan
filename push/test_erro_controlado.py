# -*- coding: utf-8 -*-
"""`POST /tarefas/erro-controlado/`: a prova de que o Sentry recebe erro real.

`config/observabilidade.py` (`ligar_sentry`) fica mudo sem `SENTRY_DSN`, e
"funciona no código" não é a mesma coisa que "o evento aparece no painel". O
operador precisa, uma vez por troca de DSN, mandar um erro de VERDADE contra
um pedido de verdade em produção e ver o Sentry recebê-lo — sem esperar um
defeito de propósito para confirmar isso. A rota reusa o token e o portão de
`TarefaLembretesView` (`push.tarefas`) de propósito: sem o `Authorization`
certo ela não levanta nada, então vazar a URL não dá a ninguém um jeito de
derrubar o processo.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from push.tests import VAPID

TOKEN = "token-de-ensaio"
COM_TOKEN = dict(VAPID, NUTRIPLAN_TAREFAS_TOKEN=TOKEN)


@override_settings(**COM_TOKEN)
class OErroControladoTests(TestCase):
    def setUp(self):
        self.url = reverse("erro_controlado")

    def _post(self, token=TOKEN):
        extra = {"HTTP_AUTHORIZATION": "Bearer " + token} if token is not None else {}
        return self.client.post(self.url, **extra)

    def test_get_nao_e_aceito(self):
        """Só POST: ninguém navega para esta rota, e o GET não deve nem
        chegar perto do portão do token."""
        resposta = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer " + TOKEN)
        self.assertEqual(resposta.status_code, 405)

    def test_sem_header_e_403_e_nao_levanta_nada(self):
        """Sem `Authorization`, a rota é muda — nem chega a avaliar o token,
        muito menos a explodir."""
        resposta = self._post(token=None)
        self.assertEqual(resposta.status_code, 403)

    def test_token_errado_e_403(self):
        resposta = self._post(token="outro")
        self.assertEqual(resposta.status_code, 403)

    @override_settings(NUTRIPLAN_TAREFAS_TOKEN="")
    def test_sem_a_variavel_a_tarefa_nao_existe(self):
        """Igual à tarefa de lembretes: sem a variável é configuração
        ausente (503), não credencial errada (403)."""
        resposta = self._post()
        self.assertEqual(resposta.status_code, 503)

    def test_o_token_certo_levanta_o_erro_que_o_sentry_deve_capturar(self):
        """O cliente de teste do Django reergue a excepção da view (é o
        `raise_request_exception` padrão) — é assim que confirmamos que a
        rota de fato produz um erro de verdade, e não um 500 mudo."""
        with self.assertRaises(RuntimeError) as ctx:
            self._post()
        self.assertIn("Erro controlado", str(ctx.exception))
