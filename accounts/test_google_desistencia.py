# -*- coding: utf-8 -*-
"""Desistir do login com Google terminava em 500.

O caminho, medido de ponta a ponta antes da correção:

  1. a pessoa toca em "Entrar com Google";
  2. o Google mostra a tela de consentimento;
  3. ela muda de ideia e toca em "Cancelar" — que é uma coisa comum de fazer,
     e não um caso de borda;
  4. o Google devolve `error=access_denied` para o callback;
  5. o allauth traduz isso em `AuthError.CANCELLED` e redireciona para
     `socialaccount_login_cancelled`;
  6. a view dele reverte `account_login` — e o nome não existia.

Resultado: **HTTP 500 na porta de entrada do app**, para quem só desistiu.

`account_login` mora em `allauth.account.urls`, que `config/urls.py` deixa de
fora de propósito: o allauth entra como motor e não como interface, para não
existirem duas telas de entrar. A decisão continua certa. O que faltava era o
NOME apontar para a porta que já existe — 25 lugares da biblioteca o revertem,
o `AccountMiddleware` instalado entre eles, então a ausência dele não era um
buraco de três rotas e sim uma classe inteira de 500 latentes.
"""
import re
from urllib.parse import parse_qs, urlparse

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import NoReverseMatch, get_resolver, reverse

from accounts.tests import GOOGLE_DE_TESTE


def rotas_sociais_sem_parametro():
    """Toda rota social que dá para visitar digitando, direto do URLconf.

    Enumerar em vez de listar: uma rota nova da biblioteca entra aqui sozinha
    no dia em que alguém montar outro provedor.
    """

    def varrer(res, prefixo=""):
        for p in res.url_patterns:
            padrao = prefixo + str(p.pattern)
            if hasattr(p, "url_patterns"):
                yield from varrer(p, padrao)
            else:
                yield padrao

    for padrao in varrer(get_resolver()):
        if not padrao.startswith(("conta/social/", "conta/google/")):
            continue
        if "<" in padrao or "(" in padrao:
            continue
        yield "/" + padrao


@override_settings(**GOOGLE_DE_TESTE)
class DesistirDoGoogleLevaDeVoltaParaEntrarTests(TestCase):
    """O defeito, contado do jeito que a pessoa o encontra."""

    def cancelar_no_google(self):
        """O fluxo real, com o `state` que o próprio app gerou.

        Com um `state` inventado o allauth cai noutro ramo de erro e devolve
        401 — o teste passaria sem nunca visitar o caminho do cancelamento.
        """
        pedido = self.client.post("/conta/google/login/", {"process": "login"})
        estado = parse_qs(urlparse(pedido["Location"]).query)["state"][0]

        return self.client.get(
            "/conta/google/login/callback/?error=access_denied&state=" + estado
        )

    def test_quem_desiste_no_google_volta_para_a_tela_de_entrar(self):
        resposta = self.client.get(self.cancelar_no_google()["Location"])

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], reverse("accounts:login"))

    def test_o_caminho_inteiro_nao_passa_por_erro_de_servidor(self):
        """A asserção que teria pego o defeito: seguir os redirecionamentos
        até o fim, como o navegador faz, e olhar o que a pessoa vê."""
        resposta = self.client.get(
            self.cancelar_no_google()["Location"], follow=True
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.redirect_chain[-1][0], reverse("accounts:login"))

    def test_a_tela_que_ela_recebe_e_a_do_app(self):
        """Não basta não quebrar: a tela nua da biblioteca — sem `app.css`, sem
        navegação e sem identidade — é a "segunda interface" que
        `config/urls.py` recusa. Medida antes: 1.071 bytes, texto em português
        da biblioteca, nenhum estilo do produto."""
        html = self.client.get(
            self.cancelar_no_google()["Location"], follow=True
        ).content.decode()

        self.assertIn("app.css", html)
        self.assertNotIn("cancelar o login em nosso site", html)


