"""Testes do cadastro e do wizard de onboarding.

O foco é o fluxo: o que acontece quando a pessoa avança, volta, pula ou
abandona no meio. É onde um wizard quebra na prática.
"""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import DietaryTag, TagKind

from .models import ONBOARDING_DONE, Profile, TrainingDay, User, WeightEntry


def step_url(step):
    return reverse("accounts:onboarding_step", kwargs={"step": step})


STEP1 = {"sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82.4"}
STEP2 = {"goal": "cut", "activity_level": "light"}
STEP3 = {"weekdays": ["0", "2", "4"], "start_time": "19:00", "duration_min": 60}
STEP4 = {"wake_time": "07:00", "sleep_time": "23:30"}


class SignupTests(TestCase):
    url = reverse("accounts:signup")

    def test_signup_creates_user_logs_in_and_goes_to_step_1(self):
        response = self.client.post(
            self.url,
            {
                "first_name": "Gabriel",
                "email": "Gabriel@Exemplo.com",
                "password1": "senha-bem-forte-123",
                "password2": "senha-bem-forte-123",
            },
        )
        self.assertRedirects(response, step_url(1))
        user = User.objects.get()
        self.assertEqual(user.email, "gabriel@exemplo.com")  # normalizado
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(email="ja@existe.com", password="x")
        response = self.client.post(
            self.url,
            {
                "first_name": "Outro",
                "email": "ja@existe.com",
                "password1": "senha-bem-forte-123",
                "password2": "senha-bem-forte-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Já existe uma conta", response.context["form"].errors["email"][0])
        self.assertEqual(User.objects.count(), 1)


class OnboardingFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="gabriel@exemplo.com", password="senha-bem-forte-123", first_name="Gabriel"
        )
        self.client.force_login(self.user)
        self.vegetariana = DietaryTag.objects.create(
            slug="vegetariana", name="Vegetariana", kind=TagKind.RESTRICTION
        )

    def complete_all_steps(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(3), STEP3)
        return self.client.post(
            step_url(4), {**STEP4, "dietary_tags": [self.vegetariana.pk]}
        )

    def test_step_1_creates_profile_and_first_weight_entry(self):
        response = self.client.post(step_url(1), STEP1)
        self.assertRedirects(response, step_url(2))

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.height_cm, 178)
        self.assertEqual(profile.birth_date, date(1995, 4, 12))
        self.assertEqual(profile.onboarding_step, 2)
        self.assertEqual(WeightEntry.objects.get(user=self.user).weight_kg, Decimal("82.40"))

    def test_cannot_skip_ahead_by_typing_the_url(self):
        # Sem perfil nenhum, qualquer passo adiante volta para o 1
        self.assertRedirects(self.client.get(step_url(3)), step_url(1))

        self.client.post(step_url(1), STEP1)
        # Com o passo 1 feito, o 3 ainda redireciona para o pendente (2)
        self.assertRedirects(self.client.get(step_url(3)), step_url(2))

    def test_can_go_back_and_edit_a_previous_step(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)

        response = self.client.get(step_url(1))
        self.assertEqual(response.status_code, 200)
        # O form volta preenchido, inclusive com o peso, que não é campo do Profile
        self.assertEqual(response.context["form"].initial["height_cm"], 178)
        self.assertEqual(response.context["form"].fields["weight_kg"].initial, Decimal("82.40"))

    def test_reediting_step_1_does_not_reset_progress(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(1), {**STEP1, "height_cm": 180})

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.height_cm, 180)
        self.assertEqual(profile.onboarding_step, 3)  # não voltou para 2

    def test_step_1_twice_in_the_same_day_updates_the_weight_instead_of_duplicating(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(1), {**STEP1, "weight_kg": "81.0"})

        entries = WeightEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.get().weight_kg, Decimal("81.00"))

    def test_step_3_creates_one_training_day_per_weekday(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        response = self.client.post(step_url(3), STEP3)

        self.assertRedirects(response, step_url(4))
        days = TrainingDay.objects.filter(user=self.user).order_by("weekday")
        self.assertEqual([d.weekday for d in days], [0, 2, 4])
        self.assertEqual(days[0].start_time, time(19, 0))

    def test_step_3_removes_weekdays_that_were_unchecked(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(3), {**STEP3, "weekdays": ["1"]})

        self.assertEqual([d.weekday for d in TrainingDay.objects.filter(user=self.user)], [1])

    def test_full_flow_completes_onboarding_and_lands_on_dashboard(self):
        response = self.complete_all_steps()
        self.assertRedirects(response, reverse("plans:today"))

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.onboarding_step, ONBOARDING_DONE)
        self.assertTrue(profile.onboarding_complete)
        self.assertIsNotNone(profile.onboarding_completed_at)
        self.assertEqual(list(profile.dietary_tags.all()), [self.vegetariana])

    def test_editing_after_completion_returns_to_profile_not_to_the_next_step(self):
        self.complete_all_steps()
        response = self.client.post(step_url(2), {"goal": "bulk", "activity_level": "active"})

        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertEqual(Profile.objects.get(user=self.user).goal, "bulk")

    def test_entry_url_resumes_at_the_pending_step(self):
        self.client.post(step_url(1), STEP1)
        self.assertRedirects(self.client.get(reverse("accounts:onboarding")), step_url(2))

        self.complete_all_steps()
        self.assertRedirects(
            self.client.get(reverse("accounts:onboarding")), reverse("plans:today")
        )


class ValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@b.com", password="senha-bem-forte-123")
        self.client.force_login(self.user)

    def test_minor_is_blocked_with_an_explanation(self):
        response = self.client.post(step_url(1), {**STEP1, "birth_date": "2015-01-01"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("acompanhamento profissional", str(response.context["form"].errors))
        self.assertFalse(Profile.objects.exists())

    def test_future_birth_date_is_blocked(self):
        response = self.client.post(step_url(1), {**STEP1, "birth_date": "2099-01-01"})
        self.assertIn("futuro", str(response.context["form"].errors))

    def test_sleeping_after_midnight_is_valid(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(3), STEP3)
        response = self.client.post(
            step_url(4), {"wake_time": "07:00", "sleep_time": "01:30"}
        )
        self.assertRedirects(response, reverse("plans:today"))

    def test_absurdly_short_awake_window_is_blocked(self):
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(3), STEP3)
        response = self.client.post(
            step_url(4), {"wake_time": "07:00", "sleep_time": "10:00"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("muito curta", str(response.context["form"].errors))


class AccessControlTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("plans:today"))
        self.assertIn(reverse("accounts:login"), response.url)

    def test_dashboard_requires_completed_onboarding(self):
        user = User.objects.create_user(email="c@d.com", password="senha-bem-forte-123")
        self.client.force_login(user)
        response = self.client.get(reverse("plans:today"))
        self.assertRedirects(
            response, reverse("accounts:onboarding"), target_status_code=302
        )

    def test_onboarding_requires_login(self):
        response = self.client.get(step_url(1))
        self.assertIn(reverse("accounts:login"), response.url)
