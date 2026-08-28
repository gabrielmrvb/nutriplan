"""Testes do cadastro e do wizard de onboarding.

O foco é o fluxo: o que acontece quando a pessoa avança, volta, pula ou
abandona no meio. É onde um wizard quebra na prática.
"""
from datetime import date, time
from decimal import Decimal

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from catalog.models import DietaryTag, TagKind

from .models import ONBOARDING_DONE, Profile, TrainingDay, User, WeightEntry


def step_url(step):
    return reverse("accounts:onboarding_step", kwargs={"step": step})


STEP1 = {"sex": "M", "birth_date": "1995-04-12", "height_cm": 178, "weight_kg": "82.4"}
STEP2 = {"goal": "cut", "activity_level": "light"}
STEP3 = {"weekdays": ["0", "2", "4"], "start_time": "19:00", "duration_min": 60}
STEP4 = {"split_preference": "three"}
STEP5 = {"meal_style": "quick", "wake_time": "07:00", "sleep_time": "23:30"}


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

    def _ate_a_janela(self):
        """Os quatro passos anteriores ao da janela do dia."""
        self.client.post(step_url(1), STEP1)
        self.client.post(step_url(2), STEP2)
        self.client.post(step_url(3), STEP3)
        self.client.post(step_url(4), STEP4)

    def test_sleeping_after_midnight_is_valid(self):
        self._ate_a_janela()
        response = self.client.post(
            step_url(5), {**STEP5, "wake_time": "07:00", "sleep_time": "01:30"}
        )
        self.assertRedirects(response, reverse("plans:today"))

    def test_absurdly_short_awake_window_is_blocked(self):
        self._ate_a_janela()
        response = self.client.post(
            step_url(5), {**STEP5, "wake_time": "07:00", "sleep_time": "10:00"}
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
        self.client.post(step_url(3), STEP3)
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
        resposta = self.client.post(
            step_url(5), {**STEP5, "wake_time": "07:00", "sleep_time": "10:00"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("muito curta", str(resposta.context["form"].errors))

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
        bloco = html.split("Restrições e rotina", 1)[1].split("</section>", 1)[0]
        self.assertIn(step_url(5), bloco)
        self.assertNotIn(step_url(4), bloco)

    def test_the_two_new_preferences_are_visible_and_editable(self):
        """Elas entraram no onboarding e nunca apareceram aqui — quem quisesse
        trocar teria que adivinhar em qual passo do wizard elas moram."""
        html = self.client.get(self.url).content.decode()
        divisao = html.split("Divisão de treino", 1)[1].split("</section>", 1)[0]
        self.assertIn("3 grupos por dia", divisao)
        self.assertIn(step_url(4), divisao)

        # O cardápio mora no cartão que leva ao passo 5, que é onde ele é
        # editado. Juntos num cartão só, o "Editar" mandava quem queria trocar
        # o cardápio para a tela de divisão de treino.
        comida = html.split("Restrições e rotina", 1)[1].split("</section>", 1)[0]
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

    def test_all_five_destinations_are_reachable_from_it(self):
        """São cinco, e não quatro. Suplementos é uma tela real e a barra é a
        ÚNICA porta para ela — tirá-la daqui deixaria a tela órfã, alcançável
        só por quem digitasse o endereço."""
        barra = self.html.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
        for rota in (
            reverse("plans:today"),
            reverse("workouts:routine"),
            reverse("supplements:list"),
            reverse("plans:history"),
            reverse("accounts:profile"),
        ):
            with self.subTest(rota=rota):
                self.assertIn(f'href="{rota}"', barra)

    def test_every_tab_has_an_icon_above_its_label(self):
        barra = self.html.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(barra.count("<svg"), 5)

    def test_the_columns_are_equal_so_the_row_never_drifts(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        bloco = css.split(chr(10) + ".tabbar {", 1)[1].split("}", 1)[0]
        self.assertIn("repeat(5, 1fr)", bloco)

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
