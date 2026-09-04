# -*- coding: utf-8 -*-
"""Tentar senha em série para de sair de graça — no web e na API.

O QUE ESTAVA ABERTO
===================

Medido antes: `AppLoginView` não tinha gancho de falha nenhum, e
`POST /api/v1/token/` também não. Os limites que existiam em
`accounts/limites.py` protegem a RECUPERAÇÃO DE SENHA — cota de e-mail —, não
autenticação. Não havia axes nem defender. Uma porta de força bruta em duas
superfícies.

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

    def api(self, email, senha, ip="203.0.113.10"):
        return self.client.post(
            reverse("api:token"),
            json.dumps({"email": email, "senha": senha}),
            content_type="application/json",
            REMOTE_ADDR=ip,
        )


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

    def test_a_api_para_de_aceitar_depois_do_limite(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.api(self.pessoa.email, ERRADA)

        # A senha CERTA, e ainda assim recusada: é isso que faz o limite valer.
        resposta = self.api(self.pessoa.email, SENHA)

        self.assertEqual(resposta.status_code, 401)
        self.assertNotIn("token", json.loads(resposta.content.decode()))

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
            self.api("alvo%d@exemplo.com" % i, ERRADA)

        self.assertEqual(self.api(self.pessoa.email, SENHA).status_code, 401)


class NinguemTrancaAContaDeOutraPessoaTests(Base):
    """A recusa que define a política.

    Um limite por e-mail sozinho seria uma arma: bastaria saber o endereço para
    deixar a dona de fora. Aqui as tentativas de um atacante prendem o IP DELE,
    e não a conta dela.
    """

    def test_a_dona_entra_do_aparelho_dela_mesmo_sob_ataque(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL * 3):
            self.api(self.pessoa.email, ERRADA, ip="198.51.100.7")

        de_casa = self.api(self.pessoa.email, SENHA, ip="203.0.113.10")

        self.assertEqual(de_casa.status_code, 200)
        self.assertIn("token", json.loads(de_casa.content.decode()))


class ARecusaNaoVirouOraculoTests(Base):
    """Limitado ou não, existente ou não: a mesma resposta."""

    def test_conta_inexistente_e_senha_errada_continuam_iguais(self):
        a = self.api(self.pessoa.email, ERRADA)
        b = self.api("ninguem@exemplo.com", ERRADA)

        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.content, b.content)

    def test_limitado_responde_igual_a_senha_errada(self):
        """Um status diferente diria ao atacante que ele achou o teto — e, se o
        teto fosse por e-mail, diria que a conta existe."""
        antes = self.api(self.pessoa.email, ERRADA)
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.api(self.pessoa.email, ERRADA)
        depois = self.api(self.pessoa.email, ERRADA)

        self.assertEqual(antes.status_code, depois.status_code)
        self.assertEqual(antes.content, depois.content)


class AJanelaExpiraTests(Base):
    """Bloqueio permanente é negação de serviço com outro nome."""

    def test_depois_da_janela_a_pessoa_entra_de_novo(self):
        for _ in range(entrada.LIMITE_POR_ORIGEM_E_EMAIL):
            self.api(self.pessoa.email, ERRADA)
        self.assertEqual(self.api(self.pessoa.email, SENHA).status_code, 401)

        # As tentativas envelhecem para fora da janela.
        velho = timezone.now() - timezone.timedelta(
            minutes=entrada.JANELA_MINUTOS + 1
        )
        TentativaDeEntrada.objects.update(criado_em=velho)

        self.assertEqual(self.api(self.pessoa.email, SENHA).status_code, 200)


class OQueFicaGuardadoTests(Base):
    """A tabela conta, e não vira lista de quem usa o app."""

    def test_o_email_nao_e_guardado_em_claro(self):
        self.api(self.pessoa.email, ERRADA)

        guardado = json.dumps(list(TentativaDeEntrada.objects.values()), default=str)

        self.assertNotIn(self.pessoa.email, guardado)

    def test_o_ip_nao_e_guardado_em_claro(self):
        self.api(self.pessoa.email, ERRADA, ip="198.51.100.7")

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
                reverse("api:token"),
                json.dumps({"email": self.pessoa.email, "senha": ERRADA}),
                content_type="application/json",
                REMOTE_ADDR="203.0.113.10",
                HTTP_X_FORWARDED_FOR="1.2.3.4",
            )

        # Mesmo trocando o cabeçalho, a origem real continua sendo a mesma.
        driblando = self.client.post(
            reverse("api:token"),
            json.dumps({"email": self.pessoa.email, "senha": SENHA}),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )

        self.assertEqual(driblando.status_code, 401)
