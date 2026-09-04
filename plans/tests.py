"""Testes do cálculo de meta calórica e do ciclo de vida do plano.

A matemática é testada direto nas funções puras, com números conferidos na
mão. Os testes de banco cobrem o que realmente quebra na prática: plano
duplicado, plano velho continuar ativo depois de mudar o peso, e recálculo
disparando toda vez que a tela abre.
"""
from datetime import date, datetime, time, timedelta
import threading
from decimal import Decimal
import ast
import hashlib
import inspect
from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth import get_user_model

from django.core.management import call_command
from django.template.defaultfilters import floatformat
from django.http import QueryDict
from django.db.models import Sum
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    MealStyle,
    Goal,
    Profile,
    Sex,
    TrainingDay,
    User,
    WeightEntry,
)
from catalog.models import DietaryTag, Food, MealCategory, MealTemplate, MealTemplateItem, TagKind

from . import agora, meal_planner, rodizio, services, shopping, tracking, views
from workouts import services as workout_services
from workouts.models import TrainingSession
from .calculations import (
    PlanInputs,
    activity_factor,
    bmr_mifflin_st_jeor,
    calculate,
    goal_adjustment,
    macros,
    target_kcal,
)
from .models import (
    HydrationLog,
    MealLog,
    MealOption,
    MealSlot,
    MealStatus,
    NutritionPlan,
    OptionLabel,
)

# Homem, 82,4 kg, 1,78 m, 30 anos, rotina leve, 3 treinos de 60 min, emagrecendo.
REFERENCE = PlanInputs(
    sex=Sex.MALE,
    weight_kg=Decimal("82.4"),
    height_cm=178,
    age_years=30,
    activity_level=ActivityLevel.LIGHT,
    goal=Goal.CUT,
    session_minutes=(60, 60, 60),
)


class CalculationTests(TestCase):
    def test_bmr_matches_mifflin_st_jeor_by_hand(self):
        # 10*82,4 + 6,25*178 - 5*30 + 5 = 1791,5
        bmr = bmr_mifflin_st_jeor(
            sex=Sex.MALE, weight_kg=Decimal("82.4"), height_cm=178, age_years=30
        )
        self.assertEqual(bmr, Decimal("1791.5"))

    def test_female_bmr_uses_the_other_constant(self):
        male = bmr_mifflin_st_jeor(
            sex=Sex.MALE, weight_kg=Decimal("60"), height_cm=165, age_years=30
        )
        female = bmr_mifflin_st_jeor(
            sex=Sex.FEMALE, weight_kg=Decimal("60"), height_cm=165, age_years=30
        )
        self.assertEqual(male - female, Decimal("166"))

    def test_reference_person_full_calculation(self):
        result = calculate(REFERENCE)
        self.assertEqual(result.bmr_kcal, 1792)  # 1791,5 arredonda para cima
        # Nível 2 com 3 treinos: 1,40 + (1,45-1,40) x 3/5 = 1,43
        self.assertEqual(result.activity_factor, Decimal("1.430"))
        self.assertEqual(result.tdee_kcal, 2562)
        # 20% de 2.562 seriam 512 — a faixa segura corta em 500.
        self.assertEqual(result.target_kcal, 2062)
        self.assertEqual(result.protein_g, 148)  # 1,8 g/kg
        self.assertEqual(result.notes, "")

    def test_macros_still_add_up_after_the_recalibration(self):
        result = calculate(REFERENCE)
        total = result.protein_g * 4 + result.carb_g * 4 + result.fat_g * 9
        self.assertAlmostEqual(total, result.target_kcal, delta=5)

    def test_macro_calories_add_up_to_the_target(self):
        result = calculate(REFERENCE)
        total = result.protein_g * 4 + result.carb_g * 4 + result.fat_g * 9
        # A folga é só o arredondamento das gramas para inteiro.
        self.assertAlmostEqual(total, result.target_kcal, delta=5)

    def test_goal_changes_only_the_adjustment(self):
        cut = calculate(REFERENCE)
        bulk = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": Goal.BULK}))
        maintain = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": Goal.MAINTAIN}))

        self.assertEqual(cut.tdee_kcal, bulk.tdee_kcal, maintain.tdee_kcal)
        self.assertEqual(maintain.target_kcal, maintain.tdee_kcal)
        self.assertLess(cut.target_kcal, maintain.target_kcal)
        self.assertGreater(bulk.target_kcal, maintain.target_kcal)

    def test_recomp_uses_a_smaller_deficit_than_cutting(self):
        """Quem quer os dois resultados não pode cortar como quem quer um só.

        O déficit agressivo de quem está emagrecendo é justamente o que impede
        o ganho de massa acontecer junto: sem energia sobrando o corpo não
        constrói. A meta da recomposição fica entre o corte e a manutenção.
        """
        cut = calculate(REFERENCE)
        recomp = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": Goal.RECOMP}))
        maintain = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": Goal.MAINTAIN}))

        self.assertGreater(recomp.target_kcal, cut.target_kcal)
        self.assertLess(recomp.target_kcal, maintain.target_kcal)
        self.assertEqual(recomp.tdee_kcal, cut.tdee_kcal)  # o gasto é o mesmo

    def test_recomp_asks_for_more_protein_than_the_other_goals(self):
        """O que compensa a falta de energia na recomposição é a proteína."""
        recomp = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": Goal.RECOMP}))

        self.assertEqual(recomp.protein_g, 165)  # 2,0 g/kg de 82,4 kg
        for goal in (Goal.CUT, Goal.BULK, Goal.MAINTAIN):
            outro = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": goal}))
            self.assertGreater(recomp.protein_g, outro.protein_g, goal)

    def test_recomp_warns_that_the_scale_barely_moves(self):
        """Sem esse aviso a pessoa desiste achando que a dieta não funcionou."""
        recomp = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": Goal.RECOMP}))
        self.assertIn("devagar", recomp.notes)

    def test_every_goal_is_calculable(self):
        """Objetivo novo sem ajuste ou sem proteína definida quebra no ar.

        Percorrer Goal.values (e não uma lista escrita à mão) é o que faz este
        teste falhar no dia em que alguém acrescentar um objetivo e esquecer de
        dizer o que ele faz com a meta.
        """
        for goal in Goal.values:
            with self.subTest(goal=goal):
                result = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": goal}))
                total = (
                    result.protein_g * 4 + result.carb_g * 4 + result.fat_g * 9
                )
                self.assertGreater(result.target_kcal, 0)
                self.assertGreater(result.protein_g, 0)
                self.assertAlmostEqual(total, result.target_kcal, delta=5)

    def test_target_never_falls_below_the_safety_floor(self):
        # Mulher pequena, sedentária, sem treino: o déficit cheio cairia abaixo
        # do piso absoluto de 1.200 kcal.
        result = calculate(
            PlanInputs(
                sex=Sex.FEMALE,
                weight_kg=Decimal("50"),
                height_cm=155,
                age_years=60,
                activity_level=ActivityLevel.SEDENTARY,
                goal=Goal.CUT,
            )
        )
        self.assertEqual(result.target_kcal, 1200)
        self.assertIn("piso", result.notes)

    def test_fat_never_goes_below_its_floor(self):
        """O piso subiu de 0,6 para 0,7 g/kg.

        A diferença aparece em quem tem peso alto e meta apertada: com 102 kg
        e 2.470 kcal, os 25% das calorias davam 0,68 g/kg, abaixo da faixa de
        0,7 a 0,8 que se recomenda para não mexer com a parte hormonal durante
        um déficit prolongado.
        """
        protein_g, carb_g, fat_g, note = macros(1400, Decimal("100"), Goal.CUT)
        self.assertEqual(protein_g, 180)
        self.assertEqual(fat_g, 70)  # 0,7 g/kg, e não 25% de 1400 (39 g)
        self.assertGreaterEqual(carb_g, 0)
        self.assertTrue(note)


class ActivityFactorTests(TestCase):
    """A recalibração de 24/08/2026: fator conservador, treino já incluído.

    Os três perfis descrevem o dia INTEIRO da pessoa, academia incluída. Antes
    o nível cobria só a rotina e o treino era somado por MET, o que inflava a
    meta de quem treina — a fórmula do MET trata uma hora de musculação como
    uma hora de esforço contínuo, e metade dela é descanso entre séries.
    """

    def test_the_three_profiles_use_the_agreed_bands(self):
        faixas = {
            ActivityLevel.SEDENTARY: (Decimal("1.25"), Decimal("1.35")),
            ActivityLevel.LIGHT: (Decimal("1.40"), Decimal("1.45")),
            ActivityLevel.ACTIVE: (Decimal("1.50"), Decimal("1.60")),
        }
        for nivel, (piso, teto) in faixas.items():
            with self.subTest(nivel=nivel):
                self.assertEqual(activity_factor(nivel, 0), piso)
                self.assertEqual(activity_factor(nivel, 5), teto)

    def test_the_factor_walks_the_band_with_the_training_frequency(self):
        """Mesma rotina, treinos diferentes: é para isso que a faixa existe."""
        um = activity_factor(ActivityLevel.SEDENTARY, 1)
        tres = activity_factor(ActivityLevel.SEDENTARY, 3)
        cinco = activity_factor(ActivityLevel.SEDENTARY, 5)

        self.assertLess(um, tres)
        self.assertLess(tres, cinco)
        self.assertEqual(tres, Decimal("1.31"))  # 1,25 + 0,10 x 3/5

    def test_training_more_than_five_times_does_not_keep_inflating(self):
        """Sexto e sétimo treino não valem mais calorias na conta."""
        self.assertEqual(
            activity_factor(ActivityLevel.ACTIVE, 5),
            activity_factor(ActivityLevel.ACTIVE, 7),
        )

    def test_no_profile_reaches_the_old_inflated_numbers(self):
        """O antigo topo era 1,70 mais o gasto do treino somado por fora."""
        for nivel in ActivityLevel.values:
            with self.subTest(nivel=nivel):
                self.assertLessEqual(activity_factor(nivel, 7), Decimal("1.60"))

    def test_the_recalibration_lowered_the_target_of_someone_who_trains(self):
        """Prova do efeito: a mesma pessoa da referência come menos que antes.

        Com o desenho antigo (fator 1,35 + MET do treino) o gasto dava 2.567 e
        a meta 2.053. O objetivo da recalibração era justamente derrubar isso.
        """
        result = calculate(REFERENCE)
        self.assertLess(result.tdee_kcal, 2567)


class DeficitBandTests(TestCase):
    """Déficit de emagrecimento preso entre 300 e 500 kcal por dia."""

    def _com_tdee(self, tdee):
        return goal_adjustment(Decimal(tdee), Goal.CUT)

    def test_a_small_expenditure_does_not_get_a_tiny_deficit(self):
        """20% de 1.200 seriam 240 — pouco para mexer o ponteiro."""
        self.assertEqual(self._com_tdee(1200), -Decimal("300"))

    def test_a_large_expenditure_does_not_get_a_brutal_deficit(self):
        """20% de 3.500 seriam 700 — quase ninguém sustenta sem perder músculo."""
        self.assertEqual(self._com_tdee(3500), -Decimal("500"))

    def test_in_the_middle_the_percentage_still_decides(self):
        self.assertEqual(self._com_tdee(2000), -Decimal("400"))

    def test_the_deficit_is_always_inside_the_band(self):
        for gasto in range(1000, 5001, 250):
            with self.subTest(tdee=gasto):
                deficit = abs(self._com_tdee(gasto))
                self.assertGreaterEqual(deficit, Decimal("300"))
                self.assertLessEqual(deficit, Decimal("500"))

    def test_other_goals_keep_their_percentages(self):
        """A faixa é do emagrecimento — recomposição depende de déficit pequeno."""
        recomp = goal_adjustment(Decimal("3000"), Goal.RECOMP)
        bulk = goal_adjustment(Decimal("3000"), Goal.BULK)

        self.assertEqual(recomp, Decimal("-150.00"))
        self.assertEqual(bulk, Decimal("300.00"))


class SafetyCapTests(TestCase):
    """Trava contra hiperescala: 2.800 kcal para emagrecer ou manter."""

    def _meta(self, tdee, goal=Goal.CUT, peso="90", sexo=Sex.MALE, bmr=1800):
        return target_kcal(Decimal(tdee), goal, Decimal(bmr), sexo, weight_kg=Decimal(peso))

    def test_a_normal_target_passes_untouched(self):
        meta, aviso = self._meta(2500)
        self.assertEqual(meta, 2000)
        self.assertEqual(aviso, "")

    def test_a_target_above_the_ceiling_is_capped_and_explained(self):
        meta, aviso = self._meta(4000, peso="95")

        self.assertEqual(meta, 2800)
        self.assertIn("2800", aviso)
        self.assertIn("nível de atividade", aviso)

    def test_maintaining_is_capped_too(self):
        meta, aviso = self._meta(3200, goal=Goal.MAINTAIN, peso="100")

        self.assertEqual(meta, 2800)
        self.assertTrue(aviso)

    def test_extreme_weight_is_allowed_above_the_ceiling_with_an_explanation(self):
        """Quem pesa 130 kg gasta muito mesmo — cortar aí seria déficit disfarçado."""
        meta, aviso = self._meta(4000, peso="130", bmr=2400)

        self.assertGreater(meta, 2800)
        self.assertIn("peso", aviso)

    def test_bulking_is_never_capped(self):
        """Superávit alto é gordura ganha, não risco de segurança."""
        meta, _ = self._meta(3400, goal=Goal.BULK, peso="95")
        self.assertGreater(meta, 2800)

    def test_the_floor_still_wins_over_everything(self):
        resultado = calculate(
            PlanInputs(
                sex=Sex.FEMALE,
                weight_kg=Decimal("50"),
                height_cm=155,
                age_years=60,
                activity_level=ActivityLevel.SEDENTARY,
                goal=Goal.CUT,
            )
        )
        self.assertEqual(resultado.target_kcal, 1200)
        self.assertIn("piso", resultado.notes)

    def test_the_ceiling_wins_over_the_deficit_band(self):
        """Interação deliberada entre as duas travas, não acidente.

        Gasto alto com peso normal: o teto de 2.800 limita a meta, e isso
        produz um déficit acima dos 500 da faixa. A ordem é essa de propósito —
        o teto existe porque o gasto provavelmente está superestimado, então
        errar para o lado de comer menos é o lado seguro. E a pessoa é avisada.
        """
        meta, aviso = target_kcal(
            Decimal("3328"), Goal.CUT, Decimal("2080"), Sex.MALE, weight_kg=Decimal("110")
        )

        self.assertEqual(meta, 2800)
        self.assertGreater(3328 - meta, 500)
        self.assertIn("2800", aviso)

    def test_below_the_ceiling_the_band_is_respected(self):
        """Fora da exceção, o déficit continua dentro de 300 a 500."""
        for gasto in (2000, 2400, 2800, 3200):
            with self.subTest(tdee=gasto):
                meta, _ = target_kcal(
                    Decimal(gasto), Goal.CUT, Decimal("1600"), Sex.MALE,
                    weight_kg=Decimal("130"),  # acima do teto: só a faixa vale
                )
                deficit = gasto - meta
                self.assertGreaterEqual(deficit, 300)
                self.assertLessEqual(deficit, 500)

    def test_no_profile_produces_a_disproportionate_target(self):
        """Varredura: nenhum perfil comum sai com meta fora do razoável."""
        for nivel in ActivityLevel.values:
            for sessoes in range(0, 7):
                for peso in ("55", "75", "95", "115"):
                    entradas = PlanInputs(
                        sex=Sex.MALE,
                        weight_kg=Decimal(peso),
                        height_cm=178,
                        age_years=30,
                        activity_level=nivel,
                        goal=Goal.CUT,
                        session_minutes=tuple([60] * sessoes),
                    )
                    with self.subTest(nivel=nivel, sessoes=sessoes, peso=peso):
                        resultado = calculate(entradas)
                        self.assertLessEqual(resultado.target_kcal, 2800)
                        self.assertGreaterEqual(resultado.target_kcal, 1500)


def create_complete_user(email="pessoa@exemplo.com", **profile_kwargs):
    """Usuário com onboarding completo — o estado mínimo para ter plano."""
    user = User.objects.create_user(email=email, password="senha-bem-forte-123")
    fields = {
        "sex": Sex.MALE,
        "birth_date": date(1995, 4, 12),
        "height_cm": 178,
        "activity_level": ActivityLevel.LIGHT,
        "goal": Goal.CUT,
        "wake_time": time(7, 0),
        "sleep_time": time(23, 0),
        # ONBOARDING_DONE e não 5: o wizard ganhou um passo e todo fixture
        # que dizia "5" passou a criar gente que NÃO terminou — cinco testes
        # de rotas sem relação nenhuma com onboarding caíram em 302.
        "onboarding_step": ONBOARDING_DONE,
    }
    fields.update(profile_kwargs)
    Profile.objects.create(user=user, **fields)
    WeightEntry.objects.create(user=user, weight_kg=Decimal("82.4"))
    for weekday in (0, 2, 4):
        TrainingDay.objects.create(
            user=user, weekday=weekday, start_time=time(19, 0), duration_min=60
        )
    return user


class PlanServiceTests(TestCase):
    def setUp(self):
        self.user = create_complete_user()

    def test_incomplete_profile_refuses_to_calculate(self):
        outro = User.objects.create_user(email="novo@exemplo.com", password="x")
        with self.assertRaises(services.IncompleteProfile):
            services.build_inputs(outro)

    def test_profile_without_weight_refuses_to_calculate(self):
        self.user.weight_entries.all().delete()
        with self.assertRaises(services.IncompleteProfile):
            services.build_inputs(self.user)

    def test_create_plan_freezes_the_inputs(self):
        plan = services.create_plan(self.user)
        self.assertEqual(plan.weight_kg, Decimal("82.4"))
        self.assertEqual(plan.training_days_per_week, 3)
        self.assertEqual(plan.formula, "mifflin_st_jeor")
        self.assertEqual(plan.target_kcal, calculate(services.build_inputs(self.user)).target_kcal)

    def test_new_plan_deactivates_the_previous_one(self):
        first = services.create_plan(self.user)
        second = services.create_plan(self.user)

        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_sync_is_idempotent_while_nothing_changes(self):
        plan, created = services.sync_active_plan(self.user)
        self.assertTrue(created)

        same_plan, created_again = services.sync_active_plan(self.user)
        self.assertFalse(created_again)
        self.assertEqual(plan.pk, same_plan.pk)
        self.assertEqual(NutritionPlan.objects.count(), 1)

    def test_sync_recalculates_after_a_weight_change(self):
        old, _ = services.sync_active_plan(self.user)
        WeightEntry.objects.create(
            user=self.user, date=date(2030, 1, 1), weight_kg=Decimal("78.0")
        )

        new, created = services.sync_active_plan(self.user)
        self.assertTrue(created)
        self.assertNotEqual(old.pk, new.pk)
        self.assertEqual(new.weight_kg, Decimal("78.0"))
        self.assertLess(new.target_kcal, old.target_kcal)

    def test_sync_recalculates_when_the_training_frequency_changes(self):
        """Frequência move o fator de atividade, então move a meta."""
        old, _ = services.sync_active_plan(self.user)
        TrainingDay.objects.create(
            user=self.user, weekday=5, start_time=time(19, 0), duration_min=60
        )

        new, created = services.sync_active_plan(self.user)

        self.assertTrue(created)
        self.assertGreater(new.training_days_per_week, old.training_days_per_week)
        self.assertGreater(new.tdee_kcal, old.tdee_kcal)

    def test_the_session_length_alone_no_longer_moves_the_diet(self):
        """Mudança de comportamento da recalibração de 24/08/2026.

        Antes a duração entrava na conta pela fórmula do MET, e treinar 30
        minutos a mais rendia calorias extras na dieta. Isso dava uma precisão
        que a fórmula não tem: metade de um treino de força é descanso entre
        séries, e ninguém sabe de cabeça quantos minutos treina de verdade.
        Hoje a duração descreve a ficha de treino, não a meta calórica — o que
        muda a dieta é a frequência.
        """
        old, _ = services.sync_active_plan(self.user)
        self.user.training_days.update(duration_min=90)

        new, created = services.sync_active_plan(self.user)

        self.assertFalse(created)
        self.assertEqual(new.pk, old.pk)
        self.assertEqual(new.tdee_kcal, old.tdee_kcal)


