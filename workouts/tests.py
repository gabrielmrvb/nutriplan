"""Testes da rotina de treino.

O que interessa cobrir aqui é a regra de treinamento, não o CRUD: a divisão
escolhida bate com a frequência, o ciclo repete quando a pessoa treina mais
dias do que a divisão tem letras, e a ficha acompanha quando a rotina muda.
"""
from datetime import date, time, timedelta
from decimal import Decimal
import re
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

from workouts import health_export
from accounts.models import (
    ONBOARDING_DONE,
    ActivityLevel,
    SplitPreference,
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
    WorkoutTemplateItem,
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
        onboarding_step=ONBOARDING_DONE,
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
    # Todas as cinco são oferecidas agora: a preferência por grupos por dia
    # trouxe ABCD e ABCDE de volta, e o que era peso morto no catálogo virou a
    # resposta de "1 grupo por dia" e "2 grupos por dia".
    OFERECIDAS = (Split.FULL, Split.AB, Split.ABC, Split.ABCD, Split.ABCDE)

    def test_every_offered_split_is_in_the_catalog(self):
        for split in self.OFERECIDAS:
            with self.subTest(split=split):
                self.assertTrue(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).exists()
                )

    def test_the_four_and_five_day_splits_are_back_in_the_catalog(self):
        """ABCD e ABCDE voltaram, e a reversão é deliberada.

        Elas foram aposentadas quando a divisão era escolhida SÓ pela
        frequência: com uma resposta por número de dias, ABC cobria de três
        dias para cima e as outras duas eram peso morto no catálogo.

        Com a preferência por grupos por dia elas passam a ser a resposta de
        duas perguntas que ABC não responde: "1 grupo por dia" precisa de cinco
        dias, e "2 grupos por dia" precisa de quatro. Sem elas, as duas opções
        da tela apontariam para um catálogo vazio — `templates_for()` devolve
        lista vazia e `build_sessions` divide pelo tamanho dela.
        """
        for split, dias in ((Split.ABCD, 4), (Split.ABCDE, 5)):
            with self.subTest(split=split):
                self.assertEqual(
                    WorkoutTemplate.objects.filter(split=split, is_active=True).count(),
                    dias,
                )

    def test_each_split_has_the_days_its_name_promises(self):
        esperado = {
            Split.FULL: 1,
            Split.AB: 2,
            Split.ABC: 3,
            Split.ABCD: 4,
            Split.ABCDE: 5,
        }
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
            # O composto continua descansando MAIS que o isolado — 80s contra
            # 60 —, mas a régua caiu de 90 para 80.
            #
            # Foi pedido: o descanso padrão do app passou para a faixa de 1:00
            # a 1:20. É uma decisão de treino, não de tela, e vale registrar o
            # que ela troca: com 3 minutos entre séries pesadas se completa
            # mais repetição na mesma carga, que é o que constrói força. Com
            # 80s a sessão fica muito mais curta e mais densa. São dois estilos
            # legítimos, e este app agora prescreve o segundo.
            for item in items:
                if item.exercise.is_compound:
                    self.assertGreaterEqual(item.rest_seconds, 80, str(item.exercise))
                else:
                    self.assertGreaterEqual(item.rest_seconds, 60, str(item.exercise))
                self.assertLessEqual(item.rest_seconds, 80, str(item.exercise))

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

        self.assertContains(response, "Ver vídeo de execução")
        self.assertContains(response, "youtube-nocookie.com/embed/")

    def test_the_button_does_not_promise_a_video_that_is_missing(self):
        """O rótulo diz "vídeo": todo exercício ativo precisa ter um.

        Um botão que abre um drawer vazio é pior do que botão nenhum — a
        pessoa toca, não acontece nada, e passa a desconfiar dos outros.
        """
        sem_clipe = [
            exercicio.name
            for exercicio in Exercise.objects.filter(is_active=True)
            if not exercicio.video_embed_url
        ]
        self.assertEqual(sem_clipe, [])

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
        # Um cronômetro por EXERCÍCIO.
        #
        # Era um por série, quando cada série tinha a própria linha. Com o
        # registro único, o botão é um só — e o descanso continua sendo entre
        # séries: ele é tocado a cada uma, no mesmo lugar.
        self.assertEqual(corpo.count('data-descanso="'), len(exercicios))
        for item in exercicios:
            with self.subTest(exercicio=item.exercise.name):
                self.assertIn(f'data-descanso="{item.rest_seconds}"', corpo)

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
        # Ancorado na CLASSE, e nao em `<summary` cru: o exercicio virou
        # sanfona depois desta ficha, e a contagem crua passou a somar as duas.
        self.assertEqual(html.count("ficha__resumo"), plano.sessions.count())

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
        # Um registro por exercício, e não uma linha por série: as quatro
        # linhas empilhadas viraram um formulário só.
        self.assertEqual(html.count('class="registro"'), total)

    def test_opening_one_closes_the_others(self):
        """`<details name>` faria isso nativamente, mas só em navegador
        recente — e este projeto já perdeu a barra de navegação por confiar num
        recurso novo. O JS cobre todo mundo."""
        html = self._pagina()
        self.assertIn('addEventListener("toggle"', html)
        self.assertIn("[data-ficha][open]", html)
        self.assertIn("outra.open = false", html)


