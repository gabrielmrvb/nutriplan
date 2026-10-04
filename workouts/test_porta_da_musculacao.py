"""/TREINO/ É A PORTA PARA COMEÇAR A MUSCULAÇÃO (decisão do dono, #138, 28/09/2026).

Para quem disse que não faz musculação, a aba Treino era um parágrafo
("Você disse que não faz musculação…") e um link pequeno de rodapé — a
tela só texto que a onda 5 do pente-fino de qualidade mediu. A decisão é
que ela vire a porta de ativar a musculação depois: o convite é o botão
principal da tela. E "Exercícios que já fiz", vazia, mandava essa pessoa
"Ver a semana" — de uma ficha que ela não tem.
"""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Musculacao, TrainingDay
from plans.tests import create_complete_user
from workouts.models import TrainingPlan

ETAPA_2 = reverse("accounts:onboarding_step", kwargs={"step": 2}) + "?origem=treino"


class AAbaTreinoDeQuemNaoFazMusculacaoTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(musculacao=Musculacao.NAO)
        TrainingDay.objects.filter(user=self.user).delete()
        TrainingPlan.objects.filter(user=self.user).update(is_active=False)
        self.client.force_login(self.user)

    def test_o_convite_e_o_botao_principal(self):
        tela = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIn('class="btn btn--primary btn--block" href="%s"' % ETAPA_2.replace("&", "&amp;"), tela)
        self.assertIn("Começar a musculação", tela)
        self.assertNotIn("btn-link--rodape", tela)

    def test_exercicios_que_ja_fiz_nao_manda_ver_a_semana(self):
        tela = self.client.get(reverse("workouts:exercicios_feitos"))
        self.assertNotContains(tela, "Ver a semana")
        self.assertContains(tela, "Começar a musculação")

    def test_controle_quem_faz_musculacao_e_nao_tem_serie_ve_a_semana(self):
        self.user.profile.musculacao = Musculacao.SIM
        self.user.profile.save(update_fields=["musculacao"])
        self.assertContains(self.client.get(reverse("workouts:exercicios_feitos")), "Ver a semana")