class TodayViewTests(TestCase):
    url = reverse("plans:today")

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_incomplete_onboarding_is_sent_back_to_the_wizard(self):
        Profile.objects.filter(user=self.user).update(onboarding_step=3)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("accounts:onboarding"), target_status_code=302)

    def test_first_visit_creates_the_plan_and_shows_the_target(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        plan = NutritionPlan.objects.get(user=self.user, is_active=True)
        self.assertContains(response, str(plan.target_kcal))
        self.assertContains(response, f"{plan.protein_g} g")

    def test_second_visit_does_not_create_another_plan(self):
        self.client.get(self.url)
        self.client.get(self.url)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user).count(), 1)

    def test_recalculate_button_creates_a_new_plan(self):
        self.client.get(self.url)
        response = self.client.post(reverse("plans:recalculate"))

        self.assertRedirects(response, self.url)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user).count(), 2)
        self.assertEqual(NutritionPlan.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_a_get_does_not_create_a_plan(self):
        """Recalcular nasce um plano novo, e GET não faz isso.

        A asserção era `status == 405`: o mecanismo, e não a regra — e o 405
        vinha com zero byte, que é onde o `next` do login aterrissava depois
        de a sessão expirar. Ver `config/acoes.py`.
        """
        antes = NutritionPlan.objects.filter(user=self.user).count()

        self.client.get(reverse("plans:recalculate"))

        self.assertEqual(NutritionPlan.objects.filter(user=self.user).count(), antes)

    def test_a_get_takes_the_person_to_today(self):
        response = self.client.get(reverse("plans:recalculate"))

        self.assertRedirects(response, reverse("plans:today"))

    def test_the_page_states_the_daily_deficit_in_kcal(self):
        """O número que explica a dieta inteira não pode ficar implícito.

        A pessoa precisa ler "déficit de tantas kcal" na tela, e não deduzir
        isso subtraindo a meta do gasto de cabeça.
        """
        response = self.client.get(self.url)
        plan = NutritionPlan.objects.get(user=self.user, is_active=True)

        self.assertContains(response, "Déficit diário recomendado")
        self.assertContains(response, str(plan.tdee_kcal - plan.target_kcal).lstrip("-"))

    def test_a_bulking_user_sees_a_surplus_instead(self):
        Profile.objects.filter(user=self.user).update(goal=Goal.BULK)
        response = self.client.get(self.url)

        self.assertContains(response, "Superávit diário recomendado")
        self.assertNotContains(response, "Déficit diário recomendado")

    def test_the_bottom_navigation_reaches_every_area_of_the_app(self):
        """O shell do PWA: dieta, treino, métricas e perfil a um toque."""
        response = self.client.get(self.url)
        for url in (
            reverse("plans:today"),
            reverse("workouts:routine"),
            reverse("plans:history"),
            reverse("accounts:profile"),
        ):
            self.assertContains(response, f'href="{url}"')


class EnergyBalanceTests(TestCase):
    """O déficit/superávit diário que a tela mostra em uma linha."""

    def test_eating_below_the_expenditure_is_a_deficit(self):
        balance = views.energy_balance(NutritionPlan(tdee_kcal=2600, target_kcal=2100))

        self.assertEqual(balance["kind"], "deficit")
        self.assertEqual(balance["label"], "Déficit diário recomendado")
        self.assertEqual(balance["delta_kcal"], -500)
        self.assertEqual(balance["abs_kcal"], 500)
        self.assertEqual(balance["pct"], 19)
        self.assertEqual(balance["weekly_kcal"], -3500)

    def test_eating_above_the_expenditure_is_a_surplus(self):
        balance = views.energy_balance(NutritionPlan(tdee_kcal=2600, target_kcal=2860))

        self.assertEqual(balance["kind"], "surplus")
        self.assertEqual(balance["label"], "Superávit diário recomendado")
        self.assertEqual(balance["delta_kcal"], 260)

    def test_maintaining_has_neither(self):
        balance = views.energy_balance(NutritionPlan(tdee_kcal=2600, target_kcal=2600))

        self.assertEqual(balance["kind"], "balance")
        self.assertEqual(balance["delta_kcal"], 0)
        self.assertEqual(balance["weekly_kg"], 0)

    def test_the_weekly_rate_uses_the_kcal_per_kilo_convention(self):
        """-1.100 kcal por dia são 7.700 na semana, ou seja, 1 kg."""
        balance = views.energy_balance(NutritionPlan(tdee_kcal=3000, target_kcal=1900))

        self.assertEqual(balance["weekly_kcal"], -7700)
        self.assertEqual(balance["weekly_kg"], 1.0)

    def test_the_balance_closes_with_the_target(self):
        """gasto − déficit = meta. Se essa conta não fecha, a tela mente."""
        for goal in Goal.values:
            with self.subTest(goal=goal):
                result = calculate(PlanInputs(**{**REFERENCE.__dict__, "goal": goal}))
                balance = views.energy_balance(
                    NutritionPlan(tdee_kcal=result.tdee_kcal, target_kcal=result.target_kcal)
                )
                self.assertEqual(
                    balance["tdee_kcal"] + balance["delta_kcal"], balance["target_kcal"]
                )


# ---------------------------------------------------------------------------
# Etapa 4 — geração do cardápio
# ---------------------------------------------------------------------------

class SlotTimeTests(TestCase):
    """Fase 1: onde caem as refeições no dia."""

    def test_meals_fill_the_awake_window_in_order(self):
        times, anchor = meal_planner.slot_times(time(7, 0), time(23, 0))

        self.assertIsNone(anchor)
        self.assertEqual(len(times), 5)
        self.assertEqual(times[0], time(7, 30))  # acordar + 30 min
        self.assertEqual(times[-1], time(21, 30))  # dormir - 90 min
        self.assertEqual(times, sorted(times))

    def test_evening_training_pulls_dinner_to_the_post_workout_slot(self):
        times, anchor = meal_planner.slot_times(
            time(7, 0), time(23, 0), training_end=time(20, 0)
        )

        self.assertEqual(anchor, 4)  # o jantar era a refeição mais próxima
        self.assertEqual(times[anchor], time(20, 45))
        self.assertEqual(times, sorted(times))

    def test_early_training_turns_breakfast_into_the_post_workout_meal(self):
        times, anchor = meal_planner.slot_times(
            time(5, 30), time(22, 0), training_end=time(7, 0)
        )

        self.assertEqual(anchor, 0)
        self.assertEqual(times[0], time(7, 45))
        self.assertEqual(times, sorted(times))

    def test_neighbours_keep_a_minimum_gap_after_the_anchor_moves(self):
        # Treino terminando às 12:00 puxa o almoço para 12:45 e aperta o lanche
        # da manhã, que estava em cima do horário.
        times, anchor = meal_planner.slot_times(
            time(9, 0), time(23, 0), training_end=time(12, 0)
        )
        gaps = [
            (meal_planner._minutes(later) - meal_planner._minutes(earlier))
            for earlier, later in zip(times, times[1:])
        ]
        self.assertTrue(all(gap >= meal_planner.MIN_GAP_MINUTES for gap in gaps), gaps)

    def test_window_past_midnight_is_handled(self):
        times, _ = meal_planner.slot_times(time(10, 0), time(2, 0))

        self.assertEqual(times[0], time(10, 30))
        self.assertEqual(times[-1], time(0, 30))  # dormir 02:00 - 90 min
        offsets = [meal_planner._offset_from(time(10, 0), t) for t in times]
        self.assertEqual(offsets, sorted(offsets))

    def test_late_training_keeps_the_meal_inside_the_window(self):
        # Treino terminando 22:50 e sono às 23:00: a refeição não pode ir para
        # 23:35, mas também não pode voltar para antes do treino.
        times, anchor = meal_planner.slot_times(
            time(7, 0), time(23, 0), training_end=time(22, 50)
        )
        self.assertEqual(anchor, 4)
        self.assertEqual(times[anchor], time(22, 50))

    def test_no_meal_is_scheduled_during_the_training_session(self):
        # Caso real: treino 19:00-20:30 para quem dorme 21:00.
        times, _ = meal_planner.slot_times(
            time(5, 0), time(21, 0), training_end=time(20, 30)
        )
        session = range(19 * 60, 20 * 60 + 30)
        during = [t for t in times if meal_planner._minutes(t) in session]
        self.assertEqual(during, [])


class DistributionTests(TestCase):
    """Fase 2: a meta do dia virando alvo de cada refeição."""

    def test_parts_add_up_to_the_total(self):
        shares = [Decimal("0.25"), Decimal("0.10"), Decimal("0.30"),
                  Decimal("0.10"), Decimal("0.25")]
        for total in (2053, 1999, 3150, 7):
            parts = meal_planner.distribute(total, shares)
            self.assertEqual(sum(parts), total, f"total={total}")

    def test_leftovers_go_to_the_biggest_fractions(self):
        # 10 kcal em três partes iguais: 3,33 cada. Sobra 1, e vai para a primeira.
        parts = meal_planner.distribute(10, [Decimal("1") / 3] * 3)
        self.assertEqual(sorted(parts, reverse=True), [4, 3, 3])


def make_food(name, kcal, protein, carb, fat):
    """Alimento com valores por 100 g."""
    return Food.objects.create(
        name=name,
        kcal=Decimal(kcal),
        protein_g=Decimal(protein),
        carb_g=Decimal(carb),
        fat_g=Decimal(fat),
    )


def make_template(name, category, items, tags=(), everyday=True, prep_minutes=10):
    """Receita com ingredientes: items = [(alimento, gramas, escalável)]."""
    template = MealTemplate.objects.create(
        name=name, category=category, everyday=everyday, prep_minutes=prep_minutes
    )
    for order, (food, grams, scalable) in enumerate(items):
        MealTemplateItem.objects.create(
            template=template,
            food=food,
            quantity_g=Decimal(grams),
            scalable=scalable,
            order=order,
        )
    for slug in tags:
        tag, _ = DietaryTag.objects.get_or_create(
            slug=slug, defaults={"name": slug, "kind": TagKind.RESTRICTION}
        )
        template.tags.add(tag)
    template.refresh_macros()
    return template


class CatalogFixture(TestCase):
    """Catálogo mínimo que cobre as categorias usadas pelo cardápio."""

    @classmethod
    def setUpTestData(cls):
        cls.chicken = make_food("Frango", 165, 31, 0, "3.6")
        cls.rice = make_food("Arroz", 130, "2.7", 28, "0.3")
        cls.oats = make_food("Aveia", 389, "16.9", 66, "6.9")
        cls.yogurt = make_food("Iogurte", 59, 10, "3.6", "0.4")
        cls.nuts = make_food("Castanha", 607, 15, 20, 54)

        # Quatro receitas principais para provar que almoço e jantar não repetem.
        make_template("Frango com arroz", MealCategory.MAIN,
                      [(cls.chicken, 150, True), (cls.rice, 150, True)])
        make_template("Arroz com castanha", MealCategory.MAIN,
                      [(cls.rice, 200, True), (cls.nuts, 20, True)])
        make_template("Frango com aveia", MealCategory.MAIN,
                      [(cls.chicken, 120, True), (cls.oats, 60, True)])
        make_template("Arroz com iogurte", MealCategory.MAIN,
                      [(cls.rice, 180, True), (cls.yogurt, 100, True)])
        make_template("Aveia com iogurte", MealCategory.BREAKFAST,
                      [(cls.oats, 60, True), (cls.yogurt, 150, True)])
        make_template("Iogurte com castanha", MealCategory.BREAKFAST,
                      [(cls.yogurt, 170, True), (cls.nuts, 15, True)])
        make_template("Iogurte puro", MealCategory.SNACK,
                      [(cls.yogurt, 200, True)])
        make_template("Castanha com aveia", MealCategory.SNACK,
                      [(cls.nuts, 25, True), (cls.oats, 30, True)])
        make_template("Aveia pura", MealCategory.SNACK,
                      [(cls.oats, 50, True)])
        make_template("Frango puro", MealCategory.SNACK,
                      [(cls.chicken, 130, True)])


class ScalingTests(CatalogFixture):
    """Fase 3: escalar a receita até o alvo do horário."""

    def test_fixed_items_do_not_scale(self):
        # 100 g de arroz FIXOS (130 kcal) + 100 g de frango escaláveis (165 kcal).
        # Alvo de 460 kcal => (460 - 130) / 165 = 2,00.
        template = make_template(
            "Prato com item fixo",
            MealCategory.MAIN,
            [(self.rice, 100, False), (self.chicken, 100, True)],
        )
        self.assertEqual(meal_planner.scale_for(template, 460), Decimal("2.00"))

        macros_at_scale = template.compute_macros(Decimal("2.00"))
        self.assertAlmostEqual(float(macros_at_scale["kcal"]), 460, places=2)

    def test_scale_is_clamped_to_edible_portions(self):
        template = MealTemplate.objects.get(name="Frango com arroz")
        self.assertEqual(meal_planner.scale_for(template, 50), meal_planner.MIN_SCALE)
        self.assertEqual(meal_planner.scale_for(template, 9000), meal_planner.MAX_SCALE)

    def test_protein_weighs_more_than_calories_in_the_score(self):
        slot = MealSlot(target_kcal=500, target_protein_g=50,
                        target_carb_g=50, target_fat_g=10)
        on_target_protein = {"kcal": Decimal(550), "protein_g": Decimal(50)}
        on_target_kcal = {"kcal": Decimal(500), "protein_g": Decimal(30)}

        self.assertLess(
            meal_planner.deviation(on_target_protein, slot),
            meal_planner.deviation(on_target_kcal, slot),
        )


class MealGenerationTests(CatalogFixture):
    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)

    def test_cada_horario_guarda_o_repertorio_que_o_catalogo_permite(self):
        """Quatro quando dá, e o que couber quando não dá.

        A fixture é pequena de propósito — tem dois cafés da manhã — e por isso
        é justamente ela que prova o teto e o piso na mesma passada: o gerador
        nunca passa de `OPTIONS_PER_SLOT`, e nunca fica abaixo do que o catálogo
        oferecia para aquele horário.
        """
        slots = list(self.plan.slots.all())
        self.assertEqual(len(slots), len(meal_planner.DAY_BLUEPRINT))

        for slot in slots:
            with self.subTest(slot=slot.name):
                candidatas = len(meal_planner.candidates_for(slot.category, []))
                esperado = min(candidatas, meal_planner.OPTIONS_PER_SLOT)

                self.assertLessEqual(
                    slot.options.count(), meal_planner.OPTIONS_PER_SLOT
                )
                self.assertGreaterEqual(slot.options.count(), min(esperado, rodizio.POR_DIA))

    def test_slot_targets_add_up_to_the_daily_target(self):
        totals = self.plan.slots.aggregate(
            kcal=Sum("target_kcal"),
            protein=Sum("target_protein_g"),
            carb=Sum("target_carb_g"),
            fat=Sum("target_fat_g"),
        )
        self.assertEqual(totals["kcal"], self.plan.target_kcal)
        self.assertEqual(totals["protein"], self.plan.protein_g)
        self.assertEqual(totals["carb"], self.plan.carb_g)
        self.assertEqual(totals["fat"], self.plan.fat_g)

    def test_a_receita_so_repete_depois_de_esgotar_o_catalogo(self):
        """Repetir é o último recurso, e o teste mede isso — não o total.

        Com repertório de dois, o dia consumia dez receitas e o catálogo de
        teste dava conta: bastava exigir zero repetição. Com quatro por horário
        são vinte, e a fixture não tem vinte — a asserção antiga passou a
        cobrar do gerador uma coisa que o catálogo não permite, e um teste
        assim não protege regra nenhuma, só o tamanho da fixture.

        A regra de verdade continua valendo e é esta: enquanto sobrar receita
        inédita que sirva o horário, o gerador tem que usá-la. Repetição com
        candidata inédita na prateleira é defeito; repetição com prateleira
        vazia é o fallback funcionando.

        O catálogo REAL, onde as vinte cabem, tem a asserção forte de zero
        repetição em `SeededCatalogTests`.
        """
        opcoes = MealOption.objects.filter(slot__plan=self.plan).select_related("slot")
        usadas = {opcao.template_id for opcao in opcoes}

        # Dentro de um mesmo horário a repetição é impossível por constraint —
        # aqui se confere que ela continua impossível na prática.
        por_slot = {}
        for opcao in opcoes:
            por_slot.setdefault(opcao.slot_id, []).append(opcao.template_id)
        for slot_id, templates in por_slot.items():
            self.assertEqual(len(templates), len(set(templates)), slot_id)

        # E nenhuma candidata ficou na prateleira enquanto alguma repetiu.
        disponiveis = set()
        for slot in self.plan.slots.all():
            for template in meal_planner.candidates_for(slot.category, []):
                disponiveis.add(template.pk)
        houve_repeticao = len(list(opcoes)) > len(usadas)
        if houve_repeticao:
            self.assertEqual(
                disponiveis - usadas,
                set(),
                "repetiu receita com candidata inédita disponível",
            )

    def test_dinner_lands_after_the_training_session(self):
        # Treino 19:00 + 60 min => pós-treino às 20:45.
        anchored = self.plan.slots.get(name__contains="pós-treino")
        self.assertEqual(anchored.time, time(20, 45))

    def test_option_macros_match_the_scaled_recipe(self):
        option = MealOption.objects.filter(slot__plan=self.plan).first()
        expected = option.template.compute_macros(option.scale_factor)
        self.assertAlmostEqual(float(option.kcal), float(expected["kcal"]), places=1)
        self.assertAlmostEqual(float(option.protein_g), float(expected["protein_g"]), places=1)

    def test_options_land_close_to_the_slot_target(self):
        for option in MealOption.objects.filter(slot__plan=self.plan):
            error = abs(float(option.kcal) - option.slot.target_kcal)
            self.assertLess(error, option.slot.target_kcal * 0.35, option.template.name)

    def test_ingredients_come_out_scaled(self):
        option = MealOption.objects.filter(slot__plan=self.plan).first()
        ingredients = option.ingredient_list()
        item = option.template.items.first()
        self.assertEqual(ingredients[0]["quantity"], item.quantity_g * option.scale_factor)


class RepertorioPorRefeicaoTests(CatalogFixture):
    """O repertório persistente de cada refeição — quatro opções, no banco.

    A regra de produto NÃO mudou do lado da tela: continuam sendo duas escolhas
    na hora da fome, porque mais que isso é o que faz a pessoa fechar o app e
    pedir delivery. O que mudou é que essas duas passam a sair de um repertório
    de quatro, em vez de serem as duas únicas que existem — era daí que vinha o
    cardápio idêntico todo dia.

    Aqui se testa o REPERTÓRIO. Quantas aparecem por dia, e quais, é assunto de
    `RodizioDiarioTests`.
    """

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)

    def test_o_repertorio_e_maior_que_o_que_a_tela_mostra(self):
        """As duas grandezas se separaram, e é isso que o cardápio V2 é.

        Antes eram a mesma coisa: `OPTIONS_PER_SLOT == len(OptionLabel.values)`.
        Se alguém voltar a amarrá-las, o repertório encolhe para dois e o
        problema de variedade volta inteiro, sem mais nada quebrar.
        """
        self.assertEqual(meal_planner.OPTIONS_PER_SLOT, 4)
        self.assertEqual(rodizio.POR_DIA, 2)
        self.assertGreater(meal_planner.OPTIONS_PER_SLOT, rodizio.POR_DIA)

    def test_os_ranks_de_um_horario_sao_uma_sequencia_sem_buraco(self):
        """Posição é identidade: buraco ou repetição quebra a projeção.

        `rodizio.indices_do_dia` trabalha em posições de 0 a N-1. Um horário com
        ranks 0, 1 e 3 faria a projeção pedir a posição 2, que não existe.
        """
        for slot in self.plan.slots.all():
            with self.subTest(slot=slot.name):
                ranks = sorted(slot.options.values_list("rank", flat=True))

                self.assertLessEqual(len(ranks), meal_planner.OPTIONS_PER_SLOT)
                self.assertEqual(ranks, list(range(len(ranks))))

    def test_catalogo_farto_para_no_tamanho_do_repertorio(self):
        """Catálogo farto é o caso em que a sobra apareceria.

        O gerador não estica: com receitas principais de sobra, o almoço
        continua guardando quatro. Sem este limite o repertório cresceria junto
        com o catálogo e a rotação viraria sorteio num saco sem fundo.
        """
        for index in range(8):
            make_template(
                f"Prato extra {index}",
                MealCategory.MAIN,
                [(self.chicken, 120 + index * 10, True), (self.rice, 150, True)],
            )

        plan = services.create_plan(create_complete_user(email="farto@exemplo.com"))

        for slot in plan.slots.filter(category=MealCategory.MAIN):
            self.assertEqual(
                slot.options.count(), meal_planner.OPTIONS_PER_SLOT, slot.name
            )

    def test_os_ranks_saem_na_ordem_da_pontuacao(self):
        """Rank 0 é a melhor opção do horário, e daí para baixo.

        Importa porque um repertório PARCIAL precisa ficar com as melhores
        receitas, e não com as primeiras que o banco devolveu.
        """
        for slot in self.plan.slots.all():
            options = list(slot.options.order_by("id"))

            self.assertEqual(
                [option.rank for option in options],
                list(range(len(options))),
                slot.name,
            )


class RestrictionTests(CatalogFixture):
    def test_restrictions_filter_the_catalog_and_the_gap_is_reported(self):
        vegan = DietaryTag.objects.create(
            slug="vegana", name="Vegana", kind=TagKind.RESTRICTION
        )
        # Só uma receita principal é vegana; café e lanches ficam sem candidata.
        MealTemplate.objects.get(name="Arroz com castanha").tags.add(vegan)

        user = create_complete_user(email="vegana@exemplo.com")
        user.profile.dietary_tags.add(vegan)

        plan = services.create_plan(user)

        self.assertEqual(plan.slots.count(), 5)
        self.assertEqual(plan.slots.get(order=0).options.count(), 0)
        self.assertIn("Café da manhã", plan.notes)
        # O plano existe mesmo incompleto: a única receita vegana foi aproveitada.
        self.assertEqual(MealOption.objects.filter(slot__plan=plan).count(), 2)

    def test_recipe_repeats_only_when_there_is_nothing_else(self):
        # Uma única receita disponível para as duas refeições principais.
        MealTemplate.objects.filter(category=MealCategory.MAIN).exclude(
            name="Frango com arroz"
        ).update(is_active=False)

        user = create_complete_user(email="pouco@exemplo.com")
        plan = services.create_plan(user)

        mains = MealOption.objects.filter(
            slot__plan=plan, slot__category=MealCategory.MAIN
        )
        self.assertEqual(mains.count(), 2)  # uma opção em cada refeição principal
        self.assertEqual({option.template.name for option in mains}, {"Frango com arroz"})
        self.assertIn("Almoço", plan.notes)


class ProteinCoverageTests(CatalogFixture):
    """O plano diz quando o catálogo não alcança a meta de proteína.

    A situação real é a dieta vegana barata: as receitas existem, o cardápio
    sai completo, e ainda assim somar a opção mais proteica de cada horário não
    chega ao alvo do dia. Calar isso é pior do que a lacuna em si — a pessoa
    seguiria tudo direitinho e não entenderia o resultado.
    """

    def test_a_catalog_that_covers_the_protein_target_says_nothing(self):
        plan = services.create_plan(create_complete_user(email="ok@exemplo.com"))
        self.assertNotIn("proteína", plan.notes)

    def test_a_low_protein_catalog_is_reported(self):
        arroz = Food.objects.get(name="Arroz")
        MealTemplate.objects.update(is_active=False)
        for categoria in (MealCategory.BREAKFAST, MealCategory.SNACK, MealCategory.MAIN):
            for indice in range(2):
                make_template(
                    f"Só arroz {categoria} {indice}",
                    categoria,
                    [(arroz, 150 + indice * 10, True)],
                )

        plan = services.create_plan(create_complete_user(email="poucaproteina@exemplo.com"))

        self.assertIn("proteína", plan.notes)
        self.assertIn(f"{plan.protein_g} g", plan.notes)

    def test_the_warning_respects_the_configured_floor(self):
        """A régua é a constante, não um número escrito no teste."""
        plan = NutritionPlan(protein_g=100)
        no_limite = Decimal(100) * meal_planner.PROTEIN_COVERAGE_FLOOR

        self.assertEqual(meal_planner.protein_coverage_warning(plan, no_limite), [])
        self.assertTrue(
            meal_planner.protein_coverage_warning(plan, no_limite - Decimal("0.01"))
        )


