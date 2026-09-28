"""QUEM NÃO FAZ MUSCULAÇÃO NÃO VÊ TREINO NA HOME (decisão do dono, #138, 28/09/2026).

A persona que só corre respondeu "não" na etapa 2 e mesmo assim a Home
abria com um cartão "Treino · Sem ficha · Montar treino" — cobrando a
ficha que ela disse não querer, no lugar do que ela FAZ. Hoje o painel
dela é Alimentação e Corrida primeiro, e o cartão de treino não existe.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Musculacao, TrainingDay
from plans.tests import create_complete_user
from plans.views import cartoes_do_painel
from workouts.models import TrainingPlan


class OPainelDeQuemNaoFazMusculacaoTests(TestCase):
    def test_sem_musculacao_o_painel_nao_tem_treino_e_tem_corrida(self):
        chaves = [c["chave"] for c in cartoes_do_painel("", declarados=(), faz_musculacao=False)]
        self.assertNotIn("treino", chaves)
        self.assertEqual(chaves[:2], ["dieta", "corrida"])

    def test_a_area_principal_continua_primeiro(self):
        chaves = [c["chave"] for c in cartoes_do_painel("corrida", declarados=("corrida",), faz_musculacao=False)]
        self.assertEqual(chaves[:2], ["corrida", "dieta"])

    def test_controle_quem_faz_musculacao_continua_com_o_cartao_de_treino(self):
        chaves = [c["chave"] for c in cartoes_do_painel("", declarados=())]
        self.assertIn("treino", chaves)
        self.assertNotIn("corrida", chaves)


class AHomeDeQuemSoCorreTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(musculacao=Musculacao.NAO)
        TrainingDay.objects.filter(user=self.user).delete()
        TrainingPlan.objects.filter(user=self.user).update(is_active=False)
        self.client.force_login(self.user)

    def test_a_home_nao_cobra_ficha_e_mostra_a_corrida(self):
        home = self.client.get(reverse("plans:today"))
        self.assertNotContains(home, "Montar treino")
        self.assertNotContains(home, "Sem ficha")
        # O cartão de corrida, ancorado no texto visível do estado vazio.
        self.assertContains(home, "Registrar corrida")

    def test_controle_quem_nao_respondeu_ainda_ve_montar_treino(self):
        self.user.profile.musculacao = ""
        self.user.profile.save(update_fields=["musculacao"])
        home = self.client.get(reverse("plans:today"))
        self.assertContains(home, "Montar treino")
