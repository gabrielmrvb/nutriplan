"""Testes da rotina de treino.

O que interessa cobrir aqui é a regra de treinamento, não o CRUD: a divisão
escolhida bate com a frequência, o ciclo repete quando a pessoa treina mais
dias do que a divisão tem letras, e a ficha acompanha quando a rotina muda.
"""
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

import urllib.error
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import assistant
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
    Equipment,
    Exercise,
    ExerciseLog,
    SessionExercise,
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

    def test_four_days_repeat_the_cycle_instead_of_adding_a_letter(self):
        """Quatro dias viram A, B, C, A — e não um quarto foco inventado."""
        self.assertEqual(services.split_for(4), Split.ABC)

    def test_three_or_more_days_all_use_the_classic_abc(self):
        """De três dias em diante, sempre ABC.

        ABCD e ABCDE existiram aqui e foram retirados. O motivo é o clássico
        por sinergia: peito e costas são antagonistas e não dividem o dia. O
        ciclo se repete para preencher a semana, o que também devolve a
        segunda sessão por grupo que uma divisão de cinco letras não dá.
        """
        for dias in (3, 4, 5, 6, 7):
            with self.subTest(dias=dias):
                self.assertEqual(services.split_for(dias), Split.ABC)

        # Menos que três continua como estava.
        self.assertEqual(services.split_for(1), Split.FULL)
        self.assertEqual(services.split_for(2), Split.AB)


class SeededWorkoutTests(TestCase):
    """O catálogo de treino precisa bancar todas as divisões."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    #: As divisões que o app oferece hoje. ABCD e ABCDE continuam no enum,
    #: porque fichas antigas apontam para elas, mas saíram do catálogo — a
    #: divisão passou a ser estritamente a clássica por sinergia.
    OFERECIDAS = (Split.FULL, Split.AB, Split.ABC)

    def test_every_offered_split_is_in_the_catalog(self):
        for split in self.OFERECIDAS:
            with self.subTest(split=split):
                self.assertTrue(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).exists()
                )

    def test_the_retired_splits_are_not_offered(self):
        """ABCD e ABCDE continuam no enum porque fichas antigas apontam para
        elas, mas nenhum treino novo é montado por elas.

        Num banco recém-semeado elas simplesmente não existem; num banco que
        já as teve, o seed as desativa em vez de apagar. Os dois casos passam
        pela mesma afirmação: não há template ATIVO.
        """
        for split in (Split.ABCD, Split.ABCDE):
            with self.subTest(split=split):
                self.assertFalse(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).exists()
                )

    def test_each_split_has_the_days_its_name_promises(self):
        esperado = {Split.FULL: 1, Split.AB: 2, Split.ABC: 3}
        for split, dias in esperado.items():
            with self.subTest(split=split):
                self.assertEqual(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).count(),
                    dias,
                )

    def test_every_workout_fits_in_a_gym_session(self):
        """A sessão cabe em noventa minutos.

        O teto era de oito exercícios, herdado de quando a meta era 45 a 55
        minutos. Com noventa minutos de orçamento o limite deixa de ser a
        contagem e passa a ser o relógio: nove exercícios com três minutos de
        descanso nos compostos pesados cabem, e é o que permite três
        exercícios de tríceps e de bíceps sem espremer o descanso.
        """
        for template in WorkoutTemplate.objects.filter(is_active=True):
            with self.subTest(treino=str(template)):
                self.assertGreaterEqual(template.items.count(), 4)
                self.assertLessEqual(template.estimated_minutes, 90)
                # Menos de meia hora não é treino, é aquecimento.
                self.assertGreaterEqual(template.estimated_minutes, 30)

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
        for split in self.OFERECIDAS:
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

    def test_the_cycle_repeats_to_fill_the_week(self):
        """Cinco dias viram A, B, C, A, B.

        Repetir o ciclo é o que dá duas sessões a empurrar e a puxar na mesma
        semana. Uma divisão de cinco letras daria uma sessão por grupo, e
        frequência importa para hipertrofia.
        """
        user = create_user(weekdays=(0, 1, 2, 3, 4))
        plan = services.create_routine(user)

        self.assertEqual(
            list(plan.sessions.values_list("label", flat=True)),
            ["A", "B", "C", "A", "B"],
        )

    def test_a_sixth_day_completes_a_second_cycle(self):
        user = create_user(email="seis@exemplo.com", weekdays=(0, 1, 2, 3, 4, 5))
        plan = services.create_routine(user)

        self.assertEqual(
            list(plan.sessions.values_list("label", flat=True)),
            ["A", "B", "C", "A", "B", "C"],
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
        self.assertEqual(segunda.split, Split.ABC)  # quatro dias, ciclo repetido
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
        self.assertEqual(corpo.count("exercise__ver"), exercicios)

    def test_no_player_is_loaded_before_being_asked_for(self):
        """Dezenove iframes ao abrir a tela seriam dezenove conexões ao YouTube.

        O cartão chegou a mostrar uma miniatura 16:9 por exercício, e ela
        custava 149 px de altura cada — só um cartão e meio cabia na tela do
        celular. Hoje o cartão traz um botão de uma linha, e o player nasce no
        toque, dentro do drawer.
        """
        corpo = self.client.get(self.url).content.decode()

        # Só a marcação: o script traz `createElement("iframe")` e os
        # comentários citam `<iframe>` — nenhum dos dois é um player montado.
        marcacao = corpo.split("<script>", 1)[0]
        self.assertNotIn("<iframe", marcacao)
        self.assertIn("exercise__ver", marcacao)

        # O endereço do player vem no atributo, mas nenhum player é montado
        # antes do toque — é o que evita dezenove conexões ao abrir a tela.
        self.assertIn("data-animacao=", marcacao)
        self.assertNotIn("<video", marcacao)

    def test_the_fallback_search_link_travels_with_each_exercise(self):
        """Vídeo de terceiro morre: sem saída, sobra um player quebrado.

        O link saiu do cartão e foi para o drawer — só procura outra
        demonstração quem abriu a primeira e não gostou. No cartão ele era uma
        linha a mais para quem nunca vai clicar.
        """
        corpo = self.client.get(self.url).content.decode()
        self.assertIn("youtube.com/results?search_query=", corpo)
        self.assertIn("data-busca=", corpo)
        self.assertIn("data-drawer-busca", corpo)


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
        #
        # A contagem é do gatilho `data-descanso`, e por isso ele não pode ser
        # usado como campo de dado em outro lugar: a fachada do vídeo chegou a
        # levá-lo, e tocar no vídeo disparava o descanso junto. O dado do
        # drawer mora em `data-descanso-segundos`.
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

    def test_the_media_frame_keeps_a_fixed_box(self):
        """Moldura fixa evita o salto de layout quando o player entra.

        A moldura mudou de lugar: era o segundo bloco do cartão, e passou a ser
        o topo do drawer. O motivo de existir é o mesmo — sem caixa reservada,
        a chegada do player empurra o conteúdo para baixo.
        """
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        moldura = css.split("\n.drawer__media {", 1)[1].split("}", 1)[0]
        self.assertIn("aspect-ratio: 16 / 9", moldura)

        # Short é 9:16: esticado em 16:9 ficaria com duas tarjas pretas
        # ocupando metade da tela.
        vertical = css.split("\n.drawer__media--vertical {", 1)[1].split("}", 1)[0]
        self.assertIn("aspect-ratio: 9 / 16", vertical)


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


class ExerciseDrawerTests(TestCase):
    """O drawer de execução: mídia em loop, prescrição e carga anterior."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(email="drawer@exemplo.com")
        self.client.force_login(self.user)

    def _pagina(self):
        return self.client.get(reverse("workouts:routine")).content.decode()

    def test_the_page_has_exactly_one_drawer(self):
        """Um por exercício seriam trinta players no documento, e o custo
        apareceria no 3G da academia antes de qualquer benefício."""
        html = self._pagina()
        self.assertEqual(html.count("data-drawer "), 1)
        self.assertIn("<dialog", html)

    def test_each_exercise_carries_what_the_drawer_shows(self):
        html = self._pagina()
        for atributo in (
            "data-clipe=",
            "data-series=",
            "data-reps=",
            "data-descanso-texto=",
            "data-carga=",
            "data-cue=",
            "data-musculo=",
        ):
            with self.subTest(atributo=atributo):
                self.assertIn(atributo, html)

    def test_the_clip_is_configured_to_loop_without_distraction(self):
        exercicio = Exercise.objects.exclude(video_url="").first()
        url = exercicio.video_embed_url

        for parametro in ("autoplay=1", "mute=1", "loop=1", "controls=0", "playsinline=1"):
            with self.subTest(parametro=parametro):
                self.assertIn(parametro, url)

        # `loop` sozinho não repete no YouTube: a API exige a playlist com o
        # próprio id do vídeo.
        self.assertIn(f"playlist={exercicio.video_id}", url)

        # Domínio sem cookie de rastreamento: o app já sabe peso e objetivo de
        # quem usa, não faz sentido entregar o resto para publicidade.
        self.assertIn("youtube-nocookie.com", url)

    def test_the_media_is_dropped_on_every_way_out(self):
        """O `<dialog>` fechado some da tela, mas o `<iframe>` continua no
        documento, tocando e baixando.

        Medido no navegador: fechar o drawer deixava o player rodando atrás da
        tela. A causa foi depender só do evento `close`, que naquele navegador
        não disparava. Agora a limpeza roda em cada caminho — botão, fundo,
        Esc e cronômetro — com o evento como rede de segurança.
        """
        html = self._pagina()

        self.assertIn("function limparMidia()", html)
        self.assertIn("function fecharDrawer()", html)

        limpeza = html.split("function limparMidia() {", 1)[1].split("}", 1)[0]
        self.assertIn('innerHTML = ""', limpeza)

        # Três caminhos ligados na função, mais os dois eventos nativos.
        self.assertIn("data-drawer-fechar", html)
        self.assertIn("if (event.target === drawer) fecharDrawer();", html)
        self.assertIn('drawer.addEventListener("cancel", limparMidia)', html)
        self.assertIn('drawer.addEventListener("close", limparMidia)', html)

    def test_the_drawer_can_be_closed_by_the_backdrop(self):
        html = self._pagina()
        self.assertIn("event.target === drawer", html)