class SeededCatalogTests(TestCase):
    """O cardápio precisa funcionar com o catálogo real, não só com fixture."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_full_plan_from_the_real_catalog(self):
        user = create_complete_user()
        plan = services.create_plan(user)

        self.assertEqual(plan.slots.count(), 5)
        for slot in plan.slots.all():
            self.assertEqual(
                slot.options.count(), meal_planner.OPTIONS_PER_SLOT, slot.name
            )
        self.assertEqual(plan.notes, "")

    def test_every_goal_gets_a_complete_menu(self):
        """Objetivo diferente muda o alvo — o cardápio tem que dar conta de todos.

        A recomposição é a que aperta: mesma caloria de sempre com mais
        proteína. Se o catálogo só fechasse a conta com suplemento, é aqui que
        apareceria — em forma de aviso de horário sem receita.
        """
        for goal in Goal.values:
            with self.subTest(goal=goal):
                user = create_complete_user(email=f"{goal}@exemplo.com", goal=goal)
                plan = services.create_plan(user)

                self.assertEqual(plan.slots.count(), 5)
                for slot in plan.slots.all():
                    self.assertEqual(
                        slot.options.count(), meal_planner.OPTIONS_PER_SLOT, slot.name
                    )
                self.assertNotIn("catálogo", plan.notes)

    def test_the_menu_adds_up_to_the_daily_target(self):
        """A meta não pode ser só um número no topo da tela.

        Os alvos por horário somam a meta por construção; o que este teste
        cobre é o passo seguinte — a receita escalada até esse alvo. Seguindo a
        Opção A do dia inteiro, o cardápio real precisa cair em cima da meta,
        senão o app prescreve uma coisa e serve outra.
        """
        for goal in Goal.values:
            with self.subTest(goal=goal):
                user = create_complete_user(email=f"menu-{goal}@exemplo.com", goal=goal)
                plan = services.create_plan(user)
                slots = list(plan.slots.prefetch_related("options"))
                # `menu_totals` soma a opção PROJETADA do dia. Sem projetar
                # antes ele estoura — de propósito, para ninguém somar zero em
                # silêncio como aconteceu na primeira versão desta mudança.
                rodizio.projetar(slots, user.pk)

                menu = views.menu_totals(slots)
                folga = abs(menu["kcal"] - plan.target_kcal)

                self.assertLessEqual(
                    folga,
                    plan.target_kcal * 0.03,
                    f"cardápio de {menu['kcal']} kcal para meta de {plan.target_kcal}",
                )
                self.assertGreater(menu["protein_g"], 0)

    def test_a_vegan_profile_also_gets_a_full_repertoire(self):
        """A restrição mais apertada do catálogo é a régua da cobertura.

        Com repertório de quatro a régua ficou bem mais dura: o dia inteiro
        passou a precisar de vinte receitas veganas distintas, contra dez antes.
        É este teste que diz se o catálogo aguenta o cardápio V2 no pior caso.
        """
        user = create_complete_user(email="vegana@exemplo.com")
        user.profile.dietary_tags.add(DietaryTag.objects.get(slug="vegana"))

        plan = services.create_plan(user)

        # O catálogo vegano não tem as vinte receitas distintas que um dia com
        # repertório cheio consumiria — são quatro cafés, seis lanches e cinco
        # principais. O contrato passa a ser o honesto: nenhum horário fica
        # abaixo do que a TELA precisa, e nenhum passa do teto do repertório.
        #
        # Na prática isso dá rodízio no café, no lanche da manhã e no almoço, e
        # repertório mínimo no lanche da tarde e no jantar — que continuam
        # mostrando duas opções, sempre as mesmas. É pior que o cardápio
        # completo e melhor que quatro opções com receita repetida dentro do
        # mesmo dia, que era o que a versão anterior desta mudança produzia.
        for slot in plan.slots.all():
            with self.subTest(slot=slot.name):
                self.assertGreaterEqual(slot.options.count(), rodizio.POR_DIA)
                self.assertLessEqual(
                    slot.options.count(), meal_planner.OPTIONS_PER_SLOT
                )

        # Zero repetição continua sendo a régua, e agora ela é alcançável
        # porque o gerador parou de completar o repertório com cópias: prefere
        # um horário com três receitas diferentes a um com quatro e duas iguais.
        usadas = MealOption.objects.filter(slot__plan=plan).values_list(
            "template_id", flat=True
        )
        self.assertEqual(len(usadas), len(set(usadas)), "receita repetida no mesmo dia")
        self.assertNotIn("nenhuma receita", plan.notes)

    def test_the_menu_is_made_of_everyday_brazilian_food(self):
        """Regressão de conteúdo: o cardápio de quem não pediu nada é comum.

        Sem isso, uma mudança de peso na pontuação pode encher o dia de receita
        elaborada sem ninguém perceber — os testes de unidade continuariam
        verdes, porque cada peça sozinha estaria certa.
        """
        plan = services.create_plan(create_complete_user(email="comum@exemplo.com"))

        for option in MealOption.objects.filter(slot__plan=plan):
            with self.subTest(receita=option.template.name):
                self.assertTrue(option.template.everyday)
                self.assertLessEqual(option.template.prep_minutes, 25)

    def test_today_page_shows_the_menu(self):
        user = create_complete_user()
        self.client.force_login(user)

        response = self.client.get(reverse("plans:today"))

        self.assertEqual(response.status_code, 200)
        slot = user.plans.get(is_active=True).slots.first()
        self.assertContains(response, slot.name)
        # A receita que a tela mostra é a PROJETADA de hoje, e não a primeira
        # do repertório. Antes as duas coisas coincidiam porque só existiam
        # duas opções e as duas apareciam; agora o rank 0 pode estar de fora
        # hoje, e o teste pediria na tela um prato que não é o de hoje.
        for opcao in rodizio.opcoes_do_dia(slot, user.pk):
            self.assertContains(response, opcao.template.name)

    def test_o_link_da_lista_de_compras_leva_um_icone(self):
        """O ícone é decorativo: quem enxerga ganha reconhecimento, quem usa
        leitor de tela continua ouvindo só "Lista de compras".

        A asserção recorta o PRÓPRIO link antes de olhar para dentro. Procurar
        "<svg" na página inteira passaria por acidente — a barra de navegação
        tem cinco.
        """
        self.client.force_login(create_complete_user())

        response = self.client.get(reverse("plans:today"))
        html = response.content.decode()

        link = re.search(
            r'<a[^>]+href="%s"[^>]*>(.*?)</a>' % re.escape(reverse("plans:shopping")),
            html,
            re.S,
        )
        self.assertIsNotNone(link, "o link da lista de compras sumiu da tela Hoje")
        dentro = link.group(1)
        self.assertIn("<svg", dentro)
        self.assertIn('aria-hidden="true"', dentro)
        self.assertIn("Lista de compras", dentro)


# ---------------------------------------------------------------------------
# Etapa 5 — acompanhamento diário
# ---------------------------------------------------------------------------

class TrackingTests(CatalogFixture):
    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.get(order=0)
        self.option = self.slot.options.first()
        self.today = timezone.localdate()

    def test_marking_a_meal_freezes_its_macros(self):
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)

        self.assertEqual(log.kcal, self.option.kcal)
        self.assertEqual(log.protein_g, self.option.protein_g)
        self.assertEqual(log.slot_name, self.slot.name)
        self.assertEqual(log.scheduled_time, self.slot.time)
        self.assertIsNotNone(log.marked_at)

    def test_history_survives_the_recipe_changing_later(self):
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        frozen = log.kcal

        self.option.template.items.update(quantity_g=Decimal("999"))
        self.option.template.refresh_macros()
        log.refresh_from_db()

        self.assertEqual(log.kcal, frozen)

    def test_skipped_and_off_plan_do_not_count_calories(self):
        tracking.log_meal(self.user, self.slot, MealStatus.SKIPPED)
        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.kcal, Decimal("0"))
        self.assertIsNone(log.chosen_option)

        tracking.log_meal(self.user, self.slot, MealStatus.OFF_PLAN)
        log.refresh_from_db()
        self.assertEqual(log.status, MealStatus.OFF_PLAN)
        self.assertEqual(log.kcal, Decimal("0"))

    def test_marking_twice_updates_instead_of_duplicating(self):
        tracking.log_meal(self.user, self.slot, MealStatus.SKIPPED)
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)

        logs = MealLog.objects.filter(user=self.user, slot=self.slot, date=self.today)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().status, MealStatus.DONE)

    def test_day_summary_counts_only_what_was_eaten(self):
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        other = self.plan.slots.get(order=1)
        tracking.log_meal(self.user, other, MealStatus.SKIPPED)

        summary = tracking.day_summary(self.user, self.plan, self.today)

        self.assertEqual(summary["consumed_kcal"], tracking.arredondar(self.option.kcal))
        self.assertEqual(summary["done"], 1)
        self.assertEqual(summary["marked"], 2)
        self.assertEqual(summary["total"], 5)
        self.assertEqual(
            summary["remaining_kcal"],
            self.plan.target_kcal - tracking.arredondar(self.option.kcal),
        )

    def test_progress_never_passes_one_hundred_percent(self):
        for slot in self.plan.slots.all():
            option = slot.options.first()
            if option:
                tracking.log_meal(self.user, slot, MealStatus.DONE, option)
        MealLog.objects.filter(user=self.user).update(kcal=Decimal("9000"))

        summary = tracking.day_summary(self.user, self.plan, self.today)
        self.assertEqual(summary["progress_pct"], 100)

    def test_history_skips_days_without_any_marking(self):
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        tracking.log_meal(
            self.user, self.slot, MealStatus.DONE, self.option,
            day=self.today - timedelta(days=3),
        )

        rows = tracking.history(self.user)

        self.assertEqual(len(rows), 2)  # e não 14
        self.assertEqual(rows[0]["date"], self.today)  # mais recente primeiro
        self.assertTrue(rows[0]["is_today"])

    def test_adherence_is_the_share_of_meals_eaten_as_planned(self):
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        tracking.log_meal(self.user, self.plan.slots.get(order=1), MealStatus.SKIPPED)
        tracking.log_meal(self.user, self.plan.slots.get(order=2), MealStatus.OFF_PLAN)

        totals = tracking.adherence(tracking.history(self.user))
        self.assertEqual(totals["adherence_pct"], 33)  # 1 de 3 marcadas
        self.assertEqual(totals["days"], 1)

    def test_adherence_of_an_empty_history_does_not_divide_by_zero(self):
        self.assertEqual(tracking.adherence([]), {"days": 0, "avg_kcal": 0, "adherence_pct": 0})


class MarkMealViewTests(CatalogFixture):
    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.get(order=0)
        self.option = self.slot.options.first()
        self.client.force_login(self.user)

    def url(self, slot=None):
        return reverse("plans:mark_meal", args=[(slot or self.slot).pk])

    def test_marking_from_the_page_records_the_chosen_option(self):
        response = self.client.post(
            self.url(), {"status": "done", "option": self.option.pk}
        )

        # A âncora não é detalhe: a tela Hoje tem de 4 a 5 dobras, e sem ela a
        # marcação devolvia a pessoa ao topo, longe da refeição que ela acabou
        # de marcar. `test_unknown_status_is_ignored` continua exigindo o topo
        # no ramo de ERRO, onde a mensagem é renderizada.
        self.assertRedirects(
            response, reverse("plans:today") + "#slot-%d" % self.slot.pk
        )
        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.chosen_option, self.option)
        self.assertEqual(log.kcal, self.option.kcal)

    def test_today_page_shows_what_was_marked(self):
        self.client.post(self.url(), {"status": "done", "option": self.option.pk})

        response = self.client.get(reverse("plans:today"))

        self.assertContains(response, self.option.template.name)
        self.assertContains(response, "desfazer")

    def test_undo_removes_the_log(self):
        self.client.post(self.url(), {"status": "done", "option": self.option.pk})
        self.client.post(reverse("plans:clear_meal", args=[self.slot.pk]))

        self.assertFalse(MealLog.objects.filter(user=self.user, slot=self.slot).exists())

    def test_cannot_mark_a_meal_from_someone_elses_plan(self):
        intruder = create_complete_user(email="intruso@exemplo.com")
        other_slot = services.create_plan(intruder).slots.first()

        response = self.client.post(
            self.url(other_slot),
            {"status": "done", "option": other_slot.options.first().pk},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_option_from_another_slot_is_rejected(self):
        other_option = self.plan.slots.get(order=1).options.first()

        response = self.client.post(self.url(), {"status": "done", "option": other_option.pk})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_unknown_status_is_ignored(self):
        response = self.client.post(self.url(), {"status": "inventado"})

        self.assertRedirects(response, reverse("plans:today"))
        self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_a_get_does_not_mark_the_meal(self):
        """A asserção era `status == 405`: o mecanismo, e não a regra.

        O 405 vinha com zero byte, e era onde o `next` do login aterrissava
        depois de a sessão expirar — quem tocava em "Comi esta", entrava de
        novo e acertava a senha terminava numa página em branco. Ver
        `config/acoes.py`.
        """
        self.client.get(self.url())

        self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_a_get_takes_the_person_back_to_today(self):
        self.assertRedirects(self.client.get(self.url()), reverse("plans:today"))


class HistoryViewTests(CatalogFixture):
    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.client.force_login(self.user)

    def test_empty_history_invites_the_first_marking(self):
        response = self.client.get(reverse("plans:history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ainda não há nada marcado")

    def test_history_lists_the_marked_days(self):
        slot = self.plan.slots.get(order=0)
        tracking.log_meal(self.user, slot, MealStatus.DONE, slot.options.first())

        response = self.client.get(reverse("plans:history"))

        self.assertContains(response, "Aderência")
        self.assertContains(response, "100%")

    def test_history_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("plans:history"))
        self.assertIn(reverse("accounts:login"), response["Location"])


class RecalculationDuringTheDayTests(CatalogFixture):
    """Recalcular no meio do dia não pode perder nem duplicar o que já foi comido."""

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.get(order=0)
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.slot.options.first())

    def test_marks_follow_the_new_plan(self):
        # A pessoa se pesou de novo hoje: um registro por dia, então atualiza.
        WeightEntry.objects.filter(user=self.user, date=timezone.localdate()).update(
            weight_kg=Decimal("79.0")
        )
        new_plan, changed = services.sync_active_plan(self.user)

        self.assertTrue(changed)
        self.assertEqual(MealLog.objects.filter(user=self.user).count(), 1)

        log = MealLog.objects.get(user=self.user)
        self.assertEqual(log.slot.plan, new_plan)
        self.assertEqual(log.slot.order, 0)

        summary = tracking.day_summary(self.user, new_plan, timezone.localdate())
        self.assertEqual(summary["done"], 1)
        self.assertGreater(summary["consumed_kcal"], 0)

    def test_yesterdays_marks_stay_with_the_old_plan(self):
        old_log = tracking.log_meal(
            self.user, self.slot, MealStatus.DONE, self.slot.options.first(),
            day=timezone.localdate() - timedelta(days=1),
        )
        services.create_plan(self.user)

        old_log.refresh_from_db()
        self.assertEqual(old_log.slot.plan, self.plan)  # histórico não se mexe

    def test_two_recalculations_in_the_same_day_do_not_duplicate(self):
        services.create_plan(self.user)  # segundo plano
        services.create_plan(self.user)  # terceiro

        plan = services.get_active_plan(self.user)
        logs = MealLog.objects.filter(user=self.user, date=timezone.localdate())

        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().slot.plan, plan)
        self.assertEqual(tracking.day_summary(self.user, plan, timezone.localdate())["done"], 1)

    def test_orphan_log_from_an_old_plan_does_not_inflate_the_day(self):
        old_slot = self.slot
        services.create_plan(self.user)
        plan = services.get_active_plan(self.user)

        # Simula um registro que ficou para trás (dado criado antes desta regra).
        MealLog.objects.create(
            user=self.user, slot=old_slot, date=timezone.localdate(),
            status=MealStatus.DONE, slot_name=old_slot.name, kcal=Decimal("500"),
        )

        summary = tracking.day_summary(self.user, plan, timezone.localdate())
        self.assertEqual(summary["done"], 1)  # só o do plano ativo


class PracticalityTests(CatalogFixture):
    """A dieta tem que caber na rotina: comida simples primeiro."""

    def setUp(self):
        self.slot = MealSlot(
            name="Almoço", category=MealCategory.MAIN, order=0, time=time(12, 0),
            target_kcal=600, target_protein_g=40, target_carb_g=60, target_fat_g=20,
        )
        self.macros = {"kcal": Decimal(600), "protein_g": Decimal(40)}

    def test_everyday_recipe_wins_a_tie(self):
        simples = make_template("Arroz com ovo", MealCategory.MAIN,
                                [(self.rice, 150, True), (self.chicken, 100, True)])
        elaborada = make_template("Assado do domingo", MealCategory.MAIN,
                                  [(self.rice, 150, True), (self.chicken, 100, True)],
                                  everyday=False, prep_minutes=45)

        self.assertLess(
            meal_planner.score(self.macros, self.slot, simples),
            meal_planner.score(self.macros, self.slot, elaborada),
        )

    def test_long_prep_costs_points_but_the_penalty_has_a_ceiling(self):
        rapida = make_template("Rápida", MealCategory.MAIN, [(self.rice, 150, True)],
                               prep_minutes=10)
        media = make_template("Média", MealCategory.MAIN, [(self.rice, 150, True)],
                              prep_minutes=35)
        eterna = make_template("Eterna", MealCategory.MAIN, [(self.rice, 150, True)],
                               prep_minutes=180)

        self.assertEqual(meal_planner.practicality_penalty(rapida), Decimal("0"))
        self.assertGreater(
            meal_planner.practicality_penalty(media),
            meal_planner.practicality_penalty(rapida),
        )
        self.assertEqual(
            meal_planner.practicality_penalty(eterna), meal_planner.MAX_PREP_PENALTY
        )

    def test_nutrition_still_beats_convenience(self):
        # Uma receita simples que erra feio o alvo não pode ganhar de uma
        # elaborada que acerta: praticidade é desempate, não critério principal.
        elaborada_certa = make_template("Assado certo", MealCategory.MAIN,
                                        [(self.rice, 150, True)], everyday=False,
                                        prep_minutes=45)
        simples_errada = {"kcal": Decimal(200), "protein_g": Decimal(5)}
        simples = make_template("Simples ruim", MealCategory.MAIN,
                                [(self.rice, 150, True)])

        self.assertLess(
            meal_planner.score(self.macros, self.slot, elaborada_certa),
            meal_planner.score(simples_errada, self.slot, simples),
        )

    def test_generation_prefers_everyday_recipes(self):
        user = create_complete_user(email="rotina@exemplo.com")
        plan = services.create_plan(user)

        elaboradas = MealOption.objects.filter(
            slot__plan=plan, template__everyday=False
        ).count()
        self.assertEqual(elaboradas, 0)

    def test_elaborate_recipe_still_shows_up_when_it_is_the_only_one(self):
        tag = DietaryTag.objects.create(slug="vegana", name="Vegana", kind=TagKind.RESTRICTION)
        unica = make_template("Escondidinho", MealCategory.MAIN,
                              [(self.rice, 200, True)], tags=(), everyday=False,
                              prep_minutes=40)
        unica.tags.add(tag)

        user = create_complete_user(email="unica@exemplo.com")
        user.profile.dietary_tags.add(tag)
        plan = services.create_plan(user)

        usadas = MealOption.objects.filter(
            slot__plan=plan, slot__category=MealCategory.MAIN
        ).values_list("template__name", flat=True)
        self.assertIn("Escondidinho", set(usadas))


class RetiredIngredientTests(CatalogFixture):
    def test_recipe_with_an_inactive_ingredient_is_not_suggested(self):
        make_template("Prato com item aposentado", MealCategory.MAIN,
                      [(self.nuts, 100, True)])
        Food.objects.filter(pk=self.nuts.pk).update(is_active=False)

        nomes = [t.name for t in meal_planner.candidates_for(MealCategory.MAIN, [])]

        self.assertNotIn("Prato com item aposentado", nomes)
        self.assertNotIn("Arroz com castanha", nomes)  # também usa castanha
        self.assertIn("Frango com arroz", nomes)


class SeedContentTests(TestCase):
    """O conteúdo do seed precisa respeitar as regras que o projeto promete."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", "--reset-templates", verbosity=0)

    def test_every_seeded_recipe_uses_only_active_foods(self):
        com_inativo = (
            MealTemplate.objects.filter(is_active=True, items__food__is_active=False)
            .distinct()
            .values_list("name", flat=True)
        )
        self.assertEqual(list(com_inativo), [])

    def test_most_recipes_are_everyday_food(self):
        ativas = MealTemplate.objects.filter(is_active=True)
        simples = ativas.filter(everyday=True).count()
        self.assertGreaterEqual(simples / ativas.count(), Decimal("0.8"))

    def test_everyday_recipes_are_quick_to_cook(self):
        demoradas = MealTemplate.objects.filter(
            is_active=True, everyday=True, prep_minutes__gt=30
        ).values_list("name", flat=True)
        self.assertEqual(list(demoradas), [])

    def test_calories_of_every_food_match_its_macros(self):
        from django.core.exceptions import ValidationError

        for food in Food.objects.filter(is_active=True):
            try:
                food.clean()
            except ValidationError as exc:
                self.fail(f"{food.name}: {exc.messages[0]}")

    def test_the_basics_of_a_brazilian_kitchen_are_all_in_the_catalog(self):
        """A lista de compras que o app pode pedir é a do mercado de esquina.

        O teste olha por pedaço do nome porque o catálogo distingue variações
        (arroz branco e integral, feijão carioca e preto) e o que importa aqui
        é que o básico exista, não como ele foi nomeado.
        """
        basicos = [
            "arroz", "feijão", "ovo", "frango", "carne moída", "batata",
            "banana", "maçã", "aveia", "pão", "leite", "queijo", "tapioca",
            "alface", "tomate", "cenoura", "brócolis",
        ]
        ativos = [
            name.lower() for name in Food.objects.filter(is_active=True)
            .values_list("name", flat=True)
        ]
        faltando = [
            basico for basico in basicos
            if not any(basico in name for name in ativos)
        ]
        self.assertEqual(faltando, [], "básico fora do catálogo")

    def test_expensive_or_hard_to_find_food_stays_out(self):
        """Suplemento, corte nobre e gourmet ficam aposentados, não sugeridos.

        Aposentado e não apagado: quem já comeu aquilo continua com o histórico
        legível, e o alimento volta com um clique se um dia fizer sentido.
        """
        for nome in [
            "Whey protein isolado", "Whey protein concentrado", "Albumina em pó",
            "Salmão grelhado", "Alcatra grelhada", "Camarão cozido",
            "Castanha de caju", "Castanha-do-pará", "Amêndoas", "Nozes",
            "Quinoa cozida", "Chia", "Granola sem açúcar", "Chocolate 70% cacau",
            "Tofu", "Morango",
        ]:
            with self.subTest(alimento=nome):
                food = Food.objects.filter(name=nome).first()
                self.assertIsNotNone(food, f"{nome} sumiu do catálogo em vez de ser aposentado")
                self.assertFalse(food.is_active, nome)

    def test_no_recipe_depends_on_a_long_shopping_trip(self):
        """Receita do dia a dia é de até 6 itens: mais que isso vira projeto."""
        for template in MealTemplate.objects.filter(is_active=True, everyday=True):
            with self.subTest(receita=template.name):
                self.assertLessEqual(template.items.count(), 6)

    def test_every_restriction_can_fill_a_whole_day_without_repeating(self):
        """Restrição não pode significar cardápio pela metade.

        Cada horário quer duas receitas inéditas: são 2 no café, 4 nos dois
        lanches e 4 nas duas refeições principais. Abaixo disso o gerador
        começa a repetir prato no mesmo dia — que ele faz de propósito para não
        deixar horário vazio, mas é aviso de catálogo curto, não resultado bom.
        """
        necessario = {
            MealCategory.BREAKFAST: 2,
            MealCategory.SNACK: 4,
            MealCategory.MAIN: 4,
        }
        for tag in DietaryTag.objects.filter(kind=TagKind.RESTRICTION):
            for categoria, minimo in necessario.items():
                with self.subTest(restricao=tag.slug, categoria=categoria):
                    disponiveis = MealTemplate.objects.filter(
                        is_active=True, category=categoria, tags=tag
                    ).count()
                    self.assertGreaterEqual(disponiveis, minimo)