class ExerciseAccordionTests(TestCase):
    """A segunda sanfona: os exercícios dentro da ficha aberta.

    A sanfona da semana resolveu a rolagem ENTRE treinos e deixou intacta a de
    dentro. A ficha de hoje abre com sete exercícios abertos; cada cartão traz
    a instrução, o botão de execução e uma tabela de três a quatro séries com
    campo de carga, campo de repetição e dois botões por linha. Medido nesta
    tela, a ficha aberta sozinha passa de 3.000 px — e a pessoa está em pé,
    entre séries, procurando UM exercício.

    Fechados, os sete cabem na tela de uma vez: dá para ver o treino inteiro
    sem rolar e abrir só aquele em que se vai anotar.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user(email="acordeao@exemplo.com", weekdays=(0, 1, 2, 3, 4))
        self.plano = services.create_routine(self.user)
        self.client.force_login(self.user)
        self.html = self.client.get(reverse("workouts:routine")).content.decode()

    def _total_de_exercicios(self):
        return sum(s.exercises.count() for s in self.plano.sessions.all())

    def test_every_exercise_is_a_native_disclosure(self):
        """`<details>` e não `<div>` com JavaScript, pela mesma razão da ficha.

        Abre por teclado, anuncia o estado para leitor de tela, responde ao
        Ctrl+F do navegador e funciona antes de o JavaScript carregar — numa
        academia com sinal ruim, esse último item não é detalhe.
        """
        total = self._total_de_exercicios()
        self.assertEqual(self.html.count('<details class="exercise"'), total)
        self.assertEqual(self.html.count('<summary class="exercise__head"'), total)

    def test_every_exercise_starts_minimised(self):
        """Nenhum aberto: a ficha abre mostrando o treino inteiro de uma vez.

        Sete cabeçalhos fechados cabem numa tela; um só aberto já empurra os
        outros seis para fora dela. Como a pessoa chega aqui para anotar UM
        exercício de cada vez, abrir qualquer um por antecipação é apostar em
        qual — e errar a aposta custa exatamente a rolagem que a sanfona veio
        tirar.
        """
        self.assertNotIn("data-exercicio open", self.html)

    def test_the_collapsed_header_says_enough_to_choose_without_opening(self):
        """Fechado, o cartão ainda responde "é este?".

        Número, nome e as três etiquetas — músculo, séries × repetições e
        descanso. Sem elas a sanfona troca rolagem por toque às cegas, que é
        pior: a pessoa abre três cartões para achar o que queria.
        """
        cabecalho = self.html.split('<summary class="exercise__head"', 1)[1]
        cabecalho = cabecalho.split("</summary>", 1)[0]

        item = self.plano.sessions.first().exercises.first()

        self.assertIn("exercise__order", cabecalho)
        self.assertIn(item.exercise.name, cabecalho)
        self.assertIn(item.exercise.get_muscle_group_display(), cabecalho)
        self.assertIn(item.rep_range, cabecalho)
        self.assertIn("descanso", cabecalho)
        # E a seta, que é o que diz que aquilo abre.
        self.assertIn("exercise__seta", cabecalho)

    def test_the_sets_are_in_the_page_even_when_collapsed(self):
        """O HTML continua inteiro — a sanfona economiza layout, não download.

        Vale o mesmo motivo da ficha: buscar o registro por rede ao abrir o
        exercício faria a academia com sinal ruim virar problema de produto. E é
        o que mantém o Ctrl+F do navegador achando o exercício que está fechado.

        Conta REGISTROS e não linhas de série: as quatro linhas por exercício
        viraram um formulário só.
        """
        total = self._total_de_exercicios()

        corpo = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertEqual(corpo.count('class="registro"'), total)

    def test_landing_on_an_exercise_anchor_opens_it(self):
        """Sem isto, salvar carga sem JavaScript parece não ter salvado.

        `record_load` responde JSON para quem chegou por `fetch`, mas o
        caminho sem JavaScript continua existindo e termina em
        `redirect(... + "#exercicio-<pk>")` — a âncora que devolve a pessoa ao
        exercício em vez de jogá-la no topo da página.

        Com o cartão fechado por padrão, essa âncora entrega um cartão
        FECHADO: a carga foi para o banco e a tela não mostra nada. É
        indistinguível de erro, e a resposta é tocar de novo.
        """
        self.assertIn("abrirPeloEndereco", self.html)
        self.assertIn("location.hash", self.html)
        self.assertIn('addEventListener("hashchange"', self.html)

    def test_the_chevron_turns_when_the_exercise_opens(self):
        """A seta é o estado. Sem ela virar, fechado e aberto ficam iguais no
        cabeçalho, e o único aviso de que abriu é o conteúdo aparecer — que é
        justamente o que sai da tela quando se fecha."""
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        bloco = css.split(".exercise[open] > .exercise__head .exercise__seta", 1)
        self.assertEqual(len(bloco), 2, "a seta do exercício não gira ao abrir")
        self.assertIn("rotate(180deg)", bloco[1].split("}", 1)[0])

    def test_the_execution_button_rides_with_the_badges(self):
        """O botão de vídeo mora no cabeçalho, junto das etiquetas.

        Fechado, o cartão passou a esconder o botão — e ver o movimento é
        justamente o que se quer ANTES de decidir abrir e anotar. No cabeçalho
        ele fica a um toque em qualquer estado.

        Um `<button>` dentro de `<summary>` é HTML válido, mas o toque nele
        alternaria a sanfona junto — por isso o handler do drawer precisa
        cortar o comportamento padrão.
        """
        cabecalho = self.html.split('<summary class="exercise__head"', 1)[1]
        cabecalho = cabecalho.split("</summary>", 1)[0]
        self.assertIn("exercise__ver", cabecalho)

        # E o toque não pode abrir a sanfona junto com o drawer.
        handler = self.html.split('closest("[data-clipe]")', 1)[1].split("});", 1)[0]
        self.assertIn("preventDefault", handler)

    def test_opening_one_exercise_closes_the_others(self):
        """Seleção única, como na ficha da semana: só o exercício da vez fica
        aberto.

        É o que mantém a promessa da sanfona depois do primeiro toque. Sem
        fechar o anterior, abrir três exercícios ao longo do treino devolve a
        página comprida que a sanfona veio resolver — e a pessoa não fecha
        manualmente, porque está no meio de uma série.
        """
        self.assertIn("[data-exercicio][open]", self.html)
        self.assertIn("outro.open = false", self.html)


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












# ==========================================================================
# Repetições, cronômetro automático e exportação
# ==========================================================================



class HealthExportTests(TestCase):
    """A camada de exportação para o app Saúde.

    Uma PWA não escreve no HealthKit — não existe API web, e o Health Connect
    é igual. O que dá para entregar é o cálculo e um arquivo que os
    importadores leem, e é isso que está testado aqui.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.plan = services.create_routine(self.user)
        self.exercicio = Exercise.objects.filter(is_active=True).first()
        self.hoje = timezone.localdate()
        self.client.force_login(self.user)

    def _serie(self, numero, carga="60", reps=10):
        ExerciseLog.objects.create(
            user=self.user,
            exercise=self.exercicio,
            date=self.hoje,
            set_number=numero,
            weight_kg=Decimal(carga),
            reps=reps,
        )

    def test_a_day_with_nothing_logged_exports_nothing(self):
        resumo = health_export.resumo_da_sessao(self.user)

        self.assertFalse(resumo.tem_dados)
        self.assertEqual(resumo.kcal, 0)

    def test_the_volume_is_sets_times_reps_times_load(self):
        for i in (1, 2, 3):
            self._serie(i)

        resumo = health_export.resumo_da_sessao(self.user)

        self.assertEqual(resumo.volume_kg, Decimal("1800"))
        self.assertEqual(resumo.series, 3)
        self.assertEqual(resumo.exercicios, 1)

    def test_the_duration_counts_the_rest_between_sets(self):
        """Sem contar o descanso, um treino de uma hora exportaria como dezoito
        minutos — e o app de saúde registraria um treino que não aconteceu."""
        for i in range(1, 6):
            self._serie(i)

        resumo = health_export.resumo_da_sessao(self.user)

        # Cinco séries de 40s são 3,3 minutos; com descanso, muito mais.
        self.assertGreater(resumo.minutos, 4)

    def test_the_calorie_estimate_errs_low_on_purpose(self):
        """MET 3,5 e não 6,0. A fórmula trata a hora inteira como esforço
        contínuo, quando metade dela é descanso — é a mesma decisão já tomada
        no cálculo do TDEE deste app."""
        for i in range(1, 10):
            self._serie(i)

        resumo = health_export.resumo_da_sessao(self.user)

        # Um treino de ~20 min a 82,4 kg não passa de 150 kcal com MET 3,5.
        self.assertGreater(resumo.kcal, 0)
        self.assertLess(resumo.kcal, resumo.minutos * 10)

    def test_without_a_weight_it_does_not_invent_a_calorie_number(self):
        WeightEntry.objects.filter(user=self.user).delete()
        self._serie(1)

        resumo = health_export.resumo_da_sessao(self.user)

        self.assertEqual(resumo.kcal, 0)
        self.assertTrue(resumo.tem_dados)

    def test_the_tcx_carries_duration_and_calories(self):
        for i in (1, 2, 3):
            self._serie(i)
        resumo = health_export.resumo_da_sessao(self.user)

        xml = health_export.tcx(resumo)

        self.assertIn("<TotalTimeSeconds>", xml)
        self.assertIn(f"<Calories>{resumo.kcal}</Calories>", xml)
        self.assertIn('Sport="Other"', xml)

    def test_the_tcx_refuses_to_invent_a_session(self):
        resumo = health_export.resumo_da_sessao(self.user)
        with self.assertRaises(ValueError):
            health_export.tcx(resumo)

    def test_the_download_arrives_as_a_file(self):
        self._serie(1)

        resposta = self.client.get(reverse("workouts:health_export"))

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])
        self.assertIn(".tcx", resposta["Content-Disposition"])

    def test_nothing_to_export_sends_the_person_back(self):
        resposta = self.client.get(reverse("workouts:health_export"))
        self.assertEqual(resposta.status_code, 302)

    def test_one_person_never_exports_anothers_workout(self):
        outro = create_user(email="outro@exemplo.com")
        ExerciseLog.objects.create(
            user=outro, exercise=self.exercicio, date=self.hoje,
            set_number=1, weight_kg=Decimal("100"), reps=10,
        )

        resumo = health_export.resumo_da_sessao(self.user)

        self.assertFalse(resumo.tem_dados)

    def test_the_screen_says_the_browser_cannot_write_to_health(self):
        """Prometer sincronização direta com o Apple Saúde seria mentira, e a
        tela precisa desmentir antes de a pessoa procurar o botão que não
        existe."""
        self._serie(1)
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn("Nenhum navegador escreve direto", html)