class WeekAccordionTests(TestCase):
    """As cinco fichas em sanfona, com uma aberta.

    Abertas de uma vez elas somavam 12.841 px — dezoito telas de rolagem para
    quem só queria conferir a carga de hoje. Com a sanfona são 2.828 px.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(email="sanfona@exemplo.com", weekdays=(0, 1, 2, 3, 4))
        # A ficha nasce no primeiro acesso à tela; criar aqui é o que permite
        # consultá-la antes de renderizar.
        self.plano = services.create_routine(self.user)
        self.client.force_login(self.user)

    def _pagina(self):
        return self.client.get(reverse("workouts:routine")).content.decode()

    def test_every_workout_is_a_native_disclosure(self):
        """`<details>` e não `<div>` com JavaScript.

        Traz de graça o que dá trabalho reimplementar direito: abre por
        teclado, anuncia o estado para leitor de tela, responde ao Ctrl+F do
        navegador e funciona antes de o JavaScript carregar.
        """
        html = self._pagina()
        plano = self.plano

        self.assertEqual(html.count("<details class=\"card ficha\""), plano.sessions.count())
        self.assertEqual(html.count("<summary"), plano.sessions.count())

    def test_only_one_workout_starts_open(self):
        html = self._pagina()
        self.assertEqual(html.count("data-ficha open"), 1)

    def test_the_open_one_is_today(self):
        """A pessoa abre o app para saber o que treina hoje — não para
        procurar entre cinco fichas qual é a de hoje."""
        plano = self.plano
        hoje = timezone.localdate().weekday()
        do_dia = plano.sessions.filter(weekday=hoje).first()
        if do_dia is None:
            self.skipTest("hoje é dia de descanso para este usuário")

        html = self._pagina()
        marcado = html.split("data-ficha open", 1)[0]
        # O `data-dia` mais recente antes do `open` é o da ficha aberta.
        ultimo_dia = marcado.rsplit('data-dia="', 1)[1][0]
        self.assertEqual(ultimo_dia, do_dia.label)
        self.assertIn("ficha__hoje", html)

    def test_a_rest_day_falls_back_to_the_first_workout(self):
        """Abrir nenhuma deixaria a tela parecendo vazia num domingo."""
        user = create_user(email="descanso@exemplo.com", weekdays=(0,))
        plano = services.create_routine(user)
        sessoes = list(plano.sessions.all())

        # Força o cenário: nenhuma sessão cai no dia de hoje.
        hoje = timezone.localdate().weekday()
        for i, sessao in enumerate(sessoes):
            sessao.weekday = (hoje + 1 + i) % 7
            sessao.save(update_fields=["weekday"])

        from workouts.views import marcar_ficha_aberta

        marcar_ficha_aberta(sessoes)

        self.assertTrue(sessoes[0].aberta)
        self.assertFalse(sessoes[0].eh_hoje)
        self.assertEqual(sum(1 for s in sessoes if s.aberta), 1)

    def test_the_collapsed_header_says_enough_to_choose_without_opening(self):
        html = self._pagina()
        sessao = self.plano.sessions.first()

        self.assertIn(f"Treino {sessao.label}", html)
        self.assertIn(sessao.name, html)
        self.assertIn(sessao.weekday_display, html)
        self.assertIn("exercícios ·", html)
        self.assertIn("séries", html)

    def test_the_exercises_are_in_the_page_even_when_collapsed(self):
        """O HTML vem inteiro de propósito.

        Buscar os exercícios por rede ao abrir a ficha faria a academia com
        sinal ruim virar problema de produto. O que a sanfona economiza é
        layout — conteúdo de `<details>` fechado não é medido nem pintado —,
        não o download.
        """
        html = self._pagina()
        plano = self.plano
        total = sum(s.exercises.count() for s in plano.sessions.all())

        self.assertEqual(html.count("exercise__ver"), total)
        self.assertEqual(html.count('class="set-row '), sum(
            item.sets
            for s in plano.sessions.all()
            for item in s.exercises.all()
        ))

    def test_opening_one_closes_the_others(self):
        """`<details name>` faria isso nativamente, mas só em navegador
        recente — e este projeto já perdeu a barra de navegação por confiar num
        recurso novo. O JS cobre todo mundo."""
        html = self._pagina()
        self.assertIn('addEventListener("toggle"', html)
        self.assertIn("[data-ficha][open]", html)
        self.assertIn("outra.open = false", html)


class ExerciseFrameTests(TestCase):
    """A demonstração em fotos da free-exercise-db.

    O que essa base entrega, para não haver mal-entendido: DUAS FOTOS por
    exercício, começo e fim do movimento. Não são GIFs animados nem
    renderizações 3D — isso não existe em base aberta e sem chave de API. A
    tela alterna as duas em loop, que é o que demonstra a amplitude.

    Em troca do que se perde em suavidade: domínio público, não somem quando o
    dono apaga, não abrem com introdução falada, e pesam uns 30 kB contra um
    player inteiro.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _mapa(self):
        import json

        caminho = Path(settings.BASE_DIR) / "workouts" / "data" / "media_map.json"
        return {
            nome: ident
            for nome, ident in json.loads(caminho.read_text(encoding="utf-8")).items()
            if not nome.startswith("_")
        }

    def test_every_exercise_in_the_catalog_is_in_the_map(self):
        """Exercício sem mapa fica sem demonstração e ninguém percebe."""
        mapa = self._mapa()
        faltando = [
            e.name for e in Exercise.objects.filter(is_active=True) if e.name not in mapa
        ]
        self.assertEqual(faltando, [], "exercícios sem correspondência de mídia")

    def test_the_map_has_no_leftovers(self):
        """Nome que saiu do catálogo e ficou no mapa é lixo que confunde."""
        do_catalogo = set(Exercise.objects.values_list("name", flat=True))
        sobrando = [nome for nome in self._mapa() if nome not in do_catalogo]
        self.assertEqual(sobrando, [])

    def test_no_two_exercises_share_the_same_demonstration(self):
        """Dois exercícios com a mesma foto é erro de mapa, não coincidência."""
        mapa = self._mapa()
        vistos = {}
        for nome, ident in mapa.items():
            vistos.setdefault(ident, []).append(nome)
        repetidos = {i: n for i, n in vistos.items() if len(n) > 1}
        self.assertEqual(repetidos, {})

    def test_the_frames_point_at_a_cdn_and_not_at_raw_github(self):
        """raw.githubusercontent responde, mas não é feito para ser origem de
        imagem de aplicação — não tem cache de borda nem garantia de tráfego."""
        from workouts.management.commands.sync_exercise_media import CDN, urls_de

        self.assertIn("cdn.jsdelivr.net", CDN)
        urls = urls_de("Barbell_Curl")
        self.assertEqual(len(urls), 2)
        self.assertTrue(all(u.startswith(CDN) for u in urls))
        self.assertTrue(urls[0].endswith("/0.jpg"))
        self.assertTrue(urls[1].endswith("/1.jpg"))

    def test_the_drawer_walks_down_the_media_ladder(self):
        """Três degraus, em ordem de qualidade: animação, foto, vídeo.

        Cada um só entra quando o de cima não existe. Hoje o topo está vazio
        para todo mundo — não há fonte gratuita e verificável de animação
        anatômica —, e o `<iframe>` do YouTube passou a ser o último recurso
        em vez do caminho normal.
        """
        user = create_user(email="frames@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()

        for atributo in ("data-animacao=", "data-quadros="):
            with self.subTest(atributo=atributo):
                self.assertIn(atributo, html)

        self.assertIn(
            "if (!montarAnimacao(media, dados) && !montarQuadros(media, dados)) {",
            html,
        )

    def test_the_numbers_are_filled_no_matter_which_media_is_used(self):
        """Regressão: o `if` da mídia chegou a sair da função com `return`, e
        com isso nome, séries, descanso e carga ficavam em branco sempre que a
        foto existia — ou seja, sempre."""
        user = create_user(email="numeros@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()

        corpo = html.split("function preencher(dados) {", 1)[1]
        ramo_da_midia = corpo.split("&& !montarQuadros(media, dados)) {", 1)[1]
        self.assertNotIn("return;", ramo_da_midia.split("data-drawer-nome", 1)[0])
        self.assertIn("data-drawer-series", corpo)
        self.assertIn("data-drawer-carga", corpo)

    def test_the_alternation_stops_when_the_drawer_closes(self):
        """Um `setInterval` esquecido continua trocando imagem numa tela que
        ninguém está vendo, e vai junto para o próximo exercício aberto."""
        user = create_user(email="parar@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()

        limpeza = html.split("function limparMidia() {", 1)[1].split("}", 1)[0]
        self.assertIn("pararAlternancia()", limpeza)


class AnimationImportTests(TestCase):
    """O importador de animação, e o que ele recusa.

    A fonte da animação já mudou três vezes neste projeto — YouTube, foto de
    domínio público, e agora animação premium. Por isso o comando lê um
    arquivo em vez de falar com uma API específica: trocar de fornecedor passa
    a ser trocar o arquivo, não reescrever um cliente HTTP.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def _arquivo(self, conteudo):
        import json
        import tempfile

        caminho = Path(tempfile.mkdtemp()) / "animacoes.json"
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
        return str(caminho)

    def test_a_name_that_is_not_in_the_catalog_stops_the_import(self):
        """Catálogo meio importado é pior que não importado: metade da tela
        muda de aparência e ninguém sabe por quê."""
        arquivo = self._arquivo(
            {
                "Supino reto com barra": "https://exemplo.com/a.mp4",
                "Exercício que não existe": "https://exemplo.com/b.mp4",
            }
        )

        antes = dict(Exercise.objects.values_list("name", "animation_url"))

        with self.assertRaises(CommandError):
            call_command("set_exercise_animation", arquivo, "--check", verbosity=0)

        # "Nada foi gravado" se mede comparando o antes e o depois: o seed já
        # deixa o catálogo com animação, então o vazio não serve de prova.
        self.assertEqual(dict(Exercise.objects.values_list("name", "animation_url")), antes)

    def test_a_format_the_screen_cannot_play_stops_the_import(self):
        """PDF ou JPG entrariam como imagem e apareceriam parados — recusar é
        melhor que exibir errado."""
        arquivo = self._arquivo(
            {"Supino reto com barra": "https://exemplo.com/instrucoes.pdf"}
        )

        with self.assertRaises(CommandError):
            call_command("set_exercise_animation", arquivo, "--check", verbosity=0)

    def test_the_supported_formats_are_the_ones_the_drawer_builds(self):
        from workouts.management.commands.set_exercise_animation import tipo_de

        self.assertEqual(tipo_de("https://x/a.mp4"), "video")
        self.assertEqual(tipo_de("https://x/a.webm"), "video")
        self.assertEqual(tipo_de("https://x/a.gif"), "imagem")
        self.assertEqual(tipo_de("https://x/a.webp"), "imagem")
        # Query string não pode enganar a detecção.
        self.assertEqual(tipo_de("https://x/a.mp4?v=2"), "video")
        self.assertEqual(tipo_de("https://x/pagina.html"), "")

    def test_clear_puts_the_photos_back(self):
        exercicio = Exercise.objects.first()
        exercicio.animation_url = "https://exemplo.com/a.mp4"
        exercicio.save(update_fields=["animation_url"])

        call_command("set_exercise_animation", "--clear", verbosity=0)

        exercicio.refresh_from_db()
        self.assertEqual(exercicio.animation_url, "")
        # As fotos continuam lá — a animação era uma camada por cima.
        self.assertTrue(exercicio.frames)

    def test_the_model_knows_how_to_play_each_format(self):
        exercicio = Exercise.objects.first()

        exercicio.animation_url = "https://exemplo.com/a.mp4"
        self.assertEqual(exercicio.animation_kind, "video")

        exercicio.animation_url = "https://exemplo.com/a.gif"
        self.assertEqual(exercicio.animation_kind, "imagem")

        exercicio.animation_url = ""
        self.assertEqual(exercicio.animation_kind, "")

    def test_the_animation_wins_over_the_photos_in_the_drawer(self):
        exercicio = Exercise.objects.get(name="Supino reto com barra")
        exercicio.animation_url = "https://exemplo.com/supino.mp4"
        exercicio.save(update_fields=["animation_url"])

        user = create_user(email="animacao@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('data-animacao="https://exemplo.com/supino.mp4"', html)
        self.assertIn('data-animacao-tipo="video"', html)

    def test_a_video_animation_is_muted_and_inline(self):
        """Sem `muted` o navegador recusa o autoplay; sem `playsinline` o
        iPhone abre em tela cheia por cima do app."""
        user = create_user(email="mudo@exemplo.com")
        self.client.force_login(user)
        html = self.client.get(reverse("workouts:routine")).content.decode()

        bloco = html.split("function montarAnimacao(media, dados) {", 1)[1]
        bloco = bloco.split("return true;", 1)[0]
        for atributo in ('setAttribute("muted"', 'setAttribute("playsinline"',
                         "elemento.loop = true", "elemento.autoplay = true"):
            with self.subTest(atributo=atributo):
                self.assertIn(atributo, bloco)

# ==========================================================================
# Assistente de ajuste
# ==========================================================================

def _com_alternativa(plan):
    """Um item da rotina cujo grupo muscular ainda tem substituto no catálogo.

    Peito, bíceps, panturrilha e tríceps não têm: a ficha gerada já usa todos
    os exercícios do grupo. Escolher o alvo às cegas testaria a ausência de
    alternativa em vez da escolha da alternativa.
    """
    for sessao in plan.sessions.order_by("order"):
        for item in sessao.exercises.select_related("exercise").order_by("order"):
            if assistant.candidatos_para(item):
                return sessao, item
    raise AssertionError("nenhum exercício do catálogo tem substituto")


def _sem_alternativa(plan):
    """Um item cujo grupo muscular está esgotado — o caso que exige a verdade."""
    for sessao in plan.sessions.order_by("order"):
        for item in sessao.exercises.select_related("exercise").order_by("order"):
            if not assistant.candidatos_para(item):
                return sessao, item
    raise AssertionError("todo exercício tem substituto — fixture mudou")



class SubstitutionEngineTests(TestCase):
    """A escolha do substituto.

    As regras duras — mesmo músculo, com demonstração, fora da sessão — são o
    que separa "substituição" de "outro exercício qualquer", e são as que
    quebram em silêncio: uma troca de peito por bíceps continua salvando no
    banco e continua parecendo certa na tela.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)
        self.session, self.item = _com_alternativa(self.plan)

    def _item(self):
        return self.item

    def test_a_substitute_never_changes_the_muscle_worked(self):
        for item in SessionExercise.objects.filter(
            session__plan=self.plan
        ).select_related("exercise"):
            with self.subTest(exercicio=item.exercise.name):
                for candidato in assistant.candidatos_para(item):
                    self.assertEqual(candidato.muscle_group, item.exercise.muscle_group)

    def test_a_substitute_always_has_a_demonstration(self):
        """Trocar sem quebrar a mídia é metade do pedido: um substituto sem
        animação resolve o equipamento e apaga a única coisa que ensina a
        execução."""
        for candidato in assistant.candidatos_para(self._item()):
            with self.subTest(candidato=candidato.name):
                self.assertTrue(candidato.animation_kind)

    def test_a_substitute_is_never_already_in_the_session(self):
        item = self._item()
        na_ficha = set(self.session.exercises.values_list("exercise_id", flat=True))
        for candidato in assistant.candidatos_para(item):
            with self.subTest(candidato=candidato.name):
                self.assertNotIn(candidato.pk, na_ficha)

    def test_a_retired_exercise_is_never_suggested(self):
        item = self._item()
        alvo = assistant.candidatos_para(item)[0]
        Exercise.objects.filter(pk=alvo.pk).update(is_active=False)

        self.assertNotIn(alvo.name, [c.name for c in assistant.candidatos_para(item)])

    def test_the_same_question_gets_the_same_answer(self):
        """Sem desempate estável, a mesma pergunta devolve respostas diferentes
        conforme a ordem que o banco resolver usar — e a pessoa acha que o app
        está sorteando."""
        item = self._item()
        self.assertEqual(
            [c.pk for c in assistant.candidatos_para(item)],
            [c.pk for c in assistant.candidatos_para(item)],
        )

    def test_a_rejected_option_does_not_come_back(self):
        item = self._item()
        recusado = assistant.candidatos_para(item)[0]

        outros = assistant.candidatos_para(item, excluir=[recusado.pk])

        self.assertNotIn(recusado.pk, [c.pk for c in outros])


class EquipmentSubstitutionTests(TestCase):
    """Academia cheia: o substituto tem que estar realmente livre."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)

    def _sessao_com(self, muscle_group):
        for sessao in self.plan.sessions.all():
            item = (
                sessao.exercises.filter(exercise__muscle_group=muscle_group)
                .select_related("exercise")
                .first()
            )
            if item:
                return sessao, item
        return None, None

    def test_the_catalog_knows_what_each_exercise_occupies(self):
        self.assertEqual(Exercise.objects.filter(equipment="").count(), 0)

    def test_machines_and_cables_are_the_ones_that_form_a_queue(self):
        polia = Exercise.objects.filter(equipment=Equipment.CABLE).first()
        halter = Exercise.objects.filter(equipment=Equipment.DUMBBELL).first()

        self.assertTrue(polia.disputa_equipamento)
        self.assertFalse(halter.disputa_equipamento)

    def test_a_substitute_lands_on_something_without_a_queue(self):
        """A regra não é "equipamento diferente", é "equipamento sem fila".

        Trocar polia por máquina é diferente e é inútil: numa academia cheia as
        duas estão tomadas. O teste original media a diferença e passava com
        essa troca — foi o app rodando que mostrou o erro, não ele.
        """
        alvo = None
        for sessao in self.plan.sessions.order_by("order"):
            for item in sessao.exercises.select_related("exercise").order_by("order"):
                if not item.exercise.disputa_equipamento:
                    continue
                sugestao = assistant.sugerir(sessao, assistant.EQUIPAMENTO, item=item)
                if sugestao.mudancas and sugestao.mudancas[0].novo_exercicio:
                    alvo = sugestao.mudancas[0].novo_exercicio
                    break
            if alvo:
                break

        if alvo is None:
            self.skipTest("nenhuma substituição de aparelho disputado nesta divisão")
        self.assertFalse(alvo.disputa_equipamento)

    def test_an_exhausted_muscle_group_gets_a_reorder_instead(self):
        """Peito, bíceps, panturrilha e tríceps não têm substituto: a ficha já
        usa o catálogo inteiro do grupo.

        E, olhando de perto, substituir nunca foi a resposta certa aqui. Quando
        o supino está em uso ninguém troca supino por outra coisa — faz o
        próximo exercício e volta. Reordenar é o que a pessoa já faria sozinha.
        """
        sessao, item = _sem_alternativa(self.plan)

        sugestao = assistant.sugerir(sessao, assistant.EQUIPAMENTO, item=item)

        self.assertTrue(sugestao.tem_proposta)
        mudanca = sugestao.mudancas[0]
        self.assertEqual(mudanca.tipo, "reordenar")
        self.assertIsNotNone(mudanca.parceiro)
        self.assertNotEqual(mudanca.parceiro.pk, item.pk)

    def test_the_reorder_swaps_the_two_positions(self):
        sessao, item = _sem_alternativa(self.plan)
        sugestao = assistant.sugerir(sessao, assistant.EQUIPAMENTO, item=item)
        parceiro = sugestao.mudancas[0].parceiro
        antes = (item.order, parceiro.order)

        assistant.aplicar(sessao, sugestao.mudancas)

        item.refresh_from_db()
        parceiro.refresh_from_db()
        self.assertEqual((item.order, parceiro.order), (antes[1], antes[0]))

    def test_the_reorder_keeps_every_exercise_in_the_session(self):
        """Adiar não é remover: o exercício continua no treino de hoje."""
        sessao, item = _sem_alternativa(self.plan)
        antes = set(sessao.exercises.values_list("exercise_id", flat=True))

        sugestao = assistant.sugerir(sessao, assistant.EQUIPAMENTO, item=item)
        assistant.aplicar(sessao, sugestao.mudancas)

        self.assertEqual(
            set(sessao.exercises.values_list("exercise_id", flat=True)), antes
        )

    def test_without_a_target_it_picks_something_that_actually_has_a_queue(self):
        """Sugerir trocar a flexão de braço porque "a academia está cheia" é
        responder outra pergunta: flexão não tem fila."""
        sessao = self.plan.sessions.order_by("order").first()
        if not sessao.exercises.filter(
            exercise__equipment__in=(Equipment.MACHINE, Equipment.CABLE)
        ).exists():
            self.skipTest("esta ficha não tem aparelho disputado")

        sugestao = assistant.sugerir(sessao, assistant.EQUIPAMENTO)

        self.assertTrue(sugestao.mudancas[0].item.exercise.disputa_equipamento)


class PainSubstitutionTests(TestCase):
    """Desconforto: poupar a articulação quando dá, e dizer quando não dá."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)

    def _sessao_com(self, muscle_group):
        for sessao in self.plan.sessions.all():
            item = (
                sessao.exercises.filter(exercise__muscle_group=muscle_group)
                .select_related("exercise")
                .first()
            )
            if item:
                return sessao, item
        return None, None

    def test_the_catalog_knows_which_joints_each_exercise_loads(self):
        vazios = [e.name for e in Exercise.objects.filter(is_active=True) if not e.joints]
        self.assertEqual(vazios, [], f"sem articulações curadas: {vazios}")

    def test_a_knee_complaint_moves_off_the_knee_when_possible(self):
        """Posteriores é o caso em que dá: flexora carrega o joelho, stiff e
        elevação pélvica não."""
        sessao, item = self._sessao_com(MuscleGroup.HAMSTRINGS)
        if item is None:
            self.skipTest("nenhuma sessão de posteriores nesta divisão")

        flexora = Exercise.objects.filter(
            muscle_group=MuscleGroup.HAMSTRINGS, joints__contains=["knee"]
        ).first()
        item.exercise = flexora
        item.save(update_fields=["exercise"])

        sugestao = assistant.sugerir(
            sessao, assistant.DESCONFORTO, item=item, articulacao="knee"
        )

        self.assertNotIn("knee", sugestao.mudancas[0].novo_exercicio.joints)
        self.assertEqual(sugestao.aviso, "")

    def test_when_no_exercise_spares_the_joint_the_app_says_so(self):
        """Todo exercício de quadríceps carrega o joelho. Fingir que a troca
        resolveu seria a pior coisa que o app poderia fazer aqui."""
        sessao, item = self._sessao_com(MuscleGroup.QUADS)
        if item is None:
            self.skipTest("nenhuma sessão de quadríceps nesta divisão")

        sugestao = assistant.sugerir(
            sessao, assistant.DESCONFORTO, item=item, articulacao="knee"
        )

        self.assertIn("não há troca que resolva", sugestao.aviso)
        self.assertIn("procure um profissional", sugestao.aviso)

    def test_the_app_never_claims_to_treat_anything(self):
        sessao, item = self._sessao_com(MuscleGroup.QUADS)
        if item is None:
            self.skipTest("nenhuma sessão de quadríceps nesta divisão")

        sugestao = assistant.sugerir(
            sessao, assistant.DESCONFORTO, item=item, articulacao="knee"
        )
        texto = (sugestao.aviso + " " + sugestao.resumo).lower()

        for promessa in ("cura", "trata", "resolve a dor", "seguro para"):
            with self.subTest(promessa=promessa):
                self.assertNotIn(promessa, texto)


class ExpressWorkoutTests(TestCase):
    """Treino express: tirar tempo sem tirar o treino."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)
        self.session = self.plan.sessions.order_by("order").first()

    def test_the_session_actually_gets_shorter(self):
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)

        self.assertTrue(sugestao.tem_proposta)
        self.assertLess(sugestao.minutos_depois, sugestao.minutos_antes)

    def test_the_compound_lifts_keep_their_sets(self):
        """Os compostos são o treino. Uma sessão de peito sem supino não é uma
        sessão curta, é outra coisa."""
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)

        for mudanca in sugestao.mudancas:
            if not mudanca.item.exercise.is_compound:
                continue
            with self.subTest(exercicio=mudanca.item.exercise.name):
                self.assertNotEqual(mudanca.tipo, "remocao")
                if mudanca.tipo == "ajuste":
                    self.assertEqual(mudanca.sets, mudanca.item.sets)

    def test_the_rest_of_a_compound_never_drops_below_ninety_seconds(self):
        """Cortar o descanso do agachamento para 45 segundos não encurta o
        treino: faz falhar na terceira série e treinar menos."""
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)

        for mudanca in sugestao.mudancas:
            if mudanca.tipo == "ajuste" and mudanca.item.exercise.is_compound:
                with self.subTest(exercicio=mudanca.item.exercise.name):
                    self.assertGreaterEqual(mudanca.rest_seconds, 90)

    def test_an_isolation_never_falls_below_two_sets(self):
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)

        for mudanca in sugestao.mudancas:
            if mudanca.tipo == "ajuste" and mudanca.sets is not None:
                with self.subTest(exercicio=mudanca.item.exercise.name):
                    self.assertGreaterEqual(mudanca.sets, 2)

    def test_nothing_is_ever_removed_from_the_routine(self):
        """A prévia dizia "sai hoje" e a gravação apagava a linha para sempre.

        Uma terça-feira corrida deletava a panturrilha da rotina inteira, e a
        pessoa descobriria semanas depois sem ligar uma coisa à outra. Um botão
        de pressa não pode destruir a rotina — o corte ficou só no que é
        reversível.
        """
        antes = set(self.session.exercises.values_list("pk", flat=True))
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)

        self.assertEqual([m for m in sugestao.mudancas if m.tipo == "remocao"], [])

        assistant.aplicar(self.session, sugestao.mudancas)
        self.assertEqual(
            set(self.session.exercises.values_list("pk", flat=True)), antes
        )

    def test_an_unreachable_target_is_reported_instead_of_forced(self):
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)
        alvo = sugestao.minutos_antes - assistant.CORTE_EXPRESS_MIN

        if sugestao.minutos_depois > max(alvo, assistant.MINIMO_DA_SESSAO_MIN):
            self.assertIn("não faz isso", sugestao.aviso)

    def test_an_already_short_session_is_left_alone(self):
        """Cortar 30 minutos de uma sessão de 25 desmontaria a ficha."""
        self.session.exercises.exclude(pk=self.session.exercises.first().pk).delete()
        item = self.session.exercises.first()
        item.sets = 2
        item.rest_seconds = 45
        item.save(update_fields=["sets", "rest_seconds"])

        sugestao = assistant.sugerir(self.session, assistant.TEMPO)

        self.assertFalse(sugestao.tem_proposta)
        self.assertIn("não dá para encurtar", sugestao.aviso)


class FreeRequestTests(TestCase):
    """A leitura do pedido escrito.

    É casamento por palavra-chave, e os testes cobrem o que ele promete — frase
    direta, no presente, citando o exercício. Não promete entender ironia nem
    negação, e os testes não fingem que promete.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)
        self.session = self.plan.sessions.order_by("order").first()

    def test_it_reads_the_motive(self):
        casos = [
            ("a academia ta cheia demais hoje", assistant.EQUIPAMENTO),
            ("o supino ta ocupado", assistant.EQUIPAMENTO),
            ("to sem tempo, preciso de algo rapido", assistant.TEMPO),
            ("cansei desse exercicio, quero trocar", assistant.TROCA),
            ("doi o ombro quando faco isso", assistant.DESCONFORTO),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(
                    assistant.interpretar(texto, session=self.session).motivo, esperado
                )

    def test_it_reads_the_joint(self):
        casos = [
            ("sinto desconforto no joelho", "knee"),
            ("dor no ombro direito", "shoulder"),
            ("minha lombar reclama", "lower_back"),
            ("o punho doi na pegada", "wrist"),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(assistant.interpretar(texto).articulacao, esperado)

    def test_it_finds_the_exercise_by_the_name_people_actually_type(self):
        """Ninguém escreve "Leg press 45°" — escreve "leg press"."""
        sessao = None
        for candidata in self.plan.sessions.all():
            if candidata.exercises.filter(
                exercise__name__icontains="Leg press"
            ).exists():
                sessao = candidata
                break
        if sessao is None:
            self.skipTest("nenhuma ficha com leg press nesta divisão")

        intencao = assistant.interpretar(
            "troca o leg press que ta doendo o joelho", session=sessao
        )

        self.assertIsNotNone(intencao.item)
        self.assertIn("Leg press", intencao.item.exercise.name)
        self.assertEqual(intencao.articulacao, "knee")
        self.assertEqual(intencao.motivo, assistant.DESCONFORTO)

    def test_a_specific_complaint_beats_the_generic_one(self):
        """"Pouco tempo e o aparelho ocupado" é sobre o aparelho: tempo é o
        motivo genérico, equipamento cita uma coisa concreta."""
        intencao = assistant.interpretar(
            "to com pouco tempo e ainda por cima o aparelho ta ocupado",
            session=self.session,
        )
        self.assertEqual(intencao.motivo, assistant.EQUIPAMENTO)

    def test_an_unreadable_request_falls_back_to_the_safest_motive(self):
        self.assertEqual(
            assistant.interpretar("blergh", session=self.session).motivo,
            assistant.TROCA,
        )

    def test_pain_without_a_target_does_not_guess(self):
        """"Dói" sozinho não diz qual dos seis exercícios é o culpado."""
        self.assertEqual(
            assistant.interpretar("ta doendo", session=self.session).motivo,
            assistant.TROCA,
        )

    def test_the_whole_request_turns_into_a_suggestion(self):
        sugestao = assistant.sugerir_do_texto(
            self.session, "troque o primeiro exercicio, enjoei dele"
        )
        self.assertTrue(sugestao.tem_proposta or sugestao.aviso)


class ApplyAdjustmentTests(TestCase):
    """A gravação — e o que ela não pode encostar."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)
        self.session, self.item = _com_alternativa(self.plan)

    def test_the_swap_reaches_the_session(self):
        sugestao = assistant.sugerir(self.session, assistant.TROCA, item=self.item)
        novo = sugestao.mudancas[0].novo_exercicio

        assistant.aplicar(self.session, sugestao.mudancas)

        self.item.refresh_from_db()
        self.assertEqual(self.item.exercise, novo)

    def test_the_load_history_is_never_touched(self):
        """A garantia que mais importa.

        Os registros de carga apontam para o exercício e para a data, não para
        a linha da ficha — trocar supino por crucifixo não pode apagar nem
        reescrever nenhuma série já anotada. Quem treina há seis meses tem esse
        histórico como o único registro de que evoluiu.
        """
        antigo = self.item.exercise
        hoje = timezone.localdate()
        for serie in (1, 2, 3):
            ExerciseLog.objects.create(
                user=self.user,
                exercise=antigo,
                date=hoje - timedelta(days=7),
                set_number=serie,
                weight_kg=Decimal("60"),
                reps=10,
            )
        antes = list(
            ExerciseLog.objects.filter(user=self.user)
            .order_by("pk")
            .values("pk", "exercise_id", "date", "set_number", "weight_kg", "reps")
        )

        sugestao = assistant.sugerir(self.session, assistant.TROCA, item=self.item)
        assistant.aplicar(self.session, sugestao.mudancas)

        depois = list(
            ExerciseLog.objects.filter(user=self.user)
            .order_by("pk")
            .values("pk", "exercise_id", "date", "set_number", "weight_kg", "reps")
        )
        self.assertEqual(antes, depois)

    def test_applying_marks_the_plan_as_customized(self):
        self.assertFalse(self.plan.is_customized)

        sugestao = assistant.sugerir(self.session, assistant.TROCA, item=self.item)
        assistant.aplicar(self.session, sugestao.mudancas)

        self.plan.refresh_from_db()
        self.assertTrue(self.plan.is_customized)

    def test_the_generator_stops_rewriting_an_adjusted_plan(self):
        """O risco silencioso: sem esta trava, mudar o horário de terça
        remontaria a ficha do catálogo e apagaria a troca de ontem."""
        sugestao = assistant.sugerir(self.session, assistant.TROCA, item=self.item)
        novo = sugestao.mudancas[0].novo_exercicio
        assistant.aplicar(self.session, sugestao.mudancas)

        TrainingDay.objects.filter(user=self.user).update(start_time=time(6, 30))
        _, mudou = services.sync_active_routine(self.user)

        self.assertFalse(mudou)
        self.item.refresh_from_db()
        self.assertEqual(self.item.exercise, novo)

    def test_a_retired_exercise_still_forces_a_rebuild(self):
        """Aqui o gerador não está desfazendo a escolha da pessoa: está
        avisando que o catálogo mudou embaixo dela."""
        sugestao = assistant.sugerir(self.session, assistant.TROCA, item=self.item)
        assistant.aplicar(self.session, sugestao.mudancas)
        self.item.refresh_from_db()
        Exercise.objects.filter(pk=self.item.exercise_id).update(is_active=False)

        _, mudou = services.sync_active_routine(self.user)
        self.assertTrue(mudou)

    def test_a_group_with_no_substitute_gets_the_truth(self):
        """Fingir que resolveu é a pior coisa que o app pode fazer aqui."""
        sessao, item = _sem_alternativa(self.plan)

        sugestao = assistant.sugerir(sessao, assistant.TROCA, item=item)

        self.assertFalse(sugestao.tem_proposta)
        self.assertIn("não há substituto", sugestao.aviso)
        self.assertIn("histórico de carga não se perde", sugestao.aviso)

    def test_the_express_cut_applies_every_change(self):
        sugestao = assistant.sugerir(self.session, assistant.TEMPO)
        esperados = len(sugestao.mudancas)

        aplicadas = assistant.aplicar(self.session, sugestao.mudancas)

        self.assertEqual(aplicadas, esperados)
        self.assertLessEqual(self.session.estimated_minutes, sugestao.minutos_antes)

    def test_the_last_exercise_of_a_session_is_never_removed(self):
        self.session.exercises.exclude(pk=self.item.pk).delete()
        mudanca = assistant.Mudanca(item=self.item, tipo="remocao", porque="")

        assistant.aplicar(self.session, [mudanca])

        self.assertEqual(self.session.exercises.count(), 1)


class AssistantViewTests(TestCase):
    """As telas — e a trava de quem pode mexer em qual ficha."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)
        self.session, self.item = _com_alternativa(self.plan)
        self.client.force_login(self.user)

    def _url(self, **params):
        base = reverse("workouts:assistant", args=[self.session.pk])
        if not params:
            return base
        return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    def test_the_routine_screen_offers_the_adjustment(self):
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn("data-ia-abrir", html)
        self.assertIn("Ajustar treino", html)

    def test_the_menu_lists_the_three_shortcuts(self):
        corpo = self.client.get(self._url()).content.decode()

        self.assertIn("Academia cheia", corpo)
        self.assertIn("Pouco tempo", corpo)
        self.assertIn("Substituir exercício", corpo)
        self.assertIn('name="pedido"', corpo)

    def test_swapping_asks_which_exercise_first(self):
        corpo = self.client.get(self._url(motivo="troca")).content.decode()

        self.assertIn("Qual exercício trocar?", corpo)
        # Um por exercício, mais o botão de voltar.
        self.assertEqual(corpo.count("data-ia-ir"), self.session.exercises.count() + 1)

    def test_the_preview_shows_the_change_before_anything_is_saved(self):
        antes = self.item.exercise_id

        corpo = self.client.get(
            self._url(motivo="troca", item=self.item.pk)
        ).content.decode()

        self.assertIn("Confirmar alteração", corpo)
        self.assertIn(self.item.exercise.name, corpo)
        self.item.refresh_from_db()
        self.assertEqual(self.item.exercise_id, antes, "a prévia gravou algo")

    def test_a_free_request_reaches_the_preview(self):
        corpo = self.client.get(self._url(pedido="a+academia+esta+cheia")).content.decode()
        self.assertIn("Confirmar alteração", corpo)

    def test_an_exhausted_group_shows_the_warning_and_no_confirm_button(self):
        """Sem proposta não pode haver botão de confirmar: um botão que não faz
        nada é pior que a ausência dele."""
        sessao, item = _sem_alternativa(self.plan)
        url = reverse("workouts:assistant", args=[sessao.pk])

        corpo = self.client.get(
            f"{url}?motivo=troca&item={item.pk}"
        ).content.decode()

        self.assertIn("não há substituto", corpo)
        self.assertNotIn("Confirmar alteração", corpo)

    def test_confirming_applies(self):
        sugestao = assistant.sugerir(self.session, assistant.TROCA, item=self.item)
        novo = sugestao.mudancas[0].novo_exercicio

        self.client.post(
            reverse("workouts:assistant_apply", args=[self.session.pk]),
            {"item": self.item.pk, "tipo": "troca", "valor": novo.pk},
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.exercise, novo)

    # ------------------------------------------------------------ segurança
    def test_the_session_of_another_person_is_invisible(self):
        """O id da sessão é sequencial e adivinhável. Sem o dono na consulta,
        trocar um número na URL editaria a ficha de outra pessoa."""
        outro = create_user(email="alheio@exemplo.com")
        plano_alheio = services.create_routine(outro)
        sessao_alheia = plano_alheio.sessions.first()

        leitura = self.client.get(
            reverse("workouts:assistant", args=[sessao_alheia.pk])
        )
        escrita = self.client.post(
            reverse("workouts:assistant_apply", args=[sessao_alheia.pk]),
            {"item": sessao_alheia.exercises.first().pk, "tipo": "troca", "valor": "1"},
        )

        self.assertEqual(leitura.status_code, 404)
        self.assertEqual(escrita.status_code, 404)

    def test_the_hidden_fields_cannot_smuggle_another_muscle_group(self):
        """Os campos escondidos voltam do navegador, então são entrada hostil.
        Sem revalidar, o formulário teria o poder de trocar supino por rosca."""
        rosca = Exercise.objects.filter(
            muscle_group=MuscleGroup.BICEPS, is_active=True
        ).first()
        antes = self.item.exercise_id

        self.client.post(
            reverse("workouts:assistant_apply", args=[self.session.pk]),
            {"item": self.item.pk, "tipo": "troca", "valor": rosca.pk},
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.exercise_id, antes)

    def test_the_hidden_fields_cannot_reach_another_persons_exercise(self):
        outro = create_user(email="alheio@exemplo.com")
        plano_alheio = services.create_routine(outro)
        item_alheio = plano_alheio.sessions.first().exercises.first()
        antes = item_alheio.exercise_id

        self.client.post(
            reverse("workouts:assistant_apply", args=[self.session.pk]),
            {"item": item_alheio.pk, "tipo": "troca", "valor": "1"},
        )

        item_alheio.refresh_from_db()
        self.assertEqual(item_alheio.exercise_id, antes)

    def test_absurd_numbers_are_refused(self):
        antes = (self.item.sets, self.item.rest_seconds)

        for valor in ("99,90", "3,9999", "abc", "3", ""):
            with self.subTest(valor=valor):
                self.client.post(
                    reverse("workouts:assistant_apply", args=[self.session.pk]),
                    {"item": self.item.pk, "tipo": "ajuste", "valor": valor},
                )
                self.item.refresh_from_db()
                self.assertEqual((self.item.sets, self.item.rest_seconds), antes)

    def test_it_asks_for_login(self):
        self.client.logout()
        resposta = self.client.get(self._url())

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta["Location"])

class WrongQuestionTests(TestCase):
    """Não responder a pergunta que ninguém fez.

    Os dois defeitos travados aqui não apareceram em teste nenhum: apareceram
    rodando o app e lendo a frase que ele escreveu. Os dois produziam respostas
    convincentes e erradas, que é a única categoria de erro que passa
    despercebida.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)

    def _sessao_sem(self, nome):
        for sessao in self.plan.sessions.order_by("order"):
            if not sessao.exercises.filter(exercise__name=nome).exists():
                return sessao
        return None

    def test_naming_an_exercise_from_another_day_is_answered_honestly(self):
        """"Troque o leg press" enviado no treino de costas fazia o assistente
        escolher a puxada e anunciar que ela "não carrega o joelho". Ninguém
        perguntou sobre as costas, e a frase sobre o joelho vinda de um
        exercício de puxada é pior que não responder: parece uma resposta.
        """
        sessao = self._sessao_sem("Leg press 45°")
        if sessao is None:
            self.skipTest("todas as fichas têm leg press")

        sugestao = assistant.sugerir_do_texto(
            sessao, "troque o leg press, sinto desconforto no joelho"
        )

        self.assertFalse(sugestao.tem_proposta)
        self.assertIn("Leg press", sugestao.aviso)
        self.assertIn(f"não está no Treino {sessao.label}", sugestao.aviso)

    def test_the_intent_records_what_was_named_and_not_found(self):
        sessao = self._sessao_sem("Leg press 45°")
        if sessao is None:
            self.skipTest("todas as fichas têm leg press")

        intencao = assistant.interpretar("troca o leg press", session=sessao)

        self.assertIsNone(intencao.item)
        self.assertIn("Leg press", intencao.fora_da_ficha)

    def test_an_exercise_that_is_in_the_session_is_not_flagged_as_missing(self):
        sessao = None
        for candidata in self.plan.sessions.order_by("order"):
            if candidata.exercises.filter(exercise__name="Leg press 45°").exists():
                sessao = candidata
                break
        if sessao is None:
            self.skipTest("nenhuma ficha com leg press")

        intencao = assistant.interpretar("troca o leg press", session=sessao)

        self.assertIsNotNone(intencao.item)
        self.assertIsNone(intencao.fora_da_ficha)

    def test_a_vague_request_is_not_mistaken_for_a_missing_exercise(self):
        sessao = self.plan.sessions.order_by("order").first()
        intencao = assistant.interpretar("quero mudar alguma coisa", session=sessao)
        self.assertIsNone(intencao.fora_da_ficha)


class BusyGymHonestyTests(TestCase):
    """Não prometer que está livre o que também tem fila.

    A proposta era polia → barra fixa assistida, com o texto "usa máquina e
    costuma estar livre quando a academia enche". Máquina é exatamente o que
    NÃO está livre quando a academia enche — a troca era diferente e inútil.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)

    def test_a_swap_for_a_busy_gym_never_lands_on_another_queue(self):
        for sessao in self.plan.sessions.order_by("order"):
            for item in sessao.exercises.select_related("exercise").order_by("order"):
                sugestao = assistant.sugerir(
                    sessao, assistant.EQUIPAMENTO, item=item
                )
                if not sugestao.tem_proposta:
                    continue
                novo = sugestao.mudancas[0].novo_exercicio
                if novo is None:
                    continue  # reordenação, que é a outra saída válida
                with self.subTest(de=item.exercise.name, para=novo.name):
                    self.assertFalse(
                        novo.disputa_equipamento,
                        f"{novo.name} usa {novo.get_equipment_display()}, "
                        f"que também tem fila",
                    )

    def test_when_every_alternative_has_a_queue_it_reorders(self):
        for sessao in self.plan.sessions.order_by("order"):
            for item in sessao.exercises.select_related("exercise").order_by("order"):
                livres = [
                    c for c in assistant.candidatos_para(item, evitar_equipamento=True)
                    if not c.disputa_equipamento
                ]
                if livres:
                    continue
                sugestao = assistant.sugerir(
                    sessao, assistant.EQUIPAMENTO, item=item
                )
                with self.subTest(exercicio=item.exercise.name):
                    self.assertTrue(sugestao.tem_proposta)
                    self.assertEqual(sugestao.mudancas[0].tipo, "reordenar")

    def test_the_reason_text_matches_what_the_swap_actually_does(self):
        """O texto dizia "costuma estar livre" sobre uma máquina. A frase e o
        dado precisam concordar — senão o app está inventando confiança."""
        for sessao in self.plan.sessions.order_by("order"):
            for item in sessao.exercises.select_related("exercise").order_by("order"):
                sugestao = assistant.sugerir(
                    sessao, assistant.EQUIPAMENTO, item=item
                )
                mudanca = sugestao.mudancas[0] if sugestao.mudancas else None
                if mudanca is None or mudanca.novo_exercicio is None:
                    continue
                if "costuma estar livre" not in mudanca.porque:
                    continue
                with self.subTest(exercicio=mudanca.novo_exercicio.name):
                    self.assertFalse(mudanca.novo_exercicio.disputa_equipamento)
