"""Replay da fila offline: as duas gerações de cliente, e nenhuma perda.

O que estes testes protegem, na ordem em que a medição os produziu:

1. o cliente PUBLICADO continua sincronizando quando o CSRF dele é válido —
   recusá-lo por não enviar dono quebraria a fila de todo mundo que ainda não
   recarregou a página, e foi o que a primeira versão desta camada fez;

2. nenhuma resposta faz o cliente publicado APAGAR uma operação que ainda pode
   ser aplicada. Ele remove em qualquer 4xx, e a medição mostrou que o CSRF
   velho gerava 403 — perdendo a marcação inclusive quando a mesma pessoa
   apenas saía e voltava;

3. o cliente NOVO declara o dono, e o servidor usa isso como pré-condição:
   nunca como endereço. Destino é sempre `request.user`.
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from accounts.models import SyncedOperation
from accounts.replay import (
    CODIGO_CSRF_VELHO,
    CODIGO_OUTRA_SESSAO,
    CODIGO_SEM_SESSAO,
    STATUS_PRESERVA,
)
from plans.models import HydrationLog
from plans.tests import create_complete_user

User = get_user_model()
RAIZ = Path(__file__).resolve().parent.parent


def cliente_publicado_apagaria(resposta) -> bool:
    """A regra exata do `drenar()` que está em produção hoje."""
    return resposta.status_code < 400 or 400 <= resposta.status_code < 500


class ClientePublicadoTests(TestCase):
    """A geração antiga: manda `op_id`, não manda dono, apaga em 4xx."""

    def setUp(self):
        self.a = create_complete_user(email="pub-a@exemplo.com")
        self.b = create_complete_user(email="pub-b@exemplo.com")
        self.c = Client(enforce_csrf_checks=True)

    def _entrar(self, quem):
        self.c.force_login(quem)
        self.c.get("/")
        return self.c.cookies["csrftoken"].value

    def _replay(self, token, op_id="op-legada", ml=250):
        return self.c.post(
            "/agua/",
            {"ml": str(ml), "op_id": op_id, "csrfmiddlewaretoken": token},
            HTTP_X_REQUESTED_WITH="fetch",
            follow=True,
        )

    def test_com_csrf_valido_continua_sincronizando(self):
        """O contrato que a primeira versão desta camada quebrou. Recusar
        replay sem dono derrubava a fila de todo cliente publicado."""
        token = self._entrar(self.a)

        resposta = self._replay(token)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(HydrationLog.objects.get(user=self.a).ml, 250)

    def test_com_csrf_velho_o_item_e_preservado(self):
        """O bug comprovado: `login()` rotaciona o token, o CSRF responde 403,
        e o cliente publicado apaga em 4xx."""
        token_velho = self._entrar(self.a)
        self.c.logout()
        self._entrar(self.a)

        resposta = self._replay(token_velho)

        self.assertEqual(resposta.status_code, STATUS_PRESERVA)
        self.assertEqual(resposta.json()["code"], CODIGO_CSRF_VELHO)
        self.assertFalse(cliente_publicado_apagaria(resposta))
        self.assertFalse(HydrationLog.objects.exists())

    def test_de_a_para_b_com_csrf_velho_nao_muta_ninguem(self):
        token_de_a = self._entrar(self.a)
        self.c.logout()
        self._entrar(self.b)

        resposta = self._replay(token_de_a)

        self.assertFalse(HydrationLog.objects.exists())
        self.assertFalse(SyncedOperation.objects.exists())
        self.assertFalse(cliente_publicado_apagaria(resposta))

    def test_anonimo_nao_vira_redirect_para_o_login(self):
        """`login_required` responde 302; o cliente publicado segue até a tela
        de login, que devolve 200, e a regra dele lê isso como sucesso."""
        token = self._entrar(self.a)
        self.c.logout()

        resposta = self._replay(token)

        self.assertEqual(resposta.redirect_chain, [])
        self.assertEqual(resposta.status_code, STATUS_PRESERVA)
        self.assertFalse(cliente_publicado_apagaria(resposta))

    def test_post_normal_da_tela_nao_e_afetado(self):
        """Controle: sem `op_id` é a pessoa tocando o botão, e o CSRF errado
        precisa continuar dando 403 como sempre deu."""
        self._entrar(self.a)

        resposta = self.c.post(
            "/agua/", {"ml": "250", "csrfmiddlewaretoken": "token-invalido"}
        )

        self.assertEqual(resposta.status_code, 403)


class ClienteNovoTests(TestCase):
    """A geração nova: declara o dono e renova o CSRF."""

    def setUp(self):
        self.a = create_complete_user(email="novo-a@exemplo.com")
        self.b = create_complete_user(email="novo-b@exemplo.com")
        self.c = Client(enforce_csrf_checks=True)

    def _entrar(self, quem):
        self.c.force_login(quem)
        self.c.get("/")
        return self.c.cookies["csrftoken"].value

    def _replay(self, token, dono, op_id="op-nova", ml=250):
        return self.c.post(
            "/agua/",
            {"ml": str(ml), "op_id": op_id, "csrfmiddlewaretoken": token},
            HTTP_X_REQUESTED_WITH="fetch",
            HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(dono),
            follow=True,
        )

    def test_dono_certo_e_csrf_atual_sincroniza(self):
        token = self._entrar(self.a)

        resposta = self._replay(token, dono=self.a.pk)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(HydrationLog.objects.get(user=self.a).ml, 250)
        self.assertTrue(
            SyncedOperation.objects.filter(user=self.a, op_id="op-nova").exists()
        )

    def test_dono_de_outra_pessoa_nao_muta_nada(self):
        """A aba velha de A com a sessão de B, que é o cenário cross-tab."""
        self._entrar(self.b)
        token_de_b = self.c.cookies["csrftoken"].value

        resposta = self._replay(token_de_b, dono=self.a.pk)

        self.assertEqual(resposta.status_code, STATUS_PRESERVA)
        self.assertEqual(resposta.json()["code"], CODIGO_OUTRA_SESSAO)
        self.assertFalse(HydrationLog.objects.exists())
        self.assertFalse(SyncedOperation.objects.exists())

    def test_a_recusa_por_dono_nao_marca_idempotencia(self):
        """Marcar antes de validar deixaria a conta CERTA sem reenviar: o
        servidor lembraria de um `op_id` que nunca foi aplicado."""
        self._entrar(self.b)
        token = self.c.cookies["csrftoken"].value

        self._replay(token, dono=self.a.pk)

        self.assertFalse(SyncedOperation.objects.exists())

    def test_sem_sessao_preserva(self):
        """Com o token ATUAL do anônimo, para medir a camada de sessão.

        Sair também rotaciona o CSRF, então usar o token de antes faria o
        pedido morrer na camada anterior — o teste passaria pelo motivo errado
        e nunca exercitaria a barreira de sessão.
        """
        self._entrar(self.a)
        self.c.logout()
        self.c.get("/conta/entrar/")
        token_anonimo = self.c.cookies["csrftoken"].value

        resposta = self._replay(token_anonimo, dono=self.a.pk)

        self.assertEqual(resposta.json()["code"], CODIGO_SEM_SESSAO)
        self.assertEqual(resposta.redirect_chain, [])

    def test_depois_da_recusa_a_conta_certa_ainda_sincroniza(self):
        """Preservar não basta: a operação legítima precisa conseguir subir
        depois. É o B para A."""
        self._entrar(self.b)
        self._replay(self.c.cookies["csrftoken"].value, dono=self.a.pk)
        self.c.logout()
        token_de_a = self._entrar(self.a)

        resposta = self._replay(token_de_a, dono=self.a.pk)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(HydrationLog.objects.get(user=self.a).ml, 250)
        self.assertFalse(HydrationLog.objects.filter(user=self.b).exists())


class ODonoNuncaEscolheAContaTests(TestCase):
    """Pré-condição, não endereço."""

    def setUp(self):
        self.a = create_complete_user(email="guarda-a@exemplo.com")
        self.b = create_complete_user(email="guarda-b@exemplo.com")

    def test_o_destino_e_sempre_a_sessao(self):
        self.client.force_login(self.a)

        self.client.post(
            "/agua/",
            {"ml": "250", "op_id": "forjada"},
            HTTP_X_NUTRIPLAN_REPLAY="1",
            HTTP_X_NUTRIPLAN_DONO=str(self.a.pk),
        )

        self.assertTrue(HydrationLog.objects.filter(user=self.a).exists())
        self.assertFalse(HydrationLog.objects.filter(user=self.b).exists())

    def test_o_servidor_nunca_busca_usuario_pelo_dono(self):
        """Um `User.objects.get(pk=dono)` transformaria o cabeçalho em
        endereço, e o cliente escolheria a conta."""
        fonte = (RAIZ / "accounts" / "replay.py").read_text(encoding="utf-8")

        for proibido in ("objects.get", "objects.filter", "get_user_model"):
            with self.subTest(padrao=proibido):
                self.assertNotIn(proibido, fonte)


class OsDoisClientesTests(TestCase):
    """O que a página e o worker mandam, e o que eles fazem com a resposta."""

    def setUp(self):
        self.fila = (RAIZ / "static" / "js" / "fila.js").read_text(encoding="utf-8")
        self.sw = self.client.get("/sw.js").content.decode()

    def test_a_pagina_renova_o_csrf_antes_de_enviar(self):
        """O Django lê o campo do POST primeiro e só olha o cabeçalho se ele
        estiver vazio — acrescentar `X-CSRFToken` sem trocar o campo não
        adiantaria nada."""
        corpo = self.fila[self.fila.index("function enviar(") :][:900]

        self.assertIn("dados.csrfmiddlewaretoken = atual", corpo)

    def test_a_pagina_le_o_cookie_com_regex_literal(self):
        """`"\\s"` num literal de string do JavaScript vira apenas `s`."""
        corpo = self.fila[self.fila.index("function tokenAtual(") :][:300]

        self.assertIn("/(^|;)\\s*csrftoken=([^;]+)/", corpo)

    def test_os_dois_declaram_o_dono(self):
        pagina = self.fila[self.fila.index("function enviar(") :][:1400]
        worker = self.sw[self.sw.index("async function drenarFila") :][:2800]

        for nome, corpo in (("fila.js", pagina), ("sw.js", worker)):
            with self.subTest(arquivo=nome):
                self.assertIn('"X-NutriPlan-Replay": "1"', corpo)
                self.assertIn('cabecalhos["X-NutriPlan-Dono"] = item.dono', corpo)

    def test_nenhum_dos_dois_apaga_o_que_pode_ser_reenviado(self):
        pagina = self.fila[self.fila.index("function drenar()") :][:2400]
        worker = self.sw[self.sw.index("async function drenarFila") :][:3200]

        for nome, corpo, var in (
            ("fila.js", pagina, "r"),
            ("sw.js", worker, "resposta"),
        ):
            with self.subTest(arquivo=nome):
                self.assertIn('%s.type === "opaqueredirect"' % var, corpo)
                self.assertIn("%s.status === 401 || %s.status === 403" % (var, var), corpo)
                self.assertIn("%s.status >= 500" % var, corpo)

    def test_o_worker_nao_para_no_primeiro_item_estrangeiro(self):
        """Um item de outra pessoa não pode travar a fila e impedir que o item
        de quem ESTÁ logado sincronize."""
        corpo = self.sw[self.sw.index("async function drenarFila") :][:3200]

        self.assertNotIn("break;", corpo)
        self.assertIn("continue;", corpo)

    def test_item_sem_dono_nao_ganha_cabecalho(self):
        """Quarentena: o worker não inventa dono para o item legado."""
        corpo = self.sw[self.sw.index("async function drenarFila") :][:2800]

        self.assertIn("if (item.dono)", corpo)


class ABarreiraEhCentralTests(TestCase):
    """Middleware, e não uma chamada por view."""

    def test_o_middleware_esta_instalado_depois_da_autenticacao(self):
        from django.conf import settings

        lista = list(settings.MIDDLEWARE)
        auth = lista.index("django.contrib.auth.middleware.AuthenticationMiddleware")
        barreira = lista.index("config.csrf.BarreiraDeReplayMiddleware")

        self.assertGreater(barreira, auth, "a barreira precisa de request.user")

    def test_o_csrf_tem_handler_proprio(self):
        from django.conf import settings

        self.assertEqual(settings.CSRF_FAILURE_VIEW, "config.csrf.falha_de_csrf")

    def test_ninguem_usa_csrf_exempt_no_replay(self):
        """Resolver a perda desligando o CSRF seria trocar um bug por uma
        vulnerabilidade."""
        for arquivo in ("config/csrf.py", "accounts/replay.py",
                        "plans/views.py", "workouts/views.py"):
            with self.subTest(arquivo=arquivo):
                fonte = (RAIZ / arquivo).read_text(encoding="utf-8")
                self.assertNotIn("csrf_exempt", fonte)

    def test_a_view_nao_executa_quando_o_csrf_recusa(self):
        """A resposta preservável não é bypass: nada é mutado."""
        pessoa = create_complete_user(email="sem-bypass@exemplo.com")
        c = Client(enforce_csrf_checks=True)
        c.force_login(pessoa)
        c.get("/")

        c.post(
            "/agua/",
            {"ml": "250", "op_id": "x", "csrfmiddlewaretoken": "invalido"},
        )

        self.assertFalse(HydrationLog.objects.exists())
        self.assertFalse(SyncedOperation.objects.exists())
