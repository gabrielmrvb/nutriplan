# -*- coding: utf-8 -*-
"""Tentar senha em série para de sair de graça.

O QUE ESTAVA ABERTO
===================

Medido antes: `AppLoginView` não tinha gancho de falha nenhum (e a API v1,
que existiu até 20/09/2026, também não). Os limites que existiam em
`accounts/limites.py` protegem a RECUPERAÇÃO DE SENHA — cota de e-mail —, não
autenticação. Não havia axes nem defender. Uma porta de força bruta aberta.

Desde 20/09/2026 a API v1 saiu e a única superfície é o formulário de
entrar: sucesso é 302; recusa — senha errada, conta inexistente ou limite
— é a mesma tela de 200 sem sessão. `_recusa()` extrai o que se compara.

POR QUE NO BANCO, E NÃO EM CACHE
================================

Pelo mesmo motivo que `PedidoDeRecuperacao` já documenta: o projeto usa
`LocMemCache`, o Render sobe dois workers do gunicorn e reinicia a cada
deploy. Um limite em cache valeria por worker, dobraria na prática e zeraria a
cada publicação. O que é compartilhado é o PostgreSQL.

A POLÍTICA, E O QUE ELA RECUSA DE PROPÓSITO
===========================================

Não existe limite por E-MAIL sozinho, e isso é a decisão central: um limite
assim deixaria qualquer pessoa trancar a conta de outra só sabendo o endereço.
O que existe é (origem + e-mail) e (origem), mais um teto global de
emergência. A dona da conta sempre entra do aparelho dela.

A resposta de quem está limitado é IGUAL à de senha errada. É o precedente que
o próprio projeto já fixou na recuperação: "devolver 429, ou qualquer texto
diferente, transformaria o limite num oráculo".
"""
import json
import re

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import entrada
from accounts.models import TentativaDeEntrada
from plans.tests import create_complete_user

SENHA = "senha-bem-forte-123"
ERRADA = "nao-e-essa-de-proposito"


class Base(TestCase):
    def setUp(self):
        self.pessoa = create_complete_user("entrada.dona@exemplo.com")
        self.pessoa.set_password(SENHA)
        self.pessoa.save()

    def web(self, email, senha, ip="203.0.113.10"):
        return self.client.post(
            reverse("accounts:login"),
            {"username": email, "password": senha},
            REMOTE_ADDR=ip,
        )

    def _recusa(self, resposta):
        """O que a tela de entrar diz numa recusa, sem o token de CSRF (que
        muda a cada resposta e tornaria dois HTML iguais diferentes)."""
        html = resposta.content.decode()
        html = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", html)
        # o e-mail digitado volta no campo; a comparação é sobre o RESTO
        html = re.sub(r'(name="username"[^>]*?)value="[^"]*"', r"", html)
        return resposta.status_code, resposta.wsgi_request.user.is_authenticated, html


class OUsoNormalNaoEAtrapalhadoTests(Base):
    """A primeira coisa que um limite precisa provar é que não estorva."""

    def test_entrar_de_primeira_funciona(self):
        resposta = self.web(self.pessoa.email, SENHA)

        self.assertEqual(resposta.status_code, 302)

    def test_errar_duas_vezes_e_acertar_na_terceira_funciona(self):
        self.web(self.pessoa.email, ERRADA)
        self.web(self.pessoa.email, ERRADA)

        self.assertEqual(self.web(self.pessoa.email, SENHA).status_code, 302)

    def test_o_sucesso_limpa_o_contador(self):
        """Quem errou, acertou e voltou a errar não começa do quase-limite.

        Sem isto, uma pessoa que troca de senha e digita errado algumas vezes ao
        longo do dia acabaria barrada sem nunca ter feito nada de errado.
        """
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL - 1):
            self.web(self.pessoa.email, ERRADA)
        self.web(self.pessoa.email, SENHA)

        self.assertEqual(
            entrada.falhas_de(email=self.pessoa.email, ip="203.0.113.10"), 0
        )


class ASequenciaAbusivaEBarradaTests(Base):
    """O caso que a proteção existe para cortar."""

    def test_o_web_para_de_aceitar_depois_do_limite(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.web(self.pessoa.email, ERRADA)

        resposta = self.web(self.pessoa.email, SENHA)

        self.assertEqual(resposta.status_code, 200)  # ficou na tela de entrar
        self.assertFalse(resposta.wsgi_request.user.is_authenticated)

    def test_varrer_muitos_emails_da_mesma_origem_tambem_e_barrado(self):
        """O limite por par não cortaria quem espalha as tentativas por contas
        diferentes. O limite por ORIGEM corta."""
        for i in range(entrada.LIMITE_POR_ORIGEM):
            self.web("alvo%d@exemplo.com" % i, ERRADA)

        # A senha CERTA, e ainda assim recusada: é isso que faz o limite valer.
        resposta = self.web(self.pessoa.email, SENHA)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.wsgi_request.user.is_authenticated)


