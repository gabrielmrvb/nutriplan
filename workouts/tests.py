"""Testes da rotina de treino.

O que interessa cobrir aqui é a regra de treinamento, não o CRUD: a divisão
escolhida bate com a frequência, o ciclo repete quando a pessoa treina mais
dias do que a divisão tem letras, e a ficha acompanha quando a rotina muda.
"""
from datetime import date, time, timedelta
from decimal import Decimal

import urllib.error
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ActivityLevel,
    Goal,
    Profile,
    Sex,
    TrainingDay,
    User,
    WeightEntry,
)

from . import services
from .models import (
    Exercise,
    ExerciseLog,
    Measure,
    MuscleGroup,
    Split,
    TrainingPlan,
    WorkoutTemplate,
)


def create_user(email="atleta@exemplo.com", weekdays=(0, 2, 4), duration=60):
    """Usuário com onboarding completo e dias de treino."""
    user = User.objects.create_user(email=email, password="senha-bem-forte-123")
    Profile.objects.create(
        user=user,
        sex=Sex.MALE,
        birth_date=date(1995, 4, 12),
        height_cm=178,
        activity_level=ActivityLevel.LIGHT,
        goal=Goal.BULK,
        wake_time=time(7, 0),
        sleep_time=time(23, 0),
        onboarding_step=5,
    )
    WeightEntry.objects.create(user=user, weight_kg=Decimal("82.4"))
    for weekday in weekdays:
        TrainingDay.objects.create(
            user=user, weekday=weekday, start_time=time(19, 0), duration_min=duration
        )
    return user


class SplitChoiceTests(TestCase):
    """A divisão sai da frequência — é decisão de treinamento, não de gosto."""

    def test_one_day_a_week_trains_the_whole_body(self):
        self.assertEqual(services.split_for(1), Split.FULL)

    def test_two_days_split_upper_and_lower(self):
        self.assertEqual(services.split_for(2), Split.AB)

    def test_three_days_use_push_pull_legs(self):
        self.assertEqual(services.split_for(3), Split.ABC)

    def test_four_days_get_one_focus_each(self):
        self.assertEqual(services.split_for(4), Split.ABCD)

    def test_five_or_more_days_repeat_the_three_day_cycle(self):
        """Cinco dias de ABC dá duas sessões por grupo; ABCDE daria uma só.

        Inventar um quinto e um sexto dia de "braço" preenche a semana sem
        adicionar estímulo — repetir o ciclo é o que a literatura sustenta.
        """
        for dias in (5, 6, 7):
            with self.subTest(dias=dias):
                self.assertEqual(services.split_for(dias), Split.ABC)


