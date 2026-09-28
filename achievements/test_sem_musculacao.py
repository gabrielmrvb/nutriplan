"""AS CONQUISTAS DE QUEM NÃO FAZ MUSCULAÇÃO (decisão do dono, #138, 28/09/2026).

A persona que só corre abria as Conquistas e via "Primeiro treino 0/1",
"5 treinos" e "3 dias de ofensiva" — metas de uma ficha que ela disse não
ter, e a ofensiva exige um dia treinado para valer (`regras._ofensiva`),
então nem essa ela conseguiria fechar. Hoje ela vê o que faz: corrida e
alimentação. E as duas famílias passaram a existir para todo mundo — com a
corrida só para quem corre, senão "Primeira corrida 0/1" viraria medalha
cinzenta na tela de quem só treina.
"""
from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from accounts.models import Musculacao, TrainingDay
from achievements import services
from achievements.models import UserAchievement
from achievements.regras import Familia
from plans.models import MealLog, MealStatus
from plans.tests import create_complete_user
from workouts.models import Corrida, TrainingPlan


def correr(user, dias_atras=0, km=5):
    inicio = timezone.now() - timedelta(days=dias_atras, hours=1)
    return Corrida.objects.create(
        user=user, op_id=uuid4().hex, comecou_em=inicio,
        terminou_em=inicio + timedelta(minutes=30), distancia_m=km * 1000, duracao_s=1800,
    )


def comer(user, dias_atras=0):
    return MealLog.objects.create(
        user=user, date=timezone.localdate() - timedelta(days=dias_atras), status=MealStatus.DONE,
    )


class ASoCorredoraTests(TestCase):
    def setUp(self):
        self.user = create_complete_user(musculacao=Musculacao.NAO)
        TrainingDay.objects.filter(user=self.user).delete()
        TrainingPlan.objects.filter(user=self.user).update(is_active=False)

    def familias_a_caminho(self):
        dados = services.reunir(self.user)
        return {c["regra"].familia for c in services.a_caminho(dados, set())}

    def test_a_caminho_so_tem_corrida_e_alimentacao(self):
        self.assertEqual(self.familias_a_caminho(), {Familia.CORRIDA, Familia.DIETA})

    def test_a_primeira_corrida_vira_conquista(self):
        correr(self.user)
        slugs = {c.slug for c in services.avaliar(self.user)}
        self.assertIn("primeira-corrida", slugs)

    def test_a_primeira_refeicao_registrada_vira_conquista(self):
        comer(self.user)
        slugs = {c.slug for c in services.avaliar(self.user)}
        self.assertIn("primeira-refeicao", slugs)

    def test_refeicao_pulada_nao_conta(self):
        MealLog.objects.create(user=self.user, status=MealStatus.SKIPPED)
        self.assertEqual(services.reunir(self.user).dias_com_refeicao, 0)

    def test_comi_outra_coisa_conta_porque_registrar_honesto_nao_pode_custar(self):
        MealLog.objects.create(user=self.user, status=MealStatus.OFF_PLAN)
        self.assertEqual(services.reunir(self.user).dias_com_refeicao, 1)

    def test_sete_dias_com_refeicao_contam_dias_e_nao_refeicoes(self):
        for dia in range(7):
            comer(self.user, dia)
            comer(self.user, dia)
        self.assertEqual(services.reunir(self.user).dias_com_refeicao, 7)
        self.assertIn("refeicoes-7-dias", {c.slug for c in services.avaliar(self.user)})

    def test_a_tela_nao_mostra_meta_de_treino(self):
        self.client.force_login(self.user)
        tela = self.client.get("/conquistas/")
        self.assertNotContains(tela, "Primeiro treino")
        self.assertContains(tela, "Primeira corrida")

    def test_o_vazio_convida_ao_cardapio_e_nao_ao_treino(self):
        self.client.force_login(self.user)
        tela = self.client.get("/conquistas/")
        self.assertContains(tela, "Ver o cardápio de hoje")
        self.assertNotContains(tela, "Ver o treino</a>")
        self.assertNotContains(tela, "de treino</span>")

    def test_conquista_de_treino_ganha_antes_continua_na_tela(self):
        """Conquista registra o que aconteceu — dizer "não" depois não a apaga."""
        UserAchievement.objects.create(user=self.user, slug="primeiro-treino", chave="")
        self.client.force_login(self.user)
        self.assertContains(self.client.get("/conquistas/"), "Primeiro treino")


class QuemTreinaTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()

    def test_controle_quem_treina_continua_vendo_as_de_treino(self):
        familias = {c["regra"].familia for c in services.a_caminho(services.reunir(self.user), set())}
        self.assertIn(Familia.TREINO, familias)
        self.assertIn(Familia.DIETA, familias)

    def test_quem_treina_e_nunca_correu_nao_ganha_meta_de_corrida(self):
        familias = {c["regra"].familia for c in services.a_caminho(services.reunir(self.user), set())}
        self.assertNotIn(Familia.CORRIDA, familias)

    def test_quem_treina_e_corre_ve_a_corrida(self):
        correr(self.user)
        familias = {c["regra"].familia for c in services.a_caminho(services.reunir(self.user), set())}
        self.assertIn(Familia.CORRIDA, familias)