class NinguemTrancaAContaDeOutraPessoaTests(Base):
    """A recusa que define a política.

    Um limite por e-mail sozinho seria uma arma: bastaria saber o endereço para
    deixar a dona de fora. Aqui as tentativas de um atacante prendem o IP DELE,
    e não a conta dela.
    """

    def test_a_dona_entra_do_aparelho_dela_mesmo_sob_ataque(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL * 3):
            self.web(self.pessoa.email, ERRADA, ip="198.51.100.7")

        de_casa = self.web(self.pessoa.email, SENHA, ip="203.0.113.10")

        self.assertEqual(de_casa.status_code, 302)
        self.assertTrue(de_casa.wsgi_request.user.is_authenticated)


class ARecusaNaoVirouOraculoTests(Base):
    """Limitado ou não, existente ou não: a mesma resposta."""

    def test_conta_inexistente_e_senha_errada_continuam_iguais(self):
        a = self._recusa(self.web(self.pessoa.email, ERRADA))
        b = self._recusa(self.web("ninguem@exemplo.com", ERRADA))

        self.assertEqual(a, b)

    def test_limitado_responde_igual_a_senha_errada(self):
        """Um status diferente diria ao atacante que ele achou o teto — e, se o
        teto fosse por e-mail, diria que a conta existe."""
        antes = self._recusa(self.web(self.pessoa.email, ERRADA))
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.web(self.pessoa.email, ERRADA)
        depois = self._recusa(self.web(self.pessoa.email, ERRADA))

        self.assertEqual(antes, depois)


class OLimiteNaoConfereASenhaTests(Base):
    """O docstring de `AppLoginView.post` promete que, no teto, "nem chega a
    conferir a senha". Até 20/09/2026 conferia: `formulario.is_valid()`
    chamava `authenticate` (PBKDF2 de 1 000 000 iterações — os 3–5 s que a
    auditoria mediu no login) e, com a senha errada, a mensagem entrava DUAS
    vezes na tela — um oráculo do teto que só apareceu quando o teste do
    oráculo passou a medir o web (a API v1 saiu)."""

    def test_no_teto_o_hash_da_senha_nao_e_calculado(self):
        from unittest import mock

        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.web(self.pessoa.email, ERRADA)
        with mock.patch("django.contrib.auth.forms.authenticate") as autenticar:
            resposta = self.web(self.pessoa.email, SENHA)
        autenticar.assert_not_called()
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.wsgi_request.user.is_authenticated)

    def test_a_mensagem_aparece_uma_vez_so(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.web(self.pessoa.email, ERRADA)
        html = self.web(self.pessoa.email, ERRADA).content.decode()
        self.assertEqual(html.count("E-mail ou senha incorretos"), 1)


class AJanelaExpiraTests(Base):
    """Bloqueio permanente é negação de serviço com outro nome."""

    def test_depois_da_janela_a_pessoa_entra_de_novo(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.web(self.pessoa.email, ERRADA)
        self.assertFalse(self.web(self.pessoa.email, SENHA).wsgi_request.user.is_authenticated)

        # As tentativas envelhecem para fora da janela.
        velho = timezone.now() - timezone.timedelta(
            minutes=entrada.JANELA_MINUTOS + 1
        )
        TentativaDeEntrada.objects.update(criado_em=velho)

        self.assertEqual(self.web(self.pessoa.email, SENHA).status_code, 302)


class OQueFicaGuardadoTests(Base):
    """A tabela conta, e não vira lista de quem usa o app."""

    def test_o_email_nao_e_guardado_em_claro(self):
        self.web(self.pessoa.email, ERRADA)

        guardado = json.dumps(list(TentativaDeEntrada.objects.values()), default=str)

        self.assertNotIn(self.pessoa.email, guardado)

    def test_o_ip_nao_e_guardado_em_claro(self):
        self.web(self.pessoa.email, ERRADA, ip="198.51.100.7")

        guardado = json.dumps(list(TentativaDeEntrada.objects.values()), default=str)

        self.assertNotIn("198.51.100.7", guardado)

    def test_a_origem_vem_de_ip_do_pedido_e_nao_do_cabecalho_cru(self):
        """Fora de proxy confiável, `X-Forwarded-For` é escrito pelo cliente.

        Se ele valesse, um atacante trocaria de cabeçalho a cada tentativa e o
        limite por origem não existiria. `limites.ip_do_pedido` é quem decide,
        e o padrão de `USA_PROXY_CONFIAVEL` é falso.
        """
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.client.post(
                reverse("accounts:login"),
                {"username": self.pessoa.email, "password": ERRADA},
                REMOTE_ADDR="203.0.113.10",
                HTTP_X_FORWARDED_FOR="1.2.3.4",
            )

        # Mesmo trocando o cabeçalho, a origem real continua sendo a mesma.
        driblando = self.client.post(
            reverse("accounts:login"),
            {"username": self.pessoa.email, "password": SENHA},
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )

        self.assertEqual(driblando.status_code, 200)
        self.assertFalse(driblando.wsgi_request.user.is_authenticated)