class SeededWorkoutTests(TestCase):
    """O catálogo de treino precisa bancar todas as divisões."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_every_split_is_in_the_catalog(self):
        for split in Split.values:
            with self.subTest(split=split):
                self.assertTrue(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).exists()
                )

    def test_each_split_has_the_days_its_name_promises(self):
        esperado = {Split.FULL: 1, Split.AB: 2, Split.ABC: 3, Split.ABCD: 4}
        for split, dias in esperado.items():
            with self.subTest(split=split):
                self.assertEqual(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).count(),
                    dias,
                )

    def test_every_workout_fits_in_a_gym_session(self):
        """Entre 4 e 8 exercícios: menos não cobre o dia, mais vira duas horas."""
        for template in WorkoutTemplate.objects.filter(is_active=True):
            with self.subTest(treino=str(template)):
                self.assertGreaterEqual(template.items.count(), 4)
                self.assertLessEqual(template.items.count(), 8)

    def test_compound_lifts_come_first_and_rest_longer(self):
        """Quem puxa carga vem descansado, e descansa mais entre as séries."""
        for template in WorkoutTemplate.objects.filter(is_active=True):
            items = list(template.items.all())
            with self.subTest(treino=str(template)):
                self.assertTrue(
                    items[0].exercise.is_compound,
                    f"{template} começa com isolado: {items[0].exercise}",
                )
            for item in items:
                if item.exercise.is_compound:
                    self.assertGreaterEqual(item.rest_seconds, 90, str(item.exercise))

    def test_time_based_exercises_are_measured_in_seconds(self):
        """Prancha não tem repetição — "3 x 12 de prancha" não quer dizer nada."""
        prancha = Exercise.objects.get(name="Prancha abdominal")
        for item in prancha.template_items.all():
            self.assertEqual(item.measure, Measure.SECONDS)

    def test_every_split_covers_the_whole_body(self):
        """Divisão que esquece posterior de coxa é lesão marcada para depois."""
        essenciais = {
            MuscleGroup.CHEST,
            MuscleGroup.BACK,
            MuscleGroup.QUADS,
            MuscleGroup.HAMSTRINGS,
            MuscleGroup.SHOULDERS,
        }
        for split in Split.values:
            grupos = set(
                WorkoutTemplate.objects.filter(split=split, is_active=True)
                .values_list("items__exercise__muscle_group", flat=True)
                .distinct()
            )
            with self.subTest(split=split):
                self.assertTrue(essenciais <= grupos, f"faltou: {essenciais - grupos}")


class RoutineGenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_three_days_become_an_abc_routine(self):
        user = create_user()
        plan = services.create_routine(user)

        self.assertEqual(plan.split, Split.ABC)
        self.assertEqual(plan.days_per_week, 3)
        self.assertEqual(
            list(plan.sessions.values_list("label", flat=True)), ["A", "B", "C"]
        )

    def test_the_cycle_repeats_for_five_days(self):
        user = create_user(weekdays=(0, 1, 2, 3, 4))
        plan = services.create_routine(user)

        self.assertEqual(
            list(plan.sessions.values_list("label", flat=True)),
            ["A", "B", "C", "A", "B"],
        )

    def test_the_session_lands_on_the_day_the_person_trains(self):
        user = create_user(weekdays=(1, 3, 5))
        plan = services.create_routine(user)

        self.assertEqual(
            sorted(plan.sessions.values_list("weekday", flat=True)), [1, 3, 5]
        )

    def test_the_session_copies_the_time_and_duration(self):
        user = create_user(weekdays=(0,), duration=75)
        plan = services.create_routine(user)

        session = plan.sessions.get()
        self.assertEqual(session.start_time, time(19, 0))
        self.assertEqual(session.duration_min, 75)

    def test_every_session_comes_with_its_exercises(self):
        user = create_user()
        plan = services.create_routine(user)

        for session in plan.sessions.all():
            with self.subTest(treino=session.name):
                self.assertGreaterEqual(session.exercises.count(), 4)
                self.assertGreater(session.total_sets, 0)

    def test_the_prescription_is_frozen_at_generation_time(self):
        """Mudar o catálogo amanhã não reescreve a ficha de quem treina hoje."""
        user = create_user()
        plan = services.create_routine(user)
        exercicio = plan.sessions.first().exercises.first()
        series_originais = exercicio.sets

        WorkoutTemplate.objects.filter(split=Split.ABC).first().items.update(sets=99)

        exercicio.refresh_from_db()
        self.assertEqual(exercicio.sets, series_originais)

    def test_without_training_days_there_is_no_routine(self):
        user = create_user(weekdays=())
        with self.assertRaises(services.NoTrainingDays):
            services.create_routine(user)

    def test_a_new_routine_retires_the_previous_one(self):
        user = create_user()
        services.create_routine(user)
        services.create_routine(user)

        self.assertEqual(TrainingPlan.objects.filter(user=user).count(), 2)
        self.assertEqual(
            TrainingPlan.objects.filter(user=user, is_active=True).count(), 1
        )


class RoutineSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()

    def test_nothing_changes_while_the_training_days_are_the_same(self):
        services.create_routine(self.user)
        _, mudou = services.sync_active_routine(self.user)
        self.assertFalse(mudou)

    def test_adding_a_training_day_rebuilds_the_routine(self):
        primeira = services.create_routine(self.user)
        TrainingDay.objects.create(
            user=self.user, weekday=5, start_time=time(10, 0), duration_min=60
        )

        segunda, mudou = services.sync_active_routine(self.user)

        self.assertTrue(mudou)
        self.assertNotEqual(segunda.pk, primeira.pk)
        self.assertEqual(segunda.split, Split.ABCD)  # quatro dias agora
        self.assertEqual(segunda.days_per_week, 4)

    def test_changing_the_hour_rebuilds_the_routine(self):
        """Sem isso a ficha continuaria dizendo o horário antigo."""
        services.create_routine(self.user)
        self.user.training_days.update(start_time=time(6, 30))

        plan, mudou = services.sync_active_routine(self.user)

        self.assertTrue(mudou)
        self.assertEqual(plan.sessions.first().start_time, time(6, 30))

    def test_a_retired_exercise_rebuilds_the_routine(self):
        plan = services.create_routine(self.user)
        usado = plan.sessions.first().exercises.first().exercise
        Exercise.objects.filter(pk=usado.pk).update(is_active=False)

        nova, mudou = services.sync_active_routine(self.user)

        self.assertTrue(mudou)
        self.assertNotEqual(nova.pk, plan.pk)


class WorkoutViewTests(TestCase):
    url = reverse("workouts:routine")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_incomplete_onboarding_is_sent_back_to_the_wizard(self):
        user = create_user()
        Profile.objects.filter(user=user).update(onboarding_step=3)
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("accounts:onboarding"), target_status_code=302)

    def test_the_page_shows_the_split_and_the_exercises(self):
        user = create_user()
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empurrar")
        self.assertContains(response, "Agachamento livre")
        self.assertContains(response, "descanso")

    def test_the_first_visit_creates_the_routine(self):
        user = create_user()
        self.client.force_login(user)

        self.client.get(self.url)

        self.assertEqual(TrainingPlan.objects.filter(user=user).count(), 1)

    def test_the_second_visit_does_not_create_another(self):
        user = create_user()
        self.client.force_login(user)

        self.client.get(self.url)
        self.client.get(self.url)

        self.assertEqual(TrainingPlan.objects.filter(user=user).count(), 1)

    def test_someone_without_training_days_is_invited_to_add_them(self):
        user = create_user(weekdays=())
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cadastrar meus dias de treino")
        self.assertFalse(TrainingPlan.objects.filter(user=user).exists())

    def test_the_weekly_volume_is_shown_per_muscle(self):
        user = create_user()
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertContains(response, "Séries por músculo")
        self.assertContains(response, "Peito")

    def test_rest_days_appear_in_the_week(self):
        user = create_user(weekdays=(0, 2, 4))
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertContains(response, "descanso")


class ExerciseVideoTests(TestCase):
    """O vídeo de execução: extração do id, embed e plano B."""

    def test_a_normal_youtube_link_becomes_an_embed(self):
        exercicio = Exercise(
            name="Supino", video_url="https://www.youtube.com/watch?v=abc123XYZ_-"
        )
        self.assertEqual(exercicio.video_id, "abc123XYZ_-")
        self.assertTrue(
            exercicio.video_embed_url.startswith(
                "https://www.youtube-nocookie.com/embed/abc123XYZ_-?"
            )
        )

    def test_the_embed_uses_the_privacy_domain(self):
        """Num app que já sabe peso e objetivo da pessoa, não se entrega o resto."""
        exercicio = Exercise(name="X", video_url="https://www.youtube.com/watch?v=aaa")
        self.assertIn("youtube-nocookie.com", exercicio.video_embed_url)
        self.assertNotIn("//www.youtube.com/embed", exercicio.video_embed_url)

    def test_short_and_shorts_links_also_work(self):
        """São os formatos que aparecem quando alguém copia do celular."""
        curto = Exercise(name="A", video_url="https://youtu.be/aaa111BBB")
        shorts = Exercise(name="B", video_url="https://www.youtube.com/shorts/ccc222DDD")

        self.assertEqual(curto.video_id, "aaa111BBB")
        self.assertEqual(shorts.video_id, "ccc222DDD")

    def test_a_link_from_anywhere_else_does_not_become_an_embed(self):
        """Melhor cair no plano B do que montar um iframe que não abre."""
        exercicio = Exercise(name="X", video_url="https://vimeo.com/12345")
        self.assertEqual(exercicio.video_id, "")
        self.assertEqual(exercicio.video_embed_url, "")

    def test_without_a_video_there_is_still_a_way_to_look_it_up(self):
        exercicio = Exercise(name="Rosca martelo")
        self.assertEqual(exercicio.video_embed_url, "")
        self.assertIn("Rosca+martelo", exercicio.video_search_url)
        self.assertIn("youtube.com/results", exercicio.video_search_url)


class SeededVideoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_every_exercise_in_the_catalog_has_a_video(self):
        sem_video = list(
            Exercise.objects.filter(is_active=True, video_url="").values_list(
                "name", flat=True
            )
        )
        self.assertEqual(sem_video, [])

    def test_every_seeded_video_is_embeddable(self):
        """URL cadastrada que não vira embed é erro de digitação no seed."""
        for exercicio in Exercise.objects.filter(is_active=True):
            with self.subTest(exercicio=exercicio.name):
                self.assertTrue(exercicio.video_embed_url, exercicio.video_url)

    def test_no_two_exercises_share_the_same_video(self):
        """Vídeo repetido é sinal de copiar-e-colar errado no seed."""
        ids = [
            exercicio.video_id
            for exercicio in Exercise.objects.filter(is_active=True)
        ]
        self.assertEqual(len(ids), len(set(ids)))


class WorkoutVideoViewTests(TestCase):
    url = reverse("workouts:routine")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)

    def test_each_exercise_offers_the_demonstration(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Ver execução")
        self.assertContains(response, "youtube-nocookie.com/embed/")

    def test_there_is_one_media_slot_per_exercise_in_the_routine(self):
        response = self.client.get(self.url)
        corpo = response.content.decode()

        exercicios = sum(
            session.exercises.count()
            for session in self.user.training_plans.get(is_active=True).sessions.all()
        )
        self.assertEqual(corpo.count('data-clipe="'), exercicios)
        self.assertEqual(corpo.count("exercise__media"), exercicios)

    def test_no_player_is_loaded_before_being_asked_for(self):
        """Dezenove iframes ao abrir a tela seriam dezenove conexões ao YouTube.

        A mídia começa como miniatura com botão de play; o player nasce no
        toque, dentro do próprio cartão.
        """
        corpo = self.client.get(self.url).content.decode()

        self.assertNotIn("<iframe", corpo)
        self.assertIn("exercise__thumb", corpo)

    def test_the_fallback_search_link_travels_with_each_exercise(self):
        """Vídeo de terceiro morre: sem saída, sobra um player quebrado."""
        corpo = self.client.get(self.url).content.decode()
        self.assertIn("youtube.com/results?search_query=", corpo)
        self.assertIn("exercise__fallback", corpo)


class VideoCheckCommandTests(TestCase):
    """O comando que avisa quando um vídeo de terceiro apodrece."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _run(self):
        saida = StringIO()
        call_command("check_exercise_videos", stdout=saida, stderr=saida)
        return saida.getvalue()

    @patch("workouts.management.commands.check_exercise_videos.urllib.request.urlopen")
    def test_all_videos_online_reports_success(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"title": "x"}'

        saida = self._run()

        self.assertIn("no ar e embutíveis", saida)

    @patch("workouts.management.commands.check_exercise_videos.urllib.request.urlopen")
    def test_a_blocked_video_is_reported_and_fails(self, urlopen):
        """401 é o dono desligando o embed — o caso real que aconteceu no seed."""
        urlopen.side_effect = urllib.error.HTTPError(
            "http://x", 401, "Unauthorized", {}, None
        )

        with self.assertRaises(SystemExit):
            self._run()

    @patch("workouts.management.commands.check_exercise_videos.urllib.request.urlopen")
    def test_a_dead_video_is_reported_and_fails(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)

        with self.assertRaises(SystemExit):
            self._run()


