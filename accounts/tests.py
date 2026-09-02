"""Testes do cadastro e do wizard de onboarding.

O foco é o fluxo: o que acontece quando a pessoa avança, volta, pula ou
abandona no meio. É onde um wizard quebra na prática.
"""
import ast
from unittest import mock
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from pathlib import Path

from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from allauth.socialaccount.models import SocialAccount
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from catalog.models import DietaryTag, TagKind
from plans.models import NutritionPlan
from plans.tests import create_complete_user

from push.models import PushSubscription

from . import limites, papeis
from .adapters import MAXIMO_DE_TENTATIVAS, SESSAO_TENTATIVAS, SESSAO_VINCULO
from .forms import (
    PALAVRA_DE_EXCLUSAO,
    REGRAS_ESPERADAS,
    BodyDataForm,
    PesagemForm,
    SignupForm,
)
from workouts.services import preferencia_muda_a_divisao, split_for

from .views import CAMINHO_COMPLETO, CAMINHO_CURTO

from .models import (
    AcaoAdministrativa,
    SplitPreference,
    ActivityLevel,
    Goal,
    Sex,
    RegistroAdministrativo,
    PedidoDeRecuperacao,
    ONBOARDING_DONE,
    ONBOARDING_LAST_STEP,
    Profile,
    TrainingDay,
    User,
    Weekday,
    WeightEntry,
)


def step_url(step):
    return reverse("accounts:onboarding_step", kwargs={"step": step})


STEP1 = {"sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82.4"}
STEP2 = {"goal": "cut", "activity_level": "light"}
# A janela do dia entrou no STEP3 na V2.1: os relógios do passo 3 são todos da
# mesma pergunta, e o passo 5 ficou só com a comida.
STEP3 = {
    "weekdays": ["0", "2", "4"],
    "start_time": "19:00",
    "duration_min": 60,
    "wake_time": "07:00",
    "sleep_time": "23:30",
}
STEP4 = {"split_preference": "three"}
#: Quatro dias — a partir daí a preferência de divisão muda o plano, e o passo
#: 4 volta a existir. É o fixture dos testes que precisam do caminho completo.
STEP3_COM_DIVISAO = {**STEP3, "weekdays": ["0", "1", "3", "5"]}
STEP5 = {"meal_style": "quick"}


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
        self.client.post(step_url(4), STEP4)
        return self.client.post(
            step_url(5), {**STEP5, "dietary_tags": [self.vegetariana.pk]}
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

        # Passo 5, e não 4: `STEP3` marca três dias, e desde a V2.2 a pergunta
        # de divisão é pulada quando as três preferências dariam a mesma
        # resposta. O passo 4 continua existindo — só não para esta pessoa.
        self.assertRedirects(response, step_url(5))
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

    def _ate_a_janela(self):
        """Os dois passos anteriores ao da janela do dia.

        A janela é o passo 3 desde a V2.1, e não mais o 5 — então parar no 2 é
        o que deixa a pessoa exatamente na porta da tela que se quer testar.
        """
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)

    def test_sleeping_after_midnight_is_valid(self):
        self._ate_a_janela()
        response = self.client.post(
            step_url(3), {**STEP3, "wake_time": "07:00", "sleep_time": "01:30"}
        )
        # `STEP3` tem três dias, então o passo seguinte é o 5.
        self.assertRedirects(response, step_url(5))

    def test_absurdly_short_awake_window_is_blocked(self):
        self._ate_a_janela()
        response = self.client.post(
            step_url(3), {**STEP3, "wake_time": "07:00", "sleep_time": "10:00"}
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


class WizardChromeTests(TestCase):
    """A moldura do wizard: navegação, progresso e densidade.

    O passo do onboarding é a tela mais apertada do app — até sete cartões de
    escolha, dois rótulos e o botão precisam caber em 390×844. O que se aperta
    é o respiro; nunca o alvo de toque nem o corpo do texto.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="wizard@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)

    def test_the_tab_bar_is_gone_while_the_wizard_is_open(self):
        """Os cinco destinos da barra passam por `OnboardingRequiredMixin`:
        quem toca em qualquer um antes de terminar é devolvido para cá. Eram
        cinco becos sem saída — mais os 96px que o container reserva para a
        barra, que empurravam o "Continuar" para fora da primeira tela."""
        html = self.client.get(step_url(3)).content.decode()

        self.assertNotIn('<nav class="tabbar"', html)
        self.assertNotIn("tem-tabbar", html)

    def test_the_tab_bar_comes_back_once_there_is_somewhere_to_go(self):
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(4), STEP4)
        self.client.post(step_url(5), STEP5)

        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn('<nav class="tabbar"', html)

    def test_the_tab_bar_stays_hidden_when_editing_a_step_after_finishing(self):
        """Quem já terminou e volta para editar está no mesmo fluxo focado, com
        "Voltar" e "Salvar". A barra ali só oferece saídas — por isso a trava é
        da PÁGINA e não do estado do perfil."""
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(4), STEP4)
        self.client.post(step_url(5), STEP5)

        html = self.client.get(step_url(2)).content.decode()
        self.assertNotIn('<nav class="tabbar"', html)

    def test_the_progress_reads_as_one_line_of_monospaced_digits(self):
        """Eram dois textos nas pontas opostas da linha, e o olho atravessava a
        tela para juntar duas metades da mesma informação: onde eu estou."""
        html = self.client.get(step_url(3)).content.decode()

        self.assertIn('class="wizard__label num"', html)
        self.assertIn("Passo 3/5 · 60%", html)

    def test_the_goal_cards_stand_in_two_columns_and_the_activity_in_one(self):
        """Três colunas para atividade dariam 100px por cartão a 390px, e
        "Pouco ativo" não é o rótulo mais longo dos três. São três opções: a
        lista de uma coluna se lê de uma vez."""
        html = self.client.get(step_url(2)).content.decode()

        self.assertEqual(html.count("choice-cards--duas"), 1)

    def test_no_card_description_runs_past_a_single_line_on_a_phone(self):
        """A régua é de caractere, não de pixel — mas é a mesma coisa: a coluna
        do cartão de duas colunas dá ~22 caracteres por linha na descrição, e a
        de uma coluna dá ~45. Descrição que estoura vira duas linhas, a FAIXA
        da grade cresce junto, e dois cartões pagam pela quebra de um.
        """
        from accounts.templatetags.escolhas import DETALHES

        for valor, dados in DETALHES.items():
            with self.subTest(opcao=valor):
                self.assertLessEqual(
                    len(dados[2]), 45, f"{valor}: apoio com {len(dados[2])} caracteres"
                )


class PlanBuildingScreenTests(TestCase):
    """A tela que cobre o vão entre "Concluir" e o painel pronto.

    O número que a justifica: o POST do último passo leva 9 milissegundos. Quem
    monta o plano é a PRIMEIRA abertura do painel — `sync_active_plan` roda na
    entrada da tela, não no fim do wizard —, e ali são 196ms no banco local e
    bem mais no Render, com Postgres remoto. Nesse intervalo a pessoa acabou de
    tocar "Concluir" e a tela não muda.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="montagem@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        # Caminho COMPLETO de propósito: esta classe testa a tela de montagem
        # do último passo, e quer os quatro passos anteriores para percorrer.
        self.client.post(step_url(3), STEP3_COM_DIVISAO)
        self.client.post(step_url(4), STEP4)

    def test_the_screen_exists_only_on_the_last_step(self):
        for passo in (1, 2, 3, 4):
            with self.subTest(passo=passo):
                self.assertNotContains(self.client.get(step_url(passo)), "data-montagem")
        self.assertContains(self.client.get(step_url(5)), "data-montagem")

    def test_it_starts_hidden(self):
        """Ela cobre a tela inteira. Chegar visível seria esconder o
        formulário que a pessoa precisa preencher."""
        html = self.client.get(step_url(5)).content.decode()
        bloco = html.split("data-montagem", 1)[1][:80]
        self.assertIn("hidden", bloco)

    def test_the_messages_describe_work_that_is_actually_happening(self):
        """Na ordem em que acontece: `calculate()` faz a taxa metabólica,
        `macro_rows` divide os macros, `create_routine` monta a ficha.

        Frase que descreve trabalho inexistente é tempo cobrado da pessoa para
        o app parecer que se esforçou."""
        html = self.client.get(step_url(5)).content.decode()
        for frase in ("metabólica basal", "macronutrientes", "divisão de treino"):
            with self.subTest(frase=frase):
                self.assertIn(frase, html)

    def test_someone_editing_a_finished_wizard_never_sees_it(self):
        """Quem volta para editar recebe "Salvar" e vai para o perfil. Uma tela
        dizendo "montando seu plano" ali seria mentira."""
        self.client.post(step_url(5), STEP5)
        self.assertNotContains(self.client.get(step_url(5)), "data-montagem")

    def test_the_form_still_submits_without_javascript(self):
        """A sobreposição é melhoria progressiva: quem tem o script desligado
        envia o formulário do jeito de sempre. O `<form>` continua com `action`
        e `method` — nada depende do script para o dado chegar."""
        html = self.client.get(step_url(5)).content.decode()
        formulario = html.split('<div class="card">', 1)[1].split("</form>", 1)[0]
        self.assertIn('method="post"', formulario)

        resposta = self.client.post(step_url(5), STEP5)
        self.assertRedirects(resposta, reverse("plans:today"))

    def test_a_form_error_keeps_the_person_on_the_step(self):
        """O caminho arriscado da sobreposição: sem redirecionamento, ela
        precisa sair do caminho e deixar o servidor renderizar os erros. Se
        ficasse no ar, a pessoa olharia uma tela de carregamento para sempre."""
        # O erro de exemplo era a janela de sono, que mudou para o passo 3 na
        # V2.1. O estilo de cardápio é obrigatório e continua sendo um erro
        # deste passo — que é o que o teste precisa: um POST que NÃO redireciona.
        resposta = self.client.post(step_url(5), {**STEP5, "meal_style": ""})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("meal_style", str(resposta.context["form"].errors))

        script = resposta.content.decode()
        self.assertIn("r.redirected", script)
        self.assertIn("form.submit()", script)


class WizardProgressBarTests(TestCase):
    """A trilha de progresso, que agora anda em vez de saltar."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="trilha@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)

    def test_the_bar_is_one_track_and_not_five_segments(self):
        """Segmento é ligado ou desligado: a barra saltava de 60% para 80% sem
        passar pelo caminho, e o que a pessoa via era troca de estado."""
        html = self.client.get(step_url(2)).content.decode()
        self.assertIn("wizard__trilha", html)
        self.assertIn("wizard__avanco", html)
        self.assertNotIn("wizard__step--done", html)

    def test_the_fill_carries_the_real_percentage(self):
        for passo, pct in ((2, 40), (3, 60)):
            with self.subTest(passo=passo):
                if passo == 3:
                    self.client.post(step_url(2), STEP2)
                html = self.client.get(step_url(passo)).content.decode()
                self.assertIn(f"width: {pct}%", html)

    def test_the_fill_animates_with_the_project_curve(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        regra = css.split(chr(10) + ".wizard__avanco {", 1)[1].split("}", 1)[0]
        self.assertIn("transition: width .3s var(--ease)", regra)


class ProfileActionsTests(TestCase):
    """O perfil ganha as ações que estavam escondidas ou faltando."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="perfil@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(4), STEP4)
        self.client.post(step_url(5), STEP5)
        # O plano nasce na PRIMEIRA abertura do painel, e não no fim do
        # wizard: `sync_active_plan` roda na entrada da tela. Sem esta visita o
        # perfil abriria sem plano — que é um estado real, e tem teste próprio
        # logo abaixo.
        self.client.get(reverse("plans:today"))
        self.url = reverse("accounts:profile")

    def test_logging_out_left_the_header_and_lives_here(self):
        """"Sair" ficava na barra de cima, visível em toda tela do app, a um
        dedo do logotipo — que leva para a home. Errar o alvo custa a senha de
        novo."""
        html = self.client.get(self.url).content.decode()

        self.assertIn("Sair da conta", html)
        # No celular ele some da barra de cima; no desktop continua lá, porque
        # ali a barra de cima É a navegação.
        self.assertIn("app-bar__so-desktop", html)

        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".app-bar__so-desktop { display: none; }", css)

    def test_the_logout_asks_before_doing_it(self):
        html = self.client.get(self.url).content.decode()
        formulario = html.split("Sair da conta", 1)[0]
        self.assertIn("confirm(", formulario.rsplit("<form", 1)[1])

    def test_the_logout_actually_ends_the_session(self):
        self.client.post(reverse("accounts:logout"))
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("entrar", resposta["Location"])

    def test_recalculating_is_offered_next_to_the_numbers_it_changes(self):
        """O recálculo já existia, escondido no fim do painel, depois de nove
        cartões. Um botão "recalcular" sozinho pede fé; com a meta ao lado, a
        pessoa vê de que número está saindo."""
        html = self.client.get(self.url).content.decode()

        self.assertIn("Recalcular metas", html)
        self.assertIn(reverse("plans:recalculate"), html)
        self.assertIn("metas__principal", html)

    def test_recalculating_keeps_the_old_plans(self):
        """`NutritionPlan` é retrato, não referência: o plano novo nasce ao
        lado dos antigos, e o que já foi comido continua no plano em que foi."""
        antes = self.user.plans.count()
        self.client.post(reverse("plans:recalculate"))
        self.assertEqual(self.user.plans.count(), antes + 1)
        self.assertEqual(self.user.plans.filter(is_active=True).count(), 1)

    def test_the_button_is_there_even_without_an_active_plan(self):
        """É exatamente o caso em que ele resolve alguma coisa. Escondê-lo
        deixaria a pessoa numa tela que mostra o problema e não oferece a
        saída."""
        self.user.plans.update(is_active=False)
        html = self.client.get(self.url).content.decode()
        self.assertIn("Calcular minhas metas", html)
        self.assertIn("ainda não tem um plano ativo", html)

    def test_the_restrictions_link_points_at_the_step_they_actually_live_in(self):
        """Elas eram o passo 4 até a preferência de divisão entrar na frente.
        O link ficou apontando para a tela errada desde então, mandando quem
        queria editar restrição para a escolha de divisão de treino."""
        html = self.client.get(self.url).content.decode()
        bloco = html.split("Comida e restrições", 1)[1].split("</section>", 1)[0]
        self.assertIn(step_url(5), bloco)
        self.assertNotIn(step_url(4), bloco)

    def test_the_two_new_preferences_are_visible_and_editable(self):
        """Elas entraram no onboarding e nunca apareceram aqui — quem quisesse
        trocar teria que adivinhar em qual passo do wizard elas moram.

        Quatro dias de treino porque, desde a V2.2, o cartão da divisão só
        aparece para quem a escolha muda alguma coisa.
        """
        self.client.post(step_url(3), STEP3_COM_DIVISAO)
        self.client.post(step_url(4), STEP4)
        html = self.client.get(self.url).content.decode()
        divisao = html.split("Divisão de treino", 1)[1].split("</section>", 1)[0]
        self.assertIn("3 grupos por dia", divisao)
        self.assertIn(step_url(4), divisao)

        # O cardápio mora no cartão que leva ao passo 5, que é onde ele é
        # editado. Juntos num cartão só, o "Editar" mandava quem queria trocar
        # o cardápio para a tela de divisão de treino.
        comida = html.split("Comida e restrições", 1)[1].split("</section>", 1)[0]
        self.assertIn("Rápida e econômica", comida)
        self.assertIn(step_url(5), comida)


class BottomNavigationTests(TestCase):
    """A barra de baixo: cinco destinos, e nenhum deles é "sair"."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="abas@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        for passo, dados in ((1, STEP1), (2, STEP2), (3, STEP3), (4, STEP4), (5, STEP5)):
            self.client.post(step_url(passo), dados)
        self.html = self.client.get(reverse("plans:today")).content.decode()

    def test_the_bar_never_carried_a_logout(self):
        barra = self.html.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("logout", barra)
        self.assertNotIn("Sair", barra)

    def test_all_four_destinations_are_reachable_from_it(self):
        """São quatro desde que Suplementos saiu do produto.

        Eram cinco, e a quinta era Suplementos — a barra era a ÚNICA porta
        para aquela tela. Com a tela fora, a barra passa a ter quatro itens
        mais largos, e isso é melhora: alvo maior no polegar. O que este teste
        trava é que ninguém invente uma aba nova só para reocupar o espaço.
        """
        barra = self.html.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
        for rota in (
            reverse("plans:today"),
            reverse("workouts:routine"),
            reverse("plans:history"),
            reverse("accounts:profile"),
        ):
            with self.subTest(rota=rota):
                self.assertIn(f'href="{rota}"', barra)

    def test_every_tab_has_an_icon_above_its_label(self):
        barra = self.html.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(barra.count("<svg"), 4)

    def test_the_columns_are_equal_so_the_row_never_drifts(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        bloco = css.split(chr(10) + ".tabbar {", 1)[1].split("}", 1)[0]
        self.assertIn("repeat(4, 1fr)", bloco)

    def test_suplementos_nao_volta_para_a_navegacao(self):
        """Decisão de produto, e não acidente de implementação.

        Suplemento saiu porque o NutriPlan monta alimentação com comida: o
        plano não depende de suplemento nenhum, e uma aba dedicada sugeria que
        era preciso comprar algo para cumprir a dieta.

        O model e a tabela continuam de pé, de propósito — histórico de quem
        marcou não foi apagado. É exatamente por isso que este teste existe:
        com o model vivo, reabrir a rota e recolocar o link custa duas linhas,
        e a decisão voltaria sem ninguém notar.
        """
        for barra in ("tabbar", "app-bar__nav"):
            with self.subTest(barra=barra):
                trecho = self.html.split('class="%s"' % barra, 1)[1].split(
                    "</nav>", 1
                )[0]

                self.assertNotIn("suplement", trecho.lower())
                self.assertNotIn("/suplementos/", trecho)

    def test_the_active_pill_fades_in_instead_of_appearing(self):
        """`transition: all` pegaria propriedades que ninguém quer animar —
        largura, posição, o que a próxima regra acrescentar. A lista nomeia as
        quatro que mudam no estado ativo."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        transicoes = [
            t for t in css.split(chr(10) + ".tabbar__item {")[1:]
        ]
        corpo = "".join(t.split("}", 1)[0] for t in transicoes)
        self.assertIn("background var(--dur) var(--ease)", corpo)
        self.assertIn("color var(--dur) var(--ease)", corpo)
        self.assertNotIn("transition: all", css)


