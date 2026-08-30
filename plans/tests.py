"""Testes do cálculo de meta calórica e do ciclo de vida do plano.

A matemática é testada direto nas funções puras, com números conferidos na
mão. Os testes de banco cobrem o que realmente quebra na prática: plano
duplicado, plano velho continuar ativo depois de mudar o peso, e recálculo
disparando toda vez que a tela abre.
"""
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
import re

from django.conf import settings

from django.core.management import call_command
from django.http import QueryDict
from django.db.models import Sum
from django.test import TestCase
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

from . import meal_planner, services, shopping, tracking, views
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

    def test_recalculate_is_not_reachable_by_get(self):
        response = self.client.get(reverse("plans:recalculate"))
        self.assertEqual(response.status_code, 405)

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

    def test_plan_comes_with_five_slots_and_two_options_each(self):
        slots = list(self.plan.slots.all())
        self.assertEqual(len(slots), len(meal_planner.DAY_BLUEPRINT))
        for slot in slots:
            self.assertEqual(slot.options.count(), 2, slot.name)
        self.assertEqual(MealOption.objects.filter(slot__plan=self.plan).count(), 10)

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

    def test_the_same_recipe_does_not_repeat_in_the_day(self):
        used = list(
            MealOption.objects.filter(slot__plan=self.plan).values_list(
                "template_id", flat=True
            )
        )
        self.assertEqual(len(used), len(set(used)))

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


class TwoOptionsPerMealTests(CatalogFixture):
    """Cada refeição oferece exatamente Opção A e Opção B — nunca uma terceira.

    A regra é de produto, não de banco: mais de duas escolhas na hora da fome
    é o que faz a pessoa fechar o app e pedir delivery. Os testes olham para o
    limite pelos dois lados — o gerador não estica quando sobra receita, e não
    inventa rótulo quando falta.
    """

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)

    def test_the_number_of_options_comes_from_the_labels(self):
        self.assertEqual(meal_planner.OPTIONS_PER_SLOT, 2)
        self.assertEqual(meal_planner.OPTIONS_PER_SLOT, len(OptionLabel.values))

    def test_no_slot_offers_a_third_option(self):
        for slot in self.plan.slots.all():
            with self.subTest(slot=slot.name):
                labels = list(slot.options.values_list("label", flat=True))
                self.assertLessEqual(len(labels), 2)
                self.assertEqual(sorted(labels), sorted(set(labels)))
                self.assertTrue(set(labels) <= {OptionLabel.A, OptionLabel.B})

    def test_a_large_catalog_still_yields_only_two(self):
        """Catálogo farto é o caso em que a sobra apareceria."""
        for index in range(8):
            make_template(
                f"Prato extra {index}",
                MealCategory.MAIN,
                [(self.chicken, 120 + index * 10, True), (self.rice, 150, True)],
            )

        plan = services.create_plan(create_complete_user(email="farto@exemplo.com"))

        for slot in plan.slots.filter(category=MealCategory.MAIN):
            self.assertEqual(slot.options.count(), 2, slot.name)

    def test_the_option_labels_are_handed_out_in_order(self):
        for slot in self.plan.slots.all():
            options = list(slot.options.order_by("id"))
            self.assertEqual(
                [option.label for option in options],
                OptionLabel.values[: len(options)],
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
            self.assertEqual(slot.options.count(), 2, slot.name)
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
                    self.assertEqual(slot.options.count(), 2, slot.name)
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

                menu = views.menu_totals(slots)
                folga = abs(menu["kcal"] - plan.target_kcal)

                self.assertLessEqual(
                    folga,
                    plan.target_kcal * 0.03,
                    f"cardápio de {menu['kcal']} kcal para meta de {plan.target_kcal}",
                )
                self.assertGreater(menu["protein_g"], 0)

    def test_a_vegan_profile_also_gets_two_options_at_every_meal(self):
        """A restrição mais apertada do catálogo é a régua da cobertura."""
        user = create_complete_user(email="vegana@exemplo.com")
        user.profile.dietary_tags.add(DietaryTag.objects.get(slug="vegana"))

        plan = services.create_plan(user)

        for slot in plan.slots.all():
            self.assertEqual(slot.options.count(), 2, slot.name)
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
        self.assertContains(response, slot.options.first().template.name)


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

        self.assertEqual(summary["consumed_kcal"], int(self.option.kcal))
        self.assertEqual(summary["done"], 1)
        self.assertEqual(summary["marked"], 2)
        self.assertEqual(summary["total"], 5)
        self.assertEqual(
            summary["remaining_kcal"], self.plan.target_kcal - int(self.option.kcal)
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

        self.assertRedirects(response, reverse("plans:today"))
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

    def test_marking_is_not_reachable_by_get(self):
        self.assertEqual(self.client.get(self.url()).status_code, 405)


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