class LoadRecordingTests(TestCase):
    """Registro de carga: o que transforma a ficha em progressão."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.exercise = Exercise.objects.get(name="Supino reto com barra")

    def test_recording_saves_the_load(self):
        services.record_load(self.user, self.exercise, "60")

        log = ExerciseLog.objects.get()
        self.assertEqual(log.weight_kg, Decimal("60"))
        self.assertEqual(log.date, timezone.localdate())

    def test_recording_twice_on_the_same_set_corrects_instead_of_duplicating(self):
        """Errou o número, digita de novo — não vira duas linhas no histórico."""
        services.record_load(self.user, self.exercise, "60", set_number=1)
        services.record_load(self.user, self.exercise, "62.5", set_number=1)

        self.assertEqual(ExerciseLog.objects.count(), 1)
        self.assertEqual(ExerciseLog.objects.get().weight_kg, Decimal("62.50"))

    def test_history_answers_whether_the_load_went_up(self):
        hoje = timezone.localdate()
        services.record_load(self.user, self.exercise, "57.5", day=hoje - timedelta(days=7))
        services.record_load(self.user, self.exercise, "60", day=hoje)

        historico = services.load_history(self.user, [self.exercise])[self.exercise.pk]

        self.assertEqual(historico["melhor_hoje"], Decimal("60"))
        self.assertEqual(historico["melhor_anterior"], Decimal("57.50"))
        self.assertEqual(historico["delta"], Decimal("2.50"))
        self.assertEqual(historico["data_anterior"], hoje - timedelta(days=7))

    def test_the_comparison_uses_the_heaviest_set_of_each_day(self):
        """A ordem em que se anota varia; o que responde "evoluí?" é o topo do dia."""
        hoje = timezone.localdate()
        antes = hoje - timedelta(days=7)
        services.record_load(self.user, self.exercise, "50", set_number=1, day=antes)
        services.record_load(self.user, self.exercise, "60", set_number=2, day=antes)
        services.record_load(self.user, self.exercise, "65", set_number=1, day=hoje)
        services.record_load(self.user, self.exercise, "55", set_number=2, day=hoje)

        historico = services.load_history(self.user, [self.exercise])[self.exercise.pk]

        self.assertEqual(historico["melhor_hoje"], Decimal("65"))
        self.assertEqual(historico["melhor_anterior"], Decimal("60"))
        self.assertEqual(historico["delta"], Decimal("5"))

    def test_each_set_keeps_its_own_load(self):
        """Série pesada e série leve no mesmo exercício são coisas diferentes."""
        services.record_load(self.user, self.exercise, "60", set_number=1)
        services.record_load(self.user, self.exercise, "50", set_number=2)

        historico = services.load_history(self.user, [self.exercise])[self.exercise.pk]

        self.assertEqual(historico["hoje"][1].weight_kg, Decimal("60"))
        self.assertEqual(historico["hoje"][2].weight_kg, Decimal("50"))
        self.assertEqual(ExerciseLog.objects.count(), 2)

    def test_a_load_that_dropped_shows_a_negative_delta(self):
        hoje = timezone.localdate()
        services.record_load(self.user, self.exercise, "60", day=hoje - timedelta(days=7))
        services.record_load(self.user, self.exercise, "55", day=hoje)

        historico = services.load_history(self.user, [self.exercise])[self.exercise.pk]
        self.assertEqual(historico["delta"], Decimal("-5.00"))

    def test_the_first_time_there_is_nothing_to_compare(self):
        services.record_load(self.user, self.exercise, "60")

        historico = services.load_history(self.user, [self.exercise])[self.exercise.pk]
        self.assertEqual(historico["anterior"], {})
        self.assertIsNone(historico["melhor_anterior"])
        self.assertIsNone(historico["delta"])

    def test_history_does_not_leak_between_users(self):
        outro = create_user(email="outro@exemplo.com")
        services.record_load(outro, self.exercise, "100")

        self.assertEqual(services.load_history(self.user, [self.exercise]), {})

    def test_the_history_survives_the_routine_being_rebuilt(self):
        """A ficha é refeita quando muda a frequência; a carga não pode morrer junto."""
        services.record_load(self.user, self.exercise, "60")
        services.create_routine(self.user)
        TrainingDay.objects.create(
            user=self.user, weekday=5, start_time=time(10, 0), duration_min=60
        )
        services.sync_active_routine(self.user)

        self.assertEqual(ExerciseLog.objects.filter(user=self.user).count(), 1)


class RecordLoadViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)
        self.exercise = Exercise.objects.get(name="Agachamento livre")
        self.url = reverse("workouts:record_load", args=[self.exercise.pk])

    def test_posting_a_load_saves_and_returns_to_the_exercise(self):
        """A âncora devolve a pessoa ao exercício, não ao topo da página."""
        response = self.client.post(self.url, {"weight_kg": "80", "set_number": "2"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("workouts:routine") + f"#exercicio-{self.exercise.pk}",
        )
        log = ExerciseLog.objects.get()
        self.assertEqual(log.weight_kg, Decimal("80"))
        self.assertEqual(log.set_number, 2)

    def test_an_absurd_set_number_is_clamped(self):
        self.client.post(self.url, {"weight_kg": "80", "set_number": "999"})
        self.assertLessEqual(ExerciseLog.objects.get().set_number, 20)

    def test_a_comma_is_accepted_because_that_is_how_people_type_it(self):
        self.client.post(self.url, {"weight_kg": "82,5"})
        self.assertEqual(ExerciseLog.objects.get().weight_kg, Decimal("82.50"))

    def test_garbage_does_not_create_a_record(self):
        response = self.client.post(self.url, {"weight_kg": "muito pesado"})

        self.assertRedirects(response, reverse("workouts:routine"))
        self.assertFalse(ExerciseLog.objects.exists())

    def test_an_absurd_load_is_refused(self):
        self.client.post(self.url, {"weight_kg": "5000"})
        self.assertFalse(ExerciseLog.objects.exists())

    def test_recording_is_not_reachable_by_get(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_anonymous_cannot_record(self):
        self.client.logout()
        response = self.client.post(self.url, {"weight_kg": "80"})

        self.assertIn(reverse("accounts:login"), response["Location"])
        self.assertFalse(ExerciseLog.objects.exists())

    def test_the_routine_shows_the_load_and_the_comparison(self):
        hoje = timezone.localdate()
        services.record_load(self.user, self.exercise, "75", day=hoje - timedelta(days=7))
        services.record_load(self.user, self.exercise, "80", day=hoje)

        response = self.client.get(reverse("workouts:routine"))

        self.assertContains(response, "+5")
        self.assertContains(response, 'name="weight_kg"')


class RestTimerTests(TestCase):
    """O cronômetro é do navegador, mas o tempo vem da ficha."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_each_exercise_carries_its_own_rest_time(self):
        user = create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("workouts:routine"))
        corpo = response.content.decode()

        plan = user.training_plans.get(is_active=True)
        exercicios = [
            item for session in plan.sessions.all() for item in session.exercises.all()
        ]
        # Um cronômetro por SÉRIE: é entre séries que se descansa.
        series = sum(item.sets for item in exercicios)
        self.assertEqual(corpo.count('data-descanso="'), series)
        # O descanso do multiarticular é maior — e é o que o botão precisa levar.
        self.assertIn('data-descanso="120"', corpo)

    def test_the_timer_widget_exists_once_for_the_whole_page(self):
        """Um cronômetro por exercício seriam dezoito contagens concorrendo."""
        user = create_user()
        self.client.force_login(user)

        corpo = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertEqual(corpo.count('class="rest-timer"'), 1)
        self.assertEqual(corpo.count("data-timer-valor"), 2)  # o elemento e o seletor

    def test_the_timer_does_not_appear_before_being_started(self):
        """Barra fixa visível sem ninguém ter pedido é ruído na tela."""
        user = create_user()
        self.client.force_login(user)

        corpo = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIn('data-timer hidden', corpo)