class AuthScreenTests(TestCase):
    """As telas de entrar e cadastrar.

    A queixa que originou este trabalho foi "fundo branco, desalinhado do dark
    mode". Medido: em modo escuro elas SEMPRE foram escuras — `#0d0f12`, texto
    branco, botão esmeralda. O que aparece claro é o tema CLARO do app, que
    existe de propósito e vale para todas as telas, não só para estas.

    O que faltava de verdade era outra coisa, e está aqui.
    """

    def setUp(self):
        self.login = self.client.get(reverse("accounts:login")).content.decode()
        self.cadastro = self.client.get(reverse("accounts:signup")).content.decode()
        self.css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

    def test_the_header_drops_the_link_that_repeats_the_screen(self):
        """A barra oferecia "Entrar" e "Criar conta" — e a tela de entrar já É
        entrar, com o link para criar conta no rodapé do cartão. Dois caminhos
        para o mesmo lugar, um a três centímetros do outro.

        O wordmark fica: é a primeira tela que alguém vê, e tirar a marca dali
        deixaria um formulário solto sem dono."""
        for nome, html in (("entrar", self.login), ("cadastro", self.cadastro)):
            with self.subTest(tela=nome):
                barra = html.split('<header class="app-bar"', 1)[1].split("</header>", 1)[0]
                # O wordmark é "Nutri" mais um `<span>` com "Plan" — a palavra
                # inteira não existe como texto contíguo no HTML.
                self.assertIn("app-bar__brand", barra)
                self.assertNotIn(reverse("accounts:login"), barra)
                self.assertNotIn(reverse("accounts:signup"), barra)

    def test_the_card_is_centred_and_made_of_glass(self):
        # TODOS os blocos de `.auth`, e não o primeiro: há um one-liner antigo
        # com a largura máxima, e ele vem antes no arquivo. Ler só o primeiro é
        # a armadilha recorrente desta base, e pegou este teste na estreia.
        regra = "".join(
            trecho.split("}", 1)[0]
            for trecho in self.css.split(chr(10) + ".auth--entrada {")[1:]
        )
        self.assertIn("align-content: center", regra)
        # `dvh` e não `vh`: no Safari do iPhone a barra de endereço some ao
        # rolar e `vh` continua contando a altura de antes.
        self.assertIn("dvh", regra)

        cartao = self.css.split(chr(10) + ".auth--entrada .card {", 1)[1].split("}", 1)[0]
        self.assertIn("backdrop-filter: blur(16px)", cartao)

    def test_a_browser_without_backdrop_filter_still_reads_the_card(self):
        """Sem o desfoque, o fundo translúcido deixaria o halo passar direto e
        o texto perderia contraste."""
        self.assertIn("@supports not ((backdrop-filter", self.css)

    def test_every_password_field_gets_an_eye(self):
        """Digitar senha forte às cegas num teclado de celular é onde a pessoa
        erra e desiste — e "senha incorreta" depois de três tentativas não diz
        se o erro foi de dedo ou de memória."""
        self.assertEqual(self.login.count("data-ver-senha"), 1)
        # Cadastro pede senha e confirmação.
        self.assertEqual(self.cadastro.count("data-ver-senha"), 2)

    def test_the_eye_says_what_it_will_do_and_not_what_it_is(self):
        """Olho riscado com a senha visível diria o contrário do que o botão
        faz. O corte só existe enquanto a senha está oculta."""
        self.assertIn('aria-pressed="false"', self.login)
        self.assertIn('aria-label="Mostrar a senha"', self.login)
        self.assertIn(
            '.campo-senha__olho[aria-pressed="true"] .campo-senha__corte', self.css
        )

    def test_the_eye_gives_the_cursor_back_to_the_field(self):
        """Trocar o `type` do campo manda o cursor para a posição zero, e quem
        estava no meio de digitar perderia o lugar."""
        pwa = (Path(settings.BASE_DIR) / "static" / "js" / "pwa.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("setSelectionRange", pwa)
        self.assertIn("campo.focus()", pwa)

    def test_the_footer_link_between_the_two_screens_is_a_touch_target(self):
        """Ele mede 44px porque é `.btn-link` — como texto solto num parágrafo
        dava 19 pixels de altura."""
        self.assertIn('class="btn-link"', self.login)
        self.assertIn('class="btn-link"', self.cadastro)

    def test_the_screens_follow_the_app_theme_instead_of_forcing_one(self):
        """Forçar escuro só aqui criaria a emenda que a mudança deveria
        remover: entrar numa tela escura e cair num painel claro."""
        for nome, html in (("entrar", self.login), ("cadastro", self.cadastro)):
            with self.subTest(tela=nome):
                # Nada de estilo embutido forçando um tema: as telas herdam a
                # paleta do app, como todas as outras.
                self.assertNotIn("<style", html)
                self.assertNotIn("#0d0f12", html.split("</head>", 1)[1])


class PesagemRapidaTests(TestCase):
    """A rota de peso: um número, uma tabela, nenhum efeito colateral.

    Ela existe porque registrar o peso exigia abrir o passo 1 do onboarding —
    sexo, nascimento, altura e peso, com a barra de abas sumindo, para gravar
    o único dos quatro que muda. O que estes testes defendem é o "nenhum
    efeito colateral": a rota escreve WeightEntry e para. A meta se atualiza
    depois, sozinha, pelo caminho que já existia.
    """

    url = reverse("accounts:log_weight")

    def setUp(self):
        self.user = create_complete_user(email="pesagem@exemplo.com")
        self.user.weight_entries.all().delete()
        self.client.force_login(self.user)

    # ---------------------------------------------------------------- acesso

    def test_anonymous_cannot_record_a_weight(self):
        self.client.logout()
        resposta = self.client.post(self.url, {"weight_kg": "80"})

        self.assertIn(reverse("accounts:login"), resposta["Location"])
        self.assertEqual(WeightEntry.objects.count(), 0)

    def test_an_unfinished_onboarding_goes_back_to_the_wizard(self):
        Profile.objects.filter(user=self.user).update(onboarding_step=3)
        resposta = self.client.post(self.url, {"weight_kg": "80"})

        self.assertRedirects(
            resposta, reverse("accounts:onboarding"), target_status_code=302
        )
        self.assertEqual(WeightEntry.objects.count(), 0)

    def test_the_route_only_accepts_post(self):
        """Isso muda estado. GET que escreve é GET que o navegador repete."""
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_a_weight_is_always_written_for_whoever_is_logged_in(self):
        """Ownership vive na consulta: a rota não lê identificador de gente
        nenhuma do corpo, então mandar um não muda o dono do registro."""
        outra = User.objects.create_user(
            email="outra@exemplo.com", password="senha-bem-forte-123"
        )

        self.client.post(
            self.url, {"weight_kg": "80", "user": outra.pk, "user_id": outra.pk}
        )

        self.assertEqual(outra.weight_entries.count(), 0)
        self.assertEqual(self.user.weight_entries.count(), 1)

    # --------------------------------------------------------------- escrita

    def test_a_valid_weight_creates_todays_entry(self):
        self.client.post(self.url, {"weight_kg": "80.5", "origem": "metricas"})

        entry = self.user.weight_entries.get()
        self.assertEqual(entry.date, timezone.localdate())
        self.assertEqual(entry.weight_kg, Decimal("80.50"))

    def test_a_comma_is_how_this_app_writes_a_decimal(self):
        """O campo é `type="text"` porque `type="number"` recusa vírgula, e
        aqui se digita "82,5". A mesma tradução que a carga da ficha faz."""
        self.client.post(self.url, {"weight_kg": "82,5", "origem": "hoje"})

        self.assertEqual(self.user.weight_entries.get().weight_kg, Decimal("82.50"))

    def test_recording_again_today_corrects_instead_of_stacking(self):
        """Duas pesagens no mesmo dia não existem: a segunda É a primeira,
        corrigida. Sem isso, a média do dia contaria a tentativa errada."""
        self.client.post(self.url, {"weight_kg": "82,5"})
        self.client.post(self.url, {"weight_kg": "82,0"})

        self.assertEqual(self.user.weight_entries.count(), 1)
        self.assertEqual(self.user.weight_entries.get().weight_kg, Decimal("82.00"))

    def test_the_screen_that_asked_is_the_screen_that_gets_the_answer(self):
        do_painel = self.client.post(self.url, {"weight_kg": "80", "origem": "hoje"})
        self.assertRedirects(do_painel, reverse("plans:today"))

        de_metricas = self.client.post(
            self.url, {"weight_kg": "80", "origem": "metricas"}
        )
        self.assertRedirects(de_metricas, reverse("plans:history"))

    def test_an_unknown_origin_never_becomes_a_redirect_target(self):
        """Destino escolhido pelo cliente é redirecionamento aberto. A lista é
        fechada, e o que não está nela cai no padrão."""
        resposta = self.client.post(
            self.url, {"weight_kg": "80", "origem": "https://exemplo.invalido/"}
        )

        self.assertRedirects(resposta, reverse("plans:history"))

    # ------------------------------------------------------------- validação

    def test_text_that_is_not_a_number_is_refused_with_an_example(self):
        resposta = self.client.post(
            self.url, {"weight_kg": "oitenta", "origem": "metricas"}, follow=True
        )

        self.assertEqual(WeightEntry.objects.count(), 0)
        self.assertContains(resposta, "Peso inválido — use números, como 82,5.")

    def test_what_the_person_typed_survives_a_refusal(self):
        """Apagar o que ela escreveu por causa de uma vírgula é punição: ela
        volta para um campo vazio sem saber o que estava errado."""
        self.client.post(self.url, {"weight_kg": "8o,5", "origem": "metricas"})

        # `[superfície, valor]`: sem a superfície, o painel consumia um erro
        # nascido em Métricas e a pessoa voltava para um campo vazio.
        self.assertEqual(self.client.session.get("peso_recusado"), ["metricas", "8o,5"])

    def test_a_weight_below_the_range_the_app_calculates_is_refused(self):
        """Vinte quilos é o piso do model. Abaixo disso a fórmula de taxa
        metabólica não descreve mais ninguém, e o erro precisa dizer a faixa."""
        resposta = self.client.post(
            self.url, {"weight_kg": "19", "origem": "metricas"}, follow=True
        )

        self.assertEqual(WeightEntry.objects.count(), 0)
        self.assertContains(resposta, "use de 20 a 400 kg")

    def test_a_weight_above_the_range_the_app_calculates_is_refused(self):
        resposta = self.client.post(
            self.url, {"weight_kg": "401", "origem": "metricas"}, follow=True
        )

        self.assertEqual(WeightEntry.objects.count(), 0)
        self.assertContains(resposta, "use de 20 a 400 kg")

    def test_an_empty_field_says_what_to_type(self):
        resposta = self.client.post(
            self.url, {"weight_kg": "", "origem": "metricas"}, follow=True
        )

        self.assertEqual(WeightEntry.objects.count(), 0)
        self.assertContains(resposta, "Digite o peso")

    def test_the_range_comes_from_the_model_and_is_not_rewritten(self):
        """Os limites moram no campo do model. Se alguém mudar a faixa lá, o
        formulário acompanha — dois lugares para o mesmo número é um deles
        ficando para trás."""
        do_form = PesagemForm().fields["weight_kg"].validators
        for validador in WeightEntry._meta.get_field("weight_kg").validators:
            # Identidade, e não igualdade: dois validadores com os mesmos
            # números são iguais, e é justamente a cópia que este teste
            # existe para recusar.
            self.assertTrue(
                any(v is validador for v in do_form),
                "o formulário reescreveu um validador em vez de reusar o do model",
            )

    # ------------------------------------------------------ efeito colateral

    def test_recording_a_weight_never_touches_the_profile(self):
        """A rota escreve uma tabela. `Profile.current_weight` continua
        derivado — dois lugares guardando o peso divergiriam na primeira
        correção do dia."""
        antes = Profile.objects.get(user=self.user)
        self.client.post(self.url, {"weight_kg": "77,5"})
        depois = Profile.objects.get(user=self.user)

        self.assertEqual(antes.height_cm, depois.height_cm)
        self.assertEqual(antes.sex, depois.sex)
        self.assertEqual(antes.birth_date, depois.birth_date)
        self.assertEqual(antes.kcal_adjustment, depois.kcal_adjustment)

    def test_recording_a_weight_does_not_build_a_plan_inside_the_request(self):
        """O plano novo nasce na próxima entrada de tela, por
        `sync_active_plan`. Gerar aqui duplicaria esse mecanismo e faria o
        cardápio ser remontado sobre um número que ela pode corrigir agora."""
        self.client.post(self.url, {"weight_kg": "77,5"})

        self.assertEqual(NutritionPlan.objects.filter(user=self.user).count(), 0)

    def test_the_current_weight_becomes_the_one_just_recorded(self):
        """A ponta da corrente: é `current_weight` que `build_inputs` lê, e é
        por ele que o plano percebe sozinho que o peso mudou."""
        self.client.post(self.url, {"weight_kg": "77,5"})

        self.assertEqual(
            Profile.objects.get(user=self.user).current_weight, Decimal("77.50")
        )

    def test_the_old_onboarding_path_still_records_a_weight(self):
        """O passo 1 continua existindo para editar dados corporais pelo
        Perfil, e continua gravando peso. Ele só deixou de ser o caminho para
        se pesar."""
        self.client.post(step_url(1), STEP1)

        self.assertEqual(self.user.weight_entries.count(), 1)


# ==========================================================================
# Login com Google
# ==========================================================================


def _sociallogin(email="pessoa@gmail.com", uid="google-uid-1", verificado=True, nome="Ana"):
    """Um `SocialLogin` como o que o provedor entrega depois do OIDC validado.

    Montado à mão de propósito: falar com o Google numa suíte tornaria os
    testes dependentes de rede e de credencial. O que interessa aqui é a
    POLÍTICA — o que o adapter faz com uma identidade —, e ela recebe o mesmo
    objeto vindo do provedor real ou daqui.
    """
    from allauth.account.models import EmailAddress
    from allauth.socialaccount import providers
    from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin

    conta = SocialAccount(
        provider="google",
        uid=uid,
        extra_data={"email": email, "given_name": nome, "sub": uid},
    )
    usuario = User(email=email, first_name=nome)
    # O provider vem do registro do allauth, e não é decoração: `serialize()`
    # chama `self.provider.serialize()`, e o caso 4 guarda o `SocialLogin`
    # serializado na sessão. Sem ele, o teste passaria por um caminho que a
    # aplicação real nunca percorre.
    classe = providers.registry.get_class("google")
    # O `client_id` sai das settings em vigor, e não de um literal: ele é
    # gravado na serialização e é por ele que o allauth reencontra o app ao
    # desserializar. Dois valores diferentes aqui produzem um
    # `SocialApp.DoesNotExist` que não tem nada a ver com a política.
    app = SocialApp(
        provider="google",
        client_id=settings.GOOGLE_CLIENT_ID or "id-de-teste",
        secret=settings.GOOGLE_CLIENT_SECRET or "segredo-de-teste",
    )
    login_social = SocialLogin(
        user=usuario, account=conta, provider=classe(request=None, app=app)
    )
    login_social.email_addresses = [
        EmailAddress(email=email, verified=verificado, primary=True)
    ]
    return login_social


class BotaoGoogleTests(TestCase):
    """O botão nas duas telas de entrada, e o que acontece sem credencial."""

    @override_settings(GOOGLE_LOGIN_ENABLED=True)
    def test_the_button_shows_on_both_entry_screens(self):
        for rota in ("accounts:login", "accounts:signup"):
            with self.subTest(rota=rota):
                html = self.client.get(reverse(rota)).content.decode()
                self.assertIn("Continuar com Google", html)
                self.assertIn(reverse("google_login"), html)

    @override_settings(GOOGLE_LOGIN_ENABLED=False)
    def test_without_credentials_the_button_is_simply_absent(self):
        """Um deploy sem a variável não pode mostrar um botão que leva a um erro
        do Google — e também não pode derrubar a tela."""
        for rota in ("accounts:login", "accounts:signup"):
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(rota))
                self.assertEqual(resposta.status_code, 200)
                self.assertNotIn("Continuar com Google", resposta.content.decode())

    @override_settings(GOOGLE_LOGIN_ENABLED=True)
    def test_the_button_posts_instead_of_linking(self):
        """Link abriria o fluxo por GET, sem CSRF: qualquer página de terceiro
        dispararia um login pelo navegador de quem só passou por ela."""
        html = self.client.get(reverse("accounts:login")).content.decode()
        # A tag de abertura do formulário do Google, inteira.
        abertura = html.split('class="google-entrada"', 1)[1].split(">", 1)[0]
        corpo = html.split('class="google-entrada"', 1)[1].split("</form>", 1)[0]

        self.assertIn('method="post"', abertura)
        self.assertIn("csrfmiddlewaretoken", corpo)
        # E nenhum `<a href>` para a rota, que seria a mesma porta sem token.
        self.assertNotIn('<a href="%s"' % reverse("google_login"), html)

    @override_settings(GOOGLE_LOGIN_ENABLED=True)
    def test_no_credential_ever_reaches_the_page(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertNotIn("client_id", html)
        self.assertNotIn("secret", html.lower())


class PoliticaDeVinculoTests(TestCase):
    """Os quatro casos da política, exercitados pelo adapter.

    Cada teste chama `pre_social_login` diretamente. É o ponto onde a decisão
    acontece, e testá-lo direto isola a POLÍTICA do transporte OAuth — que é da
    biblioteca e já tem testes dela.
    """

    def setUp(self):
        from accounts.adapters import NutriPlanSocialAccountAdapter

        self.adapter = NutriPlanSocialAccountAdapter()
        self.pedido = RequestFactory().get("/conta/google/login/callback/")
        SessionMiddleware(lambda r: None).process_request(self.pedido)
        self.pedido.session.save()
        # `messages` precisa de um lugar para escrever fora do ciclo normal.
        setattr(self.pedido, "_messages", FallbackStorage(self.pedido))

    # -- caso 1 ------------------------------------------------------------

    def test_an_unknown_email_is_left_for_allauth_to_create(self):
        """Sem usuário com aquele e-mail, o adapter não intervém: quem cria a
        conta é o allauth, e criar aqui seria uma segunda implementação."""
        self.adapter.pre_social_login(self.pedido, _sociallogin())
        self.assertFalse(User.objects.filter(email="pessoa@gmail.com").exists())

    # -- caso 2 ------------------------------------------------------------

    def test_an_existing_link_is_not_touched(self):
        from allauth.socialaccount.models import SocialAccount

        user = User.objects.create_user(email="volta@gmail.com", password="x-forte-123")
        SocialAccount.objects.create(user=user, provider="google", uid="uid-recorrente")

        login_social = _sociallogin(email="volta@gmail.com", uid="uid-recorrente")
        login_social.lookup()  # é o que marca `is_existing`

        self.adapter.pre_social_login(self.pedido, login_social)
        self.assertEqual(SocialAccount.objects.filter(user=user).count(), 1)

    # -- caso 3 ------------------------------------------------------------

    def test_an_account_without_a_usable_password_links_on_its_own(self):
        """Não há senha para contornar: aquela conta só pode ter nascido de um
        fluxo social ou do admin."""
        from allauth.socialaccount.models import SocialAccount

        user = User.objects.create_user(email="sem-senha@gmail.com")
        user.set_unusable_password()
        user.save()

        self.adapter.pre_social_login(
            self.pedido, _sociallogin(email="sem-senha@gmail.com", uid="uid-3")
        )
        self.assertTrue(
            SocialAccount.objects.filter(user=user, provider="google", uid="uid-3").exists()
        )

    # -- caso 4 ------------------------------------------------------------

    def test_an_account_with_a_password_is_never_linked_automatically(self):
        """A trava central desta feature.

        O NutriPlan não tem recuperação de senha, então controlar o e-mail não é
        um fator de autenticação aqui. Vincular sozinho criaria uma porta para a
        conta que não existia.
        """
        from allauth.socialaccount.models import SocialAccount

        user = User.objects.create_user(email="com-senha@gmail.com", password="senha-forte-123")

        with self.assertRaises(ImmediateHttpResponse) as capturado:
            self.adapter.pre_social_login(
                self.pedido, _sociallogin(email="com-senha@gmail.com", uid="uid-4")
            )

        self.assertEqual(capturado.exception.response.status_code, 302)
        self.assertIn(reverse("accounts:conectar_google"), capturado.exception.response["Location"])
        self.assertFalse(SocialAccount.objects.filter(user=user).exists())
        self.assertIn(SESSAO_VINCULO, self.pedido.session)

    def test_it_never_creates_a_second_account_for_the_same_email(self):
        User.objects.create_user(email="unico@gmail.com", password="senha-forte-123")

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(
                self.pedido, _sociallogin(email="unico@gmail.com", uid="uid-dup")
            )

        self.assertEqual(User.objects.filter(email__iexact="unico@gmail.com").count(), 1)

    # -- recusas -----------------------------------------------------------

    def test_an_unverified_email_is_refused(self):
        """E-mail não verificado é texto que o provedor não garante: aceitá-lo
        permitiria a qualquer conta Google reivindicar qualquer endereço."""
        with self.assertRaises(ImmediateHttpResponse) as capturado:
            self.adapter.pre_social_login(
                self.pedido, _sociallogin(verificado=False)
            )
        self.assertIn(reverse("accounts:login"), capturado.exception.response["Location"])

    def test_a_deactivated_account_cannot_get_in_or_be_linked(self):
        """O Google não reativa conta. E vincular a uma desativada seria deixar
        a porta pronta para quando ela voltasse."""
        from allauth.socialaccount.models import SocialAccount

        user = User.objects.create_user(email="off@gmail.com", password="senha-forte-123")
        user.is_active = False
        user.save()

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(
                self.pedido, _sociallogin(email="off@gmail.com", uid="uid-off")
            )
        self.assertFalse(SocialAccount.objects.filter(user=user).exists())
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_the_refusal_never_says_which_wall_was_hit(self):
        """"E-mail não verificado" e "conta desativada" contam coisas diferentes
        sobre quem está do outro lado, e as duas contam demais."""
        from django.contrib.messages import get_messages

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(self.pedido, _sociallogin(verificado=False))

        textos = [str(m) for m in get_messages(self.pedido)]
        self.assertEqual(textos, ["Não foi possível entrar com o Google. Tente novamente."])
        for vazamento in ("verific", "desativ", "OAuth", "SocialLogin", "state"):
            self.assertNotIn(vazamento, " ".join(textos))

    # -- caixa alta --------------------------------------------------------

    def test_a_different_casing_finds_the_same_account(self):
        """`User.email` é `unique=True`, e a unicidade do Postgres diferencia
        maiúsculas: sem `iexact` aqui, o login social criaria a segunda conta
        que o formulário de cadastro recusaria."""
        User.objects.create_user(email="ana@gmail.com", password="senha-forte-123")

        with self.assertRaises(ImmediateHttpResponse):
            self.adapter.pre_social_login(
                self.pedido, _sociallogin(email="Ana@Gmail.com", uid="uid-caixa")
            )
        self.assertEqual(User.objects.count(), 1)


#: Credenciais de mentira para os testes que precisam do provedor montado.
#:
#: Desserializar um `SocialLogin` faz o allauth procurar o app do provedor, e
#: sem `client_id` ele não acha nenhum. Em produção há credencial; aqui ela é
#: falsa e explícita — nenhum valor real entra em teste, e o teste do caminho
#: SEM credencial existe à parte, em `BotaoGoogleTests`.
GOOGLE_DE_TESTE = {
    "GOOGLE_LOGIN_ENABLED": True,
    "GOOGLE_CLIENT_ID": "id-de-teste.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "segredo-de-teste",
    "SOCIALACCOUNT_PROVIDERS": {
        "google": {
            "APP": {
                "client_id": "id-de-teste.apps.googleusercontent.com",
                "secret": "segredo-de-teste",
                "key": "",
            },
            "SCOPE": ["openid", "email", "profile"],
        }
    },
}


@override_settings(**GOOGLE_DE_TESTE)
class ConectarGoogleTests(TestCase):
    """A tela do caso 4: confirmar a senha para conectar."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="dono@gmail.com", password="senha-bem-forte-123"
        )
        self.url = reverse("accounts:conectar_google")

    def _com_pendencia(self, uid="uid-tela"):
        from accounts.adapters import pendencia

        sessao = self.client.session
        sessao[SESSAO_VINCULO] = pendencia(
            _sociallogin(email="dono@gmail.com", uid=uid), self.user
        )
        sessao.save()

    def test_without_a_pending_attempt_the_url_goes_nowhere(self):
        """Alguém abriu o endereço direto, ou a sessão expirou."""
        resposta = self.client.get(self.url)
        self.assertRedirects(resposta, reverse("accounts:login"))

    def test_it_shows_the_email_and_asks_only_for_the_password(self):
        self._com_pendencia()
        html = self.client.get(self.url).content.decode()

        self.assertIn("dono@gmail.com", html)
        self.assertIn("já tem uma conta", html)
        # Um campo só. E-mail editável aqui deixaria o cliente escolher a qual
        # conta se conectar, que é o que esta tela existe para impedir.
        self.assertEqual(html.count('type="password"'), 1)
        self.assertNotIn('type="email"', html)

    def test_a_wrong_password_links_nothing_and_lets_you_try_again(self):
        from allauth.socialaccount.models import SocialAccount

        self._com_pendencia()
        resposta = self.client.post(self.url, {"password": "chute-errado-999"})

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Senha incorreta")
        self.assertFalse(SocialAccount.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        # A tentativa FICA: refazer o Google inteiro por um erro de digitação
        # seria punir o dedo trocado.
        self.assertIn(SESSAO_VINCULO, self.client.session)

    def test_the_right_password_links_to_that_very_account_and_signs_in(self):
        from allauth.socialaccount.models import SocialAccount

        self._com_pendencia(uid="uid-certo")
        resposta = self.client.post(self.url, {"password": "senha-bem-forte-123"})

        self.assertRedirects(
            resposta, reverse("accounts:onboarding"), fetch_redirect_response=False
        )
        self.assertEqual(
            SocialAccount.objects.filter(
                user=self.user, provider="google", uid="uid-certo"
            ).count(),
            1,
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(User.objects.count(), 1)

    def test_the_pending_attempt_is_cleared_once_it_is_used(self):
        """Estado pendente que sobrevive ao uso é estado que alguém reaproveita."""
        self._com_pendencia()
        self.client.post(self.url, {"password": "senha-bem-forte-123"})
        self.assertNotIn(SESSAO_VINCULO, self.client.session)

    def test_a_tampered_session_is_discarded_instead_of_crashing(self):
        sessao = self.client.session
        sessao[SESSAO_VINCULO] = {"lixo": True}
        sessao.save()

        resposta = self.client.get(self.url)
        self.assertRedirects(resposta, reverse("accounts:login"))

    def test_no_token_of_any_kind_reaches_the_page(self):
        self._com_pendencia()
        html = self.client.get(self.url).content.decode()
        for segredo in ("access_token", "id_token", "refresh_token", "client_secret"):
            self.assertNotIn(segredo, html)


class GoogleNoDemoTests(TestCase):
    """O login social não pode existir sob `/demo/`.

    O middleware do demo monta o app inteiro sob o prefixo, troca
    `request.user` pela persona e recusa tudo que não é GET. O callback do
    OAuth é um GET — e callback com usuário autenticado é exatamente a condição
    de VINCULAR. Sem esta trava, alguém conectaria a própria conta Google ao
    Carlos e entraria nela pelo app real.

    Nada disso daria erro. O vínculo é silencioso.
    """

    @classmethod
    def setUpTestData(cls):
        # A mesma ordem de `demo/tests.py`: o `seed_demo` monta a ficha do
        # Carlos com as funções reais, e elas precisam do catálogo antes.
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)
        call_command("seed_demo", verbosity=0)

    def test_starting_the_flow_through_the_demo_is_refused(self):
        for rota in ("/demo/conta/google/login/", "/demo/conta/google/login/callback/"):
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertContains(resposta, "não funciona no demo", status_code=200)

    def test_the_callback_through_the_demo_links_nothing(self):
        from allauth.socialaccount.models import SocialAccount

        self.client.get("/demo/conta/google/login/callback/?code=abc&state=xyz")
        self.assertFalse(SocialAccount.objects.exists())

    def test_the_demo_persona_is_untouched(self):
        from allauth.socialaccount.models import SocialAccount

        self.client.get("/demo/conta/google/login/")
        carlos = User.objects.get(email="carlos.demo@nutriplan.invalid")
        self.assertFalse(SocialAccount.objects.filter(user=carlos).exists())

    def test_the_password_confirmation_screen_is_refused_too(self):
        """Ela conecta um vínculo. Sob o demo, conectaria à persona."""
        resposta = self.client.get("/demo/conta/conectar-google/")
        self.assertContains(resposta, "não funciona no demo", status_code=200)

    def test_every_social_route_the_project_registers_is_refused(self):
        """A lista do middleware é conferida contra o URLconf REAL.

        Escrever a lista à mão e confiar nela é como ela envelhece: o allauth
        registra mais rotas do que as óbvias — `login/token/`, `signup/`,
        `login/error/` — e um provedor novo traria as dele. Este teste varre o
        resolvedor e cobra cada uma.

        Foi assim que apareceu a que faltava: `socialaccount_connections` está
        no caminho VAZIO de `allauth.socialaccount.urls` e, montado direto sob
        `conta/`, respondia 200 sob `/demo/conta/` com a tela "contas
        conectadas" da biblioteca renderizada para a persona.
        """
        from django.urls import get_resolver

        from demo.middleware import RECUSADAS

        def caminhos(resolver, prefixo=""):
            for padrao in resolver.url_patterns:
                alvo = prefixo + str(padrao.pattern)
                if hasattr(padrao, "url_patterns"):
                    yield from caminhos(padrao, alvo)
                else:
                    yield "/" + alvo, getattr(padrao, "name", None)

        passam = [
            url
            for url, nome in caminhos(get_resolver())
            # O admin fica de fora: ele já era alcançável sob `/demo/` antes
            # desta feature, e a persona não é `staff` — o próprio admin a
            # manda para o login dele.
            if not url.startswith("/admin/")
            and ("google" in url or "social" in url or "conectar-google" in url)
            and not url.startswith(RECUSADAS)
        ]
        self.assertEqual(passam, [], "rota social alcançável pelo demo")

    def test_the_library_connections_screen_is_not_at_the_account_root(self):
        """`/conta/` era 404 e não pode virar tela da biblioteca."""
        self.assertContains(
            self.client.get("/demo/conta/social/"), "não funciona no demo", status_code=200
        )

    def test_the_demo_itself_still_works(self):
        for rota in ("/demo/", "/demo/hoje/", "/demo/treino/", "/demo/conta/perfil/"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)


class AutenticacaoTradicionalIntactaTests(TestCase):
    """O que existia antes continua exatamente como era.

    A feature acrescenta um caminho; não pode mexer no que já havia.
    """

    def test_signing_up_with_email_and_password_still_works(self):
        resposta = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Tradicional",
                "email": "tradicional@exemplo.com",
                "password1": "senha-bem-forte-123",
                "password2": "senha-bem-forte-123",
            },
        )
        self.assertRedirects(
            resposta,
            reverse("accounts:onboarding_step", kwargs={"step": 1}),
            fetch_redirect_response=False,
        )
        self.assertTrue(User.objects.filter(email="tradicional@exemplo.com").exists())

    def test_logging_in_with_email_and_password_still_works(self):
        User.objects.create_user(email="volta@exemplo.com", password="senha-bem-forte-123")
        resposta = self.client.post(
            reverse("accounts:login"),
            {"username": "volta@exemplo.com", "password": "senha-bem-forte-123"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_getting_the_password_wrong_shows_the_form_again_and_not_a_500(self):
        """O caminho MAIS percorrido de qualquer tela de login, e o que a
        primeira versão desta feature quebrou.

        Com senha certa o `ModelBackend` responde primeiro e nada mais roda —
        por isso o teste do caminho feliz passava. Com senha errada ele devolve
        `None`, o Django cai no backend do allauth, e ele filtrava por um campo
        `username` que este modelo não tem: `FieldError`, 500 na cara de quem
        errou uma letra.

        Consertado por `ACCOUNT_USER_MODEL_USERNAME_FIELD = None` e
        `ACCOUNT_LOGIN_METHODS = {"email"}`.
        """
        User.objects.create_user(email="erra@exemplo.com", password="senha-bem-forte-123")
        resposta = self.client.post(
            reverse("accounts:login"),
            {"username": "erra@exemplo.com", "password": "chute-errado-999"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_an_email_that_does_not_exist_also_fails_cleanly(self):
        resposta = self.client.post(
            reverse("accounts:login"),
            {"username": "ninguem@exemplo.com", "password": "qualquer-coisa-123"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_allauth_knows_this_model_has_no_username(self):
        """A configuração que sustenta os dois testes acima."""
        self.assertIsNone(settings.ACCOUNT_USER_MODEL_USERNAME_FIELD)
        self.assertEqual(set(settings.ACCOUNT_LOGIN_METHODS), {"email"})

    def test_the_model_backend_is_still_first(self):
        """Ele é quem autentica e-mail e senha. O do allauth entra ao lado, não
        no lugar."""
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS[0],
            "django.contrib.auth.backends.ModelBackend",
        )

    def test_logging_out_still_ends_the_local_session(self):
        User.objects.create_user(email="sai@exemplo.com", password="senha-bem-forte-123")
        self.client.login(username="sai@exemplo.com", password="senha-bem-forte-123")
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ConfiguracaoDoGoogleTests(TestCase):
    """As decisões de configuração que sustentam a política."""

    def test_email_authentication_stays_off(self):
        """O interruptor que entraria na frente da tela de senha.

        Ligá-lo faria o allauth entrar na conta local só porque o e-mail bate —
        que é exatamente o caso 4, e exatamente o que a política recusa.
        """
        self.assertFalse(settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION)
        self.assertFalse(settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT)

    def test_tokens_are_not_stored(self):
        """Guardar `access_token` seria guardar credencial de acesso à conta
        Google de alguém para nunca mais usar."""
        self.assertFalse(settings.SOCIALACCOUNT_STORE_TOKENS)

    def test_only_the_three_minimum_scopes_are_asked_for(self):
        escopos = settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"]
        self.assertEqual(sorted(escopos), ["email", "openid", "profile"])

    def test_the_credentials_come_from_the_environment(self):
        """Nunca do banco: o plano gratuito do Render apaga o banco por volta de
        23/09/2026, e credencial que mora nele some junto."""
        app = settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]
        self.assertEqual(app["client_id"], settings.GOOGLE_CLIENT_ID)
        self.assertEqual(app["secret"], settings.GOOGLE_CLIENT_SECRET)

    def test_the_library_screens_are_not_mounted(self):
        """O allauth entra como MOTOR, não como interface: uma segunda tela de
        login nasceria igual e divergiria na primeira correção."""
        from django.urls import NoReverseMatch

        for nome in ("account_login", "account_signup", "account_reset_password"):
            with self.subTest(rota=nome):
                with self.assertRaises(NoReverseMatch):
                    reverse(nome)

    def test_the_callback_lives_where_the_google_console_will_be_told(self):
        """O endereço é derivado do ponto de montagem. Se ele mudar, o Google
        recusa com `redirect_uri_mismatch` — e este teste avisa antes."""
        self.assertEqual(reverse("google_callback"), "/conta/google/login/callback/")
        self.assertEqual(reverse("google_login"), "/conta/google/login/")

    def test_sites_framework_was_not_dragged_in(self):
        """Esta versão do allauth detecta `sites` sozinha e vive sem ele."""
        self.assertNotIn("django.contrib.sites", settings.INSTALLED_APPS)


@override_settings(**GOOGLE_DE_TESTE)
class ContaDesativadaComGoogleTests(TestCase):
    """Conta desativada que JÁ tem Google vinculado — o caso 2 pelo avesso.

    Este é o caminho que a revisão pegou e que os outros testes não tocavam:
    eles chamavam `pre_social_login` direto com um vínculo NOVO, e aí o adapter
    resolve. Com o vínculo já existente o adapter não intervém — quem confere
    `is_active` é o `perform_login` da biblioteca, chamando
    `respond_user_inactive`.

    E o padrão dele faz `reverse("account_inactive")`, rota que mora em
    `allauth.account.urls` — que este projeto não monta. O resultado era um
    `NoReverseMatch` que ninguém captura, e a pessoa recebia 500 em vez de uma
    recusa. `is_active` é campo editável no admin: qualquer conta desativada
    depois de conectar o Google cairia nisso.
    """

    def test_refusing_an_inactive_user_does_not_need_a_route_we_never_mounted(self):
        from accounts.adapters import NutriPlanAccountAdapter

        pedido = RequestFactory().get("/conta/google/login/callback/")
        SessionMiddleware(lambda r: None).process_request(pedido)
        pedido.session.save()
        setattr(pedido, "_messages", FallbackStorage(pedido))

        user = User.objects.create_user(email="off2@gmail.com", password="senha-forte-123")
        user.is_active = False
        user.save()

        # Sem o adapter próprio, esta linha levantaria NoReverseMatch.
        resposta = NutriPlanAccountAdapter().respond_user_inactive(pedido, user)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_the_route_the_library_wanted_really_does_not_exist(self):
        """Se um dia alguém montar `allauth.account.urls`, este teste avisa que
        o adapter acima virou desnecessário — e que apareceu uma segunda tela
        de login junto."""
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("account_inactive")


@override_settings(**GOOGLE_DE_TESTE)
class ForcaBrutaNaConfirmacaoTests(TestCase):
    """A confirmação de senha do caso 4 não pode ser um campo de chute infinito.

    Quem chega nessa tela já completou um login Google de verdade — ou seja,
    controla a caixa de entrada e o e-mail está confirmado. É exatamente a
    ameaça que o caso 4 existe para conter. Sem limite, a tentativa pendente
    fica na sessão e o atacante chuta a senha sem repetir o Google: a última
    defesa da conta vira um formulário de força bruta.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="alvo@gmail.com", password="senha-bem-forte-123"
        )
        self.url = reverse("accounts:conectar_google")
        from accounts.adapters import pendencia

        sessao = self.client.session
        sessao[SESSAO_VINCULO] = pendencia(
            _sociallogin(email="alvo@gmail.com", uid="uid-bruta"), self.user
        )
        sessao.save()

    def test_the_pending_attempt_survives_a_typo(self):
        """Descartar no primeiro erro obrigaria a refazer o Google inteiro por
        um dedo trocado."""
        self.client.post(self.url, {"password": "errada-1"})
        self.assertIn(SESSAO_VINCULO, self.client.session)

    def test_it_gives_up_after_a_handful_of_wrong_guesses(self):
        from allauth.socialaccount.models import SocialAccount

        for tentativa in range(MAXIMO_DE_TENTATIVAS):
            resposta = self.client.post(self.url, {"password": "errada-%d" % tentativa})

        # A última recusa descarta a pendência e manda para a porta.
        self.assertRedirects(resposta, reverse("accounts:login"))
        self.assertNotIn(SESSAO_VINCULO, self.client.session)
        self.assertFalse(SocialAccount.objects.exists())

        # E aí a tela não abre mais: é preciso refazer o Google.
        self.assertRedirects(self.client.get(self.url), reverse("accounts:login"))

    def test_the_counter_resets_once_the_link_succeeds(self):
        """Senão, um erro hoje encurtaria a margem de amanhã."""
        self.client.post(self.url, {"password": "errada-1"})
        self.client.post(self.url, {"password": "senha-bem-forte-123"})
        self.assertNotIn(SESSAO_TENTATIVAS, self.client.session)


