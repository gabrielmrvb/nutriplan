# -*- coding: utf-8 -*-
"""A recusa por CSRF deixa de ser a página do Django.

Medido antes da correção, com `Client(enforce_csrf_checks=True)` postando um
token inválido em `/conta/entrar/`:

    STATUS 403 · 2.881 bytes · <title>403 Forbidden</title>
    sem `app.css`, sem marca, sem navegação
    os DOIS únicos links apontam para `docs.djangoproject.com/en/5.2/`

O caminho de recuperação levava para fora do produto, para a documentação do
framework — e a URL dizia qual framework e qual versão.

Isto NÃO é sobre enfraquecer o CSRF. A recusa continua: 403, view não executa,
nada é mutado. Só a forma de dizer muda.

Como o Django renderiza esta página importa para o que se pode afirmar aqui.
`django.views.csrf.csrf_failure` faz `t.render(request=request)` quando o
template existe: passa o REQUEST — então os context processors rodam e
`user.is_authenticated` funciona — e NÃO passa o dicionário interno com
`reason`, `docs_version` e `DEBUG`. Não há detalhe interno para vazar porque
nenhum é oferecido ao template.
"""
import json
import re

from django.test import Client, TestCase
from django.urls import reverse

from accounts.replay import CAMPO_DA_FILA, CODIGO_CSRF_VELHO
from plans.tests import create_complete_user


class UmPostComTokenVencidoRecebeATelaDoAppTests(TestCase):
    """O caso comum: a pessoa deixou a aba aberta e o token venceu."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def recusar(self):
        """Um POST normal com token inválido, pelo handler de verdade.

        `/conta/entrar/` de propósito: é a rota que qualquer pessoa alcança sem
        estar logada, e é onde uma aba velha mais provavelmente está.
        """
        return self.client.post(
            reverse("accounts:login"),
            {
                "username": "qualquer@exemplo.com",
                "password": "seja-o-que-for",
                "csrfmiddlewaretoken": "token-invalido-de-proposito",
            },
        )

    def test_o_status_continua_403(self):
        """A recusa não afrouxou. Se este teste virar 200, a correção virou
        contorno da proteção."""
        self.assertEqual(self.recusar().status_code, 403)

    def test_a_pessoa_ve_a_tela_do_nutriplan(self):
        html = self.recusar().content.decode()

        self.assertIn("app.css", html)
        self.assertIn("NutriPlan", html)

    def test_nao_e_mais_a_pagina_embutida_do_django(self):
        """As duas marcas da página do framework, medidas antes: o título e o
        link para a documentação."""
        html = self.recusar().content.decode()

        self.assertNotIn("<title>403 Forbidden</title>", html)
        self.assertNotIn("docs.djangoproject.com", html)

    def test_nao_expoe_detalhe_interno(self):
        """A URL da documentação carregava o framework E a versão. Nada disso
        precisa aparecer para quem só quer voltar a usar o app."""
        html = self.recusar().content.decode()

        for vazamento in ("djangoproject", "Traceback", "csrfmiddlewaretoken", "DEBUG"):
            with self.subTest(termo=vazamento):
                self.assertNotIn(vazamento, html)

    def test_nao_oferece_nada_que_repita_o_post(self):
        """Um formulário aqui convidaria a reenviar exatamente o pedido que
        acabou de ser recusado — e um botão de recarregar faria o navegador
        repetir o POST. A saída é sempre por GET."""
        html = self.recusar().content.decode()

        self.assertNotIn("<form", html)

    def test_anonimo_recebe_o_caminho_para_entrar(self):
        """A âncora é o BOTÃO DO CARTÃO, e não o endereço solto.

        O cabeçalho do `base.html` já tem um "Entrar" apontando para a mesma
        rota: procurar só o `href` passava verde com o botão apagado. Foi o que
        a sabotagem S228 mostrou — a mesma armadilha que o `CLAUDE.md`
        descreve, e a terceira vez que ela aparece nesta base.
        """
        html = self.recusar().content.decode()

        volta = re.search(
            r'<a[^>]*href="%s"[^>]*>\s*Entrar no NutriPlan' % reverse("accounts:login"),
            html,
        )

        self.assertIsNotNone(volta, "quem não está logado ficou sem saída")


class QuemEstaLogadoVoltaParaODiaTests(TestCase):
    """A mesma recusa, com sessão válida e token velho.

    É o caso mais comum de todos e o menos óbvio: `login()` chama
    `rotate_token`, então basta a pessoa ter entrado de novo em outra aba para
    o token daquela página ficar velho — sem nada de errado ter acontecido.
    """

    def setUp(self):
        self.pessoa = create_complete_user("csrf.logado@exemplo.com")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.pessoa)

    def recusar(self):
        return self.client.post(
            reverse("plans:log_hydration"),
            {"ml": "250", "csrfmiddlewaretoken": "token-invalido-de-proposito"},
        )

    def test_o_status_continua_403(self):
        self.assertEqual(self.recusar().status_code, 403)

    def test_ela_volta_para_o_dia_de_hoje(self):
        """Mesma âncora de texto do teste anônimo, e pelo mesmo motivo: a barra
        de abas do `base.html` já leva ao dia de hoje, então o `href` sozinho
        passaria verde com o cartão sem botão nenhum."""
        html = self.recusar().content.decode()

        volta = re.search(
            r'<a[^>]*href="%s"[^>]*>\s*Ir para o dia de hoje' % reverse("plans:today"),
            html,
        )

        self.assertIsNotNone(volta, "quem está logado ficou sem saída")

    def test_a_agua_nao_foi_registrada(self):
        """O contra-controle que impede esta correção de virar bypass: a
        recusa tem de continuar recusando. Se a água entrasse, a tela bonita
        estaria escondendo um CSRF desligado."""
        antes = self.pessoa.hydration_logs.count()

        self.recusar()

        self.assertEqual(self.pessoa.hydration_logs.count(), antes)


class OReplayDaFilaOfflineContinuaComOContratoDeleTests(TestCase):
    """O caso especial de `config/csrf.py` não pode ter sido atropelado.

    Ele existe porque o `drenar()` publicado apaga o item da fila em qualquer
    4xx: um 403 aqui destruiria a água que a pessoa marcou sem rede. A resposta
    é JSON com status próprio, e continua sendo.
    """

    def setUp(self):
        self.pessoa = create_complete_user("csrf.fila@exemplo.com")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.pessoa)

    def replay(self):
        return self.client.post(
            reverse("plans:log_hydration"),
            {
                "ml": "250",
                CAMPO_DA_FILA: "op-de-teste-csrf",
                "csrfmiddlewaretoken": "token-invalido-de-proposito",
            },
        )

    def test_ele_nao_recebe_html(self):
        resposta = self.replay()

        self.assertIn("application/json", resposta["Content-Type"])

    def test_ele_recebe_o_codigo_combinado(self):
        corpo = json.loads(self.replay().content.decode())

        self.assertEqual(corpo["code"], CODIGO_CSRF_VELHO)

    def test_ele_nao_recebe_403(self):
        """403 é exatamente o que faria a fila jogar o item fora."""
        self.assertNotEqual(self.replay().status_code, 403)
