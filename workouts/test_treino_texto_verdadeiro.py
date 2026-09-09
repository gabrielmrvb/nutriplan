"""TREINO — o resumo do programa diz de que PERÍODO o número é.

A linha dizia "85 séries no total", e o total é da SEMANA: `total_sets` soma
`session.total_sets` de todas as sessões do plano. "No total" convida a ler
como o treino de hoje, que é o cartão logo acima — e 85 séries num dia é um
número absurdo o bastante para a pessoa desconfiar do app inteiro.

Custa duas palavras dizer o período certo.

O teste mede a PROPRIEDADE, e não só a frase: o número exibido tem de ser a
soma da semana, e uma sessão sozinha tem de ser menor que ele quando há mais
de uma. Sem isso, alguém "consertaria" o texto trocando a variável por
`hoje.total_sets` e a linha continuaria mentindo, agora ao contrário.
"""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import services
from .tests import create_user


class OTotalDeSeriesDizQueEDaSemanaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        # Três dias: a semana precisa ter MAIS de uma sessão, senão a soma
        # semanal e a de uma sessão dariam igual e o teste do número não
        # distinguiria as duas.
        self.pessoa = create_user(weekdays=(0, 2, 4))
        services.sync_active_routine(self.pessoa)
        self.client.force_login(self.pessoa)

    def _tela(self):
        return self.client.get(reverse("workouts:routine"))

    def test_o_resumo_do_programa_diz_por_semana(self):
        self.assertContains(self._tela(), "séries por semana")

    def test_o_resumo_nao_diz_mais_no_total(self):
        """"No total" convida a ler como o treino de hoje."""
        self.assertNotContains(self._tela(), "séries no total")

    def test_o_numero_exibido_e_mesmo_a_soma_da_semana(self):
        """A frase certa sobre o número errado continuaria sendo mentira."""
        resposta = self._tela()
        plano = resposta.context["plan"]
        semana = sum(s.total_sets for s in plano.sessions.all())

        self.assertEqual(resposta.context["total_sets"], semana)
        self.assertContains(resposta, "%d séries por semana" % semana)

    def test_uma_sessao_sozinha_e_menor_que_a_semana(self):
        """Controle: se as duas contas dessem igual, o teste acima não mediria
        nada — é o caso de quem treina uma vez por semana."""
        plano = self._tela().context["plan"]
        sessoes = list(plano.sessions.all())

        self.assertGreater(len(sessoes), 1)
        self.assertLess(sessoes[0].total_sets,
                        sum(s.total_sets for s in sessoes))