class ShareCardTests(TestCase):
    """O card de compartilhamento, desenhado no aparelho."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        services.create_routine(self.user)
        self.client.force_login(self.user)

    def _serie(self):
        ExerciseLog.objects.create(
            user=self.user,
            exercise=Exercise.objects.filter(is_active=True).first(),
            date=timezone.localdate(),
            set_number=1,
            weight_kg=Decimal("80"),
            reps=10,
        )

    def test_nothing_logged_means_no_summary_card(self):
        """Um card de resumo vazio em cima da ficha é ruído no dia em que a
        pessoa ainda não começou."""
        html = self.client.get(reverse("workouts:routine")).content.decode()
        # A âncora é a classe da seção, e não um atributo `data-`: TODOS os
        # atributos deste card aparecem também no <script> que os lê, e o
        # script renderiza sempre. Errei nisso duas vezes seguidas — o seletor
        # do JavaScript e o marcador do HTML são a mesma string.
        self.assertNotIn('class="card resumo"', html)
        self.assertNotIn("Treino de hoje", html)

    def test_the_card_carries_the_numbers_the_canvas_draws(self):
        self._serie()

        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn('class="card resumo"', html)
        self.assertIn("Treino de hoje", html)
        for atributo in ("data-volume", "data-series", "data-minutos",
                         "data-exercicios", "data-kcal", "data-data"):
            with self.subTest(atributo=atributo):
                self.assertIn(atributo, html)

    def test_it_shares_natively_when_it_can_and_downloads_when_it_cannot(self):
        self._serie()
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn("navigator.canShare", html)
        self.assertIn("navigator", html)
        self.assertIn('link.download = "treino-nutriplan.png"', html)

    def test_the_canvas_uses_a_format_instagram_does_not_crop(self):
        self._serie()
        html = self.client.get(reverse("workouts:routine")).content.decode()

        self.assertIn("c.width = 1080", html)
        self.assertIn("c.height = 1350", html)


class ImpeccableStyleTests(TestCase):
    """As regras do catálogo Impeccable 3.6.0 que dá para checar no CSS.

    O motor deles é JavaScript e exige Node 22.18+, que não está instalado
    aqui. As definições vieram no pacote publicado e são estas — travadas
    para não regredirem.
    """

    def setUp(self):
        self.css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )
        self.linhas = self.css.splitlines()

    def test_no_interface_text_falls_below_eleven_pixels(self):
        """`undersized-ui-text`: abaixo de 11px é falha de legibilidade, não
        escolha de estilo. Havia onze lugares, um deles a 9px."""
        pequenos = []
        for i, linha in enumerate(self.linhas, 1):
            achado = re.search(r"font-size:\s*\.(\d+)rem", linha)
            if not achado:
                continue
            rem = float("0." + achado.group(1))
            if rem < 0.6875:
                pequenos.append(f"linha {i}: {rem}rem = {rem * 16:.0f}px")
        self.assertEqual(pequenos, [], f"texto abaixo de 11px: {pequenos}")

    def test_no_decorative_colour_glow_at_rest(self):
        """`dark-glow`: halo cromático de deslocamento zero num fundo escuro é
        o visual padrão de UI gerada por IA. O brilho de FOCO fica — ali ele é
        a informação, não o enfeite."""
        self.assertNotIn("--glow-brand", self.css)

        bloco = self.css.split(chr(10) + ".btn--primary {", 1)[1].split("}", 1)[0]
        self.assertNotIn("box-shadow", bloco)

    def test_the_focus_glow_survives_because_it_carries_meaning(self):
        self.assertIn(".field-input:focus", self.css)
        foco = self.css.split(".field-input:focus", 1)[1].split("}", 1)[0]
        self.assertIn("var(--glow)", foco)

    def test_the_streak_flame_does_not_pulse_forever(self):
        """`pulsing-dot`: pulso decorativo simula vivacidade. Uma sequência
        muda uma vez por dia — o esqueleto de carregamento mantém o dele,
        porque ali há mesmo algo acontecendo."""
        bloco = self.css.split(".ofensiva__chama.is-viva", 1)[1].split("}", 1)[0]
        self.assertNotIn("animation", bloco)

        self.assertIn("animation: pulso", self.css)

    def test_no_css_variable_is_declared_and_never_used(self):
        """`--glow-brand` ficou órfão quando os halos saíram. Token que ninguém
        usa é token que o próximo leitor tenta entender à toa."""
        declaradas = set(re.findall(r"^\s*(--[\w-]+):", self.css, re.M))
        usadas = set(re.findall(r"var\(\s*(--[\w-]+)", self.css))
        # `--dia` é escrito pelo atributo do elemento, não pelo CSS.
        orfas = sorted(declaradas - usadas - {"--dia"})
        self.assertEqual(orfas, [], f"tokens declarados e nunca usados: {orfas}")

# ==========================================================================
# Redesign da linha de série
# ==========================================================================



class ExerciseHeaderLayoutTests(TestCase):
    """O cabeçalho do exercício, medido em vez de conferido no olho.

    Os três defeitos desta rodada tinham a mesma forma: a regra de CSS
    continuou descrevendo um elemento que o HTML deixou de ser. O botão de
    execução virou ícone redondo de 44px numa versão, ganhou rótulo de 24
    caracteres na seguinte, e a regra `width: 2.75rem; border-radius: 50%`
    ficou — o texto quebrou em SETE linhas de uma palavra dentro do círculo e
    o cabeçalho inchou de 98px para 364px por cartão.

    Nada disso quebra teste de conteúdo: o rótulo está no HTML, o botão
    responde ao clique, a página devolve 200. Só se vê olhando, e foi assim
    que ficou meses errado.
    """

    url = reverse("workouts:routine")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.user = create_user()
        self.client.force_login(self.user)
        self.css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

    def _regra(self, seletor):
        """TODOS os corpos de regra daquele seletor, juntos.

        Ler só o primeiro bloco é a armadilha recorrente deste repositório:
        `.exercise__tags` aparece duas vezes — uma para a área da grade, outra
        para o flex — e um `split(marca, 1)` devolve a primeira e afirma com
        segurança que a declaração da segunda não existe.
        """
        marca = chr(10) + seletor + " {"
        self.assertIn(marca, self.css, f"regra ausente: {seletor}")
        return "".join(t.split("}", 1)[0] for t in self.css.split(marca)[1:])

    def test_the_execution_button_has_no_fixed_width_to_squeeze_its_label(self):
        """Largura fixa num botão com rótulo é o defeito, não o sintoma.

        44px de largura para um rótulo de vinte e um caracteres não corta o texto nem
        provoca overflow — o navegador quebra palavra por palavra e cresce
        para baixo, em silêncio. Por isso a trava é na REGRA: enquanto o botão
        tiver rótulo, quem mede a largura dele é o conteúdo.
        """
        regra = self._regra(".exercise__head .exercise__ver")

        self.assertNotIn("width:", regra.replace("min-width", ""))
        self.assertNotIn("border-radius: 50%", regra)
        # O alvo de 44px continua vindo da altura, que é o que a régua mede.
        self.assertIn("min-height: 2.75rem", regra)

    def test_the_execution_label_stays_on_one_line(self):
        """`nowrap` é o que faz o rótulo DESCER inteiro em vez de quebrar.

        Sem ele, num cartão estreito o flex encolhe o botão até caber e o
        texto volta a empilhar — o mesmo defeito, só que mais tarde.
        """
        self.assertIn("white-space: nowrap", self._regra(".exercise__head .exercise__ver"))

    def test_the_button_shares_the_tag_row_instead_of_owning_a_column(self):
        """Ele é irmão das pílulas no HTML; a grade não reserva coluna para ele."""
        html = self.client.get(self.url).content.decode()

        etiquetas = html.split('class="exercise__tags"', 1)[1].split("</span>\n" + " " * 22 + "</span>", 1)[0]
        self.assertIn("exercise__ver", etiquetas)

        self.assertNotIn('"ordem nome ver seta"', self.css)
        self.assertNotIn("grid-area: ver", self.css)

    def test_the_tag_row_centres_its_items_so_the_pills_keep_their_height(self):
        """Com um alvo de 44px na fileira, o `stretch` padrão esticaria as
        pílulas de 24px para 44 e o texto delas boiaria no meio."""
        self.assertIn("align-items: center", self._regra(".exercise__tags"))

    def test_the_icon_shows_a_camera_and_not_a_list_of_lines(self):
        """Ícone e rótulo têm que prometer a MESMA coisa.

        O ícone anterior desenhava três linhas de texto — uma lista — enquanto
        `drawer__media` fica acima de `drawer__corpo` e a primeira coisa que
        aparece é o clipe. O desenho prometia a segunda tela.
        """
        html = self.client.get(self.url).content.decode()
        botao = html.split('class="exercise__ver"', 1)[1].split("</button>", 1)[0]

        self.assertIn("<rect", botao)
        # As três linhas do ícone de lista, exatamente como estavam.
        self.assertNotIn('d="M4 6h11"', botao)

    def test_the_label_reads_the_same_by_eye_and_by_ear(self):
        """O `aria-label` não pode contar outra história: quem ouve a tela
        recebe o mesmo verbo e o mesmo objeto, mais o nome do exercício."""
        html = self.client.get(self.url).content.decode()
        botao = html.split('class="exercise__ver"', 1)[1].split("</button>", 1)[0]

        self.assertIn("aria-label=\"Ver vídeo de execução de ", botao)
        self.assertIn("<span>Ver vídeo de execução</span>", botao)

    def test_every_header_element_has_a_grid_area(self):
        """Item de grade sem área nomeada não some: ele vai para uma faixa
        implícita, fora do desenho. Foi onde a prescrição estava."""
        areas = self.css.split("grid-template-areas:", 1)[1].split(";", 1)[0]
        for nome in ("ordem", "nome", "presc", "tags", "seta"):
            self.assertIn(nome, areas)
        self.assertIn(".exercise__prescricao { grid-area: presc; }", self.css)


class RestBadgeTests(TestCase):
    """O descanso escrito como num relógio.

    "1min20" na etiqueta lia como erro de digitação, e o número está certo: a
    prescrição desceu de 3 min para a faixa de 1:00 a 1:20. Era a notação que
    estava errada, não o dado.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_a_rest_with_seconds_reads_as_a_clock(self):
        self.assertEqual(SessionExercise(rest_seconds=80).rest_display, "1:20 min")
        self.assertEqual(SessionExercise(rest_seconds=90).rest_display, "1:30 min")

    def test_a_whole_minute_drops_the_seconds(self):
        self.assertEqual(SessionExercise(rest_seconds=60).rest_display, "1 min")
        self.assertEqual(SessionExercise(rest_seconds=120).rest_display, "2 min")

    def test_under_a_minute_stays_in_seconds(self):
        self.assertEqual(SessionExercise(rest_seconds=45).rest_display, "45s")

    def test_no_prescription_still_asks_for_three_minutes_between_sets(self):
        """A faixa prescrita é 1:00 a 1:20. Descanso longo tem lugar em
        movimento pesado, mas era o padrão de TODO exercício — e três minutos
        entre séries de rosca direta é o treino durando o dobro sem entregar
        nada em troca."""
        longos = {
            item.rest_seconds
            for item in WorkoutTemplateItem.objects.all()
            if item.rest_seconds > 120
        }
        self.assertEqual(longos, set())


