"""A corrida é um pilar nas telas que resumem — e não só em Áreas.

Achado #9 das personas (21/09/2026), a que só corre: o Progresso não tinha
UMA linha sobre corrida (peso, "Treino: Nenhuma série anotada", água); a
exclusão da conta listava "Estimativas 1 · Refeições 1 · Água 1 · Pesagens
1" e esquecia as duas corridas; e a caixa das refeições dizia "Ainda não
há nada marcado" para quem tinha registrado 25 séries na véspera — a frase
era das REFEIÇÕES e lia como "nada".
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.views import resumo_do_que_sera_apagado
from plans.tests import create_complete_user
from workouts.models import Corrida


def _correr(user, dias_atras, km):
    fim = timezone.now() - timedelta(days=dias_atras)
    return Corrida.objects.create(
        user=user, op_id="corrida-%d-%s" % (dias_atras, km), comecou_em=fim - timedelta(minutes=30),
        terminou_em=fim, distancia_m=int(km * 1000), duracao_s=1800,
    )


class CorridaNoProgressoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(email="corre@exemplo.com")
        self.client.force_login(self.user)

    def test_quem_correu_ve_a_corrida_no_progresso(self):
        # a suíte vive numa quarta: 1 e 2 dias atrás caem na MESMA semana
        _correr(self.user, 1, 5.0)
        _correr(self.user, 2, 4.2)
        html = self.client.get(reverse("plans:history")).content.decode()
        bloco = html.split("<h2>Corrida</h2>", 1)[1].split("</section>", 1)[0]
        self.assertIn("9,2", bloco)  # km da semana, com vírgula
        self.assertIn(reverse("workouts:corridas"), bloco)

    def test_quem_nunca_correu_nao_ganha_o_cartao(self):
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertNotIn("<h2>Corrida</h2>", html)

    def test_a_exclusao_lista_as_corridas(self):
        _correr(self.user, 1, 5.0)
        _correr(self.user, 3, 4.2)
        linhas = dict(resumo_do_que_sera_apagado(self.user))
        self.assertEqual(linhas.get("Corridas"), 2)

    def test_a_ajuda_tem_uma_pergunta_sobre_corrida(self):
        html = self.client.get(reverse("ajuda:index")).content.decode()
        self.assertIn("Eu só corro", html)
        self.assertIn("Não faço musculação", html)

    def test_a_caixa_das_refeicoes_fala_de_refeicoes(self):
        html = self.client.get(reverse("plans:history")).content.decode()
        self.assertNotIn("Ainda não há nada marcado", html)
        self.assertIn("Nenhuma refeição registrada", html)