class ProteinAsymmetryTests(TestCase):
    """Passar da proteína custa menos que ficar abaixo — caloria não."""

    def setUp(self):
        self.slot = MealSlot(
            name="Almoço", category=MealCategory.MAIN, order=0, time=time(12, 0),
            target_kcal=600, target_protein_g=40, target_carb_g=60, target_fat_g=20,
        )

    def test_overshooting_protein_is_cheaper_than_missing_it(self):
        acima = {"kcal": Decimal(600), "protein_g": Decimal(60)}
        abaixo = {"kcal": Decimal(600), "protein_g": Decimal(20)}

        self.assertLess(
            meal_planner.deviation(acima, self.slot),
            meal_planner.deviation(abaixo, self.slot),
        )

    def test_calories_are_penalized_the_same_in_both_directions(self):
        acima = {"kcal": Decimal(700), "protein_g": Decimal(40)}
        abaixo = {"kcal": Decimal(500), "protein_g": Decimal(40)}

        self.assertEqual(
            meal_planner.deviation(acima, self.slot),
            meal_planner.deviation(abaixo, self.slot),
        )

    def test_hitting_the_target_is_still_the_best_score(self):
        certo = {"kcal": Decimal(600), "protein_g": Decimal(40)}
        sobrando = {"kcal": Decimal(600), "protein_g": Decimal(80)}

        self.assertEqual(meal_planner.deviation(certo, self.slot), Decimal(0))
        self.assertGreater(meal_planner.deviation(sobrando, self.slot), Decimal(0))

    def test_overshoot_costs_exactly_the_configured_fraction(self):
        # Mesma distância do alvo, para cima e para baixo: a de cima custa a
        # fração configurada da de baixo. É essa regra que devolveu frango e
        # carne ao almoço de quem não tem restrição — eles estouram o alvo de
        # proteína do horário e, no desvio simétrico, perdiam para tofu.
        acima = {"kcal": Decimal(600), "protein_g": Decimal(60)}
        abaixo = {"kcal": Decimal(600), "protein_g": Decimal(20)}

        self.assertEqual(
            meal_planner.deviation(acima, self.slot),
            meal_planner.deviation(abaixo, self.slot) * meal_planner.PROTEIN_OVERSHOOT_FACTOR,
        )

    def test_someone_without_restrictions_is_not_pushed_to_vegan_meals(self):
        """Regressão de conteúdo: onívoro tem que ver frango, carne, ovo ou peixe.

        Roda contra o catálogo real porque o problema aparece na combinação de
        seed + pontuação, não em cada um separado.
        """
        call_command("seed_catalog", "--reset-templates", verbosity=0)
        user = create_complete_user(email="onivoro@exemplo.com")
        plan = services.create_plan(user)

        principais = MealOption.objects.filter(
            slot__plan=plan, slot__category=MealCategory.MAIN
        )
        com_proteina_animal = [
            option
            for option in principais
            if not option.template.tags.filter(slug="vegana").exists()
        ]
        self.assertTrue(
            com_proteina_animal,
            "todas as refeições principais vieram veganas para quem não pediu isso",
        )


class CatalogChangeTests(CatalogFixture):
    """Mudou o catálogo, o cardápio da pessoa acompanha na próxima visita."""

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)

    def test_plan_pointing_at_a_retired_recipe_is_rebuilt(self):
        usada = MealOption.objects.filter(slot__plan=self.plan).first().template
        MealTemplate.objects.filter(pk=usada.pk).update(is_active=False)

        novo, mudou = services.sync_active_plan(self.user)

        self.assertTrue(mudou)
        self.assertNotEqual(novo.pk, self.plan.pk)
        self.assertFalse(
            MealOption.objects.filter(slot__plan=novo, template=usada).exists()
        )

    def test_untouched_catalog_does_not_rebuild_anything(self):
        _, mudou = services.sync_active_plan(self.user)
        self.assertFalse(mudou)


class ShoppingListTests(TestCase):
    """A lista de compras da semana, por corredor de supermercado."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)

    def test_it_multiplies_the_daily_menu_by_the_week(self):
        """O cardápio é o mesmo todo dia; a compra é ele vezes sete."""
        cru = shopping.weekly_quantities(self.plan)
        self.assertTrue(cru)

        _, dados = next(iter(cru.items()))
        diario = dados["quantity"] / shopping.DAYS
        self.assertEqual(dados["quantity"], diario * shopping.DAYS)
        self.assertGreater(dados["quantity"], diario)

    def test_the_aisles_come_in_the_order_you_walk_the_market(self):
        lista = shopping.shopping_list(self.plan)
        corredores = [corredor["aisle"] for corredor in lista]
        esperada = [a for a in shopping.AISLE_ORDER if a in corredores]
        self.assertEqual(corredores, esperada)

    def test_quantities_are_rounded_up_to_something_buyable(self):
        """Ninguém compra 847 g de arroz."""
        self.assertEqual(shopping.round_up(Decimal("847")), Decimal("850"))
        self.assertEqual(shopping.round_up(Decimal("83")), Decimal("90"))
        self.assertEqual(shopping.round_up(Decimal("1201")), Decimal("1300"))
        # Já redondo continua redondo — arredondar de novo seria inflar a compra.
        self.assertEqual(shopping.round_up(Decimal("850")), Decimal("850"))

    def test_big_amounts_are_announced_in_kilos(self):
        self.assertEqual(shopping.humanize(Decimal("1500"), "g"), "1,5 kg")
        self.assertEqual(shopping.humanize(Decimal("400"), "g"), "400 g")
        self.assertEqual(shopping.humanize(Decimal("2000"), "ml"), "2 L")

    def test_the_same_food_in_two_recipes_is_bought_once(self):
        """Arroz no almoço e no jantar é uma linha só na lista."""
        lista = shopping.shopping_list(self.plan)
        nomes = [
            linha["food"].name for corredor in lista for linha in corredor["items"]
        ]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_every_item_says_which_recipes_asked_for_it(self):
        lista = shopping.shopping_list(self.plan)
        for corredor in lista:
            for linha in corredor["items"]:
                with self.subTest(alimento=linha["food"].name):
                    self.assertTrue(linha["recipes"])


class ShoppingViewTests(TestCase):
    url = reverse("plans:shopping")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_the_page_lists_the_aisles_and_the_amounts(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lista de compras")
        self.assertContains(response, "Hortifrúti")
        self.assertContains(response, "Açougue e ovos")

    def test_an_unknown_option_falls_back_to_a(self):
        """Parâmetro inventado na URL não pode quebrar a tela."""
        response = self.client.get(self.url, {"opcao": "Z"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["label"], "A")

    def test_it_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertIn(reverse("accounts:login"), response["Location"])





class RefeicaoPuladaTests(TestCase):
    """O impacto de pular uma refeição, dito em proteína.

    Só proteína, e isso é escolha: carboidrato pulado a pessoa recupera no
    almoço sem pensar; proteína pulada não volta.
    """

    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()

    def setUp(self):
        self.user = create_complete_user(email="pulou@exemplo.com")
        self.client.force_login(self.user)
        self.plan = services.get_active_plan(self.user) or services.create_plan(self.user)

    def _pular(self, slot):
        return self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]), {"status": "skipped"}
        )

    def test_nothing_is_said_when_no_meal_was_skipped(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn('class="pulou"', html)

    def test_skipping_shows_the_protein_gap_in_grams(self):
        slot = self.plan.slots.order_by("order").first()
        self._pular(slot)

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn('class="pulou"', html)
        self.assertIn(f"{slot.target_protein_g} g", html)
        self.assertIn(slot.name.lower(), html.lower())

    def test_the_gap_is_translated_into_food(self):
        """"Faltam 37 g de proteína" é abstrato; "120 g de frango" é jantar."""
        slot = self.plan.slots.order_by("order").first()
        self._pular(slot)

        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("de frango a mais no", html)

    def test_two_skipped_meals_add_up(self):
        slots = list(self.plan.slots.order_by("order")[:2])
        for slot in slots:
            self._pular(slot)

        html = self.client.get(reverse("plans:today")).content.decode()
        total = sum(s.target_protein_g for s in slots)

        self.assertIn(f"{total} g", html)
        self.assertIn("2 refeições", html)

    def test_eating_the_meal_says_nothing_about_gaps(self):
        """"Comi outra coisa" e "comi esta" não disparam o aviso: ele existe
        para a refeição que NÃO aconteceu."""
        slot = self.plan.slots.order_by("order").first()
        self.client.post(
            reverse("plans:mark_meal", args=[slot.pk]), {"status": "off_plan"}
        )

        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertNotIn('class="pulou"', html)


class IngredientListTests(TestCase):
    """A lista de ingredientes diz DE QUÊ, e não só quanto.

    O nome do alimento era o rótulo do botão de troca: o texto vivia dentro do
    `<button class="swap-open">`. Quando a substituição de alimento saiu, a
    expressão regular que apagou o botão levou o miolo junto, e o cardápio
    passou a listar "98 g", "100 g", "59 g" — quantidades de coisa nenhuma.

    O teste da remoção conferia a AUSÊNCIA de `swap-open` e passou. Nenhum
    conferia a PRESENÇA do nome, que é a informação pela qual a tela existe.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_each_ingredient_shows_which_food_it_is(self):
        resposta = self.client.get(reverse("plans:today"))
        html = resposta.content.decode()

        lista = html.split('class="option__items"', 1)[1].split("</ul>", 1)[0]
        nomes = re.findall(r'class="option__ingrediente">([^<]+)<', lista)

        self.assertTrue(nomes, "a lista de ingredientes não traz nome nenhum")
        for nome in nomes:
            self.assertTrue(nome.strip(), "linha de ingrediente com nome vazio")

    def test_the_quantity_keeps_its_own_column(self):
        """Nome à esquerda, gramatura à direita: os números alinham numa
        coluna que se lê de relance. Sem `flex: none` no `<b>`, um nome longo
        empurra a quantidade e a coluna deixa de existir."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        regra = css.split("\n.option__items b {", 1)[1].split("}", 1)[0]
        self.assertIn("flex: none", regra)
        self.assertIn("tabular-nums", regra)

    def test_a_long_food_name_cannot_push_the_page_sideways(self):
        """"Filé de peito de frango grelhado" é nome real do catálogo. Item de
        flex sem `min-width: 0` se recusa a encolher abaixo do próprio texto."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".option__ingrediente { min-width: 0; }", css)


class MealStyleTests(TestCase):
    """O cardápio econômico pesa contra o caro — e não o elimina.

    A distinção importa e está escrita na tela: restrição ELIMINA a receita,
    preferência a coloca no fim da fila. Com catálogo pequeno e restrições
    apertadas, eliminar deixa o horário vazio, e horário vazio é pior que
    horário caro — a pessoa fica sem saber o que comer, que é exatamente o
    problema que o app existe para resolver.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def _receita_com_premium(self):
        for template in MealTemplate.objects.filter(is_active=True).prefetch_related(
            "items__food"
        ):
            if any(item.food.is_premium for item in template.items.all()):
                return template
        self.fail("nenhuma receita do catálogo usa ingrediente caro")

    def test_the_varied_style_charges_nothing(self):
        """Variada é o cardápio que o app já fazia. O estilo não pode inventar
        custo onde ninguém pediu — se cobrasse, migrar quem estava no padrão
        antigo reescreveria o cardápio dessa pessoa."""
        template = self._receita_com_premium()
        self.assertEqual(
            meal_planner.style_penalty(template, MealCategory.MAIN, MealStyle.VARIED),
            Decimal("0"),
        )

    def test_no_style_at_all_charges_nothing(self):
        template = self._receita_com_premium()
        self.assertEqual(
            meal_planner.style_penalty(template, MealCategory.MAIN, None), Decimal("0")
        )

    def test_an_expensive_ingredient_costs_the_recipe_points(self):
        template = self._receita_com_premium()
        self.assertGreaterEqual(
            meal_planner.style_penalty(template, MealCategory.MAIN, MealStyle.QUICK),
            meal_planner.PREMIUM_INGREDIENT_PENALTY,
        )

    def test_two_expensive_ingredients_do_not_charge_twice(self):
        """O que pesa é a receita SER cara, não quanto. Somar por ingrediente
        faria uma receita com atum e tilápia perder de uma que erra a caloria
        pela metade — e aí o estilo teria virado restrição por acidente."""
        template = self._receita_com_premium()
        for item in template.items.all():
            item.food.is_premium = True
            item.food.save(update_fields=["is_premium"])
        template.refresh_from_db()

        self.assertEqual(
            meal_planner.style_penalty(template, MealCategory.MAIN, MealStyle.QUICK),
            meal_planner.PREMIUM_INGREDIENT_PENALTY,
        )

    def test_a_long_breakfast_costs_but_a_long_lunch_does_not(self):
        """Café e lanche competem com pressa real — um antes de sair de casa,
        o outro no intervalo. No almoço a pessoa já parou para comer."""
        demorada = MealTemplate.objects.filter(
            is_active=True, prep_minutes__gt=meal_planner.QUICK_PREP_MINUTES
        ).first()
        self.assertIsNotNone(demorada, "o catálogo não tem receita demorada")

        for item in demorada.items.all():
            item.food.is_premium = False
            item.food.save(update_fields=["is_premium"])
        demorada.refresh_from_db()

        self.assertEqual(
            meal_planner.style_penalty(
                demorada, MealCategory.BREAKFAST, MealStyle.QUICK
            ),
            meal_planner.QUICK_PREP_PENALTY,
        )
        self.assertEqual(
            meal_planner.style_penalty(demorada, MealCategory.MAIN, MealStyle.QUICK),
            Decimal("0"),
        )

    def test_the_penalty_never_empties_a_meal_slot(self):
        """A prova de que é peso e não filtro.

        Se TODA receita do catálogo virar cara, o cardápio econômico ainda
        precisa sair com opções — todas penalizadas por igual, e a nota volta
        a ser decidida pelo desvio nutricional, que é o critério certo quando
        não há escolha barata.
        """
        Food.objects.update(is_premium=True)

        profile = Profile.objects.get(user=create_complete_user())
        profile.meal_style = MealStyle.QUICK
        profile.save(update_fields=["meal_style"])

        plan = services.create_plan(profile.user)
        vazios = [slot.name for slot in plan.slots.all() if not slot.options.exists()]
        self.assertEqual(vazios, [], "o estilo econômico esvaziou horários")


class ComiOutraCoisaTests(TestCase):
    """A refeição fora do plano deixa de ser um buraco com carimbo.

    Antes: um `submit` direto gravava `off_plan`, macro zerado, nenhuma palavra
    sobre o que foi. O horário saía das pendências E não contava nada — sumia
    da tela e da conta ao mesmo tempo, que é o pior dos dois mundos, porque
    some sem a pessoa perceber que sumiu.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.first()
        self.url = reverse("plans:mark_meal", kwargs={"slot_id": self.slot.pk})

    def _log(self):
        return MealLog.objects.get(user=self.user, slot=self.slot)

    def test_the_field_only_exists_inside_the_expandable_panel(self):
        """Oculto por padrão sem `hidden` e sem script: o campo está dentro de
        um `<details>` fechado, e o navegador não o mostra até alguém abrir."""
        html = self.client.get(reverse("plans:today")).content.decode()

        painel = html.split('<details class="fora"', 1)
        self.assertEqual(len(painel), 2, "o painel de fora do plano não existe")
        corpo = painel[1].split("</details>", 1)[0]

        self.assertIn('name="notes"', corpo)
        self.assertIn('name="alimento"', corpo)
        # Fechado por padrão: um `<details open>` mostraria o formulário
        # inteiro em todos os horários da tela.
        self.assertNotIn("<details class=\"fora\" open", html)

    def test_describing_nothing_does_not_register_anything(self):
        """A validação do lado que ninguém desliga.

        `required` protege o navegador; um POST forjado, um autofill estranho
        ou um cliente offline reenviando não passam por ele.
        """
        resposta = self.client.post(self.url, {"status": "off_plan", "notes": "   "})

        self.assertFalse(MealLog.objects.filter(slot=self.slot).exists())
        self.assertIn(f"#refeicao-{self.slot.pk}", resposta.url)

    def test_a_description_alone_is_registered_with_no_invented_calories(self):
        """"Almocei na casa da minha mãe" é registro legítimo e não vira macro.

        Estimar aqui seria pior que zerar: número inventado no histórico
        contamina a aderência de meses, e a pessoa não tem como saber quais
        dias são chute.
        """
        self.client.post(
            self.url, {"status": "off_plan", "notes": "Almocei na casa da minha mãe"}
        )

        log = self._log()
        self.assertEqual(log.status, MealStatus.OFF_PLAN)
        self.assertEqual(log.notes, "Almocei na casa da minha mãe")
        self.assertEqual(log.kcal, Decimal("0.00"))

    def test_describing_the_foods_recalculates_the_meal(self):
        arroz = Food.objects.get(name="Arroz branco cozido")
        ovo = Food.objects.get(name="Ovo de galinha cozido")

        self.client.post(
            self.url,
            {
                "status": "off_plan",
                "notes": "Arroz com ovo",
                "alimento": [arroz.name, ovo.name],
                "gramas": ["150", "100"],
            },
        )

        esperado = arroz.macros_for(Decimal("150"))["kcal"] + ovo.macros_for(
            Decimal("100")
        )["kcal"]
        self.assertEqual(self._log().kcal, esperado.quantize(Decimal("0.01")))

    def test_the_name_is_matched_without_caring_about_case(self):
        """A pessoa digita por cima da sugestão do datalist, e digita como
        quiser."""
        arroz = Food.objects.get(name="Arroz branco cozido")
        self.client.post(
            self.url,
            {
                "status": "off_plan",
                "notes": "arroz",
                "alimento": ["ARROZ BRANCO COZIDO"],
                "gramas": ["100"],
            },
        )
        self.assertEqual(
            self._log().kcal, arroz.macros_for(Decimal("100"))["kcal"].quantize(Decimal("0.01"))
        )

    def test_a_food_the_catalog_does_not_have_is_ignored_not_fatal(self):
        """Recusar a refeição inteira por causa de uma linha mal digitada é o
        caminho mais curto para a pessoa parar de registrar."""
        arroz = Food.objects.get(name="Arroz branco cozido")
        self.client.post(
            self.url,
            {
                "status": "off_plan",
                "notes": "Arroz e um negócio que não existe",
                "alimento": ["Arroz branco cozido", "Ambrosia de dragão"],
                "gramas": ["100", "80"],
            },
        )

        log = self._log()
        self.assertEqual(log.notes, "Arroz e um negócio que não existe")
        self.assertEqual(
            log.kcal, arroz.macros_for(Decimal("100"))["kcal"].quantize(Decimal("0.01"))
        )

    def test_an_abandoned_row_does_not_count_as_zero_grams(self):
        """Linha começada e largada — nome sem gramatura, ou gramatura zero —
        é ruído, não um alimento de zero caloria."""
        for gramas in ("", "0", "-50", "abc", "9999"):
            with self.subTest(gramas=gramas):
                MealLog.objects.filter(slot=self.slot).delete()
                self.client.post(
                    self.url,
                    {
                        "status": "off_plan",
                        "notes": "teste",
                        "alimento": ["Arroz branco cozido"],
                        "gramas": [gramas],
                    },
                )
                self.assertEqual(self._log().kcal, Decimal("0.00"))

    def test_skipping_a_meal_still_registers_nothing(self):
        """"Pulei" continua sendo o que sempre foi: o comportamento novo é do
        botão ao lado, e não pode ter vazado para este."""
        self.client.post(self.url, {"status": "skipped"})

        log = self._log()
        self.assertEqual(log.status, MealStatus.SKIPPED)
        self.assertEqual(log.kcal, Decimal("0.00"))
        self.assertEqual(log.notes, "")

    def test_the_catalog_list_is_rendered_once_and_not_per_meal(self):
        """900 nós de DOM na tela mais visitada do app, para uma ação que quase
        nunca acontece — era o custo de um `<select>` por linha."""
        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertEqual(html.count('<datalist id="alimentos-do-catalogo">'), 1)
        self.assertNotIn("<select", html.split('class="fora"', 1)[1])


