# -*- coding: utf-8 -*-
"""`/hoje/` é um endereço antigo, e endereço antigo não responde 404.

A tela Hoje já morou em `/hoje/`: era a rota do cardápio antes de 22/09/2026,
quando "Hoje" voltou a ser o dia inteiro e o cardápio ganhou `/alimentacao/`.
Quem guardou o link, fixou na tela inicial do celular ou o tem num e-mail
recebe "Esta página não existe" — para uma tela que existe, e é a primeira
do app.

301 e não 302: é mudança PERMANENTE, e é o que faz o navegador e o buscador
pararem de pedir o endereço velho. `RedirectView` com `permanent=True` é o
caminho do Django para isso; não há view nova nem teste de conteúdo aqui —
o que se prende é o CONTRATO do endereço.
"""
from django.test import TestCase


class OEnderecoAntigoDaHomeTests(TestCase):
    def test_hoje_responde_301_para_a_raiz(self):
        resposta = self.client.get("/hoje/")
        self.assertEqual(resposta.status_code, 301)
        self.assertEqual(resposta["Location"], "/")

    def test_o_redirect_nao_pede_sessao(self):
        """Sem `LoginRequiredMixin`: o redirect é do ENDEREÇO, e mandar quem
        não está logado para a tela de entrada é trabalho da própria `/`."""
        self.client.logout()
        self.assertEqual(self.client.get("/hoje/").status_code, 301)

    def test_o_destino_e_resolvido_pelo_nome_da_rota(self):
        """`pattern_name` e não uma barra escrita: sob
        `set_script_prefix("/demo/")` o mesmo redirect reverte para dentro do
        demo, e uma URL literal jogaria quem está avaliando o produto para
        fora dele. (A doutrina do mapa de áreas, no CLAUDE.md, é a mesma.)"""
        from django.urls import get_resolver

        alvo = get_resolver().resolve("/hoje/")
        self.assertEqual(alvo.func.view_initkwargs.get("pattern_name"), "plans:today")
        self.assertTrue(alvo.func.view_initkwargs.get("permanent"))