#: Marcadores falsos e fáceis de procurar. Se algum aparecer onde não deve, o
#: teste diz exatamente qual credencial vazou.
ACCESS_FALSO = "TOKEN-SECRETO-DE-TESTE"
REFRESH_FALSO = "REFRESH-SECRETO-DE-TESTE"


@override_settings(**GOOGLE_DE_TESTE)
class CredencialNuncaEncostaNaSessaoTests(TestCase):
    """Nenhuma credencial OAuth pode ficar guardada em lugar nenhum.

    A primeira implementação guardava `sociallogin.serialize()` na sessão,
    porque é o mecanismo oficial do allauth para o fluxo de cadastro dele. Lido
    o código instalado (`socialaccount/models.py`), ele faz:

        if self.token:
            ret["token"] = serialize_instance(self.token)

    e `SocialToken` tem `token` (access) e `token_secret` (refresh) como campos
    de texto. Provado em runtime: os dois apareciam.

    Estes testes são a prova permanente de que não aparecem mais.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="cred@gmail.com", password="senha-bem-forte-123"
        )
        self.login_social = _sociallogin(email="cred@gmail.com", uid="uid-cred")
        # O token que o fluxo real traz junto.
        from allauth.socialaccount.models import SocialToken

        self.login_social.token = SocialToken(
            token=ACCESS_FALSO, token_secret=REFRESH_FALSO
        )

    def _pendencia(self):
        from accounts.adapters import pendencia

        return pendencia(self.login_social, self.user)

    def test_the_library_serialisation_really_does_carry_the_token(self):
        """A prova do problema, e o motivo de não voltarmos a usá-la.

        Se um dia o allauth parar de serializar o token, este teste falha — e
        aí a decisão pode ser revista com evidência, em vez de por memória.
        """
        bruto = json.dumps(self.login_social.serialize(), default=str)
        self.assertIn(ACCESS_FALSO, bruto)
        self.assertIn(REFRESH_FALSO, bruto)

    def test_what_we_actually_store_carries_no_credential(self):
        bruto = json.dumps(self._pendencia(), default=str)
        for marcador in (ACCESS_FALSO, REFRESH_FALSO):
            self.assertNotIn(marcador, bruto)

    def test_what_we_store_is_only_the_identity(self):
        """Quatro campos, e nenhum a mais. Um campo novo aqui é uma decisão."""
        self.assertEqual(
            sorted(self._pendencia()), ["email", "provider", "uid", "user_pk"]
        )

    def test_the_uid_and_not_the_email_is_the_permanent_identity(self):
        """E-mail muda; o `sub` do Google não."""
        guardado = self._pendencia()
        self.assertEqual(guardado["uid"], "uid-cred")
        self.assertEqual(guardado["provider"], "google")

    def test_no_credential_reaches_the_session_store(self):
        """Fim a fim: o que o servidor grava na sessão, lido do banco."""
        from django.contrib.sessions.models import Session

        sessao = self.client.session
        sessao[SESSAO_VINCULO] = self._pendencia()
        sessao.save()

        cru = Session.objects.get(session_key=sessao.session_key).session_data
        decodificado = json.dumps(
            SessionStore().decode(cru), default=str
        )
        for marcador in (ACCESS_FALSO, REFRESH_FALSO):
            self.assertNotIn(marcador, decodificado)

    def test_no_credential_reaches_the_page(self):
        sessao = self.client.session
        sessao[SESSAO_VINCULO] = self._pendencia()
        sessao.save()

        html = self.client.get(reverse("accounts:conectar_google")).content.decode()
        for marcador in (
            ACCESS_FALSO,
            REFRESH_FALSO,
            "access_token",
            "id_token",
            "refresh_token",
            "client_secret",
        ):
            self.assertNotIn(marcador, html)

    def test_no_social_token_is_ever_persisted(self):
        """`SOCIALACCOUNT_STORE_TOKENS = False`, provado pelo banco e não pela
        leitura da configuração."""
        from allauth.socialaccount.models import SocialToken

        sessao = self.client.session
        sessao[SESSAO_VINCULO] = self._pendencia()
        sessao.save()

        self.client.post(
            reverse("accounts:conectar_google"), {"password": "senha-bem-forte-123"}
        )

        self.assertEqual(SocialToken.objects.count(), 0)
        # E o vínculo em si aconteceu, senão o teste acima passaria à toa.
        self.assertTrue(
            SocialAccount.objects.filter(
                user=self.user, provider="google", uid="uid-cred"
            ).exists()
        )

    def test_linking_twice_produces_a_single_link(self):
        """A unicidade é `(provider, uid)` no modelo do allauth, e o
        `get_or_create` se apoia nela: dois envios simultâneos não podem
        produzir dois vínculos nem estourar."""
        for _ in range(2):
            sessao = self.client.session
            sessao[SESSAO_VINCULO] = self._pendencia()
            sessao.save()
            self.client.post(
                reverse("accounts:conectar_google"), {"password": "senha-bem-forte-123"}
            )

        self.assertEqual(SocialAccount.objects.filter(user=self.user).count(), 1)
        self.assertEqual(User.objects.filter(email__iexact="cred@gmail.com").count(), 1)

    def test_a_changed_email_aborts_instead_of_linking_to_the_wrong_account(self):
        """O `pk` diz qual conta; o e-mail diz que ela ainda é a mesma que o
        Google confirmou. Se a conta trocar de e-mail entre a ida e a volta, o
        vínculo é abortado."""
        sessao = self.client.session
        sessao[SESSAO_VINCULO] = self._pendencia()
        sessao.save()

        self.user.email = "outro@gmail.com"
        self.user.save()

        resposta = self.client.get(reverse("accounts:conectar_google"))
        self.assertRedirects(resposta, reverse("accounts:login"))
        self.assertFalse(SocialAccount.objects.exists())


@override_settings(**GOOGLE_DE_TESTE)
class EscopoRealDoLimiteTests(TestCase):
    """O que o limite de tentativas cobre — e o que ele deixa aberto.

    Estes testes existem para a afirmação "tem limite de 5 tentativas" não
    virar uma promessa maior do que é. O limite é POR PENDÊNCIA, e quem
    controla a caixa de entrada pode refazer o handshake e ganhar mais cinco.

    O que o limite compra é custo por tentativa. O que ele não é: proteção
    completa contra força bruta. A correção de verdade é rate limiting global
    cobrindo login e linking, com cache compartilhado — o allauth traz um, mas
    ele depende de `django.core.cache`, é declaradamente não atômico, e este
    projeto não configura `CACHES`.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="escopo@gmail.com", password="senha-bem-forte-123"
        )
        self.url = reverse("accounts:conectar_google")

    def _nova_pendencia(self):
        """Simula refazer o handshake: o adapter escreve a pendência de novo."""
        from accounts.adapters import pendencia

        sessao = self.client.session
        sessao[SESSAO_VINCULO] = pendencia(
            _sociallogin(email="escopo@gmail.com", uid="uid-escopo"), self.user
        )
        sessao.save()

    def test_a_fresh_handshake_grants_a_fresh_allowance(self):
        """A limitação honesta, provada em vez de descrita.

        Se um dia isto passar a falhar, é porque alguém acrescentou um limite
        que atravessa pendências — e aí a documentação acima precisa mudar
        junto.
        """
        for rodada in range(2):
            self._nova_pendencia()
            for tentativa in range(MAXIMO_DE_TENTATIVAS):
                self.client.post(self.url, {"password": "errada-%d" % tentativa})
            # Esgotou: a pendência foi descartada.
            self.assertNotIn(SESSAO_VINCULO, self.client.session)

        # Dez chutes no total, e a conta segue intacta e sem vínculo.
        self.assertFalse(SocialAccount.objects.exists())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("senha-bem-forte-123"))

    def test_the_traditional_login_has_no_limit_at_all(self):
        """A comparação que dá tamanho ao risco.

        A tela de entrar aceita chutes ilimitados e não exige handshake nenhum.
        A confirmação de vínculo, mesmo com a brecha acima, é a superfície de
        força bruta MENOS exposta das duas — não a mais.

        Este teste não aprova a ausência de limite no login; ele registra que
        ela existe, para a próxima missão de rate limiting achar os dois
        endpoints em vez de um.
        """
        for tentativa in range(12):
            resposta = self.client.post(
                reverse("accounts:login"),
                {"username": "escopo@gmail.com", "password": "errada-%d" % tentativa},
            )
        # Nenhum bloqueio, nenhum 429: continua devolvendo o formulário.
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class OnboardingV21Tests(TestCase):
    """A V2.1 mexeu em ONDE se responde, e em nada do que é respondido.

    Duas mudanças: os sete dias viraram chips e a janela de sono saiu do passo
    da comida para o passo da rotina. Nenhuma toca model, valor, validação ou
    número de passos — e é exatamente isso que esta classe existe para provar,
    porque "só mexi no visual" é a frase que antecede a regressão silenciosa.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="v21@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)

    def perfil(self):
        return Profile.objects.get(user=self.user)

    # A ------------------------------------------------------------- valores
    def test_os_dias_continuam_saindo_como_inteiros_de_weekday(self):
        """O chip é rótulo; o que trafega é o mesmo inteiro de antes.

        Se a abreviação tivesse virado o valor enviado, o `coerce=int` estouraria
        — e um formulário que estoura no primeiro dia de uso é melhor que um que
        grava "Seg" numa coluna de inteiro, mas nenhum dos dois pode acontecer.
        """
        self.client.post(step_url(3), STEP3)

        dias = sorted(self.user.training_days.values_list("weekday", flat=True))
        self.assertEqual(dias, [0, 2, 4])
        self.assertTrue(all(isinstance(d, int) for d in dias))

    # B -------------------------------------------------------- vários dias
    def test_marcar_a_semana_inteira_grava_os_sete(self):
        self.client.post(
            step_url(3), {**STEP3, "weekdays": ["0", "1", "2", "3", "4", "5", "6"]}
        )
        self.assertEqual(self.user.training_days.count(), 7)

    def test_desmarcar_um_dia_remove_so_ele(self):
        self.client.post(step_url(3), {**STEP3, "weekdays": ["0", "2", "4"]})
        self.client.post(step_url(3), {**STEP3, "weekdays": ["0", "4"]})

        self.assertEqual(
            sorted(self.user.training_days.values_list("weekday", flat=True)), [0, 4]
        )

    # C -------------------------------------------------------- sem mínimo
    def test_nenhum_dia_continua_sendo_resposta_aceita(self):
        """Não havia mínimo nem máximo antes, e continua não havendo.

        O campo é `required=False` de propósito: quem ainda não treina precisa
        conseguir passar da tela. Inventar um mínimo agora seria mudar a regra
        no meio de uma missão que prometeu não mudar nenhuma.
        """
        response = self.client.post(step_url(3), {**STEP3, "weekdays": []})

        # Zero dias também pula a divisão: sem treino nenhum, nenhuma das três
        # preferências muda o que o app monta.
        self.assertRedirects(response, step_url(5))
        self.assertEqual(self.user.training_days.count(), 0)

    # D / E ------------------------------------------------- voltar e voltar
    def test_voltar_ao_passo_3_traz_a_selecao_marcada(self):
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(4), STEP4)

        html = self.client.get(step_url(3)).content.decode()
        marcados = re.findall(r'<input[^>]*name="weekdays"[^>]*>', html)
        checados = [i for i in marcados if "checked" in i]

        self.assertEqual(len(marcados), 7)
        self.assertEqual(len(checados), 3)
        for valor in ("0", "2", "4"):
            self.assertTrue(
                any(f'value="{valor}"' in i and "checked" in i for i in marcados),
                f"o dia {valor} devia voltar marcado",
            )

    def test_recarregar_o_passo_3_traz_a_janela_salva(self):
        """Retomada: o sono agora vem do Profile, e não do TrainingDay.

        Sem o `initial`, reabrir o passo mostraria os campos vazios e um
        "Continuar" gravaria por cima do que já estava lá.
        """
        self.client.post(
            step_url(3), {**STEP3, "wake_time": "06:15", "sleep_time": "22:10"}
        )

        html = self.client.get(step_url(3)).content.decode()

        # O widget de hora renderiza com segundos ("06:15:00"); o que importa
        # é o campo voltar preenchido com o que foi salvo.
        self.assertIn('name="wake_time" value="06:15:00"', html)
        self.assertIn('name="sleep_time" value="22:10:00"', html)

    # F ---------------------------------------------------------- o sono
    def test_a_janela_do_dia_e_gravada_pelo_passo_3(self):
        self.client.post(
            step_url(3), {**STEP3, "wake_time": "05:45", "sleep_time": "21:20"}
        )

        perfil = self.perfil()
        self.assertEqual(perfil.wake_time, time(5, 45))
        self.assertEqual(perfil.sleep_time, time(21, 20))

    def test_o_passo_5_nao_pergunta_mais_a_janela(self):
        """A prova de que o campo MUDOU de tela, e não de que sumiu.

        Ancorada no formulário do passo, e não no HTML inteiro: procurar
        "wake_time" na página acharia qualquer resquício em script ou rodapé e
        passaria por acidente.
        """
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(4), STEP4)

        campos = self.client.get(step_url(5)).context["form"].fields

        self.assertNotIn("wake_time", campos)
        self.assertNotIn("sleep_time", campos)
        self.assertIn("meal_style", campos)
        self.assertIn("wake_time", self.client.get(step_url(3)).context["form"].fields)

    # G / H ------------------------------------------------- retomada e guarda
    def test_quem_parou_no_passo_3_volta_para_o_passo_3(self):
        self.client.get(reverse("accounts:onboarding"))
        self.assertEqual(self.perfil().onboarding_step, 3)

        response = self.client.get(reverse("accounts:onboarding"))
        self.assertRedirects(response, step_url(3))

    def test_continua_sem_dar_para_pular_etapa(self):
        """A guarda não mudou, e o sono mudar de tela não pode ter aberto atalho."""
        response = self.client.get(step_url(5))
        self.assertRedirects(response, step_url(3))

    # I --------------------------------------------------------- progresso
    def test_o_wizard_continua_com_cinco_passos(self):
        """A V2.1 reorganiza; quem mexe no número de passos é a V2.2."""
        self.assertEqual(ONBOARDING_LAST_STEP, 5)

        contexto = self.client.get(step_url(3)).context
        self.assertEqual(contexto["total_steps"], 5)
        self.assertEqual(contexto["progress_pct"], 60)

    # J ---------------------------------------------------- quem consome
    def test_o_que_o_calculo_le_continua_igual(self):
        """O consumidor não sabe por qual tela a resposta entrou.

        A janela é lida do Profile e os dias do TrainingDay — os mesmos dois
        lugares de antes. Este teste percorre o wizard inteiro pelo caminho
        novo e confere o estado final, que é o que o motor enxerga.
        """
        self.client.post(
            step_url(3), {**STEP3, "wake_time": "06:00", "sleep_time": "23:00"}
        )
        self.client.post(step_url(4), STEP4)
        self.client.post(step_url(5), STEP5)

        perfil = self.perfil()
        self.assertTrue(perfil.onboarding_complete)
        self.assertEqual(perfil.wake_time, time(6, 0))
        self.assertEqual(perfil.sleep_time, time(23, 0))
        self.assertEqual(
            sorted(self.user.training_days.values_list("weekday", flat=True)), [0, 2, 4]
        )
        self.assertEqual(perfil.split_preference, STEP4["split_preference"])
        self.assertEqual(perfil.meal_style, STEP5["meal_style"])

    # ------------------------------------------------------------- os chips
    def test_o_chip_mostra_a_abreviacao_e_fala_o_dia_inteiro(self):
        """Quem enxerga lê "Qua" numa fila de sete; quem ouve precisa do nome.

        Sem o `aria-label`, o leitor de tela anunciaria três letras sem
        contexto nenhum para reconstruir o dia.
        """
        html = self.client.get(step_url(3)).content.decode()

        self.assertIn("choice-list--dias", html)
        self.assertIn(">Qua<", html)
        self.assertIn('aria-label="Quarta-feira"', html)
        # E o nome completo continua sendo o do model, para o resto do app.
        self.assertEqual(Weekday(2).label, "Quarta-feira")


class OnboardingV22Tests(TestCase):
    """O caminho deixou de ser uma fila fixa: ele depende da resposta do passo 3.

    A pergunta de divisão só muda o plano de quem treina quatro dias ou mais —
    até três, as três preferências devolvem a mesma divisão, porque divisão não
    inventa dias que a semana não tem. Perguntar ali custava um passo inteiro e
    não comprava nada.

    O que estes testes protegem não é o número 4: é o fato de a regra ser LIDA
    de `workouts.services`, e de a navegação inteira — voltar, avançar,
    recarregar, retomar, reeditar — entender o caminho que sobrou.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="v22@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.user)
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)

    def dias(self, quantos):
        return {**STEP3, "weekdays": [str(d) for d in range(quantos)]}

    def perfil(self):
        return Profile.objects.get(user=self.user)

    # ------------------------------------------------- a regra vem do domínio
    def test_a_regra_e_lida_da_tabela_de_divisoes(self):
        """Se `SPLIT_BY_PREFERENCE` mudar, o onboarding acompanha sozinho.

        Este teste existe para que ninguém troque a chamada por um `>= 4`
        escrito à mão: o dia em que a tabela ganhar uma faixa nova, o número
        cravado ficaria mentindo em silêncio.
        """
        for poucos in (0, 1, 2, 3):
            self.assertFalse(preferencia_muda_a_divisao(poucos), f"{poucos} dias")
        for muitos in (4, 5, 6, 7):
            self.assertTrue(preferencia_muda_a_divisao(muitos), f"{muitos} dias")

    # ----------------------------------------------------- 1, 2 e 3 dias
    def test_ate_tres_dias_a_divisao_e_pulada(self):
        for quantos in (1, 2, 3):
            with self.subTest(dias=quantos):
                user = User.objects.create_user(
                    email=f"curto{quantos}@exemplo.com", password="senha-bem-forte-123"
                )
                self.client.force_login(user)
                self.client.post(step_url(1), STEP1)
                self.client.post(step_url(2), STEP2)

                resposta = self.client.post(step_url(3), self.dias(quantos))

                self.assertRedirects(resposta, step_url(5))
                self.assertEqual(Profile.objects.get(user=user).onboarding_step, 5)

    def test_quem_pula_a_divisao_nao_consegue_abrir_o_passo_4(self):
        """Não basta não oferecer: digitar a URL também não pode levar lá."""
        self.client.post(step_url(3), self.dias(2))

        resposta = self.client.get(step_url(4))

        self.assertRedirects(resposta, step_url(5))

    def test_o_progresso_conta_quatro_passos_para_quem_pula(self):
        self.client.post(step_url(3), self.dias(2))

        contexto = self.client.get(step_url(5)).context

        self.assertEqual(contexto["total_steps"], 4)
        self.assertEqual(contexto["posicao"], 4)
        self.assertEqual(contexto["progress_pct"], 100)

    # --------------------------------------------------------- 4 e 5+ dias
    def test_de_quatro_dias_em_diante_a_divisao_continua_sendo_perguntada(self):
        for quantos in (4, 5, 6, 7):
            with self.subTest(dias=quantos):
                user = User.objects.create_user(
                    email=f"longo{quantos}@exemplo.com", password="senha-bem-forte-123"
                )
                self.client.force_login(user)
                self.client.post(step_url(1), STEP1)
                self.client.post(step_url(2), STEP2)

                resposta = self.client.post(step_url(3), self.dias(quantos))

                self.assertRedirects(resposta, step_url(4))

    def test_o_progresso_conta_cinco_passos_para_quem_responde_a_divisao(self):
        self.client.post(step_url(3), self.dias(5))

        contexto = self.client.get(step_url(4)).context

        self.assertEqual(contexto["total_steps"], 5)
        self.assertEqual(contexto["posicao"], 4)
        self.assertEqual(contexto["progress_pct"], 80)

    # ------------------------------------------------------------- voltar
    def test_voltar_do_passo_5_pula_a_divisao_de_quem_a_pulou(self):
        """O botão "Voltar" segue o mesmo caminho da ida.

        Sem isto, quem pulou o 4 na ida bateria nele na volta — e o passo que
        o app decidiu esconder reapareceria pela porta dos fundos.
        """
        self.client.post(step_url(3), self.dias(2))

        anterior = self.client.get(step_url(5)).context["previous_url"]

        self.assertEqual(anterior, step_url(3))

    def test_voltar_do_passo_5_cai_na_divisao_de_quem_a_respondeu(self):
        self.client.post(step_url(3), self.dias(5))
        self.client.post(step_url(4), STEP4)

        anterior = self.client.get(step_url(5)).context["previous_url"]

        self.assertEqual(anterior, step_url(4))

    # ------------------------------------------------- recarregar e retomar
    def test_recarregar_mantem_a_pessoa_no_mesmo_passo(self):
        self.client.post(step_url(3), self.dias(2))

        primeira = self.client.get(step_url(5))
        segunda = self.client.get(step_url(5))

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(segunda.context["posicao"], 4)

    def test_retomar_leva_ao_passo_certo_do_caminho_curto(self):
        self.client.post(step_url(3), self.dias(3))

        resposta = self.client.get(reverse("accounts:onboarding"))

        self.assertRedirects(resposta, step_url(5))

    def test_quem_parou_no_passo_4_e_depois_reduziu_os_dias_nao_trava(self):
        """O caso que faria o app entrar em laço.

        A pessoa parou no 4 treinando cinco dias. Voltou ao 3, reduziu para
        dois — e agora o progresso salvo aponta para um passo que sumiu do
        caminho dela. Sem o mapeamento, a entrada mandaria para o 4, a guarda
        devolveria para a entrada, e assim por diante.
        """
        self.client.post(step_url(3), self.dias(5))
        self.assertEqual(self.perfil().onboarding_step, 4)

        self.client.post(step_url(3), self.dias(2))

        entrada = self.client.get(reverse("accounts:onboarding"))
        self.assertRedirects(entrada, step_url(5))
        self.assertEqual(self.client.get(step_url(5)).status_code, 200)

    def test_aumentar_os_dias_traz_a_divisao_de_volta(self):
        self.client.post(step_url(3), self.dias(2))
        self.assertRedirects(self.client.get(step_url(4)), step_url(5))

        self.client.post(step_url(3), self.dias(5))

        self.assertEqual(self.client.get(step_url(4)).status_code, 200)

    # --------------------------------------------------- edição posterior
    def test_quem_ja_terminou_reedita_pelo_caminho_dele(self):
        self.client.post(step_url(3), self.dias(2))
        self.client.post(step_url(5), STEP5)
        self.assertTrue(self.perfil().onboarding_complete)

        self.assertEqual(self.client.get(step_url(1)).status_code, 200)
        self.assertEqual(self.client.get(step_url(3)).status_code, 200)
        self.assertRedirects(self.client.get(step_url(4)), step_url(5))

    def test_o_perfil_esconde_a_divisao_de_quem_ela_nao_muda(self):
        self.client.post(step_url(3), self.dias(2))
        self.client.post(step_url(5), STEP5)

        html = self.client.get(reverse("accounts:profile")).content.decode()

        self.assertNotIn("Divisão de treino", html)
        # E o dado continua salvo: esconder não é apagar.
        self.assertIsNotNone(self.perfil().split_preference)

    def test_o_perfil_mostra_a_divisao_de_quem_ela_muda(self):
        self.client.post(step_url(3), self.dias(5))
        self.client.post(step_url(4), STEP4)
        self.client.post(step_url(5), STEP5)

        html = self.client.get(reverse("accounts:profile")).content.decode()

        self.assertIn("Divisão de treino", html)

    # ------------------------------------------------------ compatibilidade
    def test_quem_ja_tinha_preferencia_salva_continua_valendo(self):
        """Ninguém perde dado por causa da mudança de fluxo."""
        self.client.post(step_url(3), self.dias(5))
        self.client.post(step_url(4), STEP4)
        escolhida = self.perfil().split_preference

        self.client.post(step_url(3), self.dias(2))

        self.assertEqual(self.perfil().split_preference, escolhida)

    def test_o_plano_de_treino_continua_sendo_montado_sem_a_pergunta(self):
        """A regra de negócio não mudou — só quem responde o quê.

        `split_for` já caía na tabela por frequência quando não havia
        preferência, e é isso que sustenta pular a pergunta.
        """
        self.client.post(step_url(3), self.dias(3))
        self.client.post(step_url(5), STEP5)

        perfil = self.perfil()
        self.assertTrue(perfil.onboarding_complete)
        self.assertEqual(self.user.training_days.count(), 3)
        self.assertEqual(
            split_for(3, perfil.split_preference), split_for(3, None)
        )

    def test_o_ultimo_passo_continua_sendo_o_cinco_nos_dois_caminhos(self):
        """`ONBOARDING_DONE` e `onboarding_complete` dependem disso.

        Se o caminho curto terminasse em outro número, "terminou o onboarding"
        precisaria de duas definições — e a segunda envelheceria.
        """
        self.assertEqual(CAMINHO_CURTO[-1], ONBOARDING_LAST_STEP)
        self.assertEqual(CAMINHO_COMPLETO[-1], ONBOARDING_LAST_STEP)

    def test_ninguem_pula_etapa_no_caminho_curto(self):
        """Pular a divisão não abriu atalho para o resto."""
        outro = User.objects.create_user(
            email="pulador@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(outro)

        self.assertRedirects(self.client.get(step_url(5)), step_url(1))
        self.assertRedirects(self.client.get(step_url(3)), step_url(1))


class PesoDoOnboardingTests(TestCase):
    """O peso do passo 1 aceitando vírgula.

    O campo era `DecimalField` com `NumberInput`, ou seja `type="number"`: o
    NAVEGADOR descartava "72,4" antes de enviar, o campo chegava vazio e o
    formulário recusava dizendo que faltou preencher. Quem digita vírgula não
    passava do primeiro passo sem adivinhar que precisava de ponto.

    A defesa é dupla e nenhuma metade basta: o servidor traduz a vírgula, e o
    widget de texto deixa a vírgula chegar até ele.
    """

    def _dados(self, peso):
        return {
            "sex": "M",
            "birth_date": "1995-04-12",
            "height_cm": "178",
            "weight_kg": peso,
        }

    def test_virgula_e_aceita_e_vira_o_numero_certo(self):
        form = BodyDataForm(data=self._dados("72,4"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["weight_kg"], Decimal("72.4"))

    def test_ponto_continua_aceito(self):
        form = BodyDataForm(data=self._dados("72.4"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["weight_kg"], Decimal("72.4"))

    def test_o_navegador_nao_pode_barrar_a_virgula(self):
        """`type="number"` descarta "72,4" antes de o servidor ver.

        Traduzir no servidor não adianta se o campo nunca chega — por isso o
        widget é de texto, com teclado numérico.
        """
        html = str(BodyDataForm()["weight_kg"])

        self.assertIn('type="text"', html)
        self.assertIn('inputmode="decimal"', html)
        self.assertNotIn('type="number"', html)

    def test_texto_sem_numero_e_recusado_com_mensagem_clara(self):
        form = BodyDataForm(data=self._dados("mais ou menos setenta"))

        self.assertFalse(form.is_valid())
        self.assertIn("use números", form.errors["weight_kg"][0])

    def test_vazio_continua_sendo_erro(self):
        form = BodyDataForm(data=self._dados(""))

        self.assertFalse(form.is_valid())
        self.assertIn("weight_kg", form.errors)

    def test_negativo_e_absurdo_continuam_fora_da_faixa(self):
        for peso in ("-5", "0", "3", "900"):
            with self.subTest(peso=peso):
                form = BodyDataForm(data=self._dados(peso))
                self.assertFalse(form.is_valid())
                self.assertIn("weight_kg", form.errors)

    def test_o_peso_com_virgula_chega_gravado_no_banco(self):
        """Aceitar não basta: o número tem que persistir com o valor certo."""
        user = create_complete_user(email="virgula@exemplo.com")
        Profile.objects.filter(user=user).update(onboarding_step=1)
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 1}),
            self._dados("72,4"),
        )

        self.assertEqual(
            WeightEntry.objects.filter(user=user).latest("id").weight_kg,
            Decimal("72.40"),
        )

    def test_editar_o_peso_depois_tambem_aceita_virgula(self):
        """O passo 1 é reaberto pelo perfil — o caminho de edição usa o mesmo
        formulário e não pode divergir."""
        user = create_complete_user(email="edicao@exemplo.com")
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 1}),
            self._dados("81,25"),
        )

        self.assertEqual(
            WeightEntry.objects.filter(user=user).latest("id").weight_kg,
            Decimal("81.25"),
        )


