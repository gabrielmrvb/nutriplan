"""B2 — HOJE: a escrita nao pode custar a posicao na tela.

A tela Hoje tem de 4 a 5 dobras. Medido no navegador, em 375x812: o cartao de
agua comeca em y=2491, e cada toque em "+250" era rolar 2500px, tocar e ser
jogado de volta ao topo — porque toda escrita da tela redirecionava para
`plans:today` sem ancora. Para fechar tres litros de 250 em 250 sao doze idas.

O mesmo valia para marcar refeicao (cinco por dia, cartoes espalhados ate a
dobra 2.9) e para desfazer.

As ancoras ja existiam no template: `#hidratacao` no cartao de agua e
`#slot-<pk>` em cada refeicao — esta ultima ja usada pelo cartao AGORA para
levar ate a refeicao da vez. O conserto foi usa-las no redirect.

Os testes cobrem as duas metades, e a segunda e a que costuma faltar: nao basta
o redirect apontar para a ancora, a ancora precisa EXISTIR na pagina. Um
`#hidratacao` que nao existe no HTML deixa o navegador exatamente onde ele
estaria sem ancora nenhuma, e o teste do redirect passaria mesmo assim.
"""
from django.test import TestCase
from django.urls import reverse

from plans import services
from plans.models import MealStatus
from plans.tests import CatalogFixture, create_complete_user


class AEscritaVoltaParaOndeAPessoaEstavaTests(CatalogFixture):
    def setUp(self):
        self.pessoa = create_complete_user(email="b2@exemplo.com")
        self.plano = services.create_plan(self.pessoa)
        self.slot = self.plano.slots.get(order=0)
        self.client.force_login(self.pessoa)

    # ------------------------------------------------ agua

    def test_registrar_agua_volta_para_o_cartao_de_agua(self):
        resposta = self.client.post("/agua/", {"ml": "250"})

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            resposta["Location"].endswith("#hidratacao"), resposta["Location"]
        )

    def test_agua_invalida_fica_no_topo_onde_esta_a_mensagem(self):
        """O contra-controle. Ancorar aqui rolaria a tela para longe do texto
        que explica o que deu errado — a mensagem e renderizada no topo."""
        resposta = self.client.post("/agua/", {"ml": "37"})

        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn("#", resposta["Location"])

    def test_reenvio_da_fila_offline_tambem_volta_para_o_cartao(self):
        """A trava de idempotencia devolve sem gravar de novo, e quem esta
        reenviando tambem estava olhando o cartao."""
        self.client.post("/agua/", {"ml": "250", "op_id": "repetida"})

        resposta = self.client.post("/agua/", {"ml": "250", "op_id": "repetida"})

        self.assertTrue(resposta["Location"].endswith("#hidratacao"))

    # ------------------------------------------------ refeicao

    def test_marcar_refeicao_volta_para_a_refeicao(self):
        resposta = self.client.post(
            "/refeicao/%d/marcar/" % self.slot.pk, {"status": MealStatus.SKIPPED}
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            resposta["Location"].endswith("#slot-%d" % self.slot.pk),
            resposta["Location"],
        )

    def test_desfazer_volta_para_a_refeicao(self):
        self.client.post(
            "/refeicao/%d/marcar/" % self.slot.pk, {"status": MealStatus.SKIPPED}
        )

        resposta = self.client.post("/refeicao/%d/desfazer/" % self.slot.pk)

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            resposta["Location"].endswith("#slot-%d" % self.slot.pk),
            resposta["Location"],
        )


class AsAncorasExistemNaPaginaTests(CatalogFixture):
    """A metade que costuma faltar.

    Redirecionar para `#hidratacao` nao adianta nada se o `id` nao estiver no
    HTML: o navegador para onde pararia sem ancora nenhuma, e o teste do
    redirect continua verde. Estes testes leem a pagina.
    """

    def setUp(self):
        self.pessoa = create_complete_user(email="ancora@exemplo.com")
        self.plano = services.create_plan(self.pessoa)
        self.slot = self.plano.slots.get(order=0)
        self.client.force_login(self.pessoa)

    def test_o_cartao_de_agua_tem_a_ancora(self):
        resposta = self.client.get(reverse("plans:today"))

        self.assertContains(resposta, 'id="hidratacao"')

    def test_cada_refeicao_tem_a_sua_ancora(self):
        resposta = self.client.get(reverse("plans:today"))

        for slot in self.plano.slots.all():
            with self.subTest(slot=slot.pk):
                self.assertContains(resposta, 'id="slot-%d"' % slot.pk)

    def test_a_ancora_da_refeicao_sobrevive_a_marcacao(self):
        """`#refeicao-<pk>` NAO serve: ele fica no `<details>` do "comi outra
        coisa", que so existe enquanto a refeicao esta pendente. Depois de
        marcada ele some, e o redirect cairia no vazio. `#slot-<pk>` fica no
        cartao e continua la."""
        self.client.post(
            "/refeicao/%d/marcar/" % self.slot.pk, {"status": MealStatus.SKIPPED}
        )

        resposta = self.client.get(reverse("plans:today"))

        self.assertContains(resposta, 'id="slot-%d"' % self.slot.pk)