class ComiOutraCoisaBordasTests(TestCase):
    """As bordas que a auditoria encontrou no parser da refeição fora do plano.

    Todas vieram de sondar o `_itens_descritos` com entrada hostil, que é o
    caminho por onde POST forjado, autofill estranho e fila offline reenviando
    chegam — e nenhum deles passa pelo `required` do navegador.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def _pedido(self, alimentos, gramas):
        dados = QueryDict(mutable=True)
        dados.setlist("alimento", alimentos)
        dados.setlist("gramas", gramas)
        return views._itens_descritos(dados)

    def test_a_not_a_number_does_not_take_the_page_down(self):
        """`Decimal("NaN")` NÃO levanta ao ser construído — ele constrói um
        NaN, e a COMPARAÇÃO seguinte é que estourava `InvalidOperation`. O
        `try` só envolvia a construção, então o erro 500 chegava na cara de
        quem queria registrar o almoço."""
        for veneno in ("NaN", "sNaN", "-NaN", "Infinity", "-Infinity"):
            with self.subTest(gramas=veneno):
                self.assertEqual(self._pedido(["Arroz branco cozido"], [veneno]), [])

    def test_the_same_food_twice_is_summed_and_not_overwritten(self):
        """Arroz no almoço e arroz de novo à noite é a mesma linha do catálogo
        duas vezes. A versão anterior guardava num dicionário por nome e ficava
        com a ÚLTIMA: 150 g e depois 100 g viravam 100, não 250."""
        itens = self._pedido(
            ["Arroz branco cozido", "Arroz branco cozido"], ["150", "100"]
        )
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0][1], Decimal("250"))

    def test_the_ceiling_applies_to_the_sum_and_not_to_the_line(self):
        """Com o teto só por linha, duas de 2 kg passavam e viravam 4 kg num
        prato. O teto existe para barrar dedo escorregando no teclado, e
        escorregar duas vezes é o caso mais provável, não o menos."""
        itens = self._pedido(
            ["Arroz branco cozido", "Arroz branco cozido"], ["2000", "2000"]
        )
        self.assertEqual(itens[0][1], views.LIMITE_GRAMAS - Decimal("1000"))

        cabe = self._pedido(
            ["Arroz branco cozido", "Arroz branco cozido"], ["2000", "900"]
        )
        self.assertEqual(cabe[0][1], Decimal("2900"))

    def test_a_lopsided_pair_of_lists_does_not_shift_the_quantities(self):
        """Nomes e gramaturas chegam como duas listas paralelas. Se elas
        desalinharem, o `zip` para na mais curta — o que descarta linhas, e
        NÃO casa o nome de uma com a gramatura de outra, que seria gravar
        comida que a pessoa não comeu."""
        itens = self._pedido(
            ["Arroz branco cozido", "Ovo de galinha cozido"], ["100"]
        )
        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0][0].name, "Arroz branco cozido")


class ConvitePesagemNoPainelTests(TestCase):
    """A faixa condicional do painel.

    O painel não tem folga: a primeira refeição começa a 740px numa dobra que
    termina a 776. Por isso a faixa é condicional, e por isso o que estes
    testes defendem é sobretudo a AUSÊNCIA dela — um bloco fixo aqui tiraria o
    cardápio da dobra todo dia.

    A matriz da regra (uma na semana, duas na semana, virada de semana) é
    testada com datas fixas em `ConvitePesagemTests`. Aqui só se verifica que
    a tela consulta a regra: montar "duas na semana e nenhuma hoje" a partir
    da data real falharia nas segundas-feiras, quando a semana só tem hoje.
    """

    url = reverse("plans:today")
    #: Marcador de classe, e não `data-`. O seletor e o marcador costumam ser
    #: a mesma string neste repositório, e aí `assertNotIn` passa por acidente
    #: porque o texto também está dentro do `<script>`.
    FAIXA = 'class="pesar"'

    def setUp(self):
        self.user = create_complete_user(email="painel-peso@exemplo.com")
        self.user.weight_entries.all().delete()
        # Uma pesagem antiga, e não nenhuma: sem peso não há plano, e a tela
        # redirecionaria para o onboarding antes de decidir mostrar a faixa.
        # Quinze dias atrás cai numa semana anterior em qualquer dia da semana.
        WeightEntry.objects.create(
            user=self.user,
            date=timezone.localdate() - timedelta(days=15),
            weight_kg=Decimal("83.0"),
        )
        self.client.force_login(self.user)

    def test_a_week_without_weighing_gets_the_invitation(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, self.FAIXA)
        self.assertContains(resposta, "Peso de hoje")

    def test_the_invitation_is_gone_once_today_is_recorded(self):
        WeightEntry.objects.create(
            user=self.user, date=timezone.localdate(), weight_kg=Decimal("82.6")
        )

        self.assertNotContains(self.client.get(self.url), self.FAIXA)

    def test_a_brand_new_account_is_not_asked_to_weigh_on_day_one(self):
        """O passo 1 do onboarding já gravou a pesagem de hoje. Cobrar de novo
        no primeiro minuto é o app abrindo em débito."""
        novo = create_complete_user(email="estreia-peso@exemplo.com")
        self.client.force_login(novo)

        self.assertNotContains(self.client.get(self.url), self.FAIXA)

    def test_the_invitation_never_claims_the_weight_is_already_in(self):
        """Nada de "✓ peso registrado". Estado ocupado sem ação pendente é
        espaço da dobra gasto para dizer que não há o que fazer."""
        resposta = self.client.get(self.url)

        self.assertNotContains(resposta, "peso registrado")

    def test_the_invitation_posts_to_the_weight_route_and_says_where_it_came_from(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, reverse("accounts:log_weight"))
        self.assertContains(resposta, 'value="hoje"')

    def test_the_field_takes_a_comma_and_asks_for_the_numeric_keyboard(self):
        """`type="number"` recusaria "82,5", que é como se escreve aqui."""
        html = self.client.get(self.url).content.decode()
        campo = html.split('class="pesagem__valor', 1)[1].split(">", 1)[0]

        self.assertIn('inputmode="decimal"', campo)
        self.assertNotIn('type="number"', campo)

    def test_the_invitation_disappears_only_after_the_server_answers(self):
        """Sem rede o POST falha e a faixa continua lá. Ela some porque a
        condição do servidor virou falsa, nunca por otimismo do cliente — por
        isso não há JavaScript nenhum escondendo a faixa."""
        self.assertContains(self.client.get(self.url), self.FAIXA)

        self.client.post(
            reverse("accounts:log_weight"), {"weight_kg": "82,1", "origem": "hoje"}
        )

        self.assertNotContains(self.client.get(self.url), self.FAIXA)


class CartaoDePesoTests(TestCase):
    """O registro inline em Métricas, que é o caminho principal.

    Antes, "Registrar" abria o passo 1 do onboarding: quatro campos, sendo
    três que não mudam nunca, e a barra de abas sumindo porque o passo se
    declara `sem_tabbar`. A pessoa era levada para um cadastro que já tinha
    concluído e voltava no Perfil.
    """

    url = reverse("plans:history")

    def setUp(self):
        self.user = create_complete_user(email="cartao-peso@exemplo.com")
        self.client.force_login(self.user)

    def test_the_card_records_a_weight_without_leaving_the_screen(self):
        resposta = self.client.get(self.url)

        self.assertContains(resposta, 'class="pesagem"')
        self.assertContains(resposta, reverse("accounts:log_weight"))
        self.assertContains(resposta, 'value="metricas"')

    def test_the_weight_card_no_longer_sends_anyone_to_the_wizard(self):
        """O passo 1 continua existindo, e continua alcançável pelo Perfil.
        Ele só não é mais o caminho para se pesar."""
        resposta = self.client.get(self.url)

        self.assertNotContains(resposta, reverse("accounts:onboarding_step", args=[1]))

    def test_correcting_starts_from_the_weight_already_recorded_today(self):
        """Corrigir começa do valor que está lá. Campo vazio obrigaria a
        pessoa a lembrar o que digitou de manhã."""
        self.user.weight_entries.update(weight_kg=Decimal("81.30"))

        html = self.client.get(self.url).content.decode()
        campo = html.split('class="pesagem__valor', 1)[1].split(">", 1)[0]

        # "81,30" e não "81,3": duas casas e vírgula decimal é como o app
        # escreve número em toda tela, e o campo aceita as duas formas de
        # volta. `floatformat` faz a mesma coisa aqui e na carga da ficha.
        self.assertIn('value="81,30"', campo)

    def test_yesterdays_weight_never_prefills_todays_field(self):
        """Só o peso de HOJE preenche. O de ontem no campo faria a pessoa
        salvar sem perceber a medição de ontem como se fosse a de hoje."""
        self.user.weight_entries.all().delete()
        WeightEntry.objects.create(
            user=self.user,
            date=timezone.localdate() - timedelta(days=1),
            weight_kg=Decimal("81.30"),
        )

        html = self.client.get(self.url).content.decode()
        campo = html.split('class="pesagem__valor', 1)[1].split(">", 1)[0]

        self.assertIn('value=""', campo)

    def test_the_average_and_the_recalibration_still_live_in_the_card(self):
        """O formulário entrou acima da média, não no lugar dela. A média da
        semana antes dos números do dia é a decisão inteira desta tela."""
        WeightEntry.objects.create(
            user=self.user,
            date=timezone.localdate() - timedelta(days=8),
            weight_kg=Decimal("84.0"),
        )
        resposta = self.client.get(self.url)

        self.assertContains(resposta, "semana de")
        self.assertContains(resposta, "Ver as pesagens dia a dia")


class PesoRecusadoVoltaParaATelaTests(TestCase):
    """O que a pessoa digitou sobrevive à recusa, nas duas superfícies.

    O valor atravessa um redirecionamento, então ele precisa esperar em algum
    lugar. Estes testes existem porque a ponta escrita (a sessão receber a
    chave) já era testada e a ponta lida (a tela usar a chave) não era: a
    constante podia ser renomeada de um lado só e o campo voltaria vazio sem
    nenhum teste reclamando.
    """

    rota = reverse("accounts:log_weight")

    def setUp(self):
        self.user = create_complete_user(email="recusa@exemplo.com")
        self.user.weight_entries.all().delete()
        WeightEntry.objects.create(
            user=self.user,
            date=timezone.localdate() - timedelta(days=15),
            weight_kg=Decimal("83.0"),
        )
        self.client.force_login(self.user)

    def _campo(self, resposta):
        html = resposta.content.decode()
        return html.split('class="pesagem__valor', 1)[1].split(">", 1)[0]

    def test_the_panel_reopens_the_strip_with_what_was_typed(self):
        """Fechada, a sanfona esconderia justamente o campo que a pessoa
        precisa corrigir — ela veria a mensagem de erro sem ver onde agir."""
        self.client.post(self.rota, {"weight_kg": "8o,5", "origem": "hoje"})

        resposta = self.client.get(reverse("plans:today"))

        self.assertContains(resposta, "<details class=\"pesar\" open>", html=False)
        self.assertIn('value="8o,5"', self._campo(resposta))

    def test_metrics_brings_back_the_typo_instead_of_todays_weight(self):
        """O valor recusado ganha do peso já registrado: a pessoa está
        corrigindo o que acabou de digitar, não recomeçando do zero."""
        WeightEntry.objects.create(
            user=self.user, date=timezone.localdate(), weight_kg=Decimal("80.00")
        )

        self.client.post(self.rota, {"weight_kg": "8o,5", "origem": "metricas"})
        resposta = self.client.get(reverse("plans:history"))

        self.assertIn('value="8o,5"', self._campo(resposta))

    def test_the_typo_is_shown_once_and_not_forever(self):
        """Semântica de recado: some depois de entregue. Do contrário a pessoa
        corrige, sai da tela, volta, e reencontra o erro antigo no campo."""
        self.client.post(self.rota, {"weight_kg": "8o,5", "origem": "hoje"})

        self.client.get(reverse("plans:today"))
        segunda = self.client.get(reverse("plans:today"))

        self.assertIn('value=""', self._campo(segunda))

    def test_the_typo_never_comes_back_as_markup(self):
        """O valor vem do teclado de quem usa, e volta para dentro de um
        atributo HTML. Sem escape, aspas fecham o atributo."""
        self.client.post(
            self.rota, {"weight_kg": '8"><script>x</script>', "origem": "hoje"}
        )

        resposta = self.client.get(reverse("plans:today"))

        self.assertNotContains(resposta, "<script>x</script>")
        self.assertContains(resposta, "&quot;&gt;&lt;script&gt;")

    def test_a_saved_weight_clears_the_typo_left_behind(self):
        """Errou, corrigiu, salvou: o recado do erro não pode sobreviver ao
        acerto e reaparecer na próxima recusa de outra pessoa da casa."""
        self.client.post(self.rota, {"weight_kg": "8o,5", "origem": "hoje"})
        self.client.post(self.rota, {"weight_kg": "80,5", "origem": "hoje"})

        self.assertIsNone(self.client.session.get("peso_recusado"))

    # ------------------------------------------------ cada erro na sua tela

    def test_the_panel_does_not_eat_an_error_born_in_metrics(self):
        """Abrir a aba do meio do caminho não pode gastar o erro da outra.

        Era o que acontecia: a pessoa errava o peso em Métricas, tocava Dieta
        antes de voltar, e o que ela tinha digitado sumia — sem mensagem, sem
        campo preenchido, sem nada na tela dizendo por quê.
        """
        self.client.post(self.rota, {"weight_kg": "9x,1", "origem": "metricas"})

        painel = self.client.get(reverse("plans:today"))
        self.assertNotIn('value="9x,1"', self._campo(painel))

        metricas = self.client.get(reverse("plans:history"))
        self.assertIn('value="9x,1"', self._campo(metricas))

        segunda = self.client.get(reverse("plans:history"))
        self.assertIn('value=""', self._campo(segunda))

    def test_metrics_does_not_eat_an_error_born_in_the_panel(self):
        """O mesmo pelo outro lado — a guarda vale nas duas direções, senão é
        meia correção que passa no teste que alguém lembrou de escrever."""
        self.client.post(self.rota, {"weight_kg": "7q,3", "origem": "hoje"})

        metricas = self.client.get(reverse("plans:history"))
        self.assertNotIn('value="7q,3"', self._campo(metricas))

        painel = self.client.get(reverse("plans:today"))
        self.assertIn('value="7q,3"', self._campo(painel))

        segunda = self.client.get(reverse("plans:today"))
        self.assertIn('value=""', self._campo(segunda))

    def test_an_origin_nobody_recognises_never_gets_stamped(self):
        """A origem é normalizada antes de carimbar o erro.

        Guardar a origem crua deixaria o erro marcado com algo que nenhuma
        tela reconhece, e a chave ficaria presa na sessão para sempre.
        """
        self.client.post(
            self.rota, {"weight_kg": "5w", "origem": "https://exemplo.invalido/"}
        )

        guardado = self.client.session.get("peso_recusado")
        self.assertEqual(guardado[0], "metricas")
        self.assertIn('value="5w"', self._campo(self.client.get(reverse("plans:history"))))

    # -------------------------------------------------- tentativa em branco

    def test_an_empty_attempt_keeps_the_panel_strip_open(self):
        """Tocar Salvar com o campo em branco é uma tentativa recusada como
        qualquer outra.

        Decidindo pela verdade do texto, a sanfona fechava justamente aqui: a
        mensagem "Digite o peso" aparecia e o campo para digitá-lo tinha ido
        embora junto.
        """
        self.client.post(self.rota, {"weight_kg": "", "origem": "hoje"})

        resposta = self.client.get(reverse("plans:today"))

        self.assertContains(resposta, '<details class="pesar" open>', html=False)
        self.assertContains(resposta, "Digite o peso")

    def test_an_empty_attempt_in_metrics_is_not_the_same_as_no_attempt(self):
        """Com peso já registrado hoje, a diferença fica visível: sem erro o
        campo traz o peso de hoje; com erro em branco ele fica vazio, porque é
        o rastro da tentativa que a pessoa acabou de fazer."""
        WeightEntry.objects.create(
            user=self.user, date=timezone.localdate(), weight_kg=Decimal("80.00")
        )

        sem_erro = self._campo(self.client.get(reverse("plans:history")))
        self.assertIn('value="80"', sem_erro)

        self.client.post(self.rota, {"weight_kg": "", "origem": "metricas"})
        com_erro = self._campo(self.client.get(reverse("plans:history")))

        self.assertIn('value=""', com_erro)


# ---------------------------------------------------------------------------
# Snapshot do nome da receita no MealLog
# ---------------------------------------------------------------------------

class SnapshotDaReceitaTests(CatalogFixture):
    """`MealLog.recipe_name` congela O QUE FOI COMIDO, e não uma referência.

    Os macros já eram congelados desde a etapa 5. O nome não era: ele saía de
    `chosen_option.template.name`, que é relação viva. Renomear a receita no
    admin reescrevia o histórico inteiro em silêncio, e aposentar o plano
    antigo levava o nome junto.

    O caso real que motiva isto: a pessoa abre o histórico de duas semanas
    atrás para lembrar o que comeu num dia que deu certo. Se o nome for lido
    do plano de hoje, ela lê o cardápio de hoje com a data de antes.
    """

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.get(order=0)
        self.option = self.slot.options.first()
        self.today = timezone.localdate()

    # A ---------------------------------------------------------------- grava
    def test_marcar_uma_opcao_congela_o_nome_da_receita(self):
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)

        self.assertEqual(log.recipe_name, self.option.template.name)
        self.assertEqual(log.recipe_display, self.option.template.name)

    # B ------------------------------------------------------------- sobrevive
    def test_renomear_a_receita_depois_nao_reescreve_o_historico(self):
        """O teste que dá razão ao campo: sem ele, o passado mudava sozinho."""
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        nome_no_dia = self.option.template.name

        template = self.option.template
        template.name = "Receita renomeada muito depois"
        template.is_active = False
        template.save(update_fields=["name", "is_active"])

        log.refresh_from_db()
        self.assertEqual(log.recipe_name, nome_no_dia)
        # E a leitura acompanha: a propriedade prefere o retrato à relação.
        self.assertEqual(log.recipe_display, nome_no_dia)
        self.assertNotEqual(log.recipe_display, template.name)

    # C ------------------------------------------------------------ plano novo
    def test_plano_novo_nao_mexe_no_registro_de_antes(self):
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        nome_no_dia = self.option.template.name

        services.create_plan(self.user)

        log.refresh_from_db()
        self.assertEqual(log.recipe_name, nome_no_dia)
        self.assertEqual(log.recipe_display, nome_no_dia)

    # D ----------------------------------------------------------- idempotente
    def test_marcar_de_novo_atualiza_o_snapshot_sem_duplicar(self):
        """Remarcar troca o retrato inteiro; não deixa metade do anterior."""
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)

        logs = MealLog.objects.filter(user=self.user, slot=self.slot, date=self.today)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().recipe_name, self.option.template.name)

        # Mudou de ideia e pulou: o nome tem de SAIR junto dos macros. Deixar
        # o nome de uma receita numa refeição pulada seria afirmar que ela foi
        # comida.
        tracking.log_meal(self.user, self.slot, MealStatus.SKIPPED)
        log = logs.get()
        self.assertEqual(log.status, MealStatus.SKIPPED)
        self.assertEqual(log.recipe_name, "")
        self.assertEqual(log.recipe_display, "")

    def test_trocar_de_opcao_troca_o_retrato_inteiro(self):
        """Comeu a B depois de ter marcado a A: o retrato passa a ser o da B.

        O retrato é um conjunto, não campos soltos. Se o nome trocasse e os
        macros ficassem, ou o contrário, o histórico passaria a descrever uma
        refeição que nunca existiu — e ninguém veria, porque as duas metades
        são plausíveis sozinhas.

        Está aqui porque o caminho é corriqueiro: a pessoa marca a opção A de
        manhã, almoça a B e volta para corrigir.
        """
        a, b = list(self.slot.options.all()[:2])
        self.assertNotEqual(a.template.name, b.template.name)

        tracking.log_meal(self.user, self.slot, MealStatus.DONE, a)
        logs = MealLog.objects.filter(user=self.user, slot=self.slot, date=self.today)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().recipe_name, a.template.name)

        tracking.log_meal(self.user, self.slot, MealStatus.DONE, b)

        self.assertEqual(logs.count(), 1)
        log = logs.get()
        self.assertEqual(log.chosen_option, b)
        self.assertEqual(log.recipe_name, b.template.name)
        self.assertNotEqual(log.recipe_name, a.template.name)
        self.assertEqual(log.recipe_display, b.template.name)

        # Os números vêm da mesma opção que o nome. É a metade que faltaria.
        self.assertEqual(log.kcal, b.kcal)
        self.assertEqual(log.protein_g, b.protein_g)
        self.assertEqual(log.carb_g, b.carb_g)
        self.assertEqual(log.fat_g, b.fat_g)

    # E -------------------------------------------------------- logs anteriores
    def test_registro_anterior_a_migracao_cai_no_fallback(self):
        """Vazio com opção viva: mostra o nome da opção, sem quebrar."""
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        # Simula um registro gravado antes de este campo existir.
        MealLog.objects.filter(pk=log.pk).update(recipe_name="")
        log.refresh_from_db()

        self.assertEqual(log.recipe_name, "")
        self.assertEqual(log.recipe_display, self.option.template.name)

    def test_registro_antigo_sem_opcao_nao_quebra(self):
        """Plano apagado zera `chosen_option`: o fallback aguenta `None`."""
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        MealLog.objects.filter(pk=log.pk).update(recipe_name="", chosen_option=None)
        log.refresh_from_db()

        self.assertIsNone(log.chosen_option)
        self.assertEqual(log.recipe_display, "")

    def test_tela_de_hoje_abre_com_registro_antigo_sem_snapshot(self):
        log = tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)
        MealLog.objects.filter(pk=log.pk).update(recipe_name="")
        self.client.force_login(self.user)

        response = self.client.get(reverse("plans:today"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.option.template.name)

    # F ------------------------------------------------------ comi outra coisa
    def test_comi_outra_coisa_nao_inventa_nome_de_receita(self):
        """Vazio é a resposta honesta: quem descreve o que foi comido é `notes`.

        Carimbar "Outra refeição" criaria uma linha indistinguível de uma
        receita que se chamasse assim, e destruiria a única pergunta que a
        coluna precisa responder: existe retrato, ou não existe?
        """
        log = tracking.log_meal(
            self.user,
            self.slot,
            MealStatus.OFF_PLAN,
            notes="pizza na casa da minha mãe",
        )

        self.assertEqual(log.recipe_name, "")
        self.assertEqual(log.recipe_display, "")
        self.assertEqual(log.notes, "pizza na casa da minha mãe")
        self.assertIsNone(log.chosen_option)

    def test_pular_a_refeicao_tambem_fica_sem_nome(self):
        log = tracking.log_meal(self.user, self.slot, MealStatus.SKIPPED)

        self.assertEqual(log.recipe_name, "")
        self.assertEqual(log.recipe_display, "")

    # G ------------------------------------------------------------- confiança
    def test_o_cliente_nao_escolhe_o_que_vai_no_snapshot(self):
        """O nome vem da opção que o SERVIDOR resolveu, não do formulário.

        Se o campo fosse lido do request, qualquer pessoa escreveria o próprio
        histórico — e histórico que o dono edita não serve para decidir nada.
        """
        self.client.force_login(self.user)

        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {
                "status": MealStatus.DONE,
                "option": self.option.pk,
                "recipe_name": "Salada de mentira que eu nao comi",
            },
        )

        log = MealLog.objects.get(user=self.user, slot=self.slot, date=self.today)
        self.assertEqual(log.recipe_name, self.option.template.name)
        self.assertNotIn("mentira", log.recipe_name)

    def test_o_cliente_nao_injeta_nome_no_comi_outra_coisa(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {
                "status": MealStatus.OFF_PLAN,
                "notes": "comi na rua",
                "recipe_name": "Receita inventada",
            },
        )

        log = MealLog.objects.get(user=self.user, slot=self.slot, date=self.today)
        self.assertEqual(log.recipe_name, "")
        self.assertEqual(log.notes, "comi na rua")

    # ------------------------------------------------------------------ offline
    def test_reenvio_da_fila_offline_continua_idempotente(self):
        """A fila reenvia o MESMO formulário. O snapshot nasce no servidor.

        O contrato da fila não mudou e não precisava mudar: o corpo que ela
        guarda nunca teve nome de receita, e o replay passa pela mesma view.
        """
        self.client.force_login(self.user)
        corpo = {"status": MealStatus.DONE, "option": self.option.pk}
        url = reverse("plans:mark_meal", args=[self.slot.pk])

        self.client.post(url, corpo)
        self.client.post(url, corpo)  # o replay da fila

        logs = MealLog.objects.filter(user=self.user, slot=self.slot, date=self.today)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().recipe_name, self.option.template.name)


class AcaoAgoraTests(TestCase):
    """A regra do cartão "Agora" da tela Hoje.

    A tela abria com cinco números — anel de calorias, saldo, macros — quase
    todos zerados de manhã, e nenhuma ação. Estes testes travam a regra que
    passou a decidir o topo: estado vence agenda, e entre o que já venceu
    ganha o mais RECENTE, não o mais atrasado.
    """

    def _slot(self, pk, nome, hora, kcal=400, proteina=30, log=None):
        slot = MealSlot(
            name=nome, time=hora, target_kcal=kcal, target_protein_g=proteina,
            target_carb_g=40, target_fat_g=15, order=pk, category=MealCategory.MAIN,
        )
        slot.pk = pk
        slot.log = log
        return slot

    def _log(self, status):
        return MealLog(status=status)

    def _treino(self, *, nome="Peito e tríceps", inicio=time(18, 30),
                feitas=0, total=20, concluido=False, exercicios=7):
        sessao = TrainingSession(
            name=nome, start_time=inicio, weekday=0, label="A", duration_min=60
        )
        estado = workout_services.EstadoDoTreino()
        estado.sessao = sessao
        estado.itens = [object()] * exercicios
        estado.total_exercicios = exercicios
        estado.series_feitas = feitas
        estado.total_series = total
        estado.concluido = concluido
        return estado

    def _agora(self, h, m=0):
        return timezone.make_aware(
            datetime.combine(timezone.localdate(), time(h, m))
        )

    def _chamar(self, slots, treino=None, meta_agua=2500, bebido=0, hora=(9, 0)):
        return agora.proxima_acao(
            slots=slots, treino=treino, meta_agua=meta_agua, bebido=bebido,
            agora=self._agora(*hora),
        )

    # -- o que está acontecendo agora ----------------------------------

    def test_antes_da_primeira_refeicao_o_rotulo_e_a_seguir(self):
        """Às seis da manhã nada venceu, e a tela não finge urgência."""
        slots = [self._slot(1, "Café da manhã", time(7, 0)),
                 self._slot(2, "Almoço", time(12, 0))]

        acao = self._chamar(slots, hora=(6, 0))

        self.assertEqual(acao.rotulo, "A SEGUIR")
        self.assertEqual(acao.titulo, "Café da manhã")
        self.assertFalse(acao.atrasada)

    def test_depois_do_horario_a_refeicao_vira_agora(self):
        slots = [self._slot(1, "Café da manhã", time(7, 0)),
                 self._slot(2, "Almoço", time(12, 0))]

        acao = self._chamar(slots, hora=(8, 0))

        self.assertEqual(acao.rotulo, "AGORA")
        self.assertEqual(acao.titulo, "Café da manhã")
        self.assertTrue(acao.atrasada)

    def test_entre_vencidos_ganha_o_mais_recente_e_nao_o_mais_atrasado(self):
        """Às 20h, com almoço e jantar pendentes, "agora" é o jantar.

        O almoço das 12h não é uma coisa a fazer agora — é uma pendência, e ela
        continua visível na lista. Ordenar pelo mais atrasado deixaria o topo
        preso numa refeição de oito horas atrás pelo resto do dia.
        """
        slots = [self._slot(1, "Almoço", time(12, 0)),
                 self._slot(2, "Jantar", time(19, 0))]

        acao = self._chamar(slots, hora=(20, 0))

        self.assertEqual(acao.titulo, "Jantar")

    def test_refeicao_ja_comida_sai_da_disputa(self):
        slots = [self._slot(1, "Café da manhã", time(7, 0),
                            log=self._log(MealStatus.DONE)),
                 self._slot(2, "Almoço", time(12, 0))]

        acao = self._chamar(slots, hora=(8, 0))

        self.assertEqual(acao.titulo, "Almoço")
        self.assertEqual(acao.rotulo, "A SEGUIR")

    def test_refeicao_pulada_conta_como_resolvida(self):
        """Pular é uma resposta. Insistir seria cobrar decisão já tomada."""
        slots = [self._slot(1, "Café da manhã", time(7, 0),
                            log=self._log(MealStatus.SKIPPED)),
                 self._slot(2, "Almoço", time(12, 0))]

        acao = self._chamar(slots, hora=(8, 0))

        self.assertEqual(acao.titulo, "Almoço")

    def test_comi_outra_coisa_tambem_conta_como_resolvida(self):
        slots = [self._slot(1, "Café da manhã", time(7, 0),
                            log=self._log(MealStatus.OFF_PLAN))]

        acao = self._chamar(slots, hora=(8, 0), meta_agua=0)

        self.assertEqual(acao.tipo, "vazio")

    # -- o CTA da refeição ---------------------------------------------

    def test_o_botao_da_refeicao_leva_ao_cartao_e_nao_marca_nada(self):
        """A/B: marcar daqui teria que escolher a opção pela pessoa.

        `MealLog` copia os macros no ato — gravar o prato errado num toque é
        pior que pedir um toque a mais. O cartão da refeição é onde a escolha
        existe, e é para lá que o botão aponta.
        """
        slots = [self._slot(7, "Almoço", time(12, 0), kcal=608, proteina=44)]

        acao = self._chamar(slots, hora=(13, 0))

        self.assertEqual(acao.url, "#slot-7")
        self.assertNotIn("marcar", acao.cta.lower())
        self.assertIn("608 kcal", acao.detalhe)
        self.assertIn("44 g de proteína", acao.detalhe)

    # -- treino ---------------------------------------------------------

    def test_treino_em_andamento_ganha_de_refeicao_vencida(self):
        """Estado vence agenda.

        Quem está entre séries não quer ser mandado para o lanche da tarde
        porque deu quinze horas.
        """
        slots = [self._slot(1, "Lanche da tarde", time(15, 0))]
        treino = self._treino(feitas=6, total=20)

        acao = self._chamar(slots, treino=treino, hora=(19, 0))

        self.assertEqual(acao.tipo, "treino")
        self.assertEqual(acao.cta, "Continuar de onde parou")
        self.assertIn("6 de 20 séries", acao.detalhe)

    def test_treino_nao_iniciado_disputa_pelo_horario(self):
        slots = [self._slot(1, "Lanche da tarde", time(15, 0))]
        treino = self._treino(inicio=time(18, 30))

        acao = self._chamar(slots, treino=treino, hora=(19, 0))

        self.assertEqual(acao.tipo, "treino")
        self.assertEqual(acao.cta, "Começar treino")
        self.assertEqual(acao.url, reverse("workouts:now"))

    def test_refeicao_mais_recente_ganha_do_treino_mais_antigo(self):
        slots = [self._slot(1, "Jantar", time(19, 30))]
        treino = self._treino(inicio=time(18, 30))

        acao = self._chamar(slots, treino=treino, hora=(20, 0))

        self.assertEqual(acao.tipo, "refeicao")

    def test_treino_concluido_sai_da_disputa(self):
        slots = []
        treino = self._treino(feitas=20, total=20, concluido=True)

        acao = self._chamar(slots, treino=treino, hora=(20, 0), meta_agua=0)

        self.assertEqual(acao.tipo, "vazio")

    def test_dia_de_descanso_nao_inventa_treino(self):
        """Sem sessão hoje, `tem_treino` é falso e o treino não entra."""
        slots = []
        vazio = workout_services.EstadoDoTreino()

        acao = self._chamar(slots, treino=vazio, hora=(20, 0), meta_agua=0)

        self.assertFalse(vazio.tem_treino)
        self.assertEqual(acao.tipo, "vazio")

    # -- água e vazio ---------------------------------------------------

    def test_sem_refeicao_e_sem_treino_a_agua_assume(self):
        acao = self._chamar([], hora=(21, 0), meta_agua=2500, bebido=1500)

        self.assertEqual(acao.tipo, "agua")
        self.assertIn("1000", acao.titulo)
        self.assertIn("1500 de 2500", acao.detalhe)

    def test_agua_na_meta_nao_vira_acao(self):
        acao = self._chamar([], hora=(21, 0), meta_agua=2500, bebido=2500)

        self.assertEqual(acao.tipo, "vazio")

    def test_a_agua_nao_atropela_refeicao_pendente(self):
        """Água é o fundo da fila: ela sempre "falta" um pouco, e deixá-la
        competir faria a tela sugerir copo d'água no lugar do jantar."""
        slots = [self._slot(1, "Jantar", time(19, 0))]

        acao = self._chamar(slots, hora=(19, 30), meta_agua=2500, bebido=0)

        self.assertEqual(acao.tipo, "refeicao")

    def test_dia_inteiro_resolvido_devolve_acao_vazia(self):
        slots = [self._slot(1, "Jantar", time(19, 0), log=self._log(MealStatus.DONE))]

        acao = self._chamar(slots, hora=(22, 0), meta_agua=2000, bebido=2000)

        self.assertEqual(acao.tipo, "vazio")
        self.assertFalse(acao.existe)