class RegrasDeSenhaTests(TestCase):
    """O texto de ajuda do cadastro, e o que o mantém honesto."""

    def test_a_lista_descreve_os_validadores_realmente_configurados(self):
        """A ajuda é escrita à mão; os validadores é que recusam senha.

        Se alguém acrescentar, remover ou trocar um validador, o texto passa a
        mentir sobre a regra. Este teste quebra antes do usuário ver.
        """
        configurados = [
            v["NAME"].rsplit(".", 1)[-1]
            for v in settings.AUTH_PASSWORD_VALIDATORS
        ]

        self.assertEqual(tuple(configurados), REGRAS_ESPERADAS)

    def test_o_texto_ficou_mais_curto_que_o_padrao_do_django(self):
        from django.contrib.auth import password_validation

        padrao = str(password_validation.password_validators_help_text_html())
        nosso = str(SignupForm().fields["password1"].help_text)

        self.assertLess(len(nosso), len(padrao))
        self.assertIn("8 caracteres", nosso)

    def test_a_validacao_de_senha_continua_recusando(self):
        """O texto encurtou; a exigência, não."""
        casos = ("12345678", "senha123", "abc")
        for senha in casos:
            with self.subTest(senha=senha):
                form = SignupForm(data={
                    "first_name": "Teste", "email": "senha%s@exemplo.com" % len(senha),
                    "password1": senha, "password2": senha,
                })
                self.assertFalse(form.is_valid())
                self.assertIn("password2", form.errors)

    def test_uma_senha_boa_continua_passando(self):
        form = SignupForm(data={
            "first_name": "Teste", "email": "boa@exemplo.com",
            "password1": "Girassol!2026#", "password2": "Girassol!2026#",
        })

        self.assertTrue(form.is_valid(), form.errors)


class NavegacaoTests(TestCase):
    """A navegação de desktop e a de celular precisam alcançar as mesmas telas."""

    def setUp(self):
        self.user = create_complete_user(email="nav@exemplo.com")
        self.client.force_login(self.user)

    def test_as_duas_barras_levam_ao_mesmo_conjunto_de_telas(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        topo = html.split('class="app-bar__nav"', 1)[1].split("</nav>", 1)[0]
        baixo = html.split('class="tabbar"', 1)[1].split("</nav>", 1)[0]
        destinos = lambda t: {
            m for m in re.findall(r'href="([^"]+)"', t) if not m.startswith("#")
        }

        self.assertEqual(destinos(topo), destinos(baixo))


class FaviconTests(TestCase):
    """O navegador pede `/favicon.ico` na raiz sozinho, sem olhar o `<link>`."""

    def test_a_raiz_deixa_de_responder_404(self):
        resposta = self.client.get("/favicon.ico")

        self.assertEqual(resposta.status_code, 301)
        self.assertIn("favicon.ico", resposta["Location"])

    def test_o_destino_do_redirecionamento_e_o_arquivo_que_existe(self):
        alvo = Path(settings.BASE_DIR) / "static" / "icons" / "favicon.ico"

        self.assertTrue(alvo.exists(), "o .ico precisa existir no static")


class DataDeNascimentoNaEdicaoTests(TestCase):
    """A data já salva precisa VOLTAR preenchida ao reabrir o passo 1.

    O widget emitia `value="20/05/1990"` — correto para pt-BR e ilegível para
    `<input type="date">`, que só entende ISO. O navegador descartava em
    silêncio e o campo aparecia vazio: quem abria o passo pelo perfil só para
    corrigir o peso levava "Este campo é obrigatório" até redigitar a data.

    Achado no smoke de produção do Polimento V1, e da mesma família do peso com
    vírgula: valor válido no servidor, formato que o input HTML não lê.
    """

    def setUp(self):
        self.user = create_complete_user(email="data@exemplo.com")
        self.client.force_login(self.user)
        Profile.objects.filter(user=self.user).update(birth_date=date(1990, 5, 20))

    def _abrir(self):
        return self.client.get(step_url(1)).content.decode()

    def _valor_renderizado(self, html):
        campo = re.search(r'<input[^>]*name="birth_date"[^>]*>', html).group(0)
        achado = re.search(r'value="([^"]*)"', campo)
        return achado.group(1) if achado else ""

    def test_a_data_salva_volta_no_formato_que_o_input_entende(self):
        valor = self._valor_renderizado(self._abrir())

        self.assertEqual(valor, "1990-05-20")

    def test_o_navegador_nao_recebe_o_formato_brasileiro_no_atributo(self):
        """"20/05/1990" está certo para uma pessoa e errado para o atributo.

        O que a pessoa VÊ continua sendo o formato do locale dela — quem
        formata a exibição é o navegador, a partir do valor ISO.
        """
        self.assertNotIn("20/05/1990", self._valor_renderizado(self._abrir()))

    def test_editar_so_o_peso_preserva_a_data(self):
        """Mudar só o peso não pode mexer na data.

        Este teste NÃO é o que pega a regressão, e vale dizer por quê: o campo
        aceita `%d/%m/%Y` na entrada, então devolver "20/05/1990" ao servidor
        funcionava mesmo com o bug. Quem descartava o valor era o NAVEGADOR, e
        isso só aparece no atributo renderizado — coberto pelos dois testes de
        formato acima, que de fato caem quando o `format` sai.

        O que este aqui protege é o outro lado: que salvar peso não apague nem
        desloque a data por algum efeito colateral do formulário.
        """
        html = self._abrir()
        resposta = self.client.post(step_url(1), {
            "sex": "M",
            "birth_date": self._valor_renderizado(html),
            "height_cm": "178",
            "weight_kg": "73,5",
        })

        self.assertNotEqual(resposta.status_code, 500)
        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.birth_date, date(1990, 5, 20))
        self.assertEqual(
            WeightEntry.objects.filter(user=self.user).latest("id").weight_kg,
            Decimal("73.50"),
        )

    def test_editar_so_a_altura_tambem_preserva_a_data(self):
        html = self._abrir()
        self.client.post(step_url(1), {
            "sex": "M",
            "birth_date": self._valor_renderizado(html),
            "height_cm": "181",
            "weight_kg": "82,4",
        })

        perfil = Profile.objects.get(user=self.user)
        self.assertEqual(perfil.birth_date, date(1990, 5, 20))
        self.assertEqual(perfil.height_cm, 181)

    def test_trocar_a_data_por_outra_valida_persiste(self):
        self.client.post(step_url(1), {
            "sex": "M",
            "birth_date": "1988-11-02",
            "height_cm": "178",
            "weight_kg": "82,4",
        })

        self.assertEqual(
            Profile.objects.get(user=self.user).birth_date, date(1988, 11, 2)
        )

    def test_data_invalida_e_recusada_sem_estourar(self):
        for valor in ("", "1990-13-45", "amanhã"):
            with self.subTest(birth_date=valor):
                resposta = self.client.post(step_url(1), {
                    "sex": "M",
                    "birth_date": valor,
                    "height_cm": "178",
                    "weight_kg": "82,4",
                })

                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["form"].errors)
                self.assertEqual(
                    Profile.objects.get(user=self.user).birth_date, date(1990, 5, 20)
                )

    def test_o_widget_declara_o_formato_em_vez_de_delegar_a_javascript(self):
        """A tradução é do widget.

        Consertar isso no cliente deixaria o formulário dependente de script
        para exibir um valor que o servidor já tem — e quebraria de novo em
        toda tela que renderizasse o campo sem esse script.
        """
        widget = BodyDataForm().fields["birth_date"].widget

        self.assertEqual(widget.format, "%Y-%m-%d")


class ConfirmacaoDeEscritaTests(TestCase):
    """Confirmação só onde a tela não prova sozinha que gravou.

    A maioria das escritas do app dispensa mensagem porque o próprio elemento
    muda de estado: a refeição marcada troca de cor, a barra da água cresce, a
    série vira número. Mensagem nesses lugares seria ruído sobre um fato já
    visível — e este teste também guarda ESSA metade da decisão.

    As duas exceções são escritas em que a tela seguinte fica igual à anterior.
    """

    def setUp(self):
        self.user = create_complete_user(email="confirma@exemplo.com")
        self.client.force_login(self.user)

    def _mensagens(self, resposta):
        return [str(m) for m in resposta.context["messages"]]

    # -- pesagem ---------------------------------------------------------

    def test_registrar_peso_confirma(self):
        """O campo volta preenchido com o peso de hoje.

        Ou seja: com o número que a pessoa acabou de digitar. Antes e depois do
        envio ela vê exatamente a mesma tela, e sem mensagem nada distingue
        "gravou" de "o formulário nem foi".
        """
        resposta = self.client.post(
            reverse("accounts:log_weight"),
            {"origem": "metricas", "weight_kg": "81,3"},
            follow=True,
        )

        self.assertIn("Peso registrado.", self._mensagens(resposta))

    def test_peso_recusado_nao_confirma(self):
        resposta = self.client.post(
            reverse("accounts:log_weight"),
            {"origem": "metricas", "weight_kg": "abacaxi"},
            follow=True,
        )

        self.assertNotIn("Peso registrado.", self._mensagens(resposta))

    # -- edição de perfil -------------------------------------------------

    def test_salvar_edicao_do_perfil_confirma(self):
        """Editar redireciona para o perfil, que já mostrava os valores novos —
        mas nada dizia que o salvamento aconteceu."""
        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 1}),
            {"sex": "M", "birth_date": "1990-05-20",
             "height_cm": "178", "weight_kg": "80,0"},
            follow=True,
        )

        self.assertIn("Alterações salvas.", self._mensagens(resposta))

    def test_durante_o_onboarding_nao_ha_confirmacao(self):
        """O feedback de ter salvo é o passo seguinte aparecer.

        Dizer "pronto" a cada passo do cadastro seria a mensagem virando ruído
        justamente em quem ainda está aprendendo o app.
        """
        novo = create_complete_user(email="cadastrando@exemplo.com")
        # `onboarding_complete` é propriedade, não campo: quem guarda o
        # progresso é `onboarding_step`.
        Profile.objects.filter(user=novo).update(onboarding_step=1)
        self.client.force_login(novo)

        resposta = self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 1}),
            {"sex": "M", "birth_date": "1990-05-20",
             "height_cm": "178", "weight_kg": "80,0"},
            follow=True,
        )

        self.assertEqual(self._mensagens(resposta), [])

    # -- o outro lado da decisão -----------------------------------------

    def test_acoes_que_mudam_a_tela_continuam_caladas(self):
        """Marcar refeição, beber água e ligar suplemento não ganham mensagem.

        Se alguém "padronizar" o feedback espalhando `messages.success` pelas
        escritas, este teste quebra: são três ações de alta frequência, e um
        aviso em cada uma vira uma tela que fala o tempo todo.
        """
        fonte = (Path(settings.BASE_DIR) / "plans" / "views.py").read_text(
            encoding="utf-8"
        )
        for vista in ("class MarkMealView", "class ClearMealView",
                      "class LogHydrationView"):
            corpo = fonte.split(vista, 1)[1].split("\nclass ", 1)[0]

            self.assertNotIn("messages.success", corpo, vista)


class EstadoVazioDeTreinosTests(TestCase):
    """O cartão de treinos sem nenhum dia.

    É alcançável: `weekdays` é `required=False` no passo 3, então quem responde
    que não treina cai aqui. O cabeçalho tem "Editar", e mesmo assim o cartão
    ganhou botão — "editar" é o verbo errado quando não existe nada para
    editar, e um link de texto ao lado do título não é o convite de um cartão
    vazio.
    """

    def setUp(self):
        self.user = create_complete_user(email="semtreino@exemplo.com")
        self.user.training_days.all().delete()
        self.client.force_login(self.user)

    def test_o_cartao_vazio_oferece_o_caminho_para_cadastrar(self):
        html = self.client.get(reverse("accounts:profile")).content.decode()
        bloco = html.split("Nenhum dia de treino", 1)[1][:400]

        self.assertIn(
            reverse("accounts:onboarding_step", kwargs={"step": 3}), bloco
        )
        self.assertIn("Cadastrar dias de treino", bloco)

    def test_o_destino_do_botao_responde(self):
        """CTA que aponta para rota quebrada é pior que CTA nenhum."""
        destino = reverse("accounts:onboarding_step", kwargs={"step": 3})

        self.assertEqual(self.client.get(destino).status_code, 200)


