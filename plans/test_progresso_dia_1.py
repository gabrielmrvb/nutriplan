"""O PROGRESSO NO DIA 1 E DE QUEM SÓ CORRE (pente-fino de qualidade, onda 5, 28/09/2026).

Dois achados medidos nas capturas:

- dia 1 com treino previsto HOJE: o tile dizia "Treinos 0 de 1 ↓" às
  14h — seta de queda para um treino que ainda pode acontecer. Hoje só
  conta quando já tem série (a régua de "hoje só cobra o que já passou",
  a mesma da aderência e da seta da água);
- quem não faz musculação (#138): tile "Treinos 0 · Sem dia de treino
  previsto" e a seção Treino com "Abrir o treino de hoje". Ela vê a
  corrida no lugar, com o estado vazio levando a registrar a primeira.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Musculacao, TrainingDay
from plans import evolucao
from plans.tests import create_complete_user
from workouts.models import TrainingPlan


def dia(data, estado):
    return evolucao.DiaDoMapa(data=data, estado=estado, intensidade=0, titulo="")


class OTileDeTreinoNaoCobraHojeTests(TestCase):
    def test_hoje_sem_serie_nao_e_falta(self):
        hoje = timezone.localdate()
        tile = evolucao.tile_de_treino([dia(hoje, evolucao.FALTOU)], {hoje.weekday()})
        self.assertEqual(tile.direcao, evolucao.SEM_DIRECAO)
        self.assertEqual(tile.frase, "Hoje é dia de treino.")

    def test_controle_ontem_sem_serie_continua_falta(self):
        ontem = timezone.localdate() - timedelta(days=1)
        tile = evolucao.tile_de_treino([dia(ontem, evolucao.FALTOU)], {ontem.weekday()})
        self.assertEqual(tile.direcao, evolucao.CAINDO)
        self.assertEqual(tile.unidade, "de 1")


class OProgressoDeQuemSoCorreTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(musculacao=Musculacao.NAO)
        TrainingDay.objects.filter(user=self.user).delete()
        TrainingPlan.objects.filter(user=self.user).update(is_active=False)
        self.client.force_login(self.user)

    def test_sem_treino_e_com_corrida(self):
        tela = self.client.get(reverse("plans:history"))
        self.assertNotContains(tela, "Abrir o treino de hoje")
        self.assertNotContains(tela, 'id="area-treino"')
        self.assertContains(tela, 'id="area-corrida"')
        self.assertContains(tela, "Registrar a primeira corrida")
        chaves = [t.chave for t in tela.context["painel"]["tiles"]]
        self.assertNotIn("treino", chaves)
        self.assertIn("corrida", chaves)

    def test_controle_quem_treina_ve_o_treino(self):
        self.user.profile.musculacao = Musculacao.SIM
        self.user.profile.save(update_fields=["musculacao"])
        tela = self.client.get(reverse("plans:history"))
        self.assertContains(tela, 'id="area-treino"')