class NenhumaRotaSocialResponde5xxTests(TestCase):
    """A varredura que faltava.

    A fumaça de produção mede as telas que alguém alcança de propósito, e
    ninguém navega até `/conta/social/login/cancelled/` — o allauth navega.
    Três rotas devolviam 500 e nenhum teste olhava para lá.
    """

    def test_nenhuma_delas_devolve_erro_de_servidor(self):
        quebradas = []
        for rota in rotas_sociais_sem_parametro():
            resposta = self.client.get(rota)
            if resposta.status_code >= 500:
                quebradas.append("%s -> %s" % (rota, resposta.status_code))

        self.assertEqual(quebradas, [])

    def test_a_varredura_olha_para_alguma_coisa(self):
        """Controle positivo: uma varredura que não achasse rota nenhuma
        passaria verde para sempre."""
        self.assertGreaterEqual(len(list(rotas_sociais_sem_parametro())), 4)


@override_settings(**GOOGLE_DE_TESTE)
class QuandoOHandshakeFalhaAtelaAindaEDoAppTests(TestCase):
    """A outra saída do mesmo caminho.

    Cancelar tem rota própria. Falhar não: quando o `state` do OAuth não bate —
    página de entrar aberta há tempo demais, cookie de sessão descartado — o
    allauth renderiza `socialaccount/authentication_error.html` com 401. Sem
    override, chegava nua: 982 bytes, sem `app.css`, sem navegação, sem marca.
    """

    def falhar_no_handshake(self):
        return self.client.get(
            "/conta/google/login/callback/?error=access_denied&state=inventado"
        )

    def test_a_pessoa_recebe_a_tela_do_app(self):
        html = self.falhar_no_handshake().content.decode()

        self.assertIn("app.css", html)
        self.assertNotIn("conta de terceiros", html)

    def test_ela_tem_um_caminho_de_volta(self):
        """Beco sem saída é o defeito irmão do 500: a pessoa está deslogada,
        então a navegação do app não a leva a lugar nenhum.

        A asserção precisa ser o LINK DO CARTÃO, e não o endereço solto: o
        cabeçalho já tem um "Entrar" apontando para o mesmo lugar, e procurar
        só o `href` passava verde com o botão apagado — foi o que a sabotagem
        S190 mostrou, repetindo a armadilha que o `CLAUDE.md` descreve.
        """
        html = self.falhar_no_handshake().content.decode()

        botao = re.search(
            r'<a[^>]*href="%s"[^>]*>\s*Tentar de novo' % reverse("accounts:login"),
            html,
        )

        self.assertIsNotNone(botao, "o cartão perdeu o botão de voltar")

    def test_o_status_continua_dizendo_que_falhou(self):
        """401 é o que o allauth responde, e trocar a tela não pode trocar a
        resposta: monitoração e log leem o status, não o HTML."""
        self.assertEqual(self.falhar_no_handshake().status_code, 401)

    def test_a_tela_nao_mostra_o_detalhe_interno_da_biblioteca(self):
        """`auth_error.exception` é diagnóstico da biblioteca. Não ajuda
        ninguém a entrar, e é por onde vaza o que não precisa aparecer."""
        html = self.falhar_no_handshake().content.decode()

        for vazamento in ("Traceback", "OAuth2Error", "allauth."):
            with self.subTest(termo=vazamento):
                self.assertNotIn(vazamento, html)


class ONomeApontaParaAPortaQueJaExisteTests(TestCase):
    """Registrar o nome não é montar a tela da biblioteca."""

    def test_account_login_e_a_mesma_porta_do_app(self):
        """Uma tela de entrar, um endereço. Se este teste passar a comparar
        endereços diferentes, nasceram duas."""
        self.assertEqual(reverse("account_login"), reverse("accounts:login"))

    def test_as_outras_telas_da_biblioteca_continuam_fora(self):
        """Contra-controle da decisão original: registrar `account_login` não
        pode ter aberto a porta para o resto de `allauth.account.urls`."""
        for nome in ("account_signup", "account_reset_password", "account_email"):
            with self.subTest(rota=nome):
                with self.assertRaises(NoReverseMatch):
                    reverse(nome)