class RecuperacaoDeSenhaTests(TestCase):
    """"Esqueci minha senha" — o bloqueador de beta que não existia.

    Antes desta missão o app não tinha NENHUMA rota de senha fora do admin:
    quem esquecia a senha dependia de alguém com acesso ao banco. Agora o fluxo
    é o do Django — token assinado, expiração e invalidação no uso —, e o que é
    nosso são as telas e a resposta neutra.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="quem.esqueceu@exemplo.com", password="SenhaAntiga!2026#"
        )
        mail.outbox = []

    def _pedir(self, email):
        return self.client.post(
            reverse("accounts:password_reset"), {"email": email}, follow=True
        )

    def _link_do_email(self):
        corpo = mail.outbox[0].body
        achado = re.search(r"/conta/senha/nova/[^/]+/[^/\s]+/", corpo)
        return achado.group(0) if achado else None

    # -- pedido ----------------------------------------------------------

    def test_email_existente_recebe_o_link(self):
        self._pedir(self.user.email)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIsNotNone(self._link_do_email())

    def test_email_inexistente_nao_manda_nada(self):
        self._pedir("ninguem@exemplo.com")

        self.assertEqual(mail.outbox, [])

    def test_a_resposta_e_a_mesma_exista_ou_nao_a_conta(self):
        """A tela não pode virar um verificador de cadastro.

        É o requisito de não vazar existência de conta: se a página mudasse de
        texto, de status ou de destino conforme o e-mail existir, bastaria um
        laço sobre uma lista de e-mails para descobrir quem usa o NutriPlan.
        """
        com = self._pedir(self.user.email)
        sem = self._pedir("ninguem@exemplo.com")

        self.assertEqual(com.status_code, sem.status_code)
        self.assertEqual(
            [u for u, _ in com.redirect_chain], [u for u, _ in sem.redirect_chain]
        )
        self.assertEqual(com.content, sem.content)

    def test_a_tela_nao_afirma_que_enviou(self):
        """"Enviamos para você" seria confirmar que a conta existe."""
        html = self._pedir("ninguem@exemplo.com").content.decode()

        self.assertIn("Se existir uma conta", html)

    # -- token -----------------------------------------------------------

    def test_token_valido_abre_o_formulario(self):
        self._pedir(self.user.email)

        resposta = self.client.get(self._link_do_email(), follow=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["validlink"])

    def test_token_adulterado_e_recusado(self):
        self._pedir(self.user.email)
        link = self._link_do_email()
        quebrado = link[:-6] + "aaaaa/"

        resposta = self.client.get(quebrado, follow=True)

        self.assertFalse(resposta.context["validlink"])
        self.assertContains(resposta, "Link inválido")

    def test_token_expirado_e_recusado(self):
        """Três horas, e não os três dias do padrão do Django.

        Link de senha vivo por três dias é uma janela de três dias para quem
        tiver acesso à caixa de entrada.

        O relógio é adiantado no VERIFICADOR, e não via
        `override_settings(PASSWORD_RESET_TIMEOUT=0)`: o token nasce e é
        conferido no mesmo segundo, a diferença dá zero, e zero não é MAIOR que
        zero — o teste passava sem expirar nada.
        """
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3 * 60 * 60)
        self._pedir(self.user.email)
        link = self._link_do_email()
        quatro_horas_depois = datetime.now() + timedelta(hours=4)

        with mock.patch.object(
            PasswordResetTokenGenerator, "_now", return_value=quatro_horas_depois
        ):
            resposta = self.client.get(link, follow=True)

        self.assertFalse(resposta.context["validlink"])

    def test_o_token_nao_serve_duas_vezes(self):
        """Usar o link invalida o token — senão ele vira uma chave reserva
        permanente na caixa de entrada."""
        self._pedir(self.user.email)
        link = self._link_do_email()
        self.client.get(link, follow=True)
        self.client.post(
            self.client.get(link, follow=True).redirect_chain[-1][0]
            if False else link.rsplit("/", 2)[0] + "/set-password/",
            {"new_password1": "OutraSenha!2026#", "new_password2": "OutraSenha!2026#"},
            follow=True,
        )

        segunda = self.client.get(link, follow=True)

        self.assertFalse(segunda.context["validlink"])

    # -- senha nova ------------------------------------------------------

    def _redefinir(self, senha):
        self._pedir(self.user.email)
        link = self._link_do_email()
        self.client.get(link, follow=True)
        return self.client.post(
            link.rsplit("/", 2)[0] + "/set-password/",
            {"new_password1": senha, "new_password2": senha},
            follow=True,
        )

    def test_senha_nova_valida_passa_e_permite_entrar(self):
        self._redefinir("SenhaNova!2026#")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SenhaNova!2026#"))
        self.assertTrue(
            self.client.login(email=self.user.email, password="SenhaNova!2026#")
        )

    def test_senha_fraca_e_recusada(self):
        """A validação é a mesma do cadastro — `AUTH_PASSWORD_VALIDATORS`."""
        for fraca in ("12345678", "senha123", "abc"):
            with self.subTest(senha=fraca):
                self._redefinir(fraca)
                self.user.refresh_from_db()

                self.assertFalse(self.user.check_password(fraca))
                self.assertTrue(self.user.check_password("SenhaAntiga!2026#"))

    def test_a_senha_antiga_para_de_valer(self):
        self._redefinir("SenhaNova!2026#")

        self.assertFalse(
            self.client.login(email=self.user.email, password="SenhaAntiga!2026#")
        )

    # -- Google ----------------------------------------------------------

    def test_conta_so_do_google_nao_recebe_link_nem_ganha_senha(self):
        """`PasswordResetForm` só alcança quem tem senha utilizável.

        Uma conta criada pelo Google nunca escolheu senha: `has_usable_password`
        é falso. Mandar um link para ela criaria uma senha local que a pessoa
        não pediu — e abriria um segundo caminho de entrada numa conta que só
        tinha o do provedor.

        A resposta na tela continua sendo a mesma, então isso também não conta
        para fora que a conta é do Google.
        """
        google = User.objects.create_user(email="so.google@exemplo.com")
        google.set_unusable_password()
        google.save()
        mail.outbox = []

        resposta = self._pedir(google.email)

        self.assertEqual(mail.outbox, [])
        google.refresh_from_db()
        self.assertFalse(google.has_usable_password())
        self.assertIn("Se existir uma conta", resposta.content.decode())

    def test_a_tela_de_entrar_oferece_o_caminho(self):
        html = self.client.get(reverse("accounts:login")).content.decode()

        self.assertIn(reverse("accounts:password_reset"), html)
        self.assertIn("Esqueci minha senha", html)

    def test_o_email_diz_o_que_fazer_se_nao_foi_a_pessoa(self):
        """Quem recebe um pedido que não fez precisa saber que nada mudou."""
        self._pedir(self.user.email)
        corpo = mail.outbox[0].body

        self.assertIn("Se não foi você", corpo)
        self.assertIn("3 horas", corpo)


class TrocaDeSenhaTests(TestCase):
    """Trocar a senha estando logado."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="troca@exemplo.com", password="SenhaAtual!2026#"
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:password_change")

    def _trocar(self, atual, nova):
        return self.client.post(
            self.url,
            {"old_password": atual, "new_password1": nova, "new_password2": nova},
            follow=True,
        )

    def test_senha_atual_correta_e_nova_valida_trocam(self):
        self._trocar("SenhaAtual!2026#", "SenhaNova!2026#")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SenhaNova!2026#"))

    def test_senha_atual_errada_nao_troca(self):
        self._trocar("ChutandoAqui!2026#", "SenhaNova!2026#")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SenhaAtual!2026#"))

    def test_senha_nova_fraca_e_recusada(self):
        self._trocar("SenhaAtual!2026#", "12345678")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("SenhaAtual!2026#"))

    def test_a_sessao_sobrevive_a_troca(self):
        """`PasswordChangeView` chama `update_session_auth_hash`.

        Sem isso, trocar a senha derruba a pessoa para a tela de login logo
        depois de ela fazer a coisa certa — e a tela de sucesso estaria mentindo
        ao dizer "você continua conectado".
        """
        self._trocar("SenhaAtual!2026#", "SenhaNova!2026#")

        resposta = self.client.get(reverse("accounts:profile"))

        self.assertEqual(resposta.status_code, 200)

    def test_quem_nao_esta_logado_nao_abre_a_troca(self):
        self.client.logout()

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_o_perfil_nao_oferece_troca_para_conta_do_google(self):
        """Formulário de "senha atual" para quem nunca teve senha só produz
        "senha incorreta" — culpando a pessoa por uma promessa da tela."""
        google = create_complete_user(email="google.perfil@exemplo.com")
        google.set_unusable_password()
        google.save()
        self.client.force_login(google)

        html = self.client.get(reverse("accounts:profile")).content.decode()

        self.assertNotIn(reverse("accounts:password_change"), html)


class ExclusaoDeContaTests(TestCase):
    """"Excluir minha conta" — a única ação do app que não tem volta."""

    def setUp(self):
        self.user = create_complete_user(email="vai.sair@exemplo.com")
        self.user.set_password("MinhaSenha!2026#")
        self.user.save()
        self.client.force_login(self.user)
        self.url = reverse("accounts:excluir_conta")

    def test_a_tela_avisa_que_e_permanente(self):
        html = self.client.get(self.url).content.decode()

        self.assertIn("permanentemente", html)
        self.assertIn("Cancelar", html)

    def test_a_tela_conta_o_que_sera_apagado(self):
        """Número, e não "seus dados": é na hora de uma ação irreversível que
        a pessoa precisa medir o tamanho do que vai fazer."""
        # `create_complete_user` já grava a pesagem de hoje, e a unicidade por
        # dia recusa uma segunda. O que o teste precisa é que EXISTA pesagem.
        self.assertTrue(WeightEntry.objects.filter(user=self.user).exists())

        resposta = self.client.get(self.url)

        nomes = [nome for nome, _ in resposta.context["resumo"]]
        self.assertIn("Pesagens", nomes)

    def test_sem_confirmacao_nada_e_apagado(self):
        self.client.post(self.url, {})

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_senha_errada_nao_apaga(self):
        self.client.post(self.url, {"senha": "ChutandoAqui!2026#"})

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_senha_certa_apaga_a_conta(self):
        self.client.post(self.url, {"senha": "MinhaSenha!2026#"}, follow=True)

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_depois_de_apagar_nao_da_mais_para_entrar(self):
        email = self.user.email
        self.client.post(self.url, {"senha": "MinhaSenha!2026#"}, follow=True)

        self.assertFalse(self.client.login(email=email, password="MinhaSenha!2026#"))

    def test_a_sessao_cai_junto(self):
        """O `logout` vem ANTES do `delete`, e a sessão é ESVAZIADA.

        Conferir só que o perfil redireciona não prova nada: com o usuário
        apagado, `request.user` vira anônimo e o perfil redireciona de
        qualquer jeito — inclusive com a linha de sessão órfã ainda no banco,
        guardando o id de uma conta que não existe mais. A asserção é a chave
        de autenticação ter sumido da sessão.
        """
        from django.contrib.auth import SESSION_KEY

        self.assertIn(SESSION_KEY, self.client.session)

        self.client.post(self.url, {"senha": "MinhaSenha!2026#"}, follow=True)

        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(
            self.client.get(reverse("accounts:profile")).status_code, 302
        )

    def test_ninguem_apaga_a_conta_de_outra_pessoa(self):
        """Não há id no formulário nem na URL — a conta é sempre
        `request.user`. A proteção é a AUSÊNCIA do parâmetro, não uma checagem
        que alguém pode esquecer de escrever."""
        alheio = create_complete_user(email="alheio.conta@exemplo.com")

        self.client.post(
            self.url, {"senha": "MinhaSenha!2026#", "user": alheio.pk, "id": alheio.pk},
            follow=True,
        )

        self.assertTrue(User.objects.filter(pk=alheio.pk).exists())

    def test_quem_nao_esta_logado_nao_abre_a_exclusao(self):
        self.client.logout()

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    # -- conta do Google --------------------------------------------------

    def _google(self):
        user = create_complete_user(email="google.exclui@exemplo.com")
        user.set_unusable_password()
        user.save()
        SocialAccount.objects.create(user=user, provider="google", uid="uid-exclusao")
        self.client.force_login(user)
        return user

    def test_conta_do_google_confirma_pela_palavra(self):
        user = self._google()

        self.client.post(self.url, {"confirmacao": PALAVRA_DE_EXCLUSAO}, follow=True)

        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_conta_do_google_nao_apaga_com_palavra_errada(self):
        user = self._google()

        self.client.post(self.url, {"confirmacao": "excluir por favor"}, follow=True)

        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_conta_do_google_nao_recebe_campo_de_senha(self):
        """Pedir senha a quem nunca teve uma é inventar credencial."""
        self._google()

        resposta = self.client.get(self.url)

        self.assertNotIn("senha", resposta.context["form"].fields)
        self.assertIn("confirmacao", resposta.context["form"].fields)

    def test_o_socialaccount_vai_junto(self):
        user = self._google()

        self.client.post(self.url, {"confirmacao": PALAVRA_DE_EXCLUSAO}, follow=True)

        self.assertFalse(SocialAccount.objects.filter(user_id=user.pk).exists())

    # -- dados relacionados ----------------------------------------------

    def test_nao_sobra_dado_orfao_de_nenhuma_relacao(self):
        """Todas as relações diretas com User são CASCADE — a varredura confere
        isso no `_meta` e depois confirma no banco.

        Escrito assim, e não como uma lista de modelos: um app novo que aponte
        para `User` entra na verificação sozinho, e é justamente o modelo que
        ninguém lembrou de listar que deixaria dado pessoal para trás.
        """
        from django.contrib.auth import get_user_model

        alvo = get_user_model()
        relacoes = [
            r for r in alvo._meta.related_objects
            if r.field.model is not alvo
        ]
        self.assertGreater(len(relacoes), 8)

        pk = self.user.pk
        antes = {
            r.related_model._meta.label: r.related_model.objects.filter(
                **{r.field.name + "_id": pk}
            ).count()
            for r in relacoes
        }
        self.assertTrue(any(antes.values()), "o fixture precisa ter dado ligado")

        self.client.post(self.url, {"senha": "MinhaSenha!2026#"}, follow=True)

        for r in relacoes:
            with self.subTest(modelo=r.related_model._meta.label):
                sobrou = r.related_model.objects.filter(
                    **{r.field.name + "_id": pk}
                ).count()
                self.assertEqual(sobrou, 0)

    def test_toda_relacao_com_user_e_cascade(self):
        """A garantia estrutural por trás do teste acima.

        Se alguém acrescentar uma FK para `User` com `SET_NULL` ou `PROTECT`, a
        exclusão passa a deixar dado pessoal órfão (ou a falhar), e é melhor
        descobrir aqui do que numa conta de gente de verdade.
        """
        from django.db.models import CASCADE
        from django.contrib.auth import get_user_model

        alvo = get_user_model()
        fora = [
            "%s.%s" % (r.related_model._meta.label, r.field.name)
            for r in alvo._meta.related_objects
            if r.field.model is not alvo
            and r.field.remote_field.on_delete is not CASCADE
        ]

        self.assertEqual(fora, [])


class ExclusaoSoDaPropriaContaTests(TestCase):
    """A conta apagada e SEMPRE `request.user`. Nunca um id que veio no pedido.

    A view ja e segura por construcao — ela nem olha para o POST em busca de
    identificador. Este teste existe porque "seguro por construcao" e uma
    propriedade que some no dia em que alguem acrescenta um campo achando que
    esta ajudando, e nada quebraria: nenhum teste passava um id para provar
    que ele e ignorado. A lacuna apareceu numa sabotagem de integracao.
    """

    SENHA = "SenhaDoAtacante!2026#"

    def setUp(self):
        self.vitima = create_complete_user(email="vitima@exemplo.com")

    def _atacante(self, email):
        user = create_complete_user(email=email)
        user.set_password(self.SENHA)
        user.save()
        self.client.force_login(user)
        return user

    def _excluir(self, extra):
        dados = {"confirmacao": PALAVRA_DE_EXCLUSAO, "senha": self.SENHA}
        dados.update(extra)
        return self.client.post(reverse("accounts:excluir_conta"), dados, follow=True)

    def test_id_no_corpo_do_pedido_nao_escolhe_a_vitima(self):
        for campo in ("user_id", "usuario", "id", "pk", "user"):
            with self.subTest(campo=campo):
                self._atacante("atk-%s@exemplo.com" % campo)

                self._excluir({campo: self.vitima.pk})

                self.assertTrue(
                    User.objects.filter(pk=self.vitima.pk).exists(),
                    "a vitima foi apagada por um id vindo do pedido (%s)" % campo,
                )

    def test_quem_pede_e_quem_some(self):
        atacante = self._atacante("atacante@exemplo.com")

        self._excluir({"user_id": self.vitima.pk})

        self.assertFalse(User.objects.filter(pk=atacante.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.vitima.pk).exists())


class LogoutSeguroTests(TestCase):
    """O logout já era POST-only. Estes testes existem para continuar sendo."""

    def setUp(self):
        self.user = create_complete_user(email="saindo@exemplo.com")
        self.client.force_login(self.user)
        self.url = reverse("accounts:logout")

    def test_post_desloga(self):
        self.client.post(self.url)

        self.assertEqual(
            self.client.get(reverse("accounts:profile")).status_code, 302
        )

    def test_get_nao_desloga(self):
        """Link GET para sair é um `<img src>` numa página qualquer derrubando
        a sessão de quem passar por ela.

        A asserção é o 405, e não "a sessão sobreviveu": com um handler GET
        acrescentado à view, o CSRF ainda barraria o pedido e a sessão
        continuaria de pé — o teste passaria elogiando a proteção errada.
        Sabotagem escrita exatamente para isso é que revelou a diferença.
        """
        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 405)
        self.assertEqual(
            self.client.get(reverse("accounts:profile")).status_code, 200
        )

    def test_a_interface_usa_formulario_com_csrf(self):
        for pagina in (reverse("accounts:profile"), reverse("plans:today")):
            with self.subTest(pagina=pagina):
                html = self.client.get(pagina).content.decode()
                if self.url not in html:
                    continue
                antes = html.split(self.url, 1)[0]
                bloco = antes[antes.rfind("<form"):]

                self.assertIn('method="post"', bloco)
                self.assertIn("csrfmiddlewaretoken", html.split(self.url, 1)[1][:400])


class ConfiguracaoDeEmailTests(TestCase):
    """O que precisa estar de pé para o link de senha chegar."""

    def test_existe_um_backend_configurado(self):
        """Sem backend, `PasswordResetView` estoura e o fluxo morre na primeira
        tela. O padrão é o console — em produção o e-mail aparece no log, que é
        feio e honesto; `dummy` descartaria em silêncio, que é pior."""
        self.assertTrue(settings.EMAIL_BACKEND)
        self.assertNotIn("dummy", settings.EMAIL_BACKEND)

    def test_nenhuma_credencial_de_email_esta_no_codigo(self):
        """Host e senha vêm do ambiente, e o padrão é vazio de propósito."""
        fonte = (Path(settings.BASE_DIR) / "config" / "settings.py").read_text(
            encoding="utf-8"
        )
        arvore = ast.parse(fonte)
        atribuicoes = {}
        for no in ast.walk(arvore):
            if isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name):
                atribuicoes[no.targets[0].id] = no.value

        for nome in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
            with self.subTest(variavel=nome):
                valor = atribuicoes.get(nome)
                self.assertIsInstance(valor, ast.Call, "%s deixou de vir do env" % nome)

    def test_o_remetente_esta_definido(self):
        self.assertTrue(settings.DEFAULT_FROM_EMAIL)


