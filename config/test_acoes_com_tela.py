# -*- coding: utf-8 -*-
"""Endpoint de ação não devolve tela em branco.

O caminho, medido de ponta a ponta antes da correção:

  1. a sessão expira — o jeito mais comum de uma sessão acabar, porque ninguém
     sai do app de propósito;
  2. a pessoa toca em "+250 ml", "Comi esta" ou "Salvar peso";
  3. `login_required` manda para `/conta/entrar/?next=/agua/`;
  4. ela entra corretamente;
  5. o Django redireciona para o `next` — com um GET;
  6. `/agua/` só aceitava POST e respondia **405 com zero byte**.

Quem fez tudo certo terminava numa tela completamente em branco, sem mensagem
e sem navegação, logo depois de um login bem-sucedido.

`TodaTelaTemPortaTests` não pega isto: ele cuida de destinos que alguém alcança
de propósito, e ninguém digita `/agua/` na barra de endereço. Este caminho é
construído pelo próprio Django, no `next`.
"""
from django.test import TestCase
from django.urls import get_resolver
from django.views import View

from plans.tests import create_complete_user


def rotas_que_recebem_post():
    """Toda rota do app que responde POST, direto do URLconf.

    Enumerar em vez de listar à mão: uma view nova entra aqui sozinha, e é isso
    que faz o teste continuar valendo depois que ninguém lembrar dele.
    """
    def varrer(res, prefixo=""):
        for p in res.url_patterns:
            padrao = prefixo + str(p.pattern)
            if hasattr(p, "url_patterns"):
                yield from varrer(p, padrao)
            else:
                yield padrao, p.callback

    achadas = []
    for padrao, cb in varrer(get_resolver()):
        if padrao.startswith(("admin/", "static")):
            continue
        cls = getattr(cb, "view_class", None)
        if cls is None or not isinstance(cls, type) or not issubclass(cls, View):
            continue
        permitidos = getattr(cls, "http_method_names", None)
        if not hasattr(cls, "post"):
            continue
        if permitidos is not None and "post" not in permitidos:
            continue
        achadas.append(("/" + padrao, cls))
    return achadas


class TodaAcaoDevolveUmaTelaTests(TestCase):
    """Um GET num endpoint de ação leva à tela a que a ação pertence."""

    #: As três que ficam fora, cada uma com o motivo. A lista é curta de
    #: propósito: ela é a decisão, e não a exceção que engorda sozinha.
    FORA = {
        "/conta/sair/": (
            "LogoutView do Django é POST-only por segurança: aceitar GET "
            "deixaria qualquer imagem de terceiro deslogar a pessoa."
        ),
        "/conta/exportar/": (
            "`http_method_names = [\"post\"]` é garantia travada por teste do "
            "B7 — o service worker só cacheia GET, e a exportação carrega "
            "dado de saúde."
        ),
        "/treino/corridas/salvar/": (
            "API de JSON chamada por `fetch`, nunca destino de navegação: o "
            "cliente trata a resposta, e não o navegador."
        ),
        "/push/inscrever/": "chamada por `fetch` do próprio app, nunca navegada.",
        "/push/cancelar/": "chamada por `fetch` do próprio app, nunca navegada.",
    }

    #: O que o GET de cada ação deve devolver.
    DESTINO = {
        "/agua/": "/",
        "/refeicao/<int:slot_id>/marcar/": "/",
        "/refeicao/<int:slot_id>/desfazer/": "/",
        "/recalcular/": "/",
        "/recalibrar/": "/",
        "/conta/peso/": "/",
        "/treino/agora/serie/": "/treino/agora/",
        "/treino/exercicio/<int:exercise_id>/carga/": "/treino/",
        "/conquistas/vistas/": "/conquistas/",
    }

    def setUp(self):
        self.pessoa = create_complete_user("qa.acoes@exemplo.com")
        self.client.force_login(self.pessoa)

    def concreta(self, padrao):
        return (
            padrao.replace("<int:slot_id>", "1")
            .replace("<int:exercise_id>", "1")
        )

    def test_nenhuma_rota_de_post_responde_405_em_branco(self):
        """A regra, dita do jeito que a pessoa a encontra.

        Não é "toda rota precisa estar numa tabela": views que desenham um
        formulário no GET — entrar, criar conta, o wizard — já respondem bem e
        não precisam de nada. O que não pode existir é a rota que aceita POST e
        devolve 405 com corpo vazio, porque é nela que o `next` do login
        aterrissa.

        Uma view de POST nova cai aqui sozinha e obriga uma decisão: ou ela
        leva de volta a uma tela, ou entra em `FORA` com o motivo escrito.
        """
        em_branco = []
        for padrao, cls in rotas_que_recebem_post():
            if padrao in self.FORA:
                continue
            resposta = self.client.get(self.concreta(padrao))
            if resposta.status_code == 405:
                em_branco.append(
                    "%s (%s) -> 405 com %d bytes"
                    % (padrao, cls.__name__, len(resposta.content))
                )

        self.assertEqual(em_branco, [])

    def test_o_get_leva_para_a_tela_da_acao(self):
        for padrao, destino in self.DESTINO.items():
            with self.subTest(rota=padrao):
                resposta = self.client.get(self.concreta(padrao))

                self.assertEqual(resposta.status_code, 302, padrao)
                self.assertEqual(resposta["Location"], destino)

    def test_nenhuma_acao_devolve_pagina_em_branco(self):
        """O defeito original, dito do jeito que a pessoa o encontrou."""
        for padrao in self.DESTINO:
            with self.subTest(rota=padrao):
                resposta = self.client.get(self.concreta(padrao))

                self.assertNotEqual(resposta.status_code, 405, padrao)
                self.assertNotEqual(
                    (resposta.status_code, len(resposta.content)), (200, 0)
                )

    def test_o_post_continua_fazendo_o_que_fazia(self):
        """Contra-controle. Sem ele, uma view que passasse a redirecionar
        SEMPRE — inclusive no POST — passaria nos testes de cima com a ação
        quebrada."""
        antes = self.pessoa.hydration_logs.count() if hasattr(
            self.pessoa, "hydration_logs"
        ) else None

        resposta = self.client.post("/agua/", {"ml": "250"})

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("#hidratacao", resposta["Location"])
        if antes is not None:
            self.assertGreater(self.pessoa.hydration_logs.count(), antes)

    def test_o_mixin_nao_passa_na_frente_do_portao(self):
        """`AcaoDeTela` é a PRIMEIRA base de todas as nove views.

        Se ele respondesse antes do `dispatch` de `LoginRequiredMixin`, um GET
        anônimo receberia a tela em vez do login — e o mixin que existe para
        consertar um beco teria aberto um buraco. Ele define `get`, e não
        `dispatch`, justamente para isso: o portão continua rodando primeiro.
        """
        self.client.logout()

        for padrao in self.DESTINO:
            with self.subTest(rota=padrao):
                resposta = self.client.get(self.concreta(padrao))

                self.assertEqual(resposta.status_code, 302, padrao)
                self.assertIn("/conta/entrar/", resposta["Location"], padrao)

    def test_as_excecoes_existem_de_verdade(self):
        """Uma exceção para uma rota que não existe mais é lixo que esconde a
        próxima: o teste passaria sem cobrir nada."""
        rotas = {padrao for padrao, _ in rotas_que_recebem_post()}

        for padrao in self.FORA:
            with self.subTest(rota=padrao):
                self.assertIn(padrao, rotas)
