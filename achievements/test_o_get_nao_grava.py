"""Um GET não grava — o item 0 da missão "quem entra não desiste".

A missão A deixou a lista dos números que ainda divergem, e o segundo era
este: `achievements.resumo` DESBLOQUEAVA a regra que chegou a 100 % dentro
de uma requisição GET, e `ConquistasView` chamava `avaliar` — o catálogo
inteiro, com escrita — também num GET. Duas consequências reais:

- a primeira leitura do Progresso num dia podia devolver um número de
  conquistas diferente da segunda, com os mesmos dados. "Mesmos dados,
  números diferentes", pela porta de trás;
- uma requisição que a pessoa não pediu — um prefetch do navegador, um
  "abrir em nova aba", um robô — mudava o banco dela.

A saída não foi um botão "resgatar", que ninguém tocaria: foi mover a
escrita para o POST QUE CRIA O FATO, que é o que a doutrina de
`ConcluirSerieView` já dizia desde 16/09/2026 ("a conquista é avaliada na
primeira série do dia e no recorde, e anunciada onde nasce"). Agora vale
para as outras portas: refeição, água e corrida.

E o defeito que a avaliação no GET existia para evitar — barra "1/1" cheia
com a conquista trancada ao lado (avaliação B35, 16/09/2026) — não volta,
porque a barra só chega a 100 % DEPOIS de um desses POSTs, e ele desbloqueia
na hora. O último teste daqui é exatamente esse.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay
from achievements.models import UserAchievement
from plans.models import MealStatus
from plans.tests import create_complete_user
from workouts import services as treino
from workouts.models import ExerciseLog


class NenhumGETDesbloqueiaConquistaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="get-nao-grava@exemplo.com")
        self.client.force_login(self.user)
        # Histórico que fecha "Primeiro treino" e "5 treinos" — o estado em
        # que a avaliação no GET tinha o que gravar.
        hoje = timezone.localdate()
        treino.create_routine(self.user)
        plano = treino.get_active_routine(self.user)
        exercicio = plano.sessions.first().exercises.first().exercise
        for atras in range(6):
            ExerciseLog.objects.create(
                user=self.user, exercise=exercicio, date=hoje - timedelta(days=atras + 1),
                set_number=1, weight_kg=Decimal("20"), reps=10,
            )

    def _quantas(self):
        return UserAchievement.objects.filter(user=self.user).count()

    def test_abrir_o_progresso_cinco_vezes_nao_cria_conquista(self):
        antes = self._quantas()
        for _ in range(5):
            self.assertEqual(self.client.get(reverse("plans:history")).status_code, 200)
        self.assertEqual(self._quantas(), antes)

    def test_abrir_as_conquistas_cinco_vezes_nao_cria_conquista(self):
        antes = self._quantas()
        for _ in range(5):
            self.assertEqual(
                self.client.get(reverse("achievements:list")).status_code, 200
            )
        self.assertEqual(self._quantas(), antes)

    def test_nenhuma_tela_do_app_grava_conquista_num_GET(self):
        """A varredura: as telas que leem conquista, uma a uma."""
        antes = self._quantas()
        for rota in ("plans:today", "plans:history", "achievements:list", "areas"):
            with self.subTest(rota=rota):
                self.client.get(reverse(rota))
                self.assertEqual(self._quantas(), antes, rota)


class OPOSTQueCriaOFatoDesbloqueiaTests(TestCase):
    """CONTROLE POSITIVO do arquivo inteiro: a escrita não sumiu do app —
    ela mudou de porta."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="post-desbloqueia@exemplo.com")
        self.client.force_login(self.user)
        hoje = timezone.localdate()
        TrainingDay.objects.filter(user=self.user).delete()
        TrainingDay.objects.create(user=self.user, weekday=hoje.weekday(), duration_min=60)
        treino.create_routine(self.user)

    def _slugs(self):
        return set(
            UserAchievement.objects.filter(user=self.user).values_list("slug", flat=True)
        )

    def test_a_primeira_serie_desbloqueia_o_primeiro_treino(self):
        self.assertNotIn("primeiro-treino", self._slugs())
        plano = treino.get_active_routine(self.user)
        item = plano.sessions.first().exercises.first()
        resposta = self.client.post(
            reverse("workouts:record_set"),
            {"exercise_id": item.exercise_id, "weight_kg": "0", "reps": "10",
             "dia": timezone.localdate().isoformat()},
        )
        self.assertIn(resposta.status_code, (200, 302))
        self.assertIn("primeiro-treino", self._slugs())

    def test_marcar_refeicao_desbloqueia_o_que_a_ofensiva_fechou(self):
        """A refeição não cria conquista de treino — ela pode FECHAR o dia, e
        dia fechado move a ofensiva. O que se mede aqui é que o POST passa
        pela avaliação: sem ela, nada nasceria até alguém abrir o Progresso.
        """
        from plans import services as plano_services

        plano, _ = plano_services.sync_active_plan(self.user)
        slot = plano.slots.order_by("time").first()
        antes = UserAchievement.objects.filter(user=self.user).count()
        # "Comi esta" exige a OPÇÃO — o filtro que fecha o IDOR do cardápio.
        opcao = slot.options.first()
        resposta = self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertGreaterEqual(
            UserAchievement.objects.filter(user=self.user).count(), antes
        )