class LimiteDeRecuperacaoTests(TestCase):
    """O limite do endpoint que passou a mandar e-mail de verdade.

    O contrato inteiro está em `accounts/limites.py`. Estes testes travam as
    duas coisas que, se quebrarem, quebram em silêncio: o limite deixar de
    limitar, e o limite passar a CONTAR ALGUMA COISA para fora — porque uma
    resposta que muda quando o limite bate vira um jeito de descobrir quem tem
    conta, que é exatamente o que a tela existe para não revelar.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="limite@exemplo.com", password="SenhaDoLimite!2026#"
        )
        self.url = reverse("accounts:password_reset")
        mail.outbox = []

    def _pedir(self, email=None, ip="203.0.113.10"):
        return self.client.post(
            self.url, {"email": email or self.user.email},
            REMOTE_ADDR=ip, follow=True,
        )

    # -- o caminho de gente de verdade -----------------------------------

    def test_o_primeiro_pedido_passa(self):
        self._pedir()

        self.assertEqual(len(mail.outbox), 1)

    def test_uso_humano_normal_nao_e_bloqueado(self):
        """Pede, nao chega, pede de novo, olha o spam, pede mais uma.

        O limite por e-mail e tres justamente para caber essa sequencia — se
        bloqueasse na segunda, a protecao viraria o defeito.
        """
        for _ in range(limites.LIMITE_POR_EMAIL):
            self._pedir()

        self.assertEqual(len(mail.outbox), limites.LIMITE_POR_EMAIL)

    # -- o abuso ----------------------------------------------------------

    def test_repeticao_abusiva_para_de_enviar(self):
        for _ in range(limites.LIMITE_POR_EMAIL + 5):
            self._pedir()

        self.assertEqual(len(mail.outbox), limites.LIMITE_POR_EMAIL)

    def test_trocar_a_caixa_das_letras_nao_burla(self):
        """`Fulano@X.com` e `fulano@x.com` sao o mesmo contador.

        Sem normalizar, o limite cai na primeira tentativa de quem alternar
        maiusculas — e e a primeira coisa que alguem tenta.
        """
        variacoes = [
            self.user.email.upper(),
            self.user.email.capitalize(),
            "  " + self.user.email + "  ",
            self.user.email,
        ]
        for email in variacoes * 3:
            self._pedir(email=email)

        self.assertEqual(len(mail.outbox), limites.LIMITE_POR_EMAIL)

    def test_outro_email_nao_herda_o_limite_do_primeiro(self):
        """O limite por e-mail e POR e-mail. Se vazasse entre contas, um
        atacante bloquearia a recuperacao de senha de outra pessoa so
        gastando a propria cota."""
        outro = User.objects.create_user(
            email="outro.limite@exemplo.com", password="OutraSenha!2026#"
        )
        for _ in range(limites.LIMITE_POR_EMAIL + 3):
            self._pedir()
        mail.outbox = []

        self._pedir(email=outro.email)

        self.assertEqual(len(mail.outbox), 1)

    def test_o_limite_por_ip_corta_a_troca_de_email(self):
        """Trocar de e-mail escapa do limite por e-mail — e cai no de origem."""
        for i in range(limites.LIMITE_POR_IP + 5):
            User.objects.create_user(
                email="vitima%d@exemplo.com" % i, password="Senha!2026#Abc"
            )
            self._pedir(email="vitima%d@exemplo.com" % i)

        self.assertEqual(len(mail.outbox), limites.LIMITE_POR_IP)

    def test_o_teto_global_segura_quem_troca_de_ip(self):
        """O limite honesto: quem roda de mil maquinas passa pelos outros dois.

        `LIMITE_GLOBAL` e o que de fato impede uma tarde de abuso de consumir a
        cota diaria do provedor.
        """
        for i in range(limites.LIMITE_GLOBAL + 10):
            User.objects.create_user(
                email="alvo%d@exemplo.com" % i, password="Senha!2026#Abc"
            )
            self._pedir(email="alvo%d@exemplo.com" % i, ip="198.51.100.%d" % (i % 250))

        self.assertEqual(len(mail.outbox), limites.LIMITE_GLOBAL)

    # -- o limite nao pode contar nada para fora --------------------------

    def test_a_resposta_do_bloqueado_e_igual_a_do_normal(self):
        primeira = self._pedir()
        for _ in range(limites.LIMITE_POR_EMAIL + 3):
            self._pedir()
        bloqueada = self._pedir()

        self.assertEqual(primeira.status_code, bloqueada.status_code)
        self.assertEqual(primeira.content, bloqueada.content)
        self.assertEqual(
            [u for u, _ in primeira.redirect_chain],
            [u for u, _ in bloqueada.redirect_chain],
        )

    def test_bloqueado_continua_indistinguivel_de_email_inexistente(self):
        for _ in range(limites.LIMITE_POR_EMAIL + 3):
            self._pedir()

        bloqueada = self._pedir()
        inexistente = self._pedir(email="ninguem.aqui@exemplo.com")

        self.assertEqual(bloqueada.content, inexistente.content)

    def test_nunca_devolve_429(self):
        """429 seria um oraculo: bastaria observar quando ele aparece."""
        for _ in range(limites.LIMITE_POR_EMAIL + 5):
            resposta = self._pedir()

            self.assertNotEqual(resposta.status_code, 429)

    # -- depois da janela --------------------------------------------------

    def test_passada_a_janela_volta_a_enviar(self):
        for _ in range(limites.LIMITE_POR_EMAIL + 2):
            self._pedir()
        mail.outbox = []

        antigo = timezone.now() - timezone.timedelta(
            minutes=limites.JANELA_MINUTOS + 5
        )
        PedidoDeRecuperacao.objects.update(criado_em=antigo)

        self._pedir()

        self.assertEqual(len(mail.outbox), 1)

    def test_a_tabela_nao_cresce_para_sempre(self):
        """Sem agendador no projeto, a limpeza acontece na propria escrita —
        tabela que so cresce e problema silencioso de disco num banco
        gratuito."""
        PedidoDeRecuperacao.objects.create(tipo="email", chave="velho")
        PedidoDeRecuperacao.objects.update(
            criado_em=timezone.now() - timezone.timedelta(days=7)
        )

        self._pedir()

        self.assertFalse(PedidoDeRecuperacao.objects.filter(chave="velho").exists())

    # -- o que fica guardado ----------------------------------------------

    def test_a_tabela_nao_guarda_o_email_em_texto(self):
        """Senao ela vira uma lista de quem usa o NutriPlan — o oposto do que
        a tela de recuperacao passa o tempo todo tentando nao revelar."""
        self._pedir()

        guardado = " ".join(
            PedidoDeRecuperacao.objects.values_list("chave", flat=True)
        )
        self.assertNotIn(self.user.email, guardado)
        self.assertNotIn("limite@", guardado)
        self.assertNotIn("203.0.113.10", guardado)

    # -- IP e proxy --------------------------------------------------------

    def test_sem_proxy_confiavel_o_cabecalho_do_cliente_e_ignorado(self):
        """`X-Forwarded-For` e escrito pelo CLIENTE.

        Confiar nele sem proxy confiavel deixaria qualquer um escolher o
        proprio IP e o limite por origem viraria decoracao.
        """
        pedido = RequestFactory().get(
            "/", REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="1.2.3.4"
        )

        with override_settings(USA_PROXY_CONFIAVEL=False):
            self.assertEqual(limites.ip_do_pedido(pedido), "203.0.113.7")



class FailClosedDeEmailTests(TestCase):
    """Produção não pode voltar para o console em silêncio.

    O backend padrão é seguro para DESENVOLVIMENTO, e um padrão seguro para
    desenvolvimento é perigoso em produção: se alguém apagar as variáveis do
    Render daqui a meses, o Django volta para o console sem reclamar e cada
    "esqueci minha senha" escreve um link VÁLIDO no log da plataforma.

    `manage.py check` roda no build, então a verificação derruba o deploy em
    vez de deixar o app subir quebrado.
    """

    def _erros(self, **cfg):
        from accounts.checks import email_de_producao_esta_configurado

        with override_settings(**cfg):
            return [e.id for e in email_de_producao_esta_configurado(None)]

    SMTP_OK = dict(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.exemplo.com",
        EMAIL_HOST_USER="usuario",
        EMAIL_HOST_PASSWORD="segredo",
        DEFAULT_FROM_EMAIL="NutriPlan <nao-responda@exemplo.com>",
        EMAIL_USE_TLS=True,
    )

    def test_console_em_desenvolvimento_continua_permitido(self):
        self.assertEqual(
            self._erros(
                DEBUG=True,
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
            ),
            [],
        )

    def test_console_em_producao_derruba_a_verificacao(self):
        self.assertIn(
            "accounts.E001",
            self._erros(
                DEBUG=False,
                EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
            ),
        )

    def test_backends_que_descartam_tambem_sao_recusados(self):
        for backend in ("dummy", "locmem", "filebased"):
            with self.subTest(backend=backend):
                self.assertIn(
                    "accounts.E001",
                    self._erros(
                        DEBUG=False,
                        EMAIL_BACKEND="django.core.mail.backends.%s.EmailBackend"
                        % backend,
                    ),
                )

    def test_smtp_sem_credencial_derruba(self):
        cfg = dict(self.SMTP_OK, EMAIL_HOST_PASSWORD="")

        self.assertIn("accounts.E002", self._erros(**cfg))

    def test_smtp_sem_tls_derruba(self):
        cfg = dict(self.SMTP_OK, EMAIL_USE_TLS=False, EMAIL_USE_SSL=False)

        self.assertIn("accounts.E003", self._erros(**cfg))

    def test_smtp_completo_passa(self):
        self.assertEqual(self._erros(**self.SMTP_OK), [])

    def test_a_verificacao_nunca_imprime_o_valor_do_segredo(self):
        """Checagem que despeja a credencial no log "para ajudar a
        diagnosticar" cria o problema que veio evitar."""
        from accounts.checks import email_de_producao_esta_configurado

        cfg = dict(self.SMTP_OK, EMAIL_HOST_PASSWORD="")
        with override_settings(**cfg):
            erros = email_de_producao_esta_configurado(None)

        texto = " ".join("%s %s" % (e.msg, e.hint) for e in erros)
        self.assertNotIn("segredo", texto)
        self.assertNotIn("usuario", texto)

    def test_a_verificacao_esta_registrada_como_check_de_deploy(self):
        """Escrita e não registrada é uma verificação que nunca roda.

        E precisa ser de DEPLOY, não comum: o runner de teste do Django troca o
        backend por `locmem` e roda com `DEBUG=False`, então uma verificação
        comum derrubaria a suíte inteira acusando a configuração de teste de ser
        produção mal configurada — foi o que aconteceu na primeira versão.

        Como contrapartida, ela só roda com `--deploy`, e por isso o teste
        seguinte exige que o build passe essa flag.
        """
        from django.core.checks import registry

        comuns = {c.__name__ for c in registry.registry.get_checks()}
        de_deploy = {
            c.__name__
            for c in registry.registry.get_checks(include_deployment_checks=True)
        }

        self.assertIn("email_de_producao_esta_configurado", de_deploy)
        self.assertNotIn("email_de_producao_esta_configurado", comuns)

    def test_o_build_roda_a_verificacao_de_deploy(self):
        """Check de deploy que ninguém executa não protege nada.

        `scripts/build.sh` roda com `errexit`, então um erro aqui derruba a
        publicação antes de o app subir — que é o comportamento desejado.
        """
        build = (Path(settings.BASE_DIR) / "scripts" / "build.sh").read_text(
            encoding="utf-8"
        )

        # Só as linhas de COMANDO. O cabeçalho do arquivo cita `collectstatic`
        # em prosa, e comparar posições no texto cru mede o comentário em vez
        # da ordem de execução.
        comandos = [
            l.strip() for l in build.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        posicao = lambda trecho: next(
            (i for i, l in enumerate(comandos) if trecho in l), None
        )

        self.assertIsNotNone(posicao("check --deploy"))
        self.assertIn("--fail-level ERROR", build)

        # DEPOIS do collectstatic, e a ordem inversa nao e detalhe: `check`
        # importa a URLconf, e `config/urls.py` resolve `static()` em tempo de
        # import para o redirecionamento do favicon. Com DEBUG desligado isso
        # passa pelo storage com manifesto, que so existe depois do
        # collectstatic. A primeira versao deste teste exigia o contrario e
        # derrubava o build com "Missing staticfiles manifest entry" — um erro
        # que nao tem relacao nenhuma com o que a verificacao veio verificar.
        self.assertGreater(posicao("check --deploy"), posicao("collectstatic"))

        # E ANTES do migrate: configuracao errada nao pode chegar a mexer no
        # schema do banco. O portao continua fechado, so mudou de lugar.
        self.assertLess(posicao("check --deploy"), posicao("migrate"))
        self.assertLess(posicao("check --deploy"), posicao("seed_catalog"))


class TetoDiarioTests(TestCase):
    """O limite de 24h — o que de fato protege a cota do provedor.

    O teto horário sozinho não bastava: 50/h sustentado por seis horas dá 300,
    que é a cota diária inteira do plano gratuito consumida só com recuperação
    de senha, antes do fim da tarde.
    """

    def setUp(self):
        self.url = reverse("accounts:password_reset")
        mail.outbox = []

    def _encher(self, quantos, idade_minutos):
        """Põe `quantos` pedidos globais no passado, dentro da janela de 24h.

        Escrito direto na tabela para não depender de mandar centenas de
        e-mails de verdade só para chegar perto do teto — o que o teste mede é
        a CONTA, e a conta é a mesma.
        """
        instante = timezone.now() - timezone.timedelta(minutes=idade_minutos)
        PedidoDeRecuperacao.objects.bulk_create(
            [
                PedidoDeRecuperacao(tipo="global", chave=limites.CHAVE_GLOBAL)
                for _ in range(quantos)
            ]
        )
        PedidoDeRecuperacao.objects.filter(tipo="global").update(criado_em=instante)

    def _pedir(self, email="alguem@exemplo.com", ip="203.0.113.55"):
        return self.client.post(self.url, {"email": email}, REMOTE_ADDR=ip, follow=True)

    def test_o_teto_diario_e_menor_que_a_cota_do_provedor(self):
        """Duzentos, e não 300: a cota é do PROVEDOR, não deste endpoint.

        Se a recuperação de senha pudesse consumir a cota inteira, qualquer
        outra mensagem que o app precise mandar no mesmo dia ficaria sem espaço.
        """
        self.assertLessEqual(limites.LIMITE_GLOBAL_DIARIO, 240)
        self.assertGreater(limites.LIMITE_GLOBAL_DIARIO, limites.LIMITE_GLOBAL)
        self.assertEqual(limites.JANELA_DIARIA_MINUTOS, 60 * 24)

    def test_o_teto_horario_sozinho_nao_protegeria_o_dia(self):
        """A conta que motivou este limite, escrita como asserção.

        Se alguém subir o teto horário achando que é generosidade, este teste
        mostra a conta antes de a cota ser consumida numa tarde.
        """
        em_24h = limites.LIMITE_GLOBAL * 24

        self.assertGreater(em_24h, 300, "o teto horário sozinho estoura a cota")
        self.assertLessEqual(limites.LIMITE_GLOBAL_DIARIO, 300)

    def test_abaixo_do_teto_diario_ainda_envia(self):
        # 90 minutos atrás: fora da janela horária, dentro da de 24h.
        self._encher(limites.LIMITE_GLOBAL_DIARIO - 1, idade_minutos=90)
        User.objects.create_user(email="alguem@exemplo.com", password="Senha!2026#Abc")

        self._pedir()

        self.assertEqual(len(mail.outbox), 1)

    def test_no_teto_diario_para_de_enviar(self):
        self._encher(limites.LIMITE_GLOBAL_DIARIO, idade_minutos=90)
        User.objects.create_user(email="alguem@exemplo.com", password="Senha!2026#Abc")

        self._pedir()

        self.assertEqual(mail.outbox, [])

    def test_o_bloqueio_diario_tem_a_mesma_resposta_de_sempre(self):
        User.objects.create_user(email="alguem@exemplo.com", password="Senha!2026#Abc")
        normal = self._pedir()
        self._encher(limites.LIMITE_GLOBAL_DIARIO, idade_minutos=90)

        bloqueada = self._pedir()

        self.assertEqual(normal.status_code, bloqueada.status_code)
        self.assertEqual(normal.content, bloqueada.content)

    def test_pedido_de_ontem_nao_conta_mais(self):
        """Fora da janela de 24h, a linha deixa de influenciar."""
        self._encher(limites.LIMITE_GLOBAL_DIARIO + 20, idade_minutos=60 * 25)
        User.objects.create_user(email="alguem@exemplo.com", password="Senha!2026#Abc")

        self._pedir()

        self.assertEqual(len(mail.outbox), 1)


class RetencaoDosPedidosTests(TestCase):
    """A tabela não pode crescer para sempre num banco gratuito."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="retencao@exemplo.com", password="Senha!2026#Abc"
        )
        mail.outbox = []

    def test_a_retencao_cobre_a_maior_janela_com_folga(self):
        """Apagar antes de 24h apagaria linha que ainda conta — e o limite
        diário viraria decoração."""
        self.assertGreaterEqual(
            limites.RETENCAO_MINUTOS, limites.JANELA_DIARIA_MINUTOS * 2
        )

    def test_linha_fora_da_retencao_e_apagada_no_proximo_envio(self):
        PedidoDeRecuperacao.objects.create(tipo="global", chave="antiga")
        PedidoDeRecuperacao.objects.filter(chave="antiga").update(
            criado_em=timezone.now()
            - timezone.timedelta(minutes=limites.RETENCAO_MINUTOS + 60)
        )

        self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}, follow=True
        )

        self.assertFalse(PedidoDeRecuperacao.objects.filter(chave="antiga").exists())

    def test_linha_dentro_da_janela_diaria_NAO_e_apagada(self):
        """A limpeza não pode comer o contador que ainda está valendo."""
        PedidoDeRecuperacao.objects.create(tipo="global", chave="recente")
        PedidoDeRecuperacao.objects.filter(chave="recente").update(
            criado_em=timezone.now() - timezone.timedelta(hours=20)
        )

        self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}, follow=True
        )

        self.assertTrue(PedidoDeRecuperacao.objects.filter(chave="recente").exists())

    def test_pedido_bloqueado_nao_dispara_limpeza(self):
        """A limpeza roda no caminho raro (envio), e não em todo request —
        senão um laço de abuso vira um laço de DELETE."""
        for _ in range(limites.LIMITE_POR_EMAIL):
            self.client.post(
                reverse("accounts:password_reset"), {"email": self.user.email},
                follow=True,
            )
        PedidoDeRecuperacao.objects.create(tipo="global", chave="testemunha")
        PedidoDeRecuperacao.objects.filter(chave="testemunha").update(
            criado_em=timezone.now()
            - timezone.timedelta(minutes=limites.RETENCAO_MINUTOS + 60)
        )

        # este já está bloqueado pelo limite por e-mail
        self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}, follow=True
        )

        self.assertTrue(PedidoDeRecuperacao.objects.filter(chave="testemunha").exists())


class PrivacidadeDoContadorTests(TestCase):
    """A tabela de limites não pode virar um registro de quem usou o app."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="privado@exemplo.com", password="Senha!2026#Abc"
        )

    def test_nem_email_nem_ip_ficam_legiveis(self):
        self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email},
            REMOTE_ADDR="203.0.113.99", follow=True,
        )

        guardado = " ".join(
            "%s %s" % (p.tipo, p.chave) for p in PedidoDeRecuperacao.objects.all()
        )
        self.assertNotIn("privado@exemplo.com", guardado)
        self.assertNotIn("privado", guardado)
        self.assertNotIn("203.0.113.99", guardado)

    def test_a_chave_e_um_hmac_de_64_caracteres(self):
        self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email},
            REMOTE_ADDR="203.0.113.99", follow=True,
        )

        for pedido in PedidoDeRecuperacao.objects.exclude(tipo="global"):
            with self.subTest(tipo=pedido.tipo):
                self.assertEqual(len(pedido.chave), 64)
                self.assertRegex(pedido.chave, r"^[0-9a-f]{64}$")

    def test_o_hmac_depende_da_secret_key(self):
        """HMAC e não hash simples: sem a chave, uma tabela de e-mails comuns
        não devolve o endereço."""
        with override_settings(SECRET_KEY="chave-um"):
            um = limites._hmac("igual@exemplo.com")
        with override_settings(SECRET_KEY="chave-dois"):
            dois = limites._hmac("igual@exemplo.com")

        self.assertNotEqual(um, dois)

    def test_os_indices_esperados_existem(self):
        """Sem eles, contar e limpar varrem a tabela inteira a cada pedido."""
        nomes = {i.name for i in PedidoDeRecuperacao._meta.indexes}

        self.assertIn("idx_pedido_rec_limite", nomes)
        self.assertIn("idx_pedido_rec_retencao", nomes)
        limite = next(
            i for i in PedidoDeRecuperacao._meta.indexes
            if i.name == "idx_pedido_rec_limite"
        )
        # `criado_em` por ULTIMO: coluna de faixa antes das de igualdade
        # impede o indice de servir para as duas.
        self.assertEqual(limite.fields, ["tipo", "chave", "criado_em"])


class OrigemDoPedidoTests(TestCase):
    """O contrato de `X-Forwarded-For`, conferido no Render e não suposto.

    As duas escolhas ingênuas erram para lados opostos, e este arquivo de teste
    existe para que nenhuma das duas volte:

      primeiro item sem proxy confiável -> qualquer um escolhe o próprio IP
      último item atrás do Render       -> todo mundo cai no IP do proxy dele
    """

    def _pedido(self, **meta):
        return RequestFactory().get("/", **meta)

    def test_sem_proxy_confiavel_o_cabecalho_e_ignorado(self):
        pedido = self._pedido(
            REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="1.2.3.4"
        )

        with override_settings(USA_PROXY_CONFIAVEL=False):
            self.assertEqual(limites.ip_do_pedido(pedido), "203.0.113.7")

    def test_atras_do_render_vale_o_PRIMEIRO_item(self):
        """O Render põe o cliente na frente e ANEXA o proprio.

        Pegar o ultimo devolveria o IP do proxy — e dez pedidos de dez pessoas
        diferentes bloqueariam a decima primeira.
        """
        pedido = self._pedido(
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="198.51.100.9, 10.0.0.5, 10.0.0.1",
        )

        with override_settings(USA_PROXY_CONFIAVEL=True):
            self.assertEqual(limites.ip_do_pedido(pedido), "198.51.100.9")

    def test_usuarios_diferentes_nao_caem_no_mesmo_balde(self):
        """O sintoma que o bug do "último item" produziria."""
        with override_settings(USA_PROXY_CONFIAVEL=True):
            um = limites.ip_do_pedido(
                self._pedido(REMOTE_ADDR="10.0.0.1",
                             HTTP_X_FORWARDED_FOR="198.51.100.9, 10.0.0.1")
            )
            dois = limites.ip_do_pedido(
                self._pedido(REMOTE_ADDR="10.0.0.1",
                             HTTP_X_FORWARDED_FOR="203.0.113.4, 10.0.0.1")
            )

        self.assertNotEqual(um, dois)

    def test_cabecalho_vazio_cai_para_remote_addr(self):
        pedido = self._pedido(REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="")

        with override_settings(USA_PROXY_CONFIAVEL=True):
            self.assertEqual(limites.ip_do_pedido(pedido), "203.0.113.7")

    def test_sem_nada_ainda_devolve_uma_chave(self):
        """Sem chave, `_hmac` estouraria e a recuperação de senha cairia."""
        pedido = self._pedido()
        pedido.META.pop("REMOTE_ADDR", None)

        self.assertTrue(limites.ip_do_pedido(pedido))

    def test_o_padrao_do_projeto_e_nao_confiar(self):
        """Numa configuração desconhecida, ler o cabeçalho é confiar em quem
        não se conhece."""
        self.assertFalse(getattr(settings, "USA_PROXY_CONFIAVEL", False) is True
                         and settings.DEBUG)


class ChaveSecretaDeProducaoTests(TestCase):
    """A SECRET_KEY fraca precisa DERRUBAR o deploy, e não só piscar um aviso.

    Produção subiu meses com `security.W009` aceso e ninguém foi impedido de
    nada, porque o build roda `check --deploy --fail-level ERROR` e W é
    warning. A causa não era descuido: `generateValue: true` no `render.yaml`
    gera 256 bits em base64, que dão 44 caracteres, e o Django exige 50 — o
    gerador da plataforma produz, calado, uma chave que a régua do Django
    reprova.

    Quem tem essa chave forja token de redefinição de senha para qualquer
    conta cadastrada. É a mesma falha que `FailClosedDeEmailTests` cobre pela
    porta da frente, entrando pelos fundos.
    """

    #: 50 caracteres exatos — o mínimo que o Django aceita.
    FORTE = "k" * 50

    #: 44, que é o que o Render entrega. O número não é decorativo: ele é a
    #: razão de este teste existir.
    DO_RENDER = "r" * 44

    def _erros(self, **cfg):
        from accounts.checks import chave_secreta_de_producao_e_forte

        cfg.setdefault("DEBUG", False)
        cfg.setdefault("SECRET_KEY_FALLBACKS", [])
        with override_settings(**cfg):
            return [e.id for e in chave_secreta_de_producao_e_forte(None)]

    def test_desenvolvimento_pode_usar_a_chave_padrao(self):
        from accounts.checks import CHAVE_DE_DESENVOLVIMENTO

        self.assertEqual(
            self._erros(DEBUG=True, SECRET_KEY=CHAVE_DE_DESENVOLVIMENTO), []
        )

    def test_chave_padrao_em_producao_derruba_o_build(self):
        from accounts.checks import CHAVE_DE_DESENVOLVIMENTO

        self.assertIn(
            "accounts.E004", self._erros(SECRET_KEY=CHAVE_DE_DESENVOLVIMENTO)
        )

    def test_a_chave_de_44_do_render_e_reprovada(self):
        """O caso real, e o motivo desta verificação existir."""
        self.assertIn("accounts.E005", self._erros(SECRET_KEY=self.DO_RENDER))

    def test_chave_de_50_passa(self):
        self.assertEqual(self._erros(SECRET_KEY=self.FORTE), [])

    def test_fallback_curto_tambem_e_reprovado(self):
        """Fallback assina com a mesma força — ou fraqueza — da chave velha.

        Durante a troca, uma sessão emitida pela chave antiga continua sendo
        aceita. Deixar uma chave de 44 na lista é manter o problema em pé com
        outro nome, e o Django avisa disso em `security.W025` — com a mesma
        letra W que ninguém lê.
        """
        self.assertIn(
            "accounts.E006",
            self._erros(SECRET_KEY=self.FORTE,
                        SECRET_KEY_FALLBACKS=[self.DO_RENDER]),
        )

    def test_fallback_forte_nao_reclama(self):
        self.assertEqual(
            self._erros(SECRET_KEY=self.FORTE,
                        SECRET_KEY_FALLBACKS=["a" * 50, "b" * 60]),
            [],
        )

    def test_a_mensagem_nunca_carrega_a_chave(self):
        """Verificação que despeja o segredo no log cria o problema que veio evitar.

        O log do build do Render fica visível para quem tem acesso ao painel, e
        um `check` "prestativo" que imprime o valor para ajudar a diagnosticar
        publicaria ali a chave que assina a sessão de todo mundo.
        """
        from accounts.checks import chave_secreta_de_producao_e_forte

        segredo = "chave-que-nao-pode-vazar-de-jeito-nenhum-0123456789"
        curta = "curta-demais-mas-tambem-secreta"
        with override_settings(DEBUG=False, SECRET_KEY=curta,
                               SECRET_KEY_FALLBACKS=[segredo]):
            texto = " ".join(
                "%s %s" % (e.msg, e.hint)
                for e in chave_secreta_de_producao_e_forte(None)
            )

        self.assertNotIn(segredo, texto)
        self.assertNotIn(curta, texto)
        # ...mas o tamanho precisa aparecer, senão a mensagem não ajuda ninguém.
        self.assertIn(str(len(curta)), texto)

    def test_a_verificacao_so_roda_com_deploy(self):
        """Mesma razão da de e-mail: a suíte roda com DEBUG=False.

        Registrada como verificação comum, ela derrubaria todo `manage.py test`
        acusando a chave de desenvolvimento de ser produção mal configurada.
        """
        from django.core.checks import registry

        comuns = {c.__name__ for c in registry.registry.get_checks()}
        de_deploy = {
            c.__name__
            for c in registry.registry.get_checks(include_deployment_checks=True)
        }

        self.assertIn("chave_secreta_de_producao_e_forte", de_deploy)
        self.assertNotIn("chave_secreta_de_producao_e_forte", comuns)

    def test_o_blueprint_nao_gera_mais_a_chave_pela_plataforma(self):
        """`generateValue: true` é a causa-raiz, e ela mora no `render.yaml`.

        Sem este teste, alguém restaura a linha antiga em seis meses "porque é
        mais prático não ter que definir a variável à mão" e o W009 volta —
        agora como E005, derrubando o build, sem ninguém entender por quê.
        """
        texto = (Path(settings.BASE_DIR) / "render.yaml").read_text(
            encoding="utf-8"
        )
        bloco = texto.split("- key: DJANGO_SECRET_KEY", 1)[1].split("- key:", 1)[0]
        self.assertNotIn("generateValue", bloco)
        self.assertIn("sync: false", bloco)


