"""A sessão de quem usa o app não vence no meio do uso.

O `SESSION_COOKIE_AGE` do Django (14 dias) conta do LOGIN, não do último
uso: quem entra todo dia é deslogado a cada duas semanas, do nada, no
meio de um formulário — e é exatamente a "queda de sessão sem aviso" do
item 2 da missão de UX (22/09/2026). `SESSION_SAVE_EVERY_REQUEST` renova
a cada pedido, mas grava a sessão em TODA resposta — uma escrita a mais
em cada tela, contra o orçamento de consultas. `config.sessao.
RenovarSessaoMiddleware` renova só quando passou da METADE da vida: uma
escrita por semana, para quem usa; quem some por 14 dias continua saindo.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User


class SessaoRenovadaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sessao@exemplo.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)

    def _vencimento(self):
        return Session.objects.get(session_key=self.client.session.session_key).expire_date

    def _envelhecer(self, dias):
        """A sessão passa a vencer daqui a `dias` — a data dentro dela (que é
        o que o middleware lê) e a linha do banco."""
        sessao = self.client.session
        quase = timezone.now() + timedelta(days=dias)
        sessao.set_expiry(quase)
        sessao.save()
        return quase

    def test_a_sessao_velha_e_renovada_ao_usar(self):
        quase = self._envelhecer(3)
        self.client.get(reverse("accounts:login"))
        renovado = self._vencimento()
        self.assertGreater(renovado, quase + timedelta(days=9))
        self.assertLessEqual(renovado, timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE + 60))

    def test_a_sessao_nova_nao_e_reescrita(self):
        """Metade da vida é a régua: sessão com 10 dias pela frente não paga
        a escrita."""
        quase = self._envelhecer(10)
        self.client.get(reverse("accounts:login"))
        self.assertLess(abs((self._vencimento() - quase).total_seconds()), 5)

    def test_o_login_ja_grava_a_data_na_sessao(self):
        """Sem a data dentro da sessão o middleware não tem como saber quanto
        falta (a linha do banco custaria uma consulta): o login a grava — na
        escrita que o login já faz, e não numa segunda na primeira tela."""
        self.assertIsNotNone(self.client.session.get("_session_expiry"))

    def test_sessao_de_antes_do_deploy_ganha_a_data_na_primeira_passagem(self):
        sessao = self.client.session
        del sessao["_session_expiry"]
        sessao.save()
        self.client.get(reverse("accounts:login"))
        self.assertIsNotNone(self.client.session.get("_session_expiry"))

    def test_sem_sessao_nada_acontece(self):
        self.client.logout()
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)

    def test_o_middleware_esta_ligado_depois_da_sessao(self):
        lista = settings.MIDDLEWARE
        self.assertIn("config.sessao.RenovarSessaoMiddleware", lista)
        self.assertGreater(lista.index("config.sessao.RenovarSessaoMiddleware"), lista.index("django.contrib.sessions.middleware.SessionMiddleware"))