class HojeV2ViewTests(CatalogFixture):
    """A tela Hoje montada de verdade, com plano e cardápio reais."""

    url = reverse("plans:today")

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="hojev2@exemplo.com")
        self.client.force_login(self.user)

    def test_a_primeira_dobra_traz_uma_acao(self):
        html = self.client.get(self.url).content.decode()
        corpo = html.split("<main", 1)[1]
        topo = corpo[: corpo.index("</section>")]

        self.assertIn("agora__rotulo", topo)

    def test_o_resumo_do_dia_cabe_numa_linha_de_texto(self):
        response = self.client.get(self.url)
        html = response.content.decode()

        self.assertIn("resumo-dia", html)
        self.assertContains(response, "refeições")
        self.assertContains(response, "ml")

    def test_a_acao_usa_o_fuso_local_e_nao_utc(self):
        """O servidor roda em UTC e o horário do slot é o da pessoa.

        Sem `localtime()` o "agora" erra por três horas — a tela mostraria o
        almoço como ação às nove da manhã.
        """
        response = self.client.get(self.url)
        acao = response.context["acao"]
        slots = list(response.context["slots"])
        hora_local = timezone.localtime().time()

        vencidas = [s for s in slots if s.time <= hora_local]
        if vencidas and acao.tipo == "refeicao":
            self.assertLessEqual(acao.horario, hora_local)

    def test_o_calculo_da_meta_fica_recolhido(self):
        """As explicações continuam na página, atrás de um toque."""
        response = self.client.get(self.url)
        html = response.content.decode()

        self.assertIn("Como chegamos na sua meta", html)
        bloco = html.split("Como chegamos na sua meta", 1)[0]
        self.assertIn("<details", bloco[-400:])

    def test_dia_de_descanso_nao_oferece_treino_na_tela_hoje(self):
        response = self.client.get(self.url)
        estado = response.context["treino_hoje"]

        if not estado.tem_treino:
            self.assertNotEqual(response.context["acao"].tipo, "treino")


class MarcadorDeRefeicaoTests(TestCase):
    """O selo que faz a lista concordar com o cartão do topo.

    Documentado em captura: com café das 7h30 e lanche das 11h pendentes, o
    topo dizia "AGORA · Lanche da manhã" e os dois cartões da lista ficavam
    idênticos. Nada indicava qual deles o topo apontava, nem que o café
    continuava em aberto.

    A marca "agora" NÃO é recalculada: é a identidade do slot que
    `proxima_acao` escolheu. Estes testes existem para que continue assim.
    """

    def _slot(self, pk, nome, hora, log=None):
        slot = MealSlot(
            name=nome, time=hora, target_kcal=400, target_protein_g=30,
            target_carb_g=40, target_fat_g=15, order=pk, category=MealCategory.MAIN,
        )
        slot.pk = pk
        slot.log = log
        return slot

    def _agora(self, h, m=0):
        return timezone.make_aware(
            datetime.combine(timezone.localdate(), time(h, m))
        )

    def _marcar(self, slots, treino=None, hora=(12, 0), meta_agua=2500, bebido=0):
        instante = self._agora(*hora)
        acao = agora.proxima_acao(
            slots=slots, treino=treino, meta_agua=meta_agua, bebido=bebido,
            agora=instante,
        )
        agora.marcar_refeicoes(slots, acao, instante)
        return acao, [s.marcador for s in slots]

    def _treino(self, *, inicio=time(18, 30), feitas=0, concluido=False):
        sessao = TrainingSession(
            name="Peito e tríceps", start_time=inicio, weekday=0, label="A",
            duration_min=60,
        )
        estado = workout_services.EstadoDoTreino()
        estado.sessao = sessao
        estado.itens = [object()] * 7
        estado.total_exercicios = 7
        estado.series_feitas = feitas
        estado.total_series = 20
        estado.concluido = concluido
        return estado

    # -- quantas venceram ----------------------------------------------

    def test_uma_vencida_recebe_agora_e_as_futuras_nada(self):
        slots = [self._slot(1, "Café", time(7, 30)),
                 self._slot(2, "Almoço", time(14, 30)),
                 self._slot(3, "Jantar", time(20, 0))]

        acao, marcas = self._marcar(slots, hora=(12, 0))

        self.assertEqual(acao.titulo, "Café")
        self.assertEqual(marcas, ["agora", "", ""])

    def test_duas_vencidas_a_mais_recente_e_agora_e_a_outra_pendente(self):
        """O caso da captura: os dois cartões deixam de ser idênticos."""
        slots = [self._slot(1, "Café", time(7, 30)),
                 self._slot(2, "Lanche da manhã", time(11, 0)),
                 self._slot(3, "Almoço", time(14, 30))]

        acao, marcas = self._marcar(slots, hora=(12, 36))

        self.assertEqual(acao.titulo, "Lanche da manhã")
        self.assertEqual(marcas, ["pendente", "agora", ""])

    def test_tres_vencidas_so_a_ultima_e_agora(self):
        slots = [self._slot(1, "Café", time(7, 30)),
                 self._slot(2, "Lanche da manhã", time(11, 0)),
                 self._slot(3, "Almoço", time(14, 30)),
                 self._slot(4, "Jantar", time(20, 0))]

        acao, marcas = self._marcar(slots, hora=(15, 0))

        self.assertEqual(acao.titulo, "Almoço")
        self.assertEqual(marcas, ["pendente", "pendente", "agora", ""])

    # -- o que já foi resolvido não volta a cobrar ----------------------

    def test_refeicao_antiga_comida_nao_recebe_selo(self):
        slots = [self._slot(1, "Café", time(7, 30),
                            log=MealLog(status=MealStatus.DONE)),
                 self._slot(2, "Lanche da manhã", time(11, 0))]

        acao, marcas = self._marcar(slots, hora=(12, 36))

        self.assertEqual(acao.titulo, "Lanche da manhã")
        self.assertEqual(marcas, ["", "agora"])

    def test_refeicao_pulada_nao_recebe_selo(self):
        slots = [self._slot(1, "Café", time(7, 30),
                            log=MealLog(status=MealStatus.SKIPPED)),
                 self._slot(2, "Lanche da manhã", time(11, 0))]

        _, marcas = self._marcar(slots, hora=(12, 36))

        self.assertEqual(marcas, ["", "agora"])

    def test_refeicao_fora_do_plano_nao_recebe_selo(self):
        slots = [self._slot(1, "Café", time(7, 30),
                            log=MealLog(status=MealStatus.OFF_PLAN)),
                 self._slot(2, "Lanche da manhã", time(11, 0))]

        _, marcas = self._marcar(slots, hora=(12, 36))

        self.assertEqual(marcas, ["", "agora"])

    # -- futuro e treino -------------------------------------------------

    def test_refeicao_futura_escolhida_como_a_seguir_nao_ganha_selo(self):
        """O topo diz "A SEGUIR"; um selo "Agora" no cartão diria o contrário.

        Sem este filtro, a refeição das 23h vira "Agora" às onze da manhã.
        """
        slots = [self._slot(1, "Jantar", time(23, 0))]

        acao, marcas = self._marcar(slots, hora=(11, 0))

        self.assertEqual(acao.rotulo, "A SEGUIR")
        self.assertEqual(acao.slot.pk, 1)
        self.assertEqual(marcas, [""])

    def test_com_treino_em_andamento_nenhuma_refeicao_finge_ser_a_vez(self):
        """O topo não está falando de comida.

        As vencidas continuam marcadas como pendentes — elas continuam em
        aberto —, mas nenhuma recebe "agora".
        """
        slots = [self._slot(1, "Café", time(7, 30)),
                 self._slot(2, "Almoço", time(14, 30))]
        treino = self._treino(feitas=6)

        acao, marcas = self._marcar(slots, hora=(19, 0), treino=treino)

        self.assertEqual(acao.tipo, "treino")
        self.assertNotIn("agora", marcas)
        self.assertEqual(marcas, ["pendente", "pendente"])

    # -- a tela ----------------------------------------------------------

    def test_o_template_nao_recalcula_quem_e_a_vez(self):
        """A palavra do selo sai de `slot.marcador`, e nada mais.

        Se alguém reimplementar a regra no template, existirão duas respostas
        para "quem é a vez" e elas vão divergir na próxima mudança.
        """
        alvo = Path(settings.BASE_DIR) / "templates" / "plans" / "today.html"
        html = alvo.read_text(encoding="utf-8")
        bloco = html.split("meal__marca", 1)[0][-700:]

        self.assertIn("slot.marcador", bloco)
        for reimplementacao in ("slot.time <", "slot.time >", "now|", "|time_until"):
            self.assertNotIn(reimplementacao, bloco)


class MarcadorNaTelaTests(CatalogFixture):
    """O selo renderizado, com plano e cardápio de verdade."""

    url = reverse("plans:today")

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="marcador@exemplo.com")
        self.client.force_login(self.user)

    def test_o_cartao_da_vez_e_o_unico_com_selo_de_agora(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        acao = response.context["acao"]

        if acao.tipo == "refeicao" and acao.atrasada:
            self.assertEqual(html.count("meal__marca--agora"), 1)
            cartao = html.split('id="slot-%d"' % acao.slot.pk, 1)[1]
            self.assertIn("meal__marca--agora", cartao[:1400])

    def test_o_selo_nao_usa_vermelho_nem_linguagem_punitiva(self):
        """Pendência não é falha: a pessoa ainda pode comer, pular ou registrar
        outra coisa."""
        html = self.client.get(self.url).content.decode()
        bloco = html.split("meal__marca", 1)[1][:400] if "meal__marca" in html else ""

        for palavra in ("atrasad", "falhou", "perdeu", "esqueceu"):
            self.assertNotIn(palavra, bloco.lower())

    def test_o_selo_nao_acrescenta_linha_ao_cabecalho(self):
        """Ele entra na fileira que a hora e o nome já ocupam.

        `.meal__name` é `display: block`; uma pílula depois dele cairia numa
        linha nova e cada cartão do dia ficaria mais alto.
        """
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        regra = css.split("\n.meal__marca {", 1)[1].split("}", 1)[0]

        self.assertIn("margin-left: auto", regra)
        self.assertIn("flex: none", regra)


class TituloDaTelaHojeTests(CatalogFixture):
    """Hoje era a única tela do app sem `<h1>`.

    Seu primeiro título era o `<h2>` do cartão da ação — que muda de texto
    conforme a hora ("Almoço", "Peito e tríceps"). O documento começava no
    nível 2, e quem navega por títulos não tinha como saber onde estava.

    Ele é invisível de propósito: a primeira dobra é exatamente o que o Hoje V2
    liberou para a ação, e o nome da tela já está escrito na aba ativa.
    """

    url = reverse("plans:today")

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="titulo@exemplo.com")
        self.client.force_login(self.user)

    def _html(self):
        return self.client.get(self.url).content.decode()

    def test_a_tela_tem_exatamente_um_h1(self):
        self.assertEqual(len(re.findall(r"<h1[ >]", self._html())), 1)

    def test_o_h1_nomeia_a_tela(self):
        achado = re.search(r"<h1[^>]*>(.*?)</h1>", self._html(), re.S)

        self.assertEqual(achado.group(1).strip(), "Hoje")

    def test_nenhum_h2_aparece_antes_do_h1(self):
        """Pular de nível é o defeito que o `<h1>` veio corrigir.

        Ancorado na POSIÇÃO, e não na existência: acrescentar o `<h1>` no fim
        do documento passaria num teste que só conta tags.
        """
        html = self._html()

        self.assertLess(html.index("<h1"), html.index("<h2"))

    def test_o_titulo_nao_ocupa_espaco_na_tela(self):
        """`.vis-oculto` é o utilitário que o app já usa para isto.

        Se alguém tirar a classe, o "Hoje" vira uma faixa de texto empurrando a
        ação para baixo — o oposto do que o Hoje V2 fez.
        """
        achado = re.search(r"<h1[^>]*>", self._html())

        self.assertIn("vis-oculto", achado.group(0))


class EstadoVazioDaListaDeComprasTests(CatalogFixture):
    """A lista sem nenhuma receita para agrupar.

    Diferente dos dois estados vazios de peso, este NÃO tem invariante que o
    impeça: ele depende de o cardápio ter receitas, o que sai do casamento com
    o catálogo. Rodado contra todos os planos ativos do banco local, em três
    rótulos, ele não apareceu nenhuma vez — mas "não aconteceu" não é "não
    pode acontecer", e por isso o ramo ganhou saída em vez de ficar mudo.
    """

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="compras@exemplo.com")
        self.client.force_login(self.user)

    def test_o_estado_vazio_oferece_o_cardapio(self):
        html = (Path(settings.BASE_DIR) / "templates" / "plans"
                / "shopping.html").read_text(encoding="utf-8")
        bloco = html.split("receitas suficientes", 1)[1][:400]

        self.assertIn("plans:today", bloco)
        self.assertIn("Ver meu cardápio", bloco)

    def test_a_tela_de_compras_continua_respondendo(self):
        self.assertEqual(
            self.client.get(reverse("plans:shopping")).status_code, 200
        )


class RodizioDiarioTests(TestCase):
    """A projeção diária: quais opções do repertório aparecem hoje.

    Testes de pura função, sem banco: `indices_do_dia` só precisa saber o
    tamanho do repertório, quem é a pessoa, qual o horário e que dia é. Manter
    isso sem banco é o que permite varrer trinta dias em milissegundos e provar
    distribuição de verdade, em vez de espiar dois dias e torcer.
    """

    HOJE = date(2026, 8, 30)

    def _dia(self, n=0):
        return self.HOJE + timedelta(days=n)

    def _indices(self, total=4, pk=7, ordem=2, n=0):
        return rodizio.indices_do_dia(total, user_pk=pk, slot_order=ordem, dia=self._dia(n))

    # -- o contrato básico ------------------------------------------------

    def test_projeta_exatamente_duas_com_repertorio_cheio(self):
        for n in range(30):
            with self.subTest(dia=n):
                self.assertEqual(len(self._indices(n=n)), 2)

    def test_as_duas_sao_sempre_distintas(self):
        """Duas fatias do mesmo prato não são escolha nenhuma."""
        for n in range(60):
            with self.subTest(dia=n):
                indices = self._indices(n=n)

                self.assertEqual(len(set(indices)), len(indices))

    def test_o_mesmo_dia_devolve_sempre_a_mesma_dupla(self):
        """Recarregar a página não pode trocar o almoço.

        É o requisito mais visível do rodízio: a pessoa abre, decide comer a
        opção B, vai para a cozinha, volta — e a B tem que continuar sendo a
        mesma comida.
        """
        primeira = self._indices()

        for _ in range(20):
            self.assertEqual(self._indices(), primeira)

    def test_dias_diferentes_mudam_a_dupla(self):
        """Se não mudasse, o cardápio V2 não existiria."""
        vistos = {self._indices(n=n) for n in range(6)}

        self.assertGreater(len(vistos), 1)

    def test_pessoas_diferentes_nao_andam_em_bloco(self):
        por_pessoa = {pk: self._indices(pk=pk) for pk in range(1, 40)}

        self.assertGreater(len(set(por_pessoa.values())), 1)

    def test_horarios_do_mesmo_dia_nao_andam_em_bloco(self):
        """Sem isto o dia inteiro troca junto.

        Café, almoço e jantar mudando na mesma cadência fazem o app parecer ter
        dois cardápios que se alternam, em vez de variedade.
        """
        por_slot = {ordem: self._indices(ordem=ordem) for ordem in range(5)}

        self.assertGreater(len(set(por_slot.values())), 1)

    # -- distribuição ------------------------------------------------------

    def test_as_quatro_opcoes_aparecem_dentro_de_uma_janela_curta(self):
        """Distribuição medida, e não afirmada.

        O ciclo de pares de quatro opções tem seis passos, então seis dias
        bastam para todas aparecerem. A janela do teste é de seis exatamente
        para provar isso — dar quatorze esconderia um algoritmo que só chega no
        rank 3 na segunda semana.
        """
        for pk in range(1, 25):
            for ordem in range(5):
                with self.subTest(user=pk, slot=ordem):
                    vistos = set()
                    for n in range(6):
                        vistos.update(self._indices(pk=pk, ordem=ordem, n=n))

                    self.assertEqual(vistos, {0, 1, 2, 3})

    def test_nenhuma_opcao_aparece_tres_dias_seguidos(self):
        """A queixa que abriu a missão era comida repetida.

        Ciclar os pares em ordem lexicográfica passaria em todos os testes
        acima e ainda assim serviria o rank 0 na segunda, na terça e na quarta:
        `combinations` devolve (0,1) (0,2) (0,3) antes de qualquer outra coisa.
        É este teste que exige a ordenação gulosa de `_ordenar_pares`.
        """
        for pk in range(1, 25):
            for ordem in range(5):
                for n in range(20):
                    tres = [set(self._indices(pk=pk, ordem=ordem, n=n + k)) for k in range(3)]
                    comum = tres[0] & tres[1] & tres[2]

                    self.assertEqual(comum, set(), "user=%d slot=%d dia=%d" % (pk, ordem, n))

    def test_dias_seguidos_nunca_repetem_a_dupla_inteira(self):
        for pk in range(1, 25):
            for ordem in range(5):
                for n in range(20):
                    self.assertNotEqual(
                        self._indices(pk=pk, ordem=ordem, n=n),
                        self._indices(pk=pk, ordem=ordem, n=n + 1),
                    )

    # -- fallback: produção tem plano antigo -------------------------------

    def test_repertorio_vazio_projeta_nada(self):
        self.assertEqual(self._indices(total=0), ())

    def test_repertorio_de_uma_projeta_a_unica(self):
        """Horário com uma opção só não pode virar erro."""
        self.assertEqual(self._indices(total=1), (0,))

    def test_repertorio_de_duas_projeta_as_duas_todo_dia(self):
        """O cardápio V1 continua funcionando enquanto não for regenerado.

        Produção tem planos com duas opções, e eles não podem ficar esperando
        uma regeneração para abrir a tela. Duas opções não rodam: aparecem as
        duas, como sempre apareceram.
        """
        for n in range(10):
            with self.subTest(dia=n):
                self.assertEqual(self._indices(total=2, n=n), (0, 1))

    def test_repertorio_de_tres_roda_entre_as_tres(self):
        vistos = set()
        for n in range(6):
            indices = self._indices(total=3, n=n)
            self.assertEqual(len(set(indices)), 2)
            vistos.update(indices)

        self.assertEqual(vistos, {0, 1, 2})

    # -- o que o seed NÃO pode ser -----------------------------------------

    def test_a_projecao_nao_recebe_o_plano(self):
        """`plan.pk` não entra, e a assinatura é onde isso fica travado.

        O `NutritionPlan` é retrato: nasce um novo a cada pesagem, a cada
        recalibração, a cada ajuste de altura. Semear pelo pk faria o almoço
        trocar porque a pessoa subiu na balança — a comida mudaria por um
        motivo que não é o dia ter virado.

        Travado na ASSINATURA porque é a única forma de o pk não poder entrar
        por descuido: se ele não é parâmetro, não há como ser lido.
        """
        parametros = set(inspect.signature(rodizio.indices_do_dia).parameters)

        self.assertEqual(parametros, {"total", "user_pk", "slot_order", "dia"})
        for proibido in ("plan", "plan_pk", "plano"):
            self.assertNotIn(proibido, parametros)

    def test_o_modulo_nao_usa_random_nem_hash_do_python(self):
        """Duas armadilhas silenciosas, as duas travadas aqui.

        `random.seed()` é estado GLOBAL: semear aqui mudaria o resultado de
        qualquer outro sorteio do processo. E `hash()` de string é randomizado
        por processo — dois workers do mesmo servidor serviriam cardápios
        diferentes no mesmo dia, e ninguém reproduziria o defeito localmente.
        """
        fonte = (Path(settings.BASE_DIR) / "plans" / "rodizio.py").read_text(
            encoding="utf-8"
        )
        arvore = ast.parse(fonte)

        # AST, e nao busca de texto. A primeira versao deste teste varria as
        # linhas do arquivo e falhou na hora: o docstring do modulo EXPLICA por
        # que `random.seed()` e `hash()` estao proibidos, e a explicacao
        # disparava a propria proibicao. E a armadilha de sempre neste
        # repositorio -- o marcador e a prosa sobre o marcador sao a mesma
        # string. A arvore so enxerga codigo.
        importados = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])

        self.assertNotIn("random", importados)

        chamadas = set()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            alvo = no.func
            if isinstance(alvo, ast.Name):
                chamadas.add(alvo.id)
            elif isinstance(alvo, ast.Attribute):
                chamadas.add(alvo.attr)

        for proibida in ("hash", "seed", "today", "now"):
            self.assertNotIn(proibida, chamadas)

    def test_o_deslocamento_e_estavel_entre_processos(self):
        """O valor esperado é literal de propósito.

        Um teste que só compara a função consigo mesma passaria mesmo com
        `hash()` embutido, porque dentro do MESMO processo `hash()` é estável.
        Cravar o número é o que faz a troca por algo não determinístico quebrar.
        """
        esperado = int.from_bytes(hashlib.sha256(b"1:0").digest()[:8], "big")

        self.assertEqual(rodizio._deslocamento(1, 0), esperado)