class PaginasLegaisTests(TestCase):
    """Política e Termos: acessíveis, honestas, e rascunho enquanto forem.

    Quem está decidindo se cria conta é justamente quem precisa ler o que o app
    faz com os dados — exigir login para isso inverteria a ordem da decisão.

    E enquanto faltar a identificação de quem responde pelos dados, as páginas
    se declaram rascunho e NÃO são oferecidas nas telas de entrada. Oferecer
    "leia nossa Política de Privacidade" e entregar um texto que se diz
    incompleto é pior que não oferecer: a pessoa clica confiando.
    """

    def test_abrem_sem_login(self):
        for nome in ("privacidade", "termos"):
            resposta = self.client.get(reverse(nome), secure=True)
            self.assertEqual(resposta.status_code, 200, nome)

    def test_uma_aponta_para_a_outra(self):
        self.assertContains(
            self.client.get(reverse("privacidade"), secure=True), reverse("termos")
        )
        self.assertContains(
            self.client.get(reverse("termos"), secure=True), reverse("privacidade")
        )

    def test_sem_os_dados_do_responsavel_a_pagina_se_declara_rascunho(self):
        with override_settings(LEGAL_PUBLICADO=False):
            for nome in ("privacidade", "termos"):
                html = self.client.get(reverse(nome), secure=True).content.decode()
                self.assertIn("ainda é um rascunho", html, nome)

    def test_rascunho_nao_e_linkado_do_cadastro_nem_do_login(self):
        with override_settings(LEGAL_PUBLICADO=False):
            for tela in ("accounts:signup", "accounts:login"):
                html = self.client.get(reverse(tela), secure=True).content.decode()
                self.assertNotIn(reverse("privacidade"), html, tela)

    def test_publicada_aparece_nas_telas_de_entrada(self):
        with override_settings(
            LEGAL_PUBLICADO=True,
            LEGAL_RESPONSAVEL="Fulano de Tal",
            LEGAL_CONTATO="contato@exemplo.com",
        ):
            for tela in ("accounts:signup", "accounts:login"):
                html = self.client.get(reverse(tela), secure=True).content.decode()
                self.assertIn(reverse("privacidade"), html, tela)
                self.assertIn(reverse("termos"), html, tela)

            html = self.client.get(reverse("privacidade"), secure=True).content.decode()
            self.assertNotIn("ainda é um rascunho", html)
            self.assertIn("Fulano de Tal", html)

    def test_nunca_declaram_empresa_que_nao_existe(self):
        """Um CNPJ inventado é pior que uma lacuna: a lacuna se resolve."""
        for nome in ("privacidade", "termos"):
            html = self.client.get(reverse(nome), secure=True).content.decode()
            self.assertNotRegex(html, r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", nome)

    def test_nao_prometem_tela_que_nao_existe(self):
        """Política que manda a pessoa a um 404 promete um direito e não entrega."""
        html = self.client.get(reverse("privacidade"), secure=True).content.decode()
        for nome in ("accounts:profile", "accounts:excluir_conta",
                     "accounts:exportar_dados"):
            self.assertIn(reverse(nome), html, nome)

    def test_nao_afirmam_conformidade_absoluta(self):
        """Nenhuma promessa que ninguém pode cumprir.

        A primeira versão deste teste proibia a expressão "segurança absoluta"
        e reprovou a própria política — que a usa para NEGAR a promessa:
        "o que não podemos prometer: segurança absoluta". Procurar a frase sem
        olhar o contexto reprovava exatamente a honestidade que ela deveria
        proteger. Agora o teste procura a AFIRMAÇÃO.
        """
        for nome in ("privacidade", "termos"):
            html = self.client.get(reverse(nome), secure=True).content.decode().lower()
            for afirmacao in ("100% conforme", "totalmente seguro",
                              "garantimos a segurança", "plenamente conforme",
                              "em total conformidade"):
                self.assertNotIn(afirmacao, html, "%s: %s" % (nome, afirmacao))

    def test_a_politica_admite_que_seguranca_absoluta_nao_existe(self):
        """O contrapeso do teste acima: silenciar a promessa não basta.

        Um texto que simplesmente não fala de segurança passaria no teste
        anterior. O que se quer é a declaração honesta — e ela some fácil numa
        revisão que busca deixar o texto "mais limpo".
        """
        html = self.client.get(reverse("privacidade"), secure=True).content.decode()
        self.assertIn("segurança absoluta", html.lower())
        self.assertIn("projeto pessoal", html.lower())


class ExportarDadosTests(TestCase):
    """Portabilidade. O arquivo sai com dado de saúde e passa a viver fora do
    app — então o que ele NÃO leva importa tanto quanto o que leva."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="dono@exemplo.invalid", password="senha-bem-forte-123"
        )
        WeightEntry.objects.create(
            user=self.user, date=timezone.localdate(), weight_kg=Decimal("82.40")
        )

    def _exportar(self):
        self.client.force_login(self.user)
        resposta = self.client.post(reverse("accounts:exportar_dados"), secure=True)
        return resposta, json.loads(resposta.content.decode())

    def test_anonimo_nao_exporta(self):
        resposta = self.client.post(reverse("accounts:exportar_dados"), secure=True)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

    def test_get_nao_exporta(self):
        """Com GET, um link de terceiro dispararia o download sozinho."""
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("accounts:exportar_dados"), secure=True).status_code,
            405,
        )

    def test_sai_como_arquivo_para_baixar(self):
        resposta, _ = self._exportar()

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("application/json", resposta["Content-Type"])
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertIn("no-store", resposta["Cache-Control"])

    def test_leva_o_que_a_pessoa_produziu(self):
        _, dados = self._exportar()

        self.assertEqual(dados["conta"]["email"], self.user.email)
        self.assertEqual(dados["pesagens"][0]["peso_kg"], "82.40")
        self.assertIn("exportado_em", dados)

    def test_o_peso_nao_vira_float(self):
        """`82.40` em float vira `82.40000000000001` no arquivo que a pessoa abre."""
        _, dados = self._exportar()
        self.assertIsInstance(dados["pesagens"][0]["peso_kg"], str)

    def test_nao_leva_segredo(self):
        resposta, _ = self._exportar()
        corpo = resposta.content.decode()

        self.assertNotIn(self.user.password, corpo)
        for proibido in ("pbkdf2", "argon2", "sessionid", "csrftoken",
                         "password", "senha", "token", "secret"):
            self.assertNotIn(proibido, corpo.lower(), proibido)

    def test_so_leva_dado_de_quem_pediu(self):
        """A defesa contra IDOR é a AUSÊNCIA de parâmetro. Isto prova."""
        outra = User.objects.create_user(
            email="outra.pessoa@exemplo.invalid", password="senha-bem-forte-123"
        )
        WeightEntry.objects.create(
            user=outra, date=timezone.localdate(), weight_kg=Decimal("55.55")
        )

        resposta, dados = self._exportar()
        corpo = resposta.content.decode()

        self.assertNotIn("outra.pessoa@exemplo.invalid", corpo)
        self.assertNotIn("55.55", corpo)
        self.assertEqual(len(dados["pesagens"]), 1)


class BootstrapAdministrativoTests(TestCase):
    """Dar acesso administrativo é seguro pelo que o comando RECUSA fazer.

    Produção subiu com `staff = 0`: `/admin/` publicado e ninguém que consiga
    entrar. O caminho fácil seria `createsuperuser` com uma senha inventada — e
    ele deixa a senha no histórico do shell, cria conta que ninguém controla, e
    entrega superuser, que ignora o sistema de permissões inteiro.
    """

    EMAIL = "operador@exemplo.com"

    def setUp(self):
        self.user = User.objects.create_user(
            email=self.EMAIL, password="senha-bem-forte-123"
        )

    def test_promove_sem_tocar_na_senha(self):
        antes = User.objects.get(pk=self.user.pk).password

        call_command("promover_admin", email=self.EMAIL, verbosity=0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertEqual(User.objects.get(pk=self.user.pk).password, antes)

    def test_nao_marca_superuser(self):
        """Superuser ignora as permissões. A diferença entre "pode administrar
        o NutriPlan" e "pode tudo que o Django permite" é o que separa um erro
        de operação de um incidente."""
        call_command("promover_admin", email=self.EMAIL, verbosity=0)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)

    def test_recusa_email_que_nao_existe_em_vez_de_criar(self):
        """Um typo não pode virar conta administrativa com e-mail que ninguém
        controla."""
        with self.assertRaises(CommandError):
            call_command("promover_admin", email="ninguem@exemplo.com", verbosity=0)

        self.assertFalse(User.objects.filter(email="ninguem@exemplo.com").exists())

    def test_rodar_duas_vezes_nao_duplica_nada(self):
        call_command("promover_admin", email=self.EMAIL, verbosity=0)
        call_command("promover_admin", email=self.EMAIL, verbosity=0)

        self.user.refresh_from_db()
        self.assertEqual(self.user.groups.count(), 1)
        self.assertEqual(
            RegistroAdministrativo.objects.filter(alvo=self.user).count(),
            1,
            "a segunda execução inventou um evento de auditoria",
        )

    def test_a_primeira_promocao_e_registrada_como_primeira(self):
        """A trilha precisa distinguir "nasceu o primeiro operador" de "mais um
        operador entrou". As duas coisas têm peso diferente numa investigação."""
        call_command("promover_admin", email=self.EMAIL, verbosity=0)

        registro = RegistroAdministrativo.objects.get(alvo=self.user)
        self.assertEqual(registro.acao, AcaoAdministrativa.PRIMEIRO_ADMIN)
        self.assertIsNone(registro.ator)
        self.assertEqual(registro.alvo_email, self.EMAIL)

    def test_a_segunda_pessoa_nao_e_registrada_como_primeira(self):
        call_command("promover_admin", email=self.EMAIL, verbosity=0)
        outra = User.objects.create_user(
            email="segunda@exemplo.com", password="senha-bem-forte-123"
        )

        call_command("promover_admin", email=outra.email, verbosity=0)

        self.assertEqual(
            RegistroAdministrativo.objects.get(alvo=outra).acao,
            AcaoAdministrativa.PROMOVEU_STAFF,
        )

    def test_a_trilha_nao_guarda_senha_nem_hash(self):
        """Trilha de auditoria que vaza é pior que trilha nenhuma: ela
        concentra num lugar só o que estava espalhado."""
        call_command("promover_admin", email=self.EMAIL, verbosity=0)

        detalhe = json.dumps(RegistroAdministrativo.objects.get(alvo=self.user).detalhe)

        self.user.refresh_from_db()
        self.assertNotIn(self.user.password, detalhe)
        for proibido in ("password", "senha", "token", "hash"):
            self.assertNotIn(proibido, detalhe.lower())



    def test_promove_pela_chave_primaria(self):
        """O identificador que pode viajar num repositório PÚBLICO.

        A primeira versão usava o SHA-256 do e-mail, com o argumento de que o
        hash "permite confirmar um palpite, não descobrir o endereço". O
        argumento é falso: o espaço de e-mails é enumerável, e testar milhões
        de candidatos contra um digest é descobrir. A chave primária é um
        inteiro sequencial que não carrega nada sobre a pessoa.
        """
        call_command("promover_admin", pk=self.user.pk, verbosity=0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_id_sem_conta_derruba_em_vez_de_criar(self):
        with self.assertRaises(CommandError):
            call_command("promover_admin", pk=999999, verbosity=0)

    def test_exige_um_identificador_e_apenas_um(self):
        """Ambiguidade num comando que dá acesso administrativo se resolve
        parando."""
        with self.assertRaises(CommandError):
            call_command("promover_admin", verbosity=0)
        with self.assertRaises(CommandError):
            call_command(
                "promover_admin", email=self.EMAIL, pk=self.user.pk, verbosity=0
            )

    def test_o_bootstrap_nao_repromove_quem_perdeu_o_acesso(self):
        """A trava é a TRILHA, e não o estado da conta.

        "Se não é staff, promove" seria mais simples e estaria errado: no dia em
        que alguém for deliberadamente removido do grupo, o próximo deploy
        devolveria o acesso sozinho — desfazendo uma decisão administrativa sem
        ninguém pedir e sem nada acusar. Este é o teste que separa as duas
        implementações.
        """
        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)

        # Alguém decide remover o acesso, deliberadamente.
        self.user.refresh_from_db()
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.user.groups.clear()

        # Um deploy roda o build de novo.
        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff, "o redeploy devolveu o acesso sozinho")
        self.assertEqual(self.user.groups.count(), 0)

    def test_sem_bootstrap_a_promocao_continua_possivel(self):
        """A trava é do caminho automático. Promover de novo pela mão continua
        sendo uma decisão que alguém pode tomar."""
        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)
        self.user.refresh_from_db()
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])

        call_command("promover_admin", email=self.EMAIL, verbosity=0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)

    def test_o_build_nao_promove_ninguem(self):
        """O bootstrap saiu do fluxo normal de deploy assim que cumpriu.

        Ele existiu por uma janela: produção subiu com `staff = 0` e o Render
        gratuito não tem shell, então o único lugar que roda dentro de produção
        era o build. Cumprida a promoção, um comando que dá acesso
        administrativo a cada deploy é superfície que não paga o que custa.

        O management command CONTINUA no projeto, para uso deliberado. O que
        sai é a execução automática.

        O teste também guarda o que nunca pode voltar: e-mail ou hash de e-mail
        no build de um repositório público.
        """
        build = (Path(settings.BASE_DIR) / "scripts" / "build.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("promover_admin", build)
        self.assertNotIn("--sha256", build)
        self.assertNotIn("@gmail", build)

        # E o comando não sumiu junto.
        from django.core.management import get_commands

        self.assertIn("promover_admin", get_commands())


    def test_falha_depois_do_staff_desfaz_tudo(self):
        """Estado parcial é pior que falha: alguém com `is_staff` e sem grupo
        entra no Admin e não consegue fazer nada, e nada na trilha explica por
        quê.

        A falha é injetada na criação do registro, que é a ÚLTIMA etapa — se a
        transação não envolver o comando inteiro, é exatamente aqui que sobra
        um usuário promovido sem trilha nenhuma.
        """
        with mock.patch.object(
            RegistroAdministrativo.objects, "create", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                call_command("promover_admin", pk=self.user.pk, verbosity=0)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff, "sobrou is_staff sem trilha")
        self.assertEqual(self.user.groups.count(), 0)
        self.assertEqual(RegistroAdministrativo.objects.count(), 0)

    def test_falha_no_grupo_desfaz_o_staff(self):
        """O outro lado: promoveu, quebrou ao aplicar o papel."""
        # O patch é no NOME DENTRO DO COMANDO, e não no módulo de origem: o
        # comando faz `from accounts.papeis import sincronizar_papeis`, então
        # ele guarda a própria referência e trocar a do módulo não o atinge.
        with mock.patch(
            "accounts.management.commands.promover_admin.sincronizar_papeis",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                call_command("promover_admin", pk=self.user.pk, verbosity=0)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertEqual(RegistroAdministrativo.objects.count(), 0)

    def test_depois_de_uma_falha_o_bootstrap_ainda_funciona(self):
        """Rollback completo significa que nada ficou travado: a trilha está
        vazia, então a trava one-shot não disparou por engano."""
        with mock.patch.object(
            RegistroAdministrativo.objects, "create", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)

        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertEqual(
            RegistroAdministrativo.objects.filter(
                alvo=self.user, acao=AcaoAdministrativa.PRIMEIRO_ADMIN
            ).count(),
            1,
        )

    def test_o_banco_recusa_dois_primeiro_admin_para_a_mesma_pessoa(self):
        """A checagem em Python é atravessada por duas transações simultâneas
        antes de qualquer uma gravar. Quem torna o caso raro impossível é a
        constraint."""
        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)

        with self.assertRaises(IntegrityError):
            RegistroAdministrativo.objects.create(
                acao=AcaoAdministrativa.PRIMEIRO_ADMIN,
                alvo=self.user,
                alvo_email=self.user.email,
            )

    def test_a_conta_do_google_nao_ganha_senha_no_bootstrap(self):
        """Conta sem senha utilizável continua sem senha utilizável.

        Foi o caso da primeira conta promovida em produção: ela entra por
        Google, e `has_usable_password()` é False. Gerar uma senha aqui seria
        criar uma credencial que a pessoa não escolheu e que passaria pelo log
        do build.
        """
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])

        call_command("promover_admin", pk=self.user.pk, verbosity=0)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertFalse(self.user.has_usable_password())


    def test_apagar_a_conta_apaga_a_trilha_sobre_ela(self):
        """O direito de eliminação vence a retenção de auditoria.

        A primeira versão deste model usava `SET_NULL` para a trilha sobreviver
        à exclusão, com `alvo_email` guardado justamente para responder "quem
        foi promovido antes de a conta sumir?". `test_toda_relacao_com_user_e_cascade`
        reprovou, e estava certo: guardar o endereço de quem PEDIU exclusão é o
        que o direito de eliminação existe para impedir, e é o que a Política de
        Privacidade promete.

        O preço fica registrado: a trilha administrativa é escopada às contas
        que existem. Auditoria e eliminação estão em tensão, e aqui a
        eliminação ganha — decisão que o projeto já tinha tomado e que um model
        novo não reabre sozinho.
        """
        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)
        self.assertEqual(RegistroAdministrativo.objects.count(), 1)

        self.user.delete()

        self.assertEqual(RegistroAdministrativo.objects.count(), 0)

    def test_o_email_guardado_e_o_do_momento_da_acao(self):
        """`alvo_email` não existe para sobreviver à exclusão — existe porque
        e-mail muda. A trilha precisa dizer para qual endereço o acesso foi dado
        NAQUELE dia, e não para qual ele aponta hoje."""
        call_command("promover_admin", pk=self.user.pk, verbosity=0)

        User.objects.filter(pk=self.user.pk).update(email="outro@exemplo.com")

        registro = RegistroAdministrativo.objects.get(alvo=self.user)
        self.assertEqual(registro.alvo_email, self.EMAIL)


    def test_o_marcador_one_shot_nao_sobrevive_a_exclusao_da_conta(self):
        """DOCUMENTA o contrato atual; não propõe mudá-lo.

        A trava one-shot mora no `RegistroAdministrativo`, e esse model é
        CASCADE em relação a `User` — decisão do projeto, verificada por
        `test_toda_relacao_com_user_e_cascade`. A consequência é que apagar a
        conta apaga o marcador junto.

        Isso é coerente: a trava protege UMA pessoa contra ser repromovida, e
        se essa pessoa deixou de existir não há o que proteger. Mas ninguém
        deve assumir que o marcador é permanente — quem ler a trava sem ler
        isto pode concluir que "o bootstrap nunca mais roda", quando o correto
        é "não roda de novo para esta conta enquanto ela existir".
        """
        call_command("promover_admin", pk=self.user.pk, bootstrap=True, verbosity=0)
        self.assertEqual(
            RegistroAdministrativo.objects.filter(
                acao=AcaoAdministrativa.PRIMEIRO_ADMIN
            ).count(),
            1,
        )

        self.user.delete()

        self.assertEqual(
            RegistroAdministrativo.objects.filter(
                acao=AcaoAdministrativa.PRIMEIRO_ADMIN
            ).count(),
            0,
            "o marcador sobreviveu à exclusão da conta",
        )


class PapeisAdministrativosTests(TestCase):
    """Suporte e administração não podem ser a mesma coisa.

    Separar depois, com gente já operando como administrador, é migração de
    hábito e não de dados — por isso os dois grupos nascem juntos, mesmo com um
    operador só.
    """

    def test_sincronizar_e_idempotente(self):
        primeiro = papeis.sincronizar_papeis()
        segundo = papeis.sincronizar_papeis()

        self.assertEqual(primeiro, segundo)
        self.assertEqual(Group.objects.filter(name__in=primeiro).count(), 2)

    def test_suporte_nao_pode_mexer_em_conta(self):
        """O papel existe para atender quem escreve, não para editar a pessoa."""
        papeis.sincronizar_papeis()
        grupo = Group.objects.get(name=papeis.SUPORTE)

        codenames = set(grupo.permissions.values_list("codename", flat=True))

        self.assertIn("view_user", codenames)
        for proibida in ("change_user", "add_user", "delete_user"):
            self.assertNotIn(proibida, codenames)

    def test_nenhum_papel_pode_apagar_nada(self):
        """Excluir conta é decisão da pessoa e tem fluxo próprio. Não pode
        virar um botão de operação de rotina."""
        papeis.sincronizar_papeis()

        for papel in papeis.PAPEIS:
            codenames = set(
                Group.objects.get(name=papel).permissions.values_list(
                    "codename", flat=True
                )
            )
            with self.subTest(papel=papel):
                self.assertEqual(
                    [c for c in codenames if c.startswith("delete_")], []
                )

    def test_o_historico_da_pessoa_e_somente_leitura(self):
        """Plano, refeição e peso são retrato do que ela fez. Editar pelo
        painel reescreveria o histórico dela."""
        papeis.sincronizar_papeis()
        codenames = set(
            Group.objects.get(name=papeis.ADMINISTRADORES).permissions.values_list(
                "codename", flat=True
            )
        )

        for modelo in ("meallog", "nutritionplan", "trainingplan", "weightentry"):
            with self.subTest(modelo=modelo):
                self.assertIn(f"view_{modelo}", codenames)
                self.assertNotIn(f"change_{modelo}", codenames)

    def test_todo_model_declarado_no_papel_existe_de_verdade(self):
        """A lista de permissões é escrita à mão e o catálogo de models muda.

        Sem este teste, renomear um model deixa uma entrada morta no papel —
        e permissão que falta vira "acesso negado" para o operador, sem nada
        apontando para a causa.
        """
        for papel, desejadas in papeis.PAPEIS.items():
            for app_label, modelo in desejadas:
                with self.subTest(papel=papel, model=f"{app_label}.{modelo}"):
                    self.assertTrue(
                        ContentType.objects.filter(
                            app_label=app_label, model=modelo
                        ).exists(),
                        f"{app_label}.{modelo} não existe mais",
                    )


class EntradaDoAdminTests(TestCase):
    """O Admin autentica pelo login do NutriPlan e autoriza por `is_staff`.

    O primeiro operador entra por Google e não tem senha utilizável —
    `has_usable_password()` é False, confirmado no banco de produção. O
    formulário de login do Django Admin pede senha, e a recuperação de senha
    não atende contas sociais de propósito. Sem esta integração, a conta
    promovida ficaria com acesso administrativo que ela não consegue usar.

    O que NÃO muda: `admin_view` continua exigindo `is_active` e `is_staff` em
    toda view, e as permissões por model continuam valendo. Só a tela de login
    saiu.
    """

    def _cria(self, email, **flags):
        user = User.objects.create_user(email=email, password="senha-bem-forte-123")
        for campo, valor in flags.items():
            setattr(user, campo, valor)
        if flags:
            user.save(update_fields=list(flags))
        return user

    def test_anonimo_vai_para_o_login_do_app(self):
        resposta = self.client.get("/admin/", follow=False)
        self.assertEqual(resposta.status_code, 302)

        entrada = self.client.get(resposta["Location"], follow=False)

        self.assertEqual(entrada.status_code, 302)
        self.assertIn(reverse("accounts:login"), entrada["Location"])

    def test_usuario_comum_autenticado_nao_entra_e_nao_entra_em_laco(self):
        """Mandar de volta ao login criaria um laço: o login veria a sessão
        válida, devolveria para /admin/, e a pessoa ficaria presa entre duas
        telas sem nenhuma explicar o que houve."""
        self.client.force_login(self._cria("comum@exemplo.com"))

        resposta = self.client.get("/admin/login/", follow=False)

        self.assertEqual(resposta.status_code, 403)

    def test_staff_sem_senha_utilizavel_entra(self):
        """O caso que motivou tudo: conta Google-only."""
        admin = self._cria("google@exemplo.com", is_staff=True)
        admin.set_unusable_password()
        admin.save(update_fields=["password"])
        self.client.force_login(admin)

        self.assertFalse(admin.has_usable_password())
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_staff_com_senha_continua_entrando(self):
        """A integração não pode quebrar quem autentica do jeito antigo."""
        self.client.force_login(self._cria("comsenha@exemplo.com", is_staff=True))

        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_staff_inativo_nao_entra(self):
        """`is_staff` sozinho não basta: `admin_view` exige conta ativa, e
        desativar uma conta precisa continuar sendo suficiente para tirar o
        acesso administrativo dela."""
        inativo = self._cria("inativo@exemplo.com", is_staff=True, is_active=False)
        self.client.force_login(inativo)

        resposta = self.client.get("/admin/", follow=False)

        self.assertNotEqual(resposta.status_code, 200)

    def test_superuser_nao_e_necessario(self):
        """Nenhuma parte disto depende de superuser — a régua é `is_staff`."""
        admin = self._cria("naosuper@exemplo.com", is_staff=True)
        self.client.force_login(admin)

        self.client.get("/admin/")

        admin.refresh_from_db()
        self.assertFalse(admin.is_superuser)


