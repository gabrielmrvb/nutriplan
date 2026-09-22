"""Duas frases que mandavam a pessoa para um lugar que não existia (achados
#14 e #18 da avaliação por personas, 21–22/09/2026).

O boas-vindas sai no CADASTRO, antes do onboarding — e dizia "abra a tela
Hoje e registre a próxima refeição", sendo que a Home ainda devolve quem
não terminou as três etapas. E a ajuda dos avisos no aparelho apontava para
"Perfil › Lembretes", que nunca existiu: o cartão Lembretes mora no fim da
tela Hoje.
"""

import re

from django.core import mail
from django.test import TestCase, override_settings

from plans.tests import create_complete_user

from . import services
from .forms import PreferenciaForm


@override_settings(NUTRIPLAN_URL_BASE="https://app.exemplo")
class OBoasVindasFalaDoCadastroPrimeiroTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="nova@exemplo.com")
        self.user.first_name = "Dani"
        self.user.save()

    def _corpos(self):
        self.assertEqual(services.boas_vindas(self.user), "enviado")
        msg = mail.outbox[0]
        return msg.body, msg.alternatives[0][0]

    def test_o_primeiro_passo_e_terminar_as_tres_etapas(self):
        """Quem recebe este e-mail acabou de criar a conta e ainda não tem
        estimativa nem ficha: o passo 1 tem de ser o que ela consegue fazer
        AGORA. Nas duas versões, texto e HTML."""
        for corpo in self._corpos():
            with self.subTest(corpo=corpo[:30]):
                visivel = re.sub(r"<[^>]+>", " ", corpo)
                lista = visivel[visivel.index("O que fazer primeiro"):]
                inicio_do_1 = lista.index("1")
                inicio_do_2 = lista.index("2", inicio_do_1 + 1)
                passo_1 = lista[inicio_do_1:inicio_do_2]
                self.assertIn("3 etapas", passo_1)
                self.assertNotIn("registre a próxima refeição", passo_1)

    def test_doutrina_interna_nao_vaza_para_a_pessoa(self):
        """"Num lugar, sem promessa" é frase do CLAUDE.md, não do produto."""
        for corpo in self._corpos():
            self.assertNotIn("sem promessa", corpo)


class AAjudaDosPushesApontaParaOndeOCartaoEstaTests(TestCase):
    def test_a_ajuda_nao_inventa_uma_tela_e_diz_a_que_existe(self):
        ajuda = PreferenciaForm().fields["pushes"].help_text
        self.assertNotIn("Perfil › Lembretes", ajuda)
        self.assertIn("Hoje", ajuda)