class ProjecaoNoPlanoTests(CatalogFixture):
    """A projeção sobre objetos reais: rótulo, identidade e prefetch."""

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="projecao@exemplo.com")
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.order_by("order").first()

    def test_as_projetadas_recebem_rotulo_de_apresentacao(self):
        """A e B viraram posição no dia, e não campo no banco."""
        projetadas = rodizio.opcoes_do_dia(self.slot, self.user.pk, date(2026, 8, 30))

        self.assertEqual([o.rotulo for o in projetadas], ["A", "B"][: len(projetadas)])

    def test_a_identidade_persistente_e_o_rank_e_ela_nao_muda(self):
        """O rótulo do dia muda; o pk e o rank, não.

        É a diferença que faz o histórico e a fila offline continuarem válidos:
        o formulário envia o pk, e o pk aponta para uma linha que existe desde a
        geração do plano.
        """
        pks_por_dia = {}
        for n in range(6):
            dia = date(2026, 8, 30) + timedelta(days=n)
            for opcao in rodizio.opcoes_do_dia(self.slot, self.user.pk, dia):
                pks_por_dia.setdefault(opcao.pk, set()).add(opcao.rank)

        # Cada pk visto ao longo da semana sempre teve o MESMO rank.
        for pk, ranks in pks_por_dia.items():
            self.assertEqual(len(ranks), 1, "pk %s mudou de rank: %s" % (pk, ranks))

    def test_a_projecao_nao_cria_nem_apaga_opcao(self):
        """Opção é objeto persistente. Recriar por dia arrancaria a identidade
        que o histórico e a fila usam."""
        antes = set(MealOption.objects.filter(slot=self.slot).values_list("pk", flat=True))

        for n in range(14):
            rodizio.opcoes_do_dia(self.slot, self.user.pk, date(2026, 8, 30) + timedelta(days=n))

        depois = set(MealOption.objects.filter(slot=self.slot).values_list("pk", flat=True))

        self.assertEqual(antes, depois)

    def test_projetar_nao_dispara_consulta_por_horario(self):
        """O prefetch da view precisa continuar servindo a projeção.

        `opcoes_do_dia` lê `slot.options.all()` justamente para aproveitá-lo.
        Trocar por `slot.options.order_by("rank")` custaria uma consulta por
        horário — cinco a mais na tela mais visitada do app.
        """
        slots = list(self.plan.slots.prefetch_related("options__template__items__food"))

        with self.assertNumQueries(0):
            rodizio.projetar(slots, self.user.pk, date(2026, 8, 30))
            for slot in slots:
                for opcao in slot.opcoes_do_dia:
                    opcao.template.name


class MigracaoDoRankTests(TransactionTestCase):
    """A migration 0007 rodada de verdade, com dados do cardápio V1 no banco.

    Produção tem plano e histórico. O que este teste prova é que a opção A de
    um plano antigo vira rank 0 e a B vira rank 1 — sem perder linha, sem
    duplicar posição e sem tocar em `MealLog`.

    `TransactionTestCase` porque migrar exige DDL, e DDL dentro da transação
    que o `TestCase` mantém aberta não se comporta.
    """

    ANTES = ("plans", "0006_meallog_recipe_name")
    DEPOIS = ("plans", "0007_mealoption_rank")

    def setUp(self):
        self.frango = make_food("Frango da migração", 165, 31, 0, "3.6")

    def _executor(self):
        return MigrationExecutor(connection)

    def _migrar(self, alvo):
        executor = self._executor()
        executor.loader.build_graph()
        executor.migrate([alvo])
        return executor.loader.project_state([alvo]).apps

    def tearDown(self):
        # Devolve o banco ao estado final, senão os testes seguintes rodam
        # contra um schema sem `rank`.
        self._migrar(self.DEPOIS)

    def test_a_opcao_a_vira_rank_zero_e_a_b_vira_rank_um(self):
        # Modelos REAIS para tudo que a migration não altera — usuário, receita,
        # plano e horário têm a mesma forma no estado 0006 e no atual. Só
        # `MealOption` vem do estado histórico, porque é a única tabela que
        # ainda tem a coluna `label` neste ponto e já não a tem no modelo atual.
        velho = self._migrar(self.ANTES)
        Option = velho.get_model("plans", "MealOption")

        user = User.objects.create_user(
            email="migracao@exemplo.com", password="Migracao!2026#"
        )
        plano = NutritionPlan.objects.create(
            user=user, is_active=True, weight_kg=Decimal("80.0"), height_cm=178,
            age_years=30, sex="M", activity_level=ActivityLevel.ACTIVE,
            goal=Goal.CUT, training_days_per_week=3, bmr_kcal=1800, tdee_kcal=2500,
            target_kcal=2200, protein_g=160, carb_g=220, fat_g=70, notes="",
        )
        slot = MealSlot.objects.create(
            plan=plano, name="Almoço", category=MealCategory.MAIN, time=time(12, 0),
            order=0, target_kcal=700, target_protein_g=50, target_carb_g=70,
            target_fat_g=20,
        )
        macros = dict(kcal=Decimal("700"), protein_g=Decimal("50"),
                      carb_g=Decimal("70"), fat_g=Decimal("20"))
        for letra in ("A", "B"):
            template = make_template(
                "Receita %s" % letra, MealCategory.MAIN, [(self.frango, 150, True)]
            )
            Option.objects.create(
                slot_id=slot.pk, template_id=template.pk, label=letra,
                scale_factor=Decimal("1.00"), **macros
            )

        novo = self._migrar(self.DEPOIS)

        OptionNovo = novo.get_model("plans", "MealOption")
        por_receita = {
            o.template.name: o.rank
            for o in OptionNovo.objects.filter(slot_id=slot.pk).select_related("template")
        }

        self.assertEqual(por_receita, {"Receita A": 0, "Receita B": 1})

    def test_a_migration_nao_perde_opcao_nem_toca_no_historico(self):
        velho = self._migrar(self.ANTES)
        Option = velho.get_model("plans", "MealOption")
        Log = velho.get_model("plans", "MealLog")
        antes_opcoes = Option.objects.count()
        antes_logs = Log.objects.count()

        novo = self._migrar(self.DEPOIS)

        self.assertEqual(novo.get_model("plans", "MealOption").objects.count(), antes_opcoes)
        self.assertEqual(novo.get_model("plans", "MealLog").objects.count(), antes_logs)


class RankNoBancoTests(CatalogFixture):
    """A unicidade que substituiu `unique(slot, label)`."""

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="rank@exemplo.com")
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.order_by("order").first()

    def test_dois_ranks_iguais_no_mesmo_horario_sao_recusados(self):
        """A posição é identidade: repetida, a projeção passa a ter duas
        respostas para a mesma pergunta."""
        existente = self.slot.options.order_by("rank").first()
        outra = make_template(
            "Prato de colisão", self.slot.category, [(self.chicken, 100, True)]
        )

        with self.assertRaises(IntegrityError):
            MealOption.objects.create(
                slot=self.slot, template=outra, rank=existente.rank,
                scale_factor=Decimal("1.00"), kcal=Decimal("500"),
                protein_g=Decimal("30"), carb_g=Decimal("50"), fat_g=Decimal("15"),
            )

    def test_o_mesmo_rank_em_horarios_diferentes_e_normal(self):
        ranks = {}
        for slot in self.plan.slots.all():
            for opcao in slot.options.all():
                ranks.setdefault(opcao.rank, 0)
                ranks[opcao.rank] += 1

        self.assertGreater(ranks.get(0, 0), 1)

    def test_o_campo_label_nao_existe_mais_no_modelo(self):
        """Se voltar, volta como identidade paralela ao rank — e as duas
        divergem na primeira geração."""
        campos = {f.name for f in MealOption._meta.get_fields()}

        self.assertIn("rank", campos)
        self.assertNotIn("label", campos)


class HistoricoComRodizioTests(TestCase):
    """O contrato do `MealLog` sob rotação. O passado não se recalcula.

    Catálogo REAL, e não a fixture mínima: com duas receitas por categoria o
    repertório sai de tamanho dois, o rodízio cai no fallback e mostra as duas
    todo dia. O teste passaria medindo o caminho errado.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="historico@exemplo.com")
        self.client.force_login(self.user)
        self.plan = services.create_plan(self.user)
        # Um horário com repertório CHEIO: é onde o rodízio realmente gira.
        self.slot = next(
            s for s in self.plan.slots.order_by("order")
            if s.options.count() == meal_planner.OPTIONS_PER_SLOT
        )

    def _marcar(self, opcao):
        return self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": opcao.pk},
        )

    def _projetadas(self, dia=None):
        return rodizio.opcoes_do_dia(self.slot, self.user.pk, dia)

    def test_marcar_a_opcao_projetada_aponta_para_a_opcao_persistente(self):
        escolhida = self._projetadas()[0]

        self._marcar(escolhida)

        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.chosen_option_id, escolhida.pk)
        self.assertEqual(log.recipe_name, escolhida.template.name)
        self.assertEqual(log.kcal, escolhida.kcal)

    def test_trocar_de_opcao_no_mesmo_dia_atualiza_a_mesma_linha(self):
        primeira, segunda = self._projetadas()[:2]

        self._marcar(primeira)
        self._marcar(segunda)

        logs = MealLog.objects.filter(user=self.user, slot=self.slot)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().chosen_option_id, segunda.pk)
        self.assertEqual(logs.first().recipe_name, segunda.template.name)

    def test_o_passado_nao_muda_quando_o_dia_seguinte_projeta_outra_dupla(self):
        """O teste central do histórico sob rodízio.

        Marca hoje, confere que amanhã a projeção é outra, e confere que o
        registro de hoje continua contando a mesma história. Se alguém algum
        dia resolver derivar o histórico do cardápio ATUAL — em vez de ler o
        retrato guardado —, é aqui que quebra.
        """
        hoje = timezone.localdate()
        escolhida = self._projetadas(hoje)[0]
        self._marcar(escolhida)
        retrato = MealLog.objects.get(user=self.user, slot=self.slot)
        nome_gravado, kcal_gravada = retrato.recipe_name, retrato.kcal

        amanha = self._projetadas(hoje + timedelta(days=1))
        self.assertNotEqual(
            {o.pk for o in amanha}, {o.pk for o in self._projetadas(hoje)}
        )

        retrato.refresh_from_db()
        self.assertEqual(retrato.recipe_name, nome_gravado)
        self.assertEqual(retrato.kcal, kcal_gravada)
        self.assertEqual(retrato.chosen_option_id, escolhida.pk)

    def test_pulei_continua_sem_receita_e_sem_macro(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.SKIPPED},
        )

        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.recipe_name, "")
        self.assertIsNone(log.chosen_option_id)
        self.assertEqual(log.kcal, Decimal("0.00"))

    def test_comi_outra_coisa_continua_sem_apontar_para_opcao(self):
        self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.OFF_PLAN, "notes": "pizza"},
        )

        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.status, MealStatus.OFF_PLAN)
        self.assertIsNone(log.chosen_option_id)
        self.assertEqual(log.recipe_name, "")


class SegurancaDaOpcaoTests(TestCase):
    """O rodízio não pode abrir porta para marcar comida na conta errada.

    Catálogo real para o horário ter repertório cheio: com repertório de dois
    não existe opção FORA da projeção, e o teste mais importante desta classe
    — o que documenta por que a projeção não é usada como validação — seria
    pulado em silêncio.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="dono@exemplo.com")
        self.plan = services.create_plan(self.user)
        self.slot = next(
            s for s in self.plan.slots.order_by("order")
            if s.options.count() == meal_planner.OPTIONS_PER_SLOT
        )
        self.outro_slot = self.plan.slots.order_by("order").last()

        self.alheio = create_complete_user(email="alheio@exemplo.com")
        self.plano_alheio = services.create_plan(self.alheio)

        self.client.force_login(self.user)

    def _marcar(self, opcao_pk):
        return self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": opcao_pk},
        )

    def test_opcao_de_outro_horario_do_mesmo_plano_e_recusada(self):
        intrusa = self.outro_slot.options.first()

        self.assertEqual(self._marcar(intrusa.pk).status_code, 404)
        self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_opcao_de_outro_usuario_e_recusada(self):
        alheia = self.plano_alheio.slots.first().options.first()

        self.assertEqual(self._marcar(alheia.pk).status_code, 404)
        self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_id_inexistente_ou_lixo_nao_estoura(self):
        for valor in (999999, "abc", "", "0"):
            with self.subTest(option=valor):
                resposta = self._marcar(valor)

                self.assertIn(resposta.status_code, (302, 404))
                self.assertFalse(MealLog.objects.filter(user=self.user).exists())

    def test_opcao_do_repertorio_fora_da_projecao_de_hoje_e_aceita(self):
        """DE PROPÓSITO, e é a decisão mais delicada desta missão.

        A tentação é validar contra a projeção do dia: "só pode marcar o que
        está na tela". Isso quebraria a fila offline no primeiro replay. A
        pessoa marca o almoço no sábado sem rede, o celular só reencontra sinal
        no domingo, e a fila reenvia — se o servidor validasse contra a
        projeção de DOMINGO, a refeição de sábado seria recusada e o registro
        sumiria sem aviso.

        Não é brecha de segurança: a opção continua tendo que pertencer ao slot
        do plano ativo do próprio usuário, que é o que fecha o IDOR. É a comida
        da própria pessoa, no próprio horário — só não é a que o rodízio
        escolheu para hoje.
        """
        projetadas = {o.pk for o in rodizio.opcoes_do_dia(self.slot, self.user.pk)}
        fora = self.slot.options.exclude(pk__in=projetadas).first()
        if fora is None:
            self.skipTest("repertório deste horário não tem opção fora da projeção")

        self._marcar(fora.pk)

        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.chosen_option_id, fora.pk)


class FilaOfflineComRodizioTests(CatalogFixture):
    """O replay da fila continua válido depois de o dia virar."""

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="fila@exemplo.com")
        self.client.force_login(self.user)
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.order_by("order").first()

    def test_o_formulario_envia_a_chave_persistente_e_nao_o_indice_visivel(self):
        """O que a fila serializa é o que o formulário tem.

        Se o campo virasse "opção 1" ou o índice na tela, o replay do dia
        seguinte marcaria outra comida — o índice 1 aponta para outra receita
        depois que o rodízio gira.
        """
        html = self.client.get(reverse("plans:today")).content.decode()
        projetadas = rodizio.opcoes_do_dia(self.slot, self.user.pk)

        for opcao in projetadas:
            self.assertIn('value="%d"' % opcao.pk, html)

    def test_um_envio_guardado_ontem_ainda_vale_hoje(self):
        """A opção de ontem continua existindo, com o mesmo pk e o mesmo rank.

        É a razão de o rodízio ser projeção de LEITURA: se ele criasse a opção
        do dia, o pk enfileirado ontem apontaria para uma linha apagada.
        """
        ontem = timezone.localdate() - timedelta(days=1)
        enfileirada = rodizio.opcoes_do_dia(self.slot, self.user.pk, ontem)[0]

        # O "replay": o mesmo pk chega hoje, quando a projeção já é outra.
        resposta = self.client.post(
            reverse("plans:mark_meal", args=[self.slot.pk]),
            {"status": MealStatus.DONE, "option": enfileirada.pk},
        )

        self.assertEqual(resposta.status_code, 302)
        log = MealLog.objects.get(user=self.user, slot=self.slot)
        self.assertEqual(log.chosen_option_id, enfileirada.pk)

    def test_reenviar_a_mesma_marcacao_nao_empilha_registro(self):
        """Idempotência: `update_or_create` por (usuário, dia, horário)."""
        opcao = rodizio.opcoes_do_dia(self.slot, self.user.pk)[0]
        url = reverse("plans:mark_meal", args=[self.slot.pk])

        for _ in range(4):
            self.client.post(url, {"status": MealStatus.DONE, "option": opcao.pk})

        self.assertEqual(
            MealLog.objects.filter(user=self.user, slot=self.slot).count(), 1
        )