class NextDoAdminTests(TestCase):
    """`next` vem da URL e é controlado por quem monta o link.

    Sem validação, `?next=https://site-falso/` transforma o endereço do
    NutriPlan numa rampa: a pessoa clica num link do domínio real, autentica de
    verdade, e termina em outro site logo depois do login — que é o momento em
    que ela está mais disposta a digitar credencial de novo.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@exemplo.com", password="senha-bem-forte-123"
        )
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])
        self.client.force_login(self.admin)

    def _destino(self, next_):
        resposta = self.client.get(f"/admin/login/?next={next_}", follow=False)
        return resposta["Location"]

    def test_caminho_interno_e_preservado(self):
        self.assertEqual(self._destino("/admin/"), "/admin/")
        self.assertEqual(
            self._destino("/admin/accounts/user/"), "/admin/accounts/user/"
        )

    def test_endereco_externo_e_descartado(self):
        for hostil in (
            "https://site-falso.exemplo/",
            "http://site-falso.exemplo/",
            "//site-falso.exemplo/",
            "javascript:alert(1)",
            "\\\\site-falso.exemplo",
        ):
            with self.subTest(next=hostil):
                self.assertEqual(self._destino(hostil), reverse("admin:index"))

    def test_sem_next_volta_para_o_admin(self):
        resposta = self.client.get("/admin/login/", follow=False)

        self.assertEqual(resposta["Location"], reverse("admin:index"))


class DestinoNoLoginSocialTests(TestCase):
    """O destino de retorno precisa atravessar o botão do Google.

    Medido no navegador, em produção, antes da correção: pedir `/admin/` levava
    a `/conta/entrar/?next=/admin/` — o destino CHEGAVA ao login —, mas o
    formulário do Google enviava só `csrfmiddlewaretoken` e `process`. O
    allauth recebia o fluxo sem destino e caía em `LOGIN_REDIRECT_URL`, que é
    `/hoje/`.

    O contraste na mesma tela é o que fecha o diagnóstico: o formulário de
    senha leva o destino de graça, porque não tem `action` e o POST vai para a
    URL atual com a query string.
    """

    ENTRAR = reverse_lazy("accounts:login")
    CADASTRAR = reverse_lazy("accounts:signup")

    def _campos_do_google(self, url):
        html = self.client.get(url).content.decode()
        formulario = re.search(
            r'<form class="google-entrada".*?</form>', html, re.S
        )
        return formulario.group(0) if formulario else ""

    def test_entrar_leva_o_destino_para_o_google(self):
        formulario = self._campos_do_google(f"{self.ENTRAR}?next=/admin/")

        self.assertIn('name="next"', formulario)
        self.assertIn('value="/admin/"', formulario)

    def test_entrar_leva_subrota_administrativa(self):
        formulario = self._campos_do_google(
            f"{self.ENTRAR}?next=/admin/accounts/user/"
        )

        self.assertIn('value="/admin/accounts/user/"', formulario)

    def test_sem_destino_o_campo_nao_existe(self):
        """Campo vazio no formulário é ruído que o allauth teria que ignorar."""
        formulario = self._campos_do_google(self.ENTRAR)

        self.assertNotIn('name="next"', formulario)

    def test_cadastro_nao_carrega_destino_administrativo(self):
        """Quem cria conta vira usuário comum. Mandá-la direto para uma tela de
        acesso negado é seguro e péssimo — o primeiro minuto de uso terminaria
        num 403."""
        formulario = self._campos_do_google(f"{self.CADASTRAR}?next=/admin/")

        self.assertNotIn('name="next"', formulario)

    def test_o_valor_e_escapado_pelo_template(self):
        """Sem `safe` e sem concatenação: o escaping normal do Django é o que
        impede um destino de fechar o atributo e injetar markup."""
        formulario = self._campos_do_google(
            f"{self.ENTRAR}?next=/admin/%22%3E%3Cscript%3E"
        )

        self.assertNotIn("<script>", formulario)

    def test_o_login_por_senha_ja_levava_o_destino(self):
        """Contrato irmão, verificado para o Admin não depender só do Google.

        O formulário de senha não tem `action`, então o POST vai para a URL
        atual COM a query string, e `LoginView.get_redirect_url` lê `next` do
        GET quando não há no POST.
        """
        html = self.client.get(f"{self.ENTRAR}?next=/admin/").content.decode()
        senha = re.search(r'<form method="post"(?![^>]*google).*?</form>', html, re.S)

        self.assertIsNotNone(senha)
        self.assertNotIn('action=', senha.group(0)[:200])

    def test_o_destino_sobrevive_ao_login_por_senha(self):
        """A ponta a ponta do caminho da senha, que é a que dá para testar sem
        sair para o Google."""
        staff = User.objects.create_user(
            email="staff@exemplo.com", password="senha-bem-forte-123"
        )
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])

        resposta = self.client.post(
            f"{self.ENTRAR}?next=/admin/",
            {"username": staff.email, "password": "senha-bem-forte-123"},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], "/admin/")

    def test_usuario_comum_nao_ganha_admin_pelo_destino(self):
        """O destino leva à porta; quem decide continua sendo o AdminSite."""
        comum = User.objects.create_user(
            email="comum2@exemplo.com", password="senha-bem-forte-123"
        )

        self.client.post(
            f"{self.ENTRAR}?next=/admin/",
            {"username": comum.email, "password": "senha-bem-forte-123"},
        )

        self.assertEqual(self.client.get("/admin/login/").status_code, 403)

    def test_o_allauth_e_quem_descarta_destino_externo(self):
        """Não duplicamos a validação: `get_next_redirect_url` do allauth
        descarta o que não passa em `is_safe_url`.

        O teste afirma o CONTRATO de que a proteção existe e é do allauth — se
        um dia ele parar de sanitizar, isto quebra e a decisão de onde validar
        volta para a mesa.
        """
        from allauth.account.adapter import get_adapter
        from allauth.core.context import request_context

        # `is_safe_url` lê o host do contexto de request do allauth, e não do
        # argumento. Chamá-lo fora do contexto estoura — foi assim que a
        # primeira versão deste teste errou.
        pedido = self.client.get(self.ENTRAR).wsgi_request

        with request_context(pedido):
            adaptador = get_adapter()
            for hostil in (
                "https://site-falso.exemplo/",
                "//site-falso.exemplo/",
                "javascript:alert(1)",
            ):
                with self.subTest(destino=hostil):
                    self.assertFalse(adaptador.is_safe_url(hostil))

            self.assertTrue(adaptador.is_safe_url("/admin/"))


class EscaladaDePrivilegioNoUserAdminTests(TestCase):
    """Quem tem `change_user` não pode virar superuser pelo formulário.

    O `UserAdmin` do Django traz `is_superuser`, `is_staff`, `groups` e
    `user_permissions` no fieldset de permissões. Qualquer staff com
    `change_user` recebe esses controles — e o papel Administradores NutriPlan
    tem `change_user`, porque precisa ajustar conta de gente.

    O resultado é que a trava construída em outro lugar não vale: `/admin/auth/group/`
    responde 403 e `/admin/auth/permission/` nem está registrado, mas o
    formulário de usuário oferece os MESMOS três controles. Uma porta trancada
    e a janela ao lado aberta.

    Estes testes provam pelo ESTADO NO BANCO, e não pelo código de resposta:
    um POST que devolve 302 e não grava nada é sucesso; um que devolve 302 e
    grava é a falha. `refresh_from_db()` é o que separa os dois.

    A regra vale para QUALQUER staff não-superuser com `change_user`, e não
    para o nome de um grupo: amanhã outro grupo recebe essa permissão, e a
    proteção precisa acompanhar.
    """

    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def setUp(self):
        self.operador = User.objects.create_user(
            email="operador-admin@exemplo.com", password="senha-bem-forte-123"
        )
        self.operador.is_staff = True
        self.operador.save(update_fields=["is_staff"])
        self.operador.groups.add(Group.objects.get(name=papeis.ADMINISTRADORES))

        self.comum = User.objects.create_user(
            email="alvo-comum@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(self.operador)

    def _formulario(self, alvo, **mudancas):
        """O POST mínimo que o UserAdmin aceita, com as mudanças pedidas."""
        dados = {
            "email": alvo.email,
            "first_name": alvo.first_name,
            "last_name": alvo.last_name,
            "is_active": "on" if alvo.is_active else "",
            "last_login_0": "", "last_login_1": "",
            "date_joined_0": alvo.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": alvo.date_joined.strftime("%H:%M:%S"),
            # Os inlines exigem management form mesmo quando vazios.
            "profile-TOTAL_FORMS": "0", "profile-INITIAL_FORMS": "0",
            "profile-MIN_NUM_FORMS": "0", "profile-MAX_NUM_FORMS": "1",
            "training_days-TOTAL_FORMS": "0", "training_days-INITIAL_FORMS": "0",
            "training_days-MIN_NUM_FORMS": "0", "training_days-MAX_NUM_FORMS": "1000",
            "weight_entries-TOTAL_FORMS": "0", "weight_entries-INITIAL_FORMS": "0",
            "weight_entries-MIN_NUM_FORMS": "0", "weight_entries-MAX_NUM_FORMS": "1000",
        }
        dados.update(mudancas)
        return dados

    def _postar(self, alvo, **mudancas):
        return self.client.post(
            f"/admin/accounts/user/{alvo.pk}/change/",
            self._formulario(alvo, **mudancas),
            secure=True,
            follow=True,
        )

    def test_nao_consegue_virar_superuser(self):
        """Autoescalada: o operador tenta se promover."""
        self._postar(self.operador, is_superuser="on", is_staff="on")

        self.operador.refresh_from_db()
        self.assertFalse(
            self.operador.is_superuser,
            "um staff com change_user virou superuser pelo formulário",
        )

    def test_nao_consegue_promover_outra_pessoa_a_superuser(self):
        self._postar(self.comum, is_superuser="on", is_staff="on")

        self.comum.refresh_from_db()
        self.assertFalse(self.comum.is_superuser)
        self.assertFalse(self.comum.is_staff)

    def test_nao_consegue_conceder_grupo(self):
        grupo = Group.objects.get(name=papeis.ADMINISTRADORES)

        self._postar(self.comum, groups=[str(grupo.pk)])

        self.comum.refresh_from_db()
        self.assertEqual(list(self.comum.groups.all()), [])

    def test_nao_consegue_conceder_permissao_avulsa(self):
        """`user_permissions` é o caminho mais silencioso dos quatro: não passa
        por grupo nenhum e concede capacidade direta."""
        permissao = Permission.objects.get(codename="delete_user")

        self._postar(self.comum, user_permissions=[str(permissao.pk)])

        self.comum.refresh_from_db()
        self.assertEqual(list(self.comum.user_permissions.all()), [])

    def test_o_formulario_nao_oferece_controle_de_autorizacao(self):
        """Complementa os POSTs: o GET também não deve oferecer os controles.

        Esconder no GET sem barrar o POST seria falso conforto; barrar o POST
        sem esconder no GET seria uma tela que promete o que não cumpre. Os
        dois lados precisam concordar.
        """
        html = self.client.get(
            f"/admin/accounts/user/{self.comum.pk}/change/", secure=True
        ).content.decode()

        for campo in ("is_superuser", "groups", "user_permissions"):
            with self.subTest(campo=campo):
                self.assertNotIn(f'name="{campo}"', html)

    def test_o_administrador_continua_conseguindo_o_que_foi_aprovado(self):
        """Controle positivo: o hardening não pode inutilizar o UserAdmin.

        Sem isto, "negar tudo" passaria em todos os testes acima e destruiria a
        ferramenta que a missão existe para entregar.
        """
        resposta = self._postar(self.comum, first_name="Nome Corrigido")

        self.assertEqual(resposta.status_code, 200)
        self.comum.refresh_from_db()
        self.assertEqual(self.comum.first_name, "Nome Corrigido")

    def test_superuser_de_verdade_mantem_as_capacidades(self):
        """A trava é para staff NÃO-superuser. Um superuser legítimo continua
        administrando autorização — senão não haveria como corrigir nada."""
        raiz = User.objects.create_superuser(
            email="raiz@exemplo.com", password="senha-bem-forte-123"
        )
        self.client.force_login(raiz)

        html = self.client.get(
            f"/admin/accounts/user/{self.comum.pk}/change/", secure=True
        ).content.decode()

        self.assertIn('name="is_superuser"', html)
        self.assertIn('name="groups"', html)


class SuperficieDoAdminTests(TestCase):
    """O que o Admin oferece, medido por HTTP e não por `has_perm`.

    Permissão no banco, model registrado e URL alcançável são três coisas
    diferentes, e confundi-las já produziu duas conclusões erradas nesta
    auditoria: `Profile` foi dado como não exposto porque a varredura olhava
    só `admin.site._registry` e não enxergava inlines; e `PushSubscription` foi
    dado como exposto porque estava registrado, quando a URL responde 403.
    """

    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def setUp(self):
        self.operador = User.objects.create_user(
            email="op-superficie@exemplo.com", password="senha-bem-forte-123"
        )
        self.operador.is_staff = True
        self.operador.save(update_fields=["is_staff"])
        self.operador.groups.add(Group.objects.get(name=papeis.ADMINISTRADORES))
        self.client.force_login(self.operador)

    def test_telas_que_expoem_credencial_nao_existem(self):
        """`SocialToken` guarda token de acesso; `SocialApp`, o segredo do app
        OAuth. Desregistradas: a URL some, em vez de depender de a permissão
        continuar ausente para sempre."""
        for rota in (
            "/admin/socialaccount/socialtoken/",
            "/admin/socialaccount/socialapp/",
        ):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota, secure=True).status_code, 404)

    def test_a_assinatura_push_nunca_mostra_o_material_de_assinatura(self):
        """Mesmo com permissão concedida, endpoint e chaves não aparecem."""
        from django.contrib.auth.models import Permission

        self.operador.user_permissions.add(
            Permission.objects.get(codename="view_pushsubscription")
        )
        assinatura = PushSubscription.objects.create(
            user=self.operador,
            endpoint="https://push.exemplo/inscricao/SEGREDO-DO-ENDPOINT",
            p256dh_key="CHAVE-P256DH-QUE-NAO-PODE-VAZAR",
            auth_key="CHAVE-AUTH-QUE-NAO-PODE-VAZAR",
            user_agent="Mozilla/5.0 " + "x" * 200,
        )

        for rota in (
            "/admin/push/pushsubscription/",
            f"/admin/push/pushsubscription/{assinatura.pk}/change/",
        ):
            html = self.client.get(rota, secure=True).content.decode()
            with self.subTest(rota=rota):
                self.assertNotIn("SEGREDO-DO-ENDPOINT", html)
                self.assertNotIn("CHAVE-P256DH-QUE-NAO-PODE-VAZAR", html)
                self.assertNotIn("CHAVE-AUTH-QUE-NAO-PODE-VAZAR", html)

    def test_a_trilha_administrativa_e_imutavel_inclusive_por_post(self):
        """Esconder botão não basta: `has_*_permission` é o que o Django
        consulta antes de aceitar o pedido."""
        from django.core.management import call_command
        from django.contrib.auth.models import Permission

        self.operador.user_permissions.add(
            Permission.objects.get(codename="view_registroadministrativo")
        )
        alvo = User.objects.create_user(
            email="alvo-trilha@exemplo.com", password="senha-bem-forte-123"
        )
        call_command("promover_admin", pk=alvo.pk, verbosity=0)
        registro = RegistroAdministrativo.objects.get(alvo=alvo)
        antes = (registro.acao, registro.alvo_email)

        self.assertEqual(
            self.client.get("/admin/accounts/registroadministrativo/", secure=True).status_code,
            200,
        )
        for rota, dados in (
            ("/admin/accounts/registroadministrativo/add/", {"acao": "primeiro_admin"}),
            (f"/admin/accounts/registroadministrativo/{registro.pk}/change/", {"acao": "revogou_staff"}),
            (f"/admin/accounts/registroadministrativo/{registro.pk}/delete/", {"post": "yes"}),
        ):
            with self.subTest(rota=rota):
                self.assertIn(
                    self.client.post(rota, dados, secure=True).status_code, (403, 404)
                )

        registro.refresh_from_db()
        self.assertEqual((registro.acao, registro.alvo_email), antes)

    def test_o_peso_nao_pode_ser_editado_nem_apagado(self):
        """Peso é o dado mais sensível do app. Editar reescreveria o histórico
        de alguém; apagar destruiria a série que ela construiu."""
        from django.contrib.auth.models import Permission

        for codename in ("view_weightentry", "change_weightentry", "delete_weightentry"):
            self.operador.user_permissions.add(
                Permission.objects.get(codename=codename)
            )
        pesagem = WeightEntry.objects.create(
            user=self.operador, date=date(2026, 9, 1), weight_kg=Decimal("82.4")
        )

        self.client.post(
            f"/admin/accounts/weightentry/{pesagem.pk}/change/",
            {"user": self.operador.pk, "date": "2026-09-01", "weight_kg": "99.9"},
            secure=True,
        )
        self.client.post(
            f"/admin/accounts/weightentry/{pesagem.pk}/delete/", {"post": "yes"}, secure=True
        )

        pesagem.refresh_from_db()
        self.assertEqual(pesagem.weight_kg, Decimal("82.4"))
        self.assertTrue(WeightEntry.objects.filter(pk=pesagem.pk).exists())

    def test_o_perfil_nao_aceita_edicao_de_dado_corporal(self):
        """O inline passou a declarar campo por campo. Altura e nascimento são
        informação que a própria pessoa deu, e não há caso de suporte para
        alterá-las pelo painel."""
        perfil = Profile.objects.create(
            user=self.operador,
            sex=Sex.MALE,
            birth_date=date(1995, 4, 12),
            height_cm=178,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
        )

        html = self.client.get(
            f"/admin/accounts/user/{self.operador.pk}/change/", secure=True
        ).content.decode()

        for campo in ("profile-0-height_cm", "profile-0-birth_date", "profile-0-goal"):
            with self.subTest(campo=campo):
                self.assertNotIn(f'name="{campo}"', html)

        self.assertEqual(perfil.height_cm, 178)

    def test_a_lista_de_usuarios_nao_cresce_uma_consulta_por_linha(self):
        """Com 50 contas o Admin precisa continuar utilizável."""
        for i in range(30):
            User.objects.create_user(
                email="carga%02d@exemplo.com" % i, password="senha-bem-forte-123"
            )

        # Sete é o custo MEDIDO, e o número está escrito para que um N+1
        # futuro apareça como falha em vez de lentidão silenciosa.
        with self.assertNumQueries(7):
            self.client.get("/admin/accounts/user/", secure=True)

        # O número sozinho não prova ausência de N+1: sete com 31 contas
        # também seria o custo de uma lista que faz uma consulta por linha se
        # a página mostrasse sete linhas. A prova é o custo NÃO MUDAR quando o
        # número de linhas dobra.
        #
        # A coluna "Google" é o motivo de isto existir agora: ela vem de uma
        # relação (`SocialAccount`) e a forma ingênua — perguntar por conta —
        # custaria uma consulta por linha. Ela é `Exists` anotado no queryset,
        # que vira subconsulta dentro do mesmo SELECT.
        for i in range(30, 60):
            User.objects.create_user(
                email="carga%02d@exemplo.com" % i, password="senha-bem-forte-123"
            )
        SocialAccount.objects.create(
            user=User.objects.get(email="carga00@exemplo.com"),
            provider="google",
            uid="uid-carga-00",
        )

        with self.assertNumQueries(7):
            self.client.get("/admin/accounts/user/", secure=True)


class PedirNovaEscolhaDeDivisaoTests(TestCase):
    """A única escrita administrativa aprovada sobre o perfil.

    O caso de suporte é concreto: `preferencia_muda_a_divisao` não pergunta
    nada até três dias de treino, então quem monta a ficha treinando três vezes
    nunca vê o passo 4 e fica com o TRES que o campo trazia de fábrica. Ao
    marcar o quarto dia, a divisão passa a importar e ela está presa numa
    escolha que não fez.

    A resposta é fazer o app PERGUNTAR de novo — nunca escolher por ela. Por
    isso a ação mexe em `split_preference_confirmada` e não encosta em
    `split_preference`: atribuir uma divisão nova seria a mesma mentira, com
    outro autor.

    A permissão é de propósito e não `change_profile`: a segunda autorizaria
    vinte campos para liberar um.
    """

    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def setUp(self):
        self.operador = self._staff("op-divisao@exemplo.com", papeis.ADMINISTRADORES)
        self.suporte = self._staff("sup-divisao@exemplo.com", papeis.SUPORTE)
        self.alvo = User.objects.create_user(
            email="alvo-divisao@exemplo.com", password="senha-bem-forte-123"
        )
        self.perfil = Profile.objects.create(
            user=self.alvo,
            sex=Sex.MALE,
            birth_date=date(1995, 4, 12),
            height_cm=178,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
            split_preference=SplitPreference.TRES,
            split_preference_confirmada=True,
        )

    @staticmethod
    def _staff(email, papel):
        u = User.objects.create_user(email=email, password="senha-bem-forte-123")
        u.is_staff = True
        u.save(update_fields=["is_staff"])
        u.groups.add(Group.objects.get(name=papel))
        return u

    def _rota(self):
        return f"/admin/accounts/user/{self.alvo.pk}/pedir-nova-divisao/"

    # A e B — quem tem a capacidade
    def test_administrador_tem_a_permissao_dedicada(self):
        self.assertTrue(
            self.operador.has_perm("accounts.pedir_nova_escolha_de_divisao")
        )

    def test_suporte_nao_tem_a_permissao(self):
        self.assertFalse(
            self.suporte.has_perm("accounts.pedir_nova_escolha_de_divisao")
        )

    # C — a permissão genérica NÃO foi concedida a ninguém
    def test_ninguem_recebe_change_profile_generico(self):
        """`change_profile` cobriria vinte campos para autorizar um."""
        for papel, usuario in (
            (papeis.ADMINISTRADORES, self.operador),
            (papeis.SUPORTE, self.suporte),
        ):
            with self.subTest(papel=papel):
                self.assertFalse(usuario.has_perm("accounts.change_profile"))

    # D — o inline não oferece campo editável
    def test_o_inline_do_perfil_nao_tem_campo_editavel(self):
        self.client.force_login(self.operador)

        html = self.client.get(
            f"/admin/accounts/user/{self.alvo.pk}/change/", secure=True
        ).content.decode()

        for campo in (
            "profile-0-split_preference",
            "profile-0-split_preference_confirmada",
            "profile-0-kcal_adjustment",
            "profile-0-height_cm",
            "profile-0-birth_date",
        ):
            with self.subTest(campo=campo):
                self.assertNotIn(f'name="{campo}"', html)

    # E, F e G — o que a ação faz e o que ela não toca
    def test_a_acao_apenas_desmarca_a_confirmacao(self):
        self.client.force_login(self.operador)

        self.client.post(self._rota(), {}, secure=True)

        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.split_preference_confirmada)
        self.assertEqual(self.perfil.split_preference, SplitPreference.TRES)

    def test_a_acao_nao_altera_nenhum_outro_campo(self):
        self.client.force_login(self.operador)
        antes = {
            campo: getattr(self.perfil, campo)
            for campo in (
                "split_preference", "kcal_adjustment", "birth_date",
                "height_cm", "goal", "activity_level", "sex",
            )
        }

        self.client.post(self._rota(), {}, secure=True)

        self.perfil.refresh_from_db()
        for campo, valor in antes.items():
            with self.subTest(campo=campo):
                self.assertEqual(getattr(self.perfil, campo), valor)

    # H — no-op quando já está aguardando
    def test_quando_ja_esta_aguardando_nao_escreve_de_novo(self):
        """Trilha com evento falso é pior que trilha curta: faz alguém procurar
        uma causa que não existiu."""
        Profile.objects.filter(pk=self.perfil.pk).update(
            split_preference_confirmada=False
        )
        self.client.force_login(self.operador)
        antes = RegistroAdministrativo.objects.count()

        self.client.post(self._rota(), {}, secure=True)

        self.perfil.refresh_from_db()
        self.assertFalse(self.perfil.split_preference_confirmada)
        self.assertEqual(RegistroAdministrativo.objects.count(), antes)

    # I — sem a permissão, nada acontece
    def test_suporte_nao_executa_a_acao(self):
        self.client.force_login(self.suporte)

        resposta = self.client.post(self._rota(), {}, secure=True)

        self.assertIn(resposta.status_code, (403, 302))
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.split_preference_confirmada)

    # J — POST forjado com campos extras
    def test_post_forjado_nao_altera_nada_alem_da_operacao(self):
        """Mandar junto o que a ação não gerencia não pode funcionar: ela lê
        `user_id` da URL e ignora o corpo inteiro."""
        self.client.force_login(self.operador)

        self.client.post(
            self._rota(),
            {
                "split_preference": SplitPreference.UM,
                "kcal_adjustment": "30000",
                "birth_date": "1900-01-01",
                "height_cm": "999",
                # E as chaves que uma implementação dirigida pelo corpo leria
                # para decidir O QUE desmarcar: sem elas o teste passaria por
                # sorte, porque não haveria nada para a ação obedecer.
                "split_preference_confirmada": "on",
                "confirmada": "1",
                "campo": "split_preference",
            },
            secure=True,
        )

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.split_preference, SplitPreference.TRES)
        self.assertEqual(self.perfil.kcal_adjustment, 0)
        self.assertEqual(self.perfil.height_cm, 178)
        self.assertEqual(self.perfil.birth_date, date(1995, 4, 12))
        self.assertFalse(self.perfil.split_preference_confirmada)

    def test_a_acao_recusa_get(self):
        """GET que altera estado é acionável por uma imagem em página de
        terceiro."""
        self.client.force_login(self.operador)

        resposta = self.client.get(self._rota(), secure=True)

        self.assertEqual(resposta.status_code, 405)
        self.perfil.refresh_from_db()
        self.assertTrue(self.perfil.split_preference_confirmada)

    def test_a_mudanca_real_entra_na_trilha(self):
        self.client.force_login(self.operador)

        self.client.post(self._rota(), {}, secure=True)

        registro = RegistroAdministrativo.objects.get(
            acao=AcaoAdministrativa.PEDIU_NOVA_DIVISAO
        )
        self.assertEqual(registro.ator, self.operador)
        self.assertEqual(registro.alvo, self.alvo)
        self.assertNotIn("birth_date", json.dumps(registro.detalhe))

    def test_depois_a_pessoa_escolhe_pelo_fluxo_normal(self):
        """A ação faz o app perguntar; quem responde continua sendo a pessoa."""
        self.client.force_login(self.operador)
        self.client.post(self._rota(), {}, secure=True)

        # Quatro dias de treino: sem eles `preferencia_muda_a_divisao` devolve
        # False, o passo 4 não entra no caminho da pessoa, e o teste mediria a
        # ausência do passo em vez da escolha.
        for dia in range(4):
            TrainingDay.objects.create(
                user=self.alvo, weekday=dia, start_time=time(19, 0), duration_min=60
            )
        self.client.force_login(self.alvo)
        Profile.objects.filter(pk=self.perfil.pk).update(
            onboarding_step=ONBOARDING_DONE
        )
        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 4}),
            {"split_preference": SplitPreference.DOIS},
        )

        self.perfil.refresh_from_db()
        self.assertEqual(self.perfil.split_preference, SplitPreference.DOIS)
        self.assertTrue(self.perfil.split_preference_confirmada)


class DiasDeTreinoNaoDependemDoAdminTests(TestCase):
    """`change_trainingday` foi retirado dos dois papéis. Isto mede se alguma
    coisa dependia dele.

    A aparência do inline não responde a pergunta: `readonly_fields` some do
    formulário, mas um segundo caminho de escrita — outra tela do painel, um
    formset, uma ação — continuaria funcionando e a queda da permissão o
    quebraria em silêncio. Então a prova tem três partes: ninguém tem a
    capacidade, o HTTP do painel não escreve mesmo forjando o formset, e o
    caminho REAL continua de pé.

    O controle positivo é a parte que impede a conclusão fácil: um teste que só
    mostra "não escreveu" passaria igual se `TrainingDay` estivesse quebrado
    para todo mundo.
    """

    @classmethod
    def setUpTestData(cls):
        papeis.sincronizar_papeis()

    def setUp(self):
        self.operador = User.objects.create_user(
            email="op-dias@exemplo.com", password="senha-bem-forte-123"
        )
        self.operador.is_staff = True
        self.operador.save(update_fields=["is_staff"])
        self.operador.groups.add(Group.objects.get(name=papeis.ADMINISTRADORES))

        self.alvo = User.objects.create_user(
            email="alvo-dias@exemplo.com", password="senha-bem-forte-123"
        )
        Profile.objects.create(
            user=self.alvo,
            sex=Sex.MALE,
            birth_date=date(1995, 4, 12),
            height_cm=178,
            activity_level=ActivityLevel.LIGHT,
            goal=Goal.BULK,
            wake_time=time(7, 0),
            sleep_time=time(23, 0),
        )
        self.dia = TrainingDay.objects.create(
            user=self.alvo, weekday=0, start_time=time(19, 0), duration_min=60
        )

    def test_nenhum_papel_pode_alterar_dia_de_treino(self):
        """`has_perm` e não `permissoes_de`: a segunda devolve objetos
        `Permission`, e comparar uma string com eles é um `assertNotIn` que
        passa sempre — o teste não mede nada e a queda da permissão passaria
        despercebida."""
        for papel in (papeis.ADMINISTRADORES, papeis.SUPORTE):
            with self.subTest(papel=papel):
                pessoa = User.objects.create_user(
                    email=f"cap-{papel[:3].lower()}@exemplo.com",
                    password="senha-bem-forte-123",
                )
                pessoa.is_staff = True
                pessoa.save(update_fields=["is_staff"])
                pessoa.groups.add(Group.objects.get(name=papel))

                self.assertFalse(pessoa.has_perm("accounts.change_trainingday"))
                self.assertTrue(pessoa.has_perm("accounts.view_trainingday"))

    def test_o_painel_nao_oferece_campo_de_dia_de_treino(self):
        self.client.force_login(self.operador)

        html = self.client.get(
            f"/admin/accounts/user/{self.alvo.pk}/change/", secure=True
        ).content.decode()

        for campo in ("weekday", "start_time", "duration_min"):
            with self.subTest(campo=campo):
                self.assertNotIn(f'name="training_days-0-{campo}"', html)

    def test_formset_forjado_nao_altera_o_dia(self):
        """Sem input na tela, a tentativa vira POST direto: mandar o formset
        inteiro à mão é exatamente o que alguém faria."""
        self.client.force_login(self.operador)

        self.client.post(
            f"/admin/accounts/user/{self.alvo.pk}/change/",
            {
                "email": self.alvo.email,
                "first_name": "",
                "last_name": "",
                "is_active": "on",
                "date_joined_0": "2026-01-01",
                "date_joined_1": "10:00:00",
                "training_days-TOTAL_FORMS": "1",
                "training_days-INITIAL_FORMS": "1",
                "training_days-MIN_NUM_FORMS": "0",
                "training_days-MAX_NUM_FORMS": "1000",
                "training_days-0-id": str(self.dia.pk),
                "training_days-0-user": str(self.alvo.pk),
                "training_days-0-weekday": "5",
                "training_days-0-start_time": "05:00:00",
                "training_days-0-duration_min": "300",
                "training_days-0-DELETE": "on",
                "profile-TOTAL_FORMS": "0",
                "profile-INITIAL_FORMS": "0",
                "weight_entries-TOTAL_FORMS": "0",
                "weight_entries-INITIAL_FORMS": "0",
                "_continue": "Salvar",
            },
            secure=True,
        )

        self.dia.refresh_from_db()
        self.assertEqual(self.dia.weekday, 0)
        self.assertEqual(self.dia.start_time, time(19, 0))
        self.assertEqual(self.dia.duration_min, 60)
        self.assertEqual(TrainingDay.objects.filter(user=self.alvo).count(), 1)

    def test_a_propria_pessoa_continua_marcando_os_dias(self):
        """Controle positivo: sem ele, um TrainingDay quebrado para todo mundo
        passaria pelos testes acima como se fosse a proteção funcionando."""
        Profile.objects.filter(user=self.alvo).update(
            onboarding_step=ONBOARDING_DONE
        )
        self.client.force_login(self.alvo)

        self.client.post(
            reverse("accounts:onboarding_step", kwargs={"step": 3}),
            {
                "weekdays": ["1", "3"],
                "start_time": "18:30",
                "duration_min": "45",
                "wake_time": "07:00",
                "sleep_time": "23:00",
            },
        )

        dias = TrainingDay.objects.filter(user=self.alvo).order_by("weekday")
        self.assertEqual([d.weekday for d in dias], [1, 3])
        self.assertEqual(dias[0].duration_min, 45)
