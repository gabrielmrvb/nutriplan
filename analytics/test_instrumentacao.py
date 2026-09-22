"""Os eventos de negócio NASCEM no ponto da ação — do lado do servidor.

Por que servidor: água, refeição e série chegam pela fila offline, que drena
sem passar pela tela. Um evento de clique perderia esses; o handler que APLICA
a ação pega o online e o offline.

Cada teste posta na rota de verdade e confere que a linha nasceu com o nome
certo — e, onde importa, que NÃO nasceu (zerar água não é registrar água).
"""
from django.test import TestCase
from django.urls import reverse

from plans import services
from plans.models import MealStatus
from plans.tests import CatalogFixture, create_complete_user

from analytics.models import Event


class InstrumentacaoDeAcaoTests(CatalogFixture):
    def setUp(self):
        self.pessoa = create_complete_user(email="ev@exemplo.com")
        self.plano = services.create_plan(self.pessoa)
        self.slot = self.plano.slots.get(order=0)
        self.client.force_login(self.pessoa)

    def _nomes(self):
        return list(Event.objects.values_list("name", flat=True))

    def test_marcar_refeicao_emite_refeicao_registrada_com_a_opcao(self):
        opcao = self.slot.options.first()
        self.client.post(
            "/refeicao/%d/marcar/" % self.slot.pk,
            {"status": MealStatus.DONE, "option": opcao.pk},
        )
        evento = Event.objects.get(name="dieta.refeicao_registrada")
        self.assertEqual(evento.user, self.pessoa)
        self.assertIn("opcao", evento.props)

    def test_pular_refeicao_emite_pulou(self):
        self.client.post(
            "/refeicao/%d/marcar/" % self.slot.pk, {"status": MealStatus.SKIPPED}
        )
        self.assertIn("dieta.pulou", self._nomes())

    def test_registrar_agua_emite_agua_registrada(self):
        self.client.post("/agua/", {"ml": "250"})
        self.assertIn("agua.registrada", self._nomes())

    def test_zerar_agua_nao_emite_nada(self):
        """Zerar e desfazer não são 'registrou água'."""
        self.client.post("/agua/", {"ml": "0"})
        self.assertNotIn("agua.registrada", self._nomes())

    def test_peso_emite_faixa_nunca_o_kg_exato(self):
        self.client.post(
            reverse("accounts:log_weight"),
            {"weight_kg": "82,4", "origem": "metricas"},
        )
        evento = Event.objects.get(name="progresso.peso_registrado")
        self.assertEqual(evento.props.get("faixa"), "80-85")
        # O kg exato não pode vazar em propriedade nenhuma.
        self.assertNotIn("82.4", str(evento.props))
        self.assertNotIn("82,4", str(evento.props))


class InstrumentacaoDeContaTests(TestCase):
    def test_signup_emite_conta_criada_e_onboarding_iniciado(self):
        self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Ana",
                "email": "novo@exemplo.com",
                "password1": "senha-bem-forte-123",
                "password2": "senha-bem-forte-123",
                "termos": "on",
            },
        )
        nomes = set(Event.objects.values_list("name", flat=True))
        self.assertIn("conta.criada", nomes)
        self.assertIn("onboarding.iniciado", nomes)