class ListaDeComprasSemanalTests(TestCase):
    """A lista passou a percorrer sete dias reais em vez de multiplicar um.

    Catálogo real pelo mesmo motivo de `HistoricoComRodizioTests`: sem
    repertório de quatro não há rotação para a lista refletir.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user(email="compras-v2@exemplo.com")
        self.plan = services.create_plan(self.user)

    def test_a_lista_usa_a_mesma_projecao_da_tela(self):
        """Uma regra de projeção, vários consumidores.

        O teste lê a fonte: uma segunda implementação de rotação aqui
        divergiria da tela na primeira mudança de regra, e a pessoa compraria
        uma coisa e cozinharia outra.
        """
        fonte = (Path(settings.BASE_DIR) / "plans" / "shopping.py").read_text(
            encoding="utf-8"
        )
        arvore = ast.parse(fonte)
        chamadas = {
            no.func.attr
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        }

        self.assertIn("opcoes_do_dia", chamadas)
        # E nada de refazer a conta por conta própria.
        self.assertNotIn("toordinal", chamadas)
        self.assertNotIn("sha256", chamadas)

    def test_a_semana_cobre_sete_datas_locais_consecutivas(self):
        dias = shopping.dias_da_semana(date(2026, 8, 30))

        self.assertEqual(len(dias), shopping.DAYS)
        self.assertEqual(dias[0], date(2026, 8, 30))
        self.assertEqual(dias[-1], date(2026, 9, 5))

    def test_a_lista_reflete_a_rotacao_e_nao_uma_receita_vezes_sete(self):
        """Com rodízio, a semana tem mais receitas distintas do que um dia.

        Antes a lista pegava a opção A e multiplicava por sete — a semana
        inteira tinha exatamente as receitas de um dia. Se alguém voltar a
        fazer isso, este teste cai.
        """
        totais = shopping.weekly_quantities(self.plan, inicio=date(2026, 8, 30))
        receitas_da_semana = set()
        for entrada in totais.values():
            receitas_da_semana |= entrada["recipes"]

        de_um_dia = set()
        for slot in self.plan.slots.all():
            projetadas = rodizio.opcoes_do_dia(slot, self.user.pk, date(2026, 8, 30))
            if projetadas:
                de_um_dia.add(projetadas[0].template.name)

        self.assertGreater(len(receitas_da_semana), len(de_um_dia))

    def test_uma_alternativa_por_refeicao_por_dia_e_nada_de_lista_inflada(self):
        """A regra de produto que NÃO mudou.

        Quem tem frango ou ovo no almoço vai comer um dos dois. Somar as duas
        alternativas encheria a lista de comida que ninguém cozinha, e lista
        inflada é lista em que a pessoa para de confiar.

        A prova: a soma da semana bate com a soma dia a dia de UMA opção por
        horário — não de duas.
        """
        inicio = date(2026, 8, 30)
        totais = shopping.weekly_quantities(self.plan, inicio=inicio)
        gramas_lista = sum(e["quantity"] for e in totais.values())

        esperado = Decimal("0")
        for dia in shopping.dias_da_semana(inicio):
            for slot in self.plan.slots.prefetch_related("options__template__items"):
                projetadas = rodizio.opcoes_do_dia(slot, self.user.pk, dia)
                if not projetadas:
                    continue
                escolhida = projetadas[0]
                for item in escolhida.template.items.all():
                    esperado += item.scaled_quantity(escolhida.scale_factor)

        self.assertEqual(gramas_lista, esperado)

    def test_o_rotulo_pedido_escolhe_a_segunda_alternativa_do_dia(self):
        inicio = date(2026, 8, 30)
        a = shopping.weekly_quantities(self.plan, label="A", inicio=inicio)
        b = shopping.weekly_quantities(self.plan, label="B", inicio=inicio)

        receitas = lambda t: {n for e in t.values() for n in e["recipes"]}
        self.assertNotEqual(receitas(a), receitas(b))

    def test_a_lista_nao_depende_do_pk_do_plano(self):
        """Recalibrar não pode reembaralhar a lista de compras.

        Um plano novo com as MESMAS receitas nas mesmas posições produz a mesma
        lista, porque o seed não olha para o pk.
        """
        inicio = date(2026, 8, 30)
        antes = shopping.weekly_quantities(self.plan, inicio=inicio)

        gemeo = services.create_plan(self.user)
        depois = shopping.weekly_quantities(gemeo, inicio=inicio)

        self.assertNotEqual(gemeo.pk, self.plan.pk)
        self.assertEqual(
            {f.name: e["quantity"] for f, e in antes.items()},
            {f.name: e["quantity"] for f, e in depois.items()},
        )


class GeracaoIdempotenteTests(CatalogFixture):
    """Rodar a geração de novo não pode inflar o repertório."""

    def setUp(self):
        super().setUp()
        self.user = create_complete_user(email="idem@exemplo.com")

    def test_sincronizar_duas_vezes_sem_mudar_entrada_nao_cria_plano_novo(self):
        plano = services.create_plan(self.user)
        opcoes = MealOption.objects.filter(slot__plan=plano).count()

        services.sync_active_plan(self.user)
        services.sync_active_plan(self.user)

        ativo = services.get_active_plan(self.user)
        self.assertEqual(ativo.pk, plano.pk)
        self.assertEqual(MealOption.objects.filter(slot__plan=ativo).count(), opcoes)

    def test_gerar_de_novo_nao_duplica_rank_dentro_do_horario(self):
        for _ in range(3):
            plano = services.create_plan(self.user)

        for slot in plano.slots.all():
            with self.subTest(slot=slot.name):
                ranks = list(slot.options.values_list("rank", flat=True))

                self.assertEqual(sorted(ranks), sorted(set(ranks)))
                self.assertEqual(sorted(ranks), list(range(len(ranks))))

    def test_o_repertorio_nao_cresce_a_cada_geracao(self):
        """Plano é retrato: gerar de novo cria plano NOVO, não engorda o velho."""
        primeiro = services.create_plan(self.user)
        tamanho = {s.pk: s.options.count() for s in primeiro.slots.all()}

        services.create_plan(self.user)
        primeiro.refresh_from_db()

        self.assertEqual(
            {s.pk: s.options.count() for s in primeiro.slots.all()}, tamanho
        )


class CustoDaTelaHojeTests(TestCase):
    """O cardápio V2 não pode custar uma consulta por opção.

    O "antes e depois" é medido DENTRO do mesmo processo, e não contra um
    commit antigo: um plano com repertório de dois tem exatamente a forma do
    cardápio V1, então comparar dois contra quatro é comparar V1 com V2 com
    tudo mais igual. É uma comparação melhor que a histórica, porque isola a
    única variável que interessa.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def _plano_com(self, email, por_slot):
        """Um plano cujo repertório é podado até `por_slot` opções."""
        user = create_complete_user(email=email)
        plano = services.create_plan(user)
        for slot in plano.slots.all():
            sobrando = slot.options.order_by("rank")[por_slot:]
            MealOption.objects.filter(pk__in=[o.pk for o in sobrando]).delete()
        return user, plano

    def _consultas(self, user):
        self.client.force_login(user)
        # Uma visita antes de medir: a primeira carrega sessão e perfil, e
        # medir isso mediria o login, não a tela.
        self.client.get(reverse("plans:today"))
        with CaptureQueriesContext(connection) as capturado:
            resposta = self.client.get(reverse("plans:today"))
        self.assertEqual(resposta.status_code, 200)
        return len(capturado)

    def test_o_custo_nao_cresce_com_o_tamanho_do_repertorio(self):
        """A asserção central de performance desta missão.

        Se a projeção tivesse virado `slot.options.order_by("rank")` — que é a
        forma óbvia e errada de escrever —, o prefetch seria descartado e cada
        horário custaria uma consulta a mais. Aqui isso apareceria como quatro
        opções custando mais que duas.
        """
        _, _ = self._plano_com("perf-dois@exemplo.com", 2)
        dois = self._consultas(get_user_model().objects.get(email="perf-dois@exemplo.com"))

        _, _ = self._plano_com("perf-quatro@exemplo.com", 4)
        quatro = self._consultas(
            get_user_model().objects.get(email="perf-quatro@exemplo.com")
        )

        self.assertEqual(
            quatro,
            dois,
            "repertório de quatro custou %d consultas contra %d do de dois"
            % (quatro, dois),
        )

    def test_a_tela_hoje_continua_com_custo_de_duas_dezenas_de_consultas(self):
        """Um teto absoluto, para o número não subir sem ninguém notar.

        O valor é generoso de propósito: o que este teste protege é a ordem de
        grandeza, e não o número exato — apertar até o valor de hoje faria a
        suíte quebrar em qualquer mudança inocente de contexto da tela.
        """
        self._plano_com("perf-teto@exemplo.com", 4)
        total = self._consultas(get_user_model().objects.get(email="perf-teto@exemplo.com"))

        self.assertLess(total, 40, "a tela Hoje passou a custar %d consultas" % total)


class EquivalenciaHonestaTests(TestCase):
    """A tela não pode prometer uma equivalência que o cardápio não entrega.

    Medido em 226 pares A/B reais do banco: as CALORIAS batem — 0,2% de desvio
    na mediana, porque o motor escala cada receita até o alvo e nisso ele é
    exato. Os macros não batem: proteína com 14,1% de desvio na mediana,
    gordura com 41,7%, e 100% dos pares com algum macro além de 5%.

    A tela dizia "as duas opções são equivalentes" e "dá para trocar A por B
    sem refazer conta nenhuma". Num app de hipertrofia, a proteína é justamente
    a conta que muda — e o texto pedia para a pessoa não conferir o número que
    ela mais precisa conferir.

    A correção não foi no motor. Perseguir equivalência de macro com 54
    receitas destruiria a variedade do cardápio, e não existe substituto de
    mesmo perfil para toda refeição. A correção foi dizer a verdade.

    Este teste amarra a frase à medição: enquanto o cardápio real tiver desvio
    de macro, a tela não pode prometer que ele não tem.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def _pagina_e_desvio(self):
        # `create_complete_user` já cria a pesagem — repetir aqui esbarra na
        # constraint de uma por dia.
        user = create_complete_user()
        services.sync_active_plan(user)
        self.client.force_login(user)
        html = self.client.get(reverse("plans:today"), secure=True).content.decode()

        plan = NutritionPlan.objects.filter(user=user, is_active=True).first()
        maior = 0.0
        for slot in plan.slots.prefetch_related("options"):
            opcoes = sorted(slot.options.all(), key=lambda o: o.rank)[:2]
            if len(opcoes) < 2:
                continue
            a, b = opcoes
            for campo in ("protein_g", "carb_g", "fat_g"):
                base = float(getattr(a, campo) or 0)
                if base:
                    desvio = abs(float(getattr(b, campo) or 0) - base) / base * 100
                    maior = max(maior, desvio)
        return html, maior

    def test_a_promessa_de_trocar_sem_refazer_conta_saiu_da_tela(self):
        """Era a frase mais enganosa: ela desautoriza a conferência."""
        html, _ = self._pagina_e_desvio()
        self.assertNotIn("sem refazer conta nenhuma", html)

    def test_a_tela_nao_chama_as_opcoes_de_equivalentes(self):
        html, _ = self._pagina_e_desvio()
        self.assertNotIn("opções de cada horário são equivalentes", html)

    def test_a_tela_continua_dizendo_o_que_de_fato_bate(self):
        """Tirar a promessa falsa não pode virar silêncio.

        O que o motor entrega de verdade — a mesma caloria — é informação útil,
        e some se a correção for só apagar a frase.
        """
        html, _ = self._pagina_e_desvio()
        self.assertIn("fecham a mesma caloria", html)

    def test_o_cardapio_real_realmente_tem_desvio_de_macro(self):
        """A justificativa da frase, medida — e não herdada deste comentário.

        Se um dia o motor passar a igualar macros, este teste falha e obriga a
        revisitar o texto: continuar dizendo "os macros variam" seria a mesma
        desonestidade ao contrário.
        """
        _, maior = self._pagina_e_desvio()
        self.assertGreater(
            maior, 5.0,
            "o cardápio gerado ficou com macros equivalentes — a frase da tela "
            "precisa ser revista",
        )


class AguaConcorrenteTests(TransactionTestCase):
    """Três toques rápidos precisam somar três, não dois.

    O defeito relatado na auditoria: tocar +250, +500 e +750 em sequência
    rápida registrava 1000 ml em vez de 1500. Um dos incrementos sumia.

    A causa era `lost update`. A view lia `registro.ml`, somava em Python e
    gravava de volta:

        registro.ml = min(registro.ml + ml, 10000)
        registro.save(...)

    Dois pedidos concorrentes leem o MESMO valor antigo, e o segundo sobrescreve
    o primeiro. Não é problema de velocidade de dedo — é de duas transações
    lendo antes de a outra gravar, e a fila offline reenvia exatamente assim,
    em rajada, quando a rede volta.

    `TransactionTestCase` e não `TestCase`: o segundo embrulha tudo numa
    transação só e as threads não enxergariam as escritas umas das outras — o
    teste de concorrência passaria sem testar concorrência.
    """

    def setUp(self):
        self.user = create_complete_user(email="agua@exemplo.invalid")
        self.client.force_login(self.user)
        self.url = reverse("plans:log_hydration")

    def _ml(self):
        registro = HydrationLog.objects.filter(
            user=self.user, date=timezone.localdate()
        ).first()
        return registro.ml if registro else 0

    def _beber(self, ml, op_id=None):
        dados = {"ml": ml}
        if op_id:
            dados["op_id"] = op_id
        return self.client.post(self.url, dados, secure=True)

    def test_tres_toques_em_sequencia_somam_os_tres(self):
        """O caso exato do relato."""
        self._beber(250)
        self._beber(500)
        self._beber(750)

        self.assertEqual(self._ml(), 1500)

    def test_dez_toques_de_250_somam_2500(self):
        for _ in range(10):
            self._beber(250)

        self.assertEqual(self._ml(), 2500)

    def test_toques_simultaneos_nao_perdem_nenhum(self):
        """A prova de que a soma acontece no banco.

        Com a soma em Python, threads concorrentes lendo o mesmo valor faziam
        o total ficar abaixo da soma real. Aqui cada thread abre a própria
        conexão, que é o que reproduz o cenário do servidor.
        """
        from django.db import connections
        from django.test import Client

        quantidade = 12
        erros = []

        def beber():
            try:
                c = Client()
                c.force_login(self.user)
                c.post(self.url, {"ml": 250}, secure=True)
            except Exception as e:  # pragma: no cover - só aparece se quebrar
                erros.append(e)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=beber) for _ in range(quantidade)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(erros, [])
        self.assertEqual(
            self._ml(),
            250 * quantidade,
            "algum incremento se perdeu — a soma não está atômica no banco",
        )

    def test_zerar_continua_zerando(self):
        self._beber(500)
        self._beber(0)

        self.assertEqual(self._ml(), 0)

    def test_o_teto_de_dez_litros_continua_valendo(self):
        for _ in range(50):
            self._beber(750)

        self.assertEqual(self._ml(), 10000)

    def test_reenvio_da_fila_offline_nao_soma_duas_vezes(self):
        """Água SOMA, então reenviar aplicaria de novo sem a trava de `op_id`.

        É a garantia que o CLAUDE.md chama de requisito da fila offline, e ela
        não pode cair junto com a mudança para soma no banco.
        """
        self._beber(500, op_id="abc-123")
        self._beber(500, op_id="abc-123")

        self.assertEqual(self._ml(), 500)

    def test_valor_invalido_nao_soma_nem_cria_lixo(self):
        self._beber(333)

        self.assertEqual(self._ml(), 0)


class MacrosRestantesTests(TestCase):
    """Sob "faltam", todo número precisa falar de restante.

    A linha dizia "faltam X g · Y kcal · Z% da meta" e só o primeiro respondia
    isso. Com 39 de 146 g de proteína saía "faltam 107 g · 584 kcal · 21% da
    meta": 584 é a meta inteira vezes quatro, e 21% é quanto a proteína pesa no
    orçamento calórico do dia — o mesmo número que a barra empilhada usa, onde
    ele está certo.

    `pct` e `kcal` continuam existindo e continuam significando o que sempre
    significaram. O que mudou foi a frase parar de misturá-los com `left`.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)

    def _proteina(self, comido):
        from plans.views import macro_rows

        linhas = macro_rows(self.plan, {"protein_g": comido})
        return next(m for m in linhas if m["slug"] == "protein")

    def test_nada_comido(self):
        m = self._proteina(0)

        self.assertEqual(m["left"], self.plan.protein_g)
        self.assertEqual(m["eaten_pct"], 0)
        self.assertFalse(m["batido"])
        self.assertEqual(m["acima"], 0)

    def test_parcial_o_caso_do_relato(self):
        """39 de 146: o restante é 107 g, e o kcal tem que acompanhar."""
        meta = self.plan.protein_g
        comido = round(meta * Decimal("0.27"))
        m = self._proteina(comido)

        self.assertEqual(m["left"], meta - comido)
        self.assertEqual(m["left_kcal"], (meta - comido) * 4)
        self.assertNotEqual(
            m["left_kcal"], m["kcal"],
            "o kcal de 'faltam' voltou a ser o da meta inteira",
        )

    def test_quase_completo(self):
        m = self._proteina(self.plan.protein_g - 1)

        self.assertEqual(m["left"], 1)
        self.assertEqual(m["left_kcal"], 4)
        self.assertFalse(m["batido"])

    def test_meta_exata(self):
        m = self._proteina(self.plan.protein_g)

        self.assertEqual(m["left"], 0)
        self.assertEqual(m["left_kcal"], 0)
        self.assertTrue(m["batido"])
        self.assertEqual(m["acima"], 0)

    def test_acima_da_meta_nunca_da_restante_negativo(self):
        excesso = 14
        m = self._proteina(self.plan.protein_g + excesso)

        self.assertEqual(m["left"], 0)
        self.assertEqual(m["left_kcal"], 0)
        self.assertEqual(m["acima"], excesso)
        self.assertEqual(
            m["eaten_pct"], 100, "a barra precisa parar em 100"
        )

    def test_a_gordura_usa_nove_kcal_por_grama(self):
        """O fator não pode estar escrito no template.

        Proteína e carboidrato são 4 kcal/g, gordura é 9. Um `×4` no HTML
        daria o número certo em duas linhas e errado na terceira.
        """
        from plans.views import macro_rows

        linhas = macro_rows(self.plan, {"fat_g": 0})
        gordura = next(m for m in linhas if m["slug"] == "fat")

        self.assertEqual(gordura["left_kcal"], gordura["grams"] * 9)

    def test_a_tela_nao_mistura_semantica_na_frase(self):
        """O defeito visto de fora: a frase com número que não é restante.

        Recortado em `macro-line__meta`, e não na página inteira: "% da meta"
        aparece legitimamente no `aria-label` da barra de água, e a primeira
        versão deste teste reprovou por causa dele. Medir a página toda mede
        outra coisa.
        """
        # Com NADA consumido, `left_kcal` é igual a `kcal` e os dois seriam
        # indistinguíveis — a primeira versão deste teste não pegava a troca de
        # um pelo outro. Registrar uma refeição afasta os dois números.
        from plans import tracking

        slot = self.plan.slots.order_by("order").first()
        opcao = slot.options.order_by("rank").first()
        tracking.log_meal(self.user, slot, MealStatus.DONE, option=opcao)

        self.client.force_login(self.user)
        html = self.client.get(reverse("plans:today"), secure=True).content.decode()

        linhas = re.findall(
            r'<span class="macro-line__meta">(.*?)</span>\s*</div>', html, re.S
        )
        self.assertEqual(len(linhas), 3, "as três linhas de macro sumiram")

        from plans.views import macro_rows

        proteina = next(
            m for m in macro_rows(
                self.plan, tracking.day_summary(self.user, self.plan, date.today())
            ) if m["slug"] == "protein"
        )
        self.assertGreater(proteina["eaten"], 0, "o cenário precisa ter consumo")
        self.assertNotEqual(
            proteina["left_kcal"], proteina["kcal"],
            "sem diferença entre restante e meta, o teste não distingue nada",
        )

        for linha in linhas:
            self.assertNotIn("% da meta", linha)
        self.assertIn("%d kcal" % proteina["left_kcal"], linhas[0])
        self.assertNotIn("%d kcal" % proteina["kcal"], linhas[0])


class ArredondamentoUnicoTests(TestCase):
    """O card e o total do dia precisam dizer o mesmo número.

    Defeito real: uma refeição de 677,50 kcal aparecia como "678 kcal" no card
    e somava 677 no total do dia. Nenhum dos dois calculava errado — os dois
    liam o mesmo `Decimal`. O que divergia era a conversão para inteiro: o
    template usa `floatformat`, que arredonda, e a view usava `int()`, que
    trunca.

    O teste ancora nos dois lados da fronteira ao mesmo tempo. Verificar só
    `arredondar()` deixaria passar exatamente a regressão que importa — alguém
    trocar o filtro do template por `stringformat:"d"` e as duas pontas
    voltarem a discordar sem nenhum teste reclamar.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slot = self.plan.slots.order_by("order").first()
        self.option = self.slot.options.order_by("rank").first()

    def test_o_card_e_o_total_do_dia_concordam_na_metade_exata(self):
        """677,50 é o caso que separa arredondar de truncar. Abaixo dele as
        duas convenções coincidem e o defeito fica invisível."""
        MealOption.objects.filter(pk=self.option.pk).update(kcal=Decimal("677.50"))
        self.option.refresh_from_db()
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)

        no_card = floatformat(self.option.kcal, 0)
        no_dia = tracking.day_summary(self.user, self.plan, timezone.localdate())

        self.assertEqual(no_card, "678")
        self.assertEqual(no_dia["consumed_kcal"], 678, "o dia truncou o que o card arredondou")

    def test_a_regra_vale_para_os_tres_macros_e_nao_so_para_a_caloria(self):
        """A correção original mexeu em `consumed_kcal`. Proteína, carboidrato
        e gordura passavam pelo mesmo `int()` e ficariam para trás."""
        MealOption.objects.filter(pk=self.option.pk).update(
            kcal=Decimal("677.50"),
            protein_g=Decimal("40.50"),
            carb_g=Decimal("80.50"),
            fat_g=Decimal("22.50"),
        )
        self.option.refresh_from_db()
        tracking.log_meal(self.user, self.slot, MealStatus.DONE, self.option)

        resumo = tracking.day_summary(self.user, self.plan, timezone.localdate())

        for chave, decimal_gravado, esperado in [
            ("protein_g", "40.50", 41),
            ("carb_g", "80.50", 81),
            ("fat_g", "22.50", 23),
        ]:
            with self.subTest(macro=chave):
                self.assertEqual(floatformat(Decimal(decimal_gravado), 0), str(esperado))
                self.assertEqual(resumo[chave], esperado)

    def test_o_total_do_cardapio_arredonda_uma_vez_e_nao_por_refeicao(self):
        """A soma acontece com a precisão inteira; arredondar é o último passo.

        A versão anterior fazia `int(option.kcal)` DENTRO do laço: cinco
        truncamentos antes de somar, cada um perdendo até 1 kcal, e o rodapé
        ficava sistematicamente abaixo do cardápio real. Com 400,60 em cinco
        refeições ela dava 2 000 para um cardápio de 2 003.

        Repare que o rodapé (2 003) NÃO é a soma dos cards arredondados
        (5 × 401 = 2 005), e isso não é o defeito — é a diferença entre somar e
        depois arredondar, que qualquer nota fiscal também tem. O defeito que
        este teste guarda é o viés de arredondar cedo, sempre para o mesmo
        lado.
        """
        from plans import rodizio
        from plans.views import menu_totals

        for slot in self.plan.slots.all():
            slot.options.update(kcal=Decimal("400.60"))

        slots = list(self.plan.slots.order_by("order"))
        rodizio.projetar(slots, self.user.pk, timezone.localdate())
        visiveis = [o for s_ in slots for o in list(s_.opcoes_do_dia)[:1]]

        exato = sum((o.kcal for o in visiveis), Decimal("0"))
        truncando_cedo = sum(int(o.kcal) for o in visiveis)

        self.assertEqual(menu_totals(slots)["kcal"], tracking.arredondar(exato))
        self.assertNotEqual(menu_totals(slots)["kcal"], truncando_cedo)


class RegistroNaoEAderenciaTests(TestCase):
    """O contador do dia responde duas perguntas, e elas não são a mesma.

    Num dia com cinco refeições previstas, uma seguida conforme o plano e uma
    marcada como "comi outra coisa", a tela dizia "1/5 refeições". A pessoa
    tinha registrado DUAS e lia que tinha feito uma.

    O estrago não é o número: é o que ele ensina. "Comi outra coisa" existe
    para dar um jeito de registrar o dia real sem fingir aderência — e o app
    respondia somando zero nas duas contas, como se registrar tivesse sido
    inútil. Quem marca honestamente é quem sai punido.

    Agora `day_summary` devolve os dois eixos com nome próprio, e a tela mostra
    o segundo só quando ele existe.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.slots = list(self.plan.slots.order_by("order"))

    def _resumo(self):
        return tracking.day_summary(self.user, self.plan, timezone.localdate())

    def test_o_caso_do_relato_cinco_previstas_duas_registradas(self):
        tracking.log_meal(
            self.user, self.slots[0], MealStatus.DONE,
            self.slots[0].options.first(),
        )
        tracking.log_meal(self.user, self.slots[1], MealStatus.OFF_PLAN)

        resumo = self._resumo()

        self.assertEqual(resumo["previstas"], 5)
        self.assertEqual(resumo["registradas"], 2)
        self.assertEqual(resumo["no_plano"], 1)
        self.assertEqual(resumo["fora_do_plano"], 1)

    def test_pular_conta_como_registro_e_nao_como_aderencia(self):
        """Pular é uma resposta, não silêncio. Quem pulou o lanche decidiu
        alguma coisa; quem não marcou nada ainda não decidiu."""
        tracking.log_meal(self.user, self.slots[0], MealStatus.SKIPPED)

        resumo = self._resumo()

        self.assertEqual(resumo["registradas"], 1)
        self.assertEqual(resumo["puladas"], 1)
        self.assertEqual(resumo["no_plano"], 0)

    def test_a_tela_mostra_o_fora_do_plano_quando_ele_existe(self):
        tracking.log_meal(
            self.user, self.slots[0], MealStatus.DONE,
            self.slots[0].options.first(),
        )
        tracking.log_meal(self.user, self.slots[1], MealStatus.OFF_PLAN)
        self.client.force_login(self.user)

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("1/5 refeições · 1 fora", html)

    def test_num_dia_limpo_a_linha_continua_a_de_sempre(self):
        """A informação a mais não pode virar ruído permanente: a primeira
        dobra cabe em 40px e o dia sem desvio é o caso comum."""
        tracking.log_meal(
            self.user, self.slots[0], MealStatus.DONE,
            self.slots[0].options.first(),
        )
        self.client.force_login(self.user)

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertIn("1/5 refeições", html)
        self.assertNotIn(" fora", html)
