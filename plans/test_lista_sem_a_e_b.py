"""A lista de compras deixou de falar "Opção A" e "Opção B" (24/09/2026).

O rótulo A/B saiu da interface em 23/09 — o card de receita não escreve mais
a letra —, e a lista de compras ficou sendo o único lugar do app que ainda
pedia para a pessoa escolher entre duas coisas cujo nome ela nunca viu. A
varredura de 24/09 achou assim: dois botões, "OPÇÃO A" e "OPÇÃO B", e nada
na tela dizendo qual é qual.

Decisão do dono: os dois passam a se chamar "Com a sugestão do dia" e "Com a
outra opção". `OptionLabel` continua no banco, no `?opcao=` e no rodízio —
isto é nome de TELA, e era exatamente o que a docstring de `OptionLabel` já
dizia que ele era.
"""
from django.test import TestCase
from django.urls import reverse

from plans.models import OptionLabel


class AListaNaoFalaAeBTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        from plans import services
        from plans.tests import create_complete_user

        self.pessoa = create_complete_user(email="compras@exemplo.com")
        services.create_plan(self.pessoa)

    def _html(self):
        self.client.force_login(self.pessoa)
        return self.client.get(reverse("plans:shopping")).content.decode()

    def test_os_dois_botoes_dizem_o_que_escolhem(self):
        """O nome de cada botão descreve o que ele traz, e não uma letra que
        a pessoa não vê em lugar nenhum."""
        html = self._html()

        self.assertIn("Com a sugestão do dia", html)
        self.assertIn("Com a outra opção", html)
        self.assertNotIn("Opção A", html)
        self.assertNotIn("Opção B", html)

    def test_o_endereco_continua_sendo_a_letra(self):
        """`?opcao=A` é identidade de dado — está no banco, no rodízio e no
        link que a pessoa pode ter salvado. Trocar o RÓTULO não pode trocar
        o endereço."""
        html = self._html()

        self.assertIn("?opcao=%s" % OptionLabel.A, html)
        self.assertIn("?opcao=%s" % OptionLabel.B, html)

    def test_a_opcao_escolhida_continua_marcada(self):
        """O chip da opção da vez fica aceso — é o que diz qual lista está na
        tela."""
        self.client.force_login(self.pessoa)
        html = self.client.get(
            reverse("plans:shopping"), {"opcao": OptionLabel.B}
        ).content.decode()

        trecho = html.split("Com a outra opção", 1)[0][-260:]
        self.assertIn("chip--brand", trecho)