class SplitPreferenceTests(TestCase):
    """A preferência escolhe DENTRO do que a frequência comporta.

    O risco desta funcionalidade não é a preferência ser ignorada — é ela ser
    obedecida demais. Uma divisão de três dias com duas sessões por semana
    deixa um terço do corpo sem treinar nenhuma vez, porque a terceira letra
    nunca chega. A pessoa escolheu "poucos grupos por dia" e recebeu "perna
    nunca".
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def test_without_a_preference_nothing_changes(self):
        """O caminho de quem tem plano anterior à pergunta existir. Se esta
        coluna mudar, todo plano ativo é descartado por `plan_is_current` e
        remontado — e a pessoa perde a ficha ajustada à mão."""
        self.assertEqual(services.split_for(1), Split.FULL)
        self.assertEqual(services.split_for(2), Split.AB)
        for dias in range(3, 8):
            with self.subTest(dias=dias):
                self.assertEqual(services.split_for(dias), Split.ABC)

    def test_the_default_preference_reproduces_the_old_behaviour(self):
        """TRES é o padrão do campo justamente por isto: a migração não pode
        reescrever o plano — nem a ficha ajustada à mão — de quem nunca viu a
        pergunta."""
        for dias in range(1, 8):
            with self.subTest(dias=dias):
                self.assertEqual(
                    services.split_for(dias, SplitPreference.TRES),
                    services.split_for(dias),
                )

    def test_wanting_one_group_a_day_cannot_invent_training_days(self):
        """Um grupo por dia precisa de cinco dias. Com menos, desce para a
        divisão mais próxima que FECHA na semana — pedir cinco letras com duas
        sessões deixaria três quintos do corpo sem treinar nenhuma vez."""
        esperado = {1: Split.FULL, 2: Split.AB, 3: Split.ABC, 4: Split.ABCD,
                    5: Split.ABCDE, 6: Split.ABCDE, 7: Split.ABCDE}
        for dias, divisao in esperado.items():
            with self.subTest(dias=dias):
                self.assertEqual(services.split_for(dias, SplitPreference.UM), divisao)

    def test_two_groups_a_day_tops_out_at_the_four_day_split(self):
        """Aqui a preferência VENCE a frequência: quem treina cinco ou seis
        vezes e pede dois grupos por dia continua no ABCD, e o ciclo repete —
        A, B, C, D, A. É escolha legítima de treino, e é o ponto da tela."""
        for dias in range(4, 8):
            with self.subTest(dias=dias):
                self.assertEqual(services.split_for(dias, SplitPreference.DOIS), Split.ABCD)
        self.assertEqual(services.split_for(3, SplitPreference.DOIS), Split.ABC)
        self.assertEqual(services.split_for(1, SplitPreference.DOIS), Split.FULL)

    def test_three_groups_a_day_is_the_abc_from_three_days_up(self):
        for dias in range(3, 8):
            with self.subTest(dias=dias):
                self.assertEqual(services.split_for(dias, SplitPreference.TRES), Split.ABC)

    def test_the_secondary_muscles_never_get_a_day_of_their_own(self):
        """Trapézio, antebraço, panturrilha e abdômen entram nos acoplamentos.

        É a regra que faz a contagem da tela ser verdade: um dia rotulado "2
        grupos" que na prática treina peito, tríceps E abdômen continua sendo
        dois grupos principais. O que não pode acontecer é um deles virar o
        assunto de um dia inteiro — aí a contagem mente.
        """
        secundarios = {
            MuscleGroup.TRAPS,
            MuscleGroup.FOREARMS,
            MuscleGroup.CALVES,
            MuscleGroup.CORE,
        }
        for template in WorkoutTemplate.objects.filter(
            split__in=(Split.ABCD, Split.ABCDE), is_active=True
        ):
            grupos = {item.exercise.muscle_group for item in template.items.all()}
            with self.subTest(treino=str(template)):
                self.assertTrue(
                    grupos - secundarios,
                    f"{template} só treina músculo secundário",
                )

    def test_every_split_the_preference_can_produce_exists_in_the_catalog(self):
        """A trava que faltava.

        `Split` tem cinco valores e o catálogo tem três — ABCD e ABCDE estão no
        enum porque fichas antigas apontam para elas, e não têm template ativo.
        Uma preferência apontando para uma delas devolveria lista vazia de
        templates, e `build_sessions` divide pelo tamanho dessa lista:
        ZeroDivisionError no meio do onboarding.
        """
        for preferencia in SplitPreference.values:
            for dias in range(1, 8):
                divisao = services.split_for(dias, preferencia)
                with self.subTest(preferencia=preferencia, dias=dias):
                    self.assertTrue(
                        WorkoutTemplate.objects.filter(
                            split=divisao, is_active=True
                        ).exists(),
                        f"{preferencia} com {dias} dia(s) pede {divisao}, "
                        "que não existe no catálogo",
                    )

    def test_an_unknown_preference_falls_back_instead_of_crashing(self):
        """Valor fora do enum chega de banco antigo ou de POST forjado. A
        resposta é a tabela por frequência, não uma exceção."""
        self.assertEqual(services.split_for(3, "seja-la-o-que-for"), Split.ABC)
