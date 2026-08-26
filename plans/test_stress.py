"""Desempenho sob um ano de histórico.

Estes testes não medem tempo — medem CONSULTAS. Tempo varia com a máquina e
transformaria a suíte numa fonte de falhas intermitentes; contagem de consultas
é determinística e é onde o problema real mora.

O que eles pegam é a consulta dentro de laço. Com duas semanas de dados
qualquer desenho parece rápido, e o custo só aparece no dia trezentos — quando
a pessoa já depende do app e a tela demora. Foi assim que `muscle_volume`
apareceu: 44 idas ao banco num total de 66, porque recebia o plano e reabria um
queryset sem o prefetch que a view tinha acabado de montar.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry
from workouts.models import Exercise, ExerciseLog
from workouts.services import create_routine

from . import services, streaks, weight_trend
from .models import HydrationLog, MealLog, MealStatus
from .tests import CatalogFixture, create_complete_user

#: Um ano inteiro seria lento de montar em cada teste. Noventa dias já é
#: bastante para um N+1 aparecer — o que importa é a consulta crescer com o
#: número de LINHAS da ficha, e isso não depende de quantos dias há atrás.
DIAS = 90


class PopulatedAccountMixin:
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.rotina = create_routine(self.user)
        self._povoar()
        self.client.force_login(self.user)

    def _povoar(self):
        hoje = timezone.localdate()
        exercicios = list(Exercise.objects.filter(is_active=True)[:6])
        slots = list(self.plan.slots.all())

        WeightEntry.objects.filter(user=self.user).delete()
        WeightEntry.objects.bulk_create(
            WeightEntry(
                user=self.user,
                date=hoje - timedelta(days=i),
                weight_kg=Decimal("90") - Decimal(i) / 40,
            )
            for i in range(DIAS)
        )
        # 3500 ml e não 2500: a meta de quem pesa 90 kg é 3150 (35 ml/kg), e a
        # ofensiva cobra 90% dela. Com 2500 o dia nunca fecha e a sequência
        # ficaria em zero — medindo a fixture, não o código.
        HydrationLog.objects.bulk_create(
            HydrationLog(user=self.user, date=hoje - timedelta(days=i), ml=3500)
            for i in range(DIAS)
        )
        MealLog.objects.bulk_create(
            MealLog(
                user=self.user,
                slot=slot,
                date=hoje - timedelta(days=i),
                status=MealStatus.DONE,
                slot_name=slot.name,
                scheduled_time=slot.time,
            )
            for i in range(DIAS)
            for slot in slots
        )
        ExerciseLog.objects.bulk_create(
            ExerciseLog(
                user=self.user,
                exercise=exercicio,
                date=hoje - timedelta(days=i),
                set_number=serie,
                weight_kg=Decimal("60"),
                reps=10,
            )
            for i in range(0, DIAS, 2)
            for exercicio in exercicios
            for serie in (1, 2, 3)
        )


class ScreenQueryBudgetTests(PopulatedAccountMixin, TestCase):
    """Um teto por tela. Estourar não é lentidão — é laço com consulta dentro."""

    #: Os números vêm da medição com um ano de dados, com folga para o app
    #: crescer. Se algum deles subir de repente, apareceu um N+1.
    TETOS = {
        "plans:today": 40,
        "workouts:routine": 25,
        "plans:history": 15,
        "supplements:list": 15,
        "accounts:profile": 15,
    }

    def test_no_screen_grows_a_query_per_row(self):
        # Teto e não valor exato: `assertNumQueries` casa o número certo, e um
        # teste que quebra ao MELHORAR o desempenho é um teste que ensina a
        # ignorá-lo.
        for rota, teto in self.TETOS.items():
            with self.subTest(rota=rota):
                url = reverse(rota)
                self.client.get(url)  # aquece o que é cacheado por processo
                with CaptureQueriesContext(connection) as ctx:
                    resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertLessEqual(
                    len(ctx.captured_queries),
                    teto,
                    f"{rota} fez {len(ctx.captured_queries)} consultas "
                    f"(teto {teto}) — provável consulta dentro de laço",
                )


class MuscleVolumeRegressionTests(PopulatedAccountMixin, TestCase):
    """A regressão específica que a medição encontrou.

    `muscle_volume` recebia o PLANO e chamava `plan.sessions.all()`, abrindo um
    queryset novo — sem o prefetch que a view tinha acabado de montar. Cada
    `item.exercise` virava uma consulta: 44 de 66 na página de treino.
    """

    def test_it_reads_the_sessions_it_was_given(self):
        from workouts import views

        sessions = list(
            self.rotina.sessions.prefetch_related("exercises__exercise")
        )

        # Com as sessões já carregadas, montar o volume não custa consulta
        # nenhuma. Se alguém voltar a receber o plano, este número explode.
        with self.assertNumQueries(0):
            linhas = views.muscle_volume(sessions)

        self.assertTrue(linhas)
        self.assertTrue(all(l["sets"] > 0 for l in linhas))

    def test_the_week_overview_also_reuses_them(self):
        from workouts import views

        sessions = list(self.rotina.sessions.all())
        with self.assertNumQueries(0):
            semana = views.week_overview(sessions)

        self.assertEqual(len(semana), 7)


class HeavyComputationTests(PopulatedAccountMixin, TestCase):
    """Os cálculos que percorrem a série inteira em Python."""

    def test_the_streak_does_not_query_per_day(self):
        """Percorre 400 dias em Python, e isso é barato — o que não pode é
        consultar por dia. Medido com um ano de dados: 6 ms."""
        meta = weight_trend.hidratacao_ml(self.plan.weight_kg)
        streaks.calcular(self.user, meta_agua_ml=meta)  # aquece o cache do plano

        with CaptureQueriesContext(connection) as ctx:
            ofensiva = streaks.calcular(self.user, meta_agua_ml=meta)

        self.assertLessEqual(len(ctx.captured_queries), 8)
        self.assertGreater(ofensiva.dias, 0)

    def test_the_weight_history_is_capped(self):
        """Sem teto, o gráfico desenharia uma barra por semana desde sempre —
        cinquenta e duas colunas de 6px numa tela de 390."""
        semanas = weight_trend.analisar(self.user).semanas
        self.assertLessEqual(len(semanas), weight_trend.SEMANAS_NO_HISTORICO)

    def test_the_diet_history_is_capped(self):
        from . import tracking

        linhas = tracking.history(self.user)
        self.assertLessEqual(len(linhas), tracking.HISTORY_DAYS)


class StressSeedTests(TestCase):
    """O próprio gerador de carga."""

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)
        call_command("seed_supplements", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()

    def test_it_generates_a_year_of_everything(self):
        call_command("seed_stress", self.user.email, "--dias", "365", verbosity=0)

        self.assertGreater(WeightEntry.objects.filter(user=self.user).count(), 150)
        self.assertGreater(MealLog.objects.filter(user=self.user).count(), 1000)
        self.assertGreater(ExerciseLog.objects.filter(user=self.user).count(), 1000)

    def test_running_it_twice_does_not_double_the_history(self):
        call_command("seed_stress", self.user.email, "--dias", "60", verbosity=0)
        antes = MealLog.objects.filter(user=self.user).count()

        call_command("seed_stress", self.user.email, "--dias", "60", verbosity=0)

        self.assertEqual(MealLog.objects.filter(user=self.user).count(), antes)

    def test_the_same_seed_gives_the_same_history(self):
        """Semente fixa: comparar medições entre execuções só faz sentido se o
        histórico for o mesmo."""
        # `--limpar` nas duas: sem ele, a primeira execução carrega a pesagem
        # que o onboarding criou e a segunda a apaga — os históricos diferem
        # por causa da fixture, não do gerador.
        call_command(
            "seed_stress", self.user.email, "--dias", "30", "--limpar", verbosity=0
        )
        primeiro = list(
            WeightEntry.objects.filter(user=self.user)
            .order_by("date")
            .values_list("weight_kg", flat=True)
        )

        call_command(
            "seed_stress", self.user.email, "--dias", "30", "--limpar", verbosity=0
        )
        segundo = list(
            WeightEntry.objects.filter(user=self.user)
            .order_by("date")
            .values_list("weight_kg", flat=True)
        )

        self.assertEqual(primeiro, segundo)

    def test_it_refuses_an_account_that_does_not_exist(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_stress", "ninguem@exemplo.com", verbosity=0)

    def test_the_weight_curve_has_plateaus(self):
        """Reta descendente esconderia o caso que a tela precisa mostrar: a
        semana em que a média não se mexe."""
        call_command("seed_stress", self.user.email, "--dias", "365", verbosity=0)

        tendencia = weight_trend.analisar(self.user)
        deltas = [s.delta for s in tendencia.semanas if s.delta is not None]
        self.assertTrue(deltas, "nenhuma semana comparável")
