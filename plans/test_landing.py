# -*- coding: utf-8 -*-
"""A raiz anônima é uma landing, não o login (decisão 2 da avaliação, 20/09/2026).

A avaliação achou que a raiz do app, para quem não tem conta, caía direto no
login — sem uma frase dizendo o que o produto é, sem prova nenhuma, sem porta
para a demonstração pública que já existe. Quem chega de fora via uma tela de
senha para um app que ainda não sabe se quer.

Agora a raiz DECIDE pelo visitante: anônimo vê a landing (proposta de valor em
uma frase, três provas do produto, botão para a demonstração e para criar
conta, e um caminho discreto para entrar); quem já tem sessão continua vendo o
app (o painel do dia). O login saiu da raiz — chega-se a ele por um link, não
por um redirect na cara.
"""
from django.test import TestCase
from django.core.management import call_command
from django.urls import reverse

from workouts.tests import create_user


class RaizAnonimaEhLandingTests(TestCase):
    def test_a_raiz_anonima_mostra_a_landing_e_nao_redireciona_para_o_login(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "plans/landing.html")

    def test_a_landing_tem_a_proposta_de_valor(self):
        html = self.client.get("/").content.decode()
        self.assertIn("landing__proposta", html)
        # A voz do produto, a mesma da capa do demo ("num app só").
        self.assertIn("num app só", html)

    def test_a_landing_tem_tres_provas_do_produto(self):
        html = self.client.get("/").content.decode()
        # `landing__prova"` (com a aspa) não casa com o contêiner
        # `landing__provas"` — a armadilha do substring que o CLAUDE.md alerta.
        self.assertEqual(html.count('landing__prova"'), 3)

    def test_a_landing_leva_para_a_demonstracao_e_para_criar_conta(self):
        html = self.client.get("/").content.decode()
        self.assertIn('href="/demo/"', html)
        self.assertIn('href="%s"' % reverse("accounts:signup"), html)

    def test_a_landing_oferece_entrar_sem_ser_a_primeira_coisa(self):
        html = self.client.get("/").content.decode()
        self.assertIn('href="%s"' % reverse("accounts:login"), html)

    def test_a_landing_nao_tem_barra_de_abas(self):
        """Quem não entrou não tem para onde navegar; a barra de baixo seria
        uma promessa de destinos que exigem login."""
        r = self.client.get("/")
        self.assertTrue(r.context.get("sem_tabbar"))

    def test_a_landing_nao_toca_o_banco(self):
        """A medição de "tempo de carga" que decide o cold start: a raiz
        anônima é a página mais barata possível — ZERO consulta. Um visitante
        novo é justamente quem pega o Render dormindo, e a tela que ele vê
        primeiro não pode depender do banco (que dorme à parte, no Neon).
        Medido: 0 consultas, ~2,6 ms de render local."""
        with self.assertNumQueries(0):
            self.client.get("/")


class RaizAutenticadaContinuaSendoOAppTests(TestCase):
    def setUp(self):
        self.user = create_user(email="raiz-logada@exemplo.com")
        self.client.force_login(self.user)

    def test_quem_tem_sessao_nunca_ve_a_landing(self):
        """A landing é só para o anônimo. Logado, a raiz é o app — hoje, ou o
        onboarding se faltar plano —, nunca a página de marketing."""
        r = self.client.get("/", follow=True)
        self.assertTemplateNotUsed(r, "plans/landing.html")


class LandingNaoInvadeODemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        call_command("seed_demo", verbosity=0)

    def test_a_capa_do_demo_continua_sendo_a_capa(self):
        r = self.client.get("/demo/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateNotUsed(r, "plans/landing.html")
        self.assertContains(r, "Ambiente de demonstração")

    def test_demo_hoje_e_o_app_e_nao_a_landing(self):
        """`/demo/hoje/` passa pelo resolvedor com a persona autenticada — a
        landing (ramo anônimo) não pode sequestrá-lo."""
        r = self.client.get("/demo/hoje/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateNotUsed(r, "plans/landing.html")