class ShortClipTests(TestCase):
    """A demonstração precisa ser curta, muda e em loop — não uma aula."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_youtube_embed_plays_by_itself_muted_and_looping(self):
        exercicio = Exercise.objects.get(name="Supino reto com barra")
        embed = exercicio.video_embed_url

        self.assertIn("autoplay=1", embed)
        # Sem mute o navegador simplesmente bloqueia o autoplay.
        self.assertIn("mute=1", embed)
        self.assertIn("loop=1", embed)
        # loop de vídeo único só funciona com playlist apontando para ele mesmo.
        self.assertIn(f"playlist={exercicio.video_id}", embed)

    def test_the_media_type_is_detected_from_the_url(self):
        casos = {
            "https://exemplo.com/agachamento.gif": "gif",
            "https://exemplo.com/supino.mp4": "video",
            "https://exemplo.com/remada.webm": "video",
            "https://www.youtube.com/shorts/abc123": "youtube",
            "https://www.youtube.com/watch?v=abc123": "youtube",
            "https://exemplo.com/pagina.html": "",
            "": "",
        }
        for url, esperado in casos.items():
            with self.subTest(url=url):
                self.assertEqual(Exercise(name="X", video_url=url).clip_kind, esperado)

    def test_a_short_is_marked_as_vertical(self):
        """Short é 9:16 — renderizar em 16:9 deixa duas tarjas pretas."""
        curto = Exercise(name="A", video_url="https://www.youtube.com/shorts/abc")
        longo = Exercise(name="B", video_url="https://www.youtube.com/watch?v=abc")

        self.assertTrue(curto.is_vertical)
        self.assertFalse(longo.is_vertical)

    def test_most_of_the_catalog_uses_short_clips(self):
        """A troca de 24/08/2026: vídeo longo abre com introdução falada."""
        ativos = Exercise.objects.filter(is_active=True)
        curtos = [e for e in ativos if e.is_vertical]

        self.assertGreaterEqual(len(curtos) / ativos.count(), 0.5)

    def test_no_exercise_is_left_without_a_demonstration(self):
        sem_clipe = [
            e.name for e in Exercise.objects.filter(is_active=True) if not e.clip_kind
        ]
        self.assertEqual(sem_clipe, [])

    def test_the_routine_marks_the_type_of_each_clip(self):
        user = create_user()
        self.client.force_login(user)

        corpo = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('data-tipo="youtube"', corpo)
        self.assertIn("autoplay=1", corpo)

    def test_the_media_frame_keeps_a_16_by_9_box(self):
        """Moldura fixa evita o salto de layout quando o player entra."""
        user = create_user()
        self.client.force_login(user)

        corpo = self.client.get(reverse("workouts:routine")).content.decode()
        self.assertIn("exercise__media", corpo)


class LoadInputFormatTests(TestCase):
    """Regressão: o campo de carga precisa aceitar vírgula de verdade.

    O campo era `type="number"`, e nele o navegador simplesmente descarta
    "62,5" e envia vazio — o registro nunca chegava ao banco e a tela não
    explicava nada. Brasileiro digita vírgula; quem tem que se adaptar é o
    formulário.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_the_field_is_not_a_number_input(self):
        user = create_user()
        self.client.force_login(user)

        corpo = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('name="weight_kg"', corpo)
        self.assertNotIn('type="number" name="weight_kg"', corpo)
        self.assertIn('inputmode="decimal"', corpo)

    def test_no_template_comment_leaks_into_the_page(self):
        """`{# ... #}` do Django não é multilinha — quando é, vaza como texto."""
        user = create_user()
        self.client.force_login(user)

        corpo = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertNotIn("{#", corpo)
        self.assertNotIn("#}", corpo)
