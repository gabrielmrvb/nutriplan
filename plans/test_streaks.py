"""Testes da ofensiva e do registro de água.

A ofensiva é a única parte do app que pode dizer à pessoa que ela falhou. Um
contador que zera por engano — porque era domingo de descanso, porque ainda são
sete da manhã, porque ela nem tem plano alimentar — é pior que não existir: ele
transforma o app numa fonte de culpa e a pessoa desinstala.

Quase todo teste aqui é sobre o que a ofensiva NÃO deve cobrar.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import TrainingDay
from workouts.models import Exercise, ExerciseLog
from workouts.services import create_routine

from . import services, streaks
from .models import HydrationLog, MealStatus
from .tests import CatalogFixture, create_complete_user


class StreakRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        create_routine(self.user)
        # Segunda-feira, para os dias de treino (0, 2, 4) caírem previsíveis.
        self.hoje = date(2026, 8, 24)
        self.meta_agua = 2900

    def _treinar(self, dia):
        ExerciseLog.objects.update_or_create(
            user=self.user,
            exercise=Exercise.objects.filter(is_active=True).first(),
            date=dia,
            set_number=1,
            defaults={"weight_kg": Decimal("40"), "reps": 10},
        )

    def _comer(self, dia, feitas=4, puladas=0):
        from .models import MealLog

        MealLog.objects.filter(user=self.user, date=dia).delete()
        slots = list(self.plan.slots.order_by("order"))
        for i in range(feitas + puladas):
            MealLog.objects.create(
                user=self.user,
                slot=slots[i % len(slots)],
                date=dia,
                status=MealStatus.DONE if i < feitas else MealStatus.SKIPPED,
            )

    def _beber(self, dia, ml=None):
        HydrationLog.objects.update_or_create(
            user=self.user, date=dia, defaults={"ml": ml or self.meta_agua}
        )

    def _dia_completo(self, dia):
        if dia.weekday() in (0, 2, 4):
            self._treinar(dia)
        self._comer(dia)
        self._beber(dia)

    def _calcular(self):
        return streaks.calcular(
            self.user, hoje=self.hoje, meta_agua_ml=self.meta_agua
        )

    # --------------------------------------------------------- o básico
    def test_a_fresh_account_starts_at_zero(self):
        self.assertEqual(self._calcular().dias, 0)

    def test_three_complete_days_in_a_row_count_three(self):
        for i in range(3):
            self._dia_completo(self.hoje - timedelta(days=i))

        self.assertEqual(self._calcular().dias, 3)

    def test_a_gap_stops_the_count(self):
        for i in (0, 1, 3, 4):
            self._dia_completo(self.hoje - timedelta(days=i))

        self.assertEqual(self._calcular().dias, 2)

    # ------------------------------------------- o que NÃO deve quebrar
    def test_a_rest_day_does_not_break_the_training_streak(self):
        """A rotina prevê três dias por semana. Se o contador exigisse treino
        todo dia, a sequência morreria toda terça e o número viraria ruído."""
        terca = date(2026, 8, 25)  # não está em (0, 2, 4)
        self.hoje = terca
        self._comer(terca)
        self._beber(terca)
        # Nenhum treino registrado, de propósito.

        ofensiva = self._calcular()

        self.assertEqual(ofensiva.dias, 1)
        self.assertNotIn("treino", ofensiva.falta_hoje)

    def test_today_is_never_counted_as_a_failure(self):
        """Às sete da manhã ninguém almoçou, treinou nem bebeu três litros. Um
        contador que zerasse ao amanhecer puniria por acordar cedo."""
        for i in range(1, 4):
            self._dia_completo(self.hoje - timedelta(days=i))
        # Hoje: nada feito.

        ofensiva = self._calcular()

        self.assertEqual(ofensiva.dias, 3)
        self.assertTrue(ofensiva.em_risco)
        self.assertFalse(ofensiva.hoje_completo)

    def test_finishing_today_adds_it_to_the_count(self):
        for i in range(1, 4):
            self._dia_completo(self.hoje - timedelta(days=i))
        self._dia_completo(self.hoje)

        ofensiva = self._calcular()

        self.assertEqual(ofensiva.dias, 4)
        self.assertFalse(ofensiva.em_risco)

    def test_without_a_water_goal_water_is_not_charged(self):
        """Metas que a pessoa não tem não podem quebrar a sequência dela."""
        for i in range(1, 3):
            dia = self.hoje - timedelta(days=i)
            if dia.weekday() in (0, 2, 4):
                self._treinar(dia)
            self._comer(dia)
            # Sem beber.

        ofensiva = streaks.calcular(self.user, hoje=self.hoje, meta_agua_ml=None)
        self.assertEqual(ofensiva.dias, 2)

    # -------------------------------------------------- os limiares
    def test_eighty_percent_of_the_meals_is_enough(self):
        """Exigir perfeição de um contador de constância é a forma mais rápida
        de a pessoa desistir dele."""
        ontem = self.hoje - timedelta(days=1)
        self._comer(ontem, feitas=4, puladas=1)  # 80%
        self._beber(ontem)
        self._treinar(ontem) if ontem.weekday() in (0, 2, 4) else None

        self.assertEqual(self._calcular().dias, 1)

    def test_below_eighty_percent_breaks_it(self):
        ontem = self.hoje - timedelta(days=1)
        self._comer(ontem, feitas=3, puladas=2)  # 60%
        self._beber(ontem)

        self.assertEqual(self._calcular().dias, 0)

    def test_a_single_marked_meal_does_not_pass_as_a_perfect_day(self):
        """Sem piso, uma refeição marcada daria 100% e passaria — premiando
        quem esqueceu de usar o app em vez de quem seguiu o plano."""
        ontem = self.hoje - timedelta(days=1)
        self._comer(ontem, feitas=1)
        self._beber(ontem)

        self.assertEqual(self._calcular().dias, 0)

    def test_ninety_percent_of_the_water_is_enough(self):
        """A meta já é estimativa (35 ml/kg). Cobrar o número cheio de uma
        estimativa é falsa precisão."""
        ontem = self.hoje - timedelta(days=1)
        self._comer(ontem)
        self._beber(ontem, ml=int(self.meta_agua * 0.92))
        self._treinar(ontem) if ontem.weekday() in (0, 2, 4) else None

        self.assertEqual(self._calcular().dias, 1)

    def test_half_the_water_breaks_it(self):
        ontem = self.hoje - timedelta(days=1)
        self._comer(ontem)
        self._beber(ontem, ml=int(self.meta_agua * 0.5))

        self.assertEqual(self._calcular().dias, 0)

    # ---------------------------------------------------- o que a tela diz
    def test_the_message_says_what_is_missing_today(self):
        for i in range(1, 3):
            self._dia_completo(self.hoje - timedelta(days=i))
        self._comer(self.hoje)  # falta água (e treino, que é segunda)

        ofensiva = self._calcular()

        self.assertIn("água", ofensiva.mensagem)
        self.assertIn("água", ofensiva.falta_hoje)

    def test_the_message_never_scolds(self):
        for texto in (
            self._calcular().mensagem,
            streaks.Ofensiva(dias=0, recorde=0, hoje_completo=False,
                             falta_hoje=[]).mensagem,
            streaks.Ofensiva(dias=45, recorde=45, hoje_completo=True,
                             falta_hoje=[]).mensagem,
        ):
            with self.subTest(texto=texto):
                for aspero in ("falhou", "perdeu", "você deveria", "errado"):
                    self.assertNotIn(aspero, texto.lower())

    def test_the_record_survives_a_broken_streak(self):
        """Sem o recorde, quebrar uma sequência de trinta dias apaga trinta
        dias de história e a pessoa recomeça do zero em todos os sentidos."""
        for i in range(6, 11):
            self._dia_completo(self.hoje - timedelta(days=i))
        self._dia_completo(self.hoje - timedelta(days=1))

        ofensiva = self._calcular()

        self.assertEqual(ofensiva.dias, 1)
        self.assertGreaterEqual(ofensiva.recorde, 5)


class HydrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user()
        services.create_plan(self.user)
        self.client.force_login(self.user)
        self.url = reverse("plans:log_hydration")

    def _hoje(self):
        return HydrationLog.objects.filter(
            user=self.user, date=timezone.localdate()
        ).first()

    def test_a_tap_adds_water(self):
        self.client.post(self.url, {"ml": 500})
        self.assertEqual(self._hoje().ml, 500)

    def test_taps_add_up(self):
        """Soma em vez de definir o total: a pessoa acabou de beber um copo,
        não sabe (nem quer calcular) quanto isso faz no acumulado."""
        for volume in (250, 500, 750):
            self.client.post(self.url, {"ml": volume})

        self.assertEqual(self._hoje().ml, 1500)

    def test_zero_resets_the_day(self):
        self.client.post(self.url, {"ml": 500})
        self.client.post(self.url, {"ml": 0})

        self.assertEqual(self._hoje().ml, 0)

    def test_an_unknown_volume_is_refused(self):
        """Só os três volumes que existem no mundo: copo, garrafinha, garrafa."""
        self.client.post(self.url, {"ml": 137})
        self.assertIsNone(self._hoje())

    def test_it_never_goes_past_ten_litres(self):
        """Acima disso é toque preso, não hidratação — e um número absurdo
        estragaria a barra e a ofensiva."""
        for _ in range(20):
            self.client.post(self.url, {"ml": 750})

        self.assertLessEqual(self._hoje().ml, 10000)

    def test_one_row_per_day_and_no_more(self):
        for _ in range(5):
            self.client.post(self.url, {"ml": 250})

        self.assertEqual(HydrationLog.objects.filter(user=self.user).count(), 1)

    def test_one_person_never_drinks_for_another(self):
        outro = create_complete_user(email="outro@exemplo.com")
        self.client.post(self.url, {"ml": 500})

        self.assertFalse(HydrationLog.objects.filter(user=outro).exists())

    def test_the_dashboard_shows_the_progress(self):
        self.client.post(self.url, {"ml": 500})

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("progress__fill--agua", html)
        self.assertIn("500", html)

    def test_the_goal_used_to_be_decorative(self):
        """A meta de água existia desde sempre e não tinha onde marcar. Sem
        registro ela não muda comportamento e a ofensiva não pode contá-la."""
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn(reverse("plans:log_hydration"), html)

    def test_it_asks_for_login(self):
        self.client.logout()
        resposta = self.client.post(self.url, {"ml": 500})

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])
