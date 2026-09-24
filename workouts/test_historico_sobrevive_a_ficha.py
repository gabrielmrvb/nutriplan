# -*- coding: utf-8 -*-
"""Série registrada não some quando a ficha é remontada.

MEDIDO no navegador em 24/09/2026: três séries de supino inclinado
registradas pela execução; equipamento trocado no Perfil para "só o peso do
corpo"; no dia seguinte `sync_active_routine` remonta a ficha, o supino sai
dela — e `/treino/exercicio/12/` passa a responder **404**. As séries
continuavam no banco: só a exportação as mostrava.

A causa era o filtro de `ExercicioView`, que buscava o exercício DENTRO do
plano ativo. O filtro existe por uma razão boa e ela continua valendo (IDOR:
a leitura é da pessoa, não de qualquer id) — o que faltava era a segunda
porta, que é a mais forte das duas: **o exercício em que ESTA pessoa
registrou série é dela**, esteja ele na ficha de hoje ou não.

O 404 continua para o que não é dela: id inexistente, exercício que ela
nunca fez e que não está na ficha dela.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Equipamento
from workouts import services
from workouts.models import Exercise, ExerciseLog, TrainingPlan
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class OExercicioQueSaiuDaFichaContinuaAbrindoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="ficha@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        sessao = services.sessao_do_dia(plano, timezone.localdate())
        self.exercicio = sessao.exercises.first().exercise
        # A série é de ONTEM: com série de hoje a ficha não é remontada
        # ("há série registrada hoje, então a ficha muda amanhã"), e o
        # defeito só aparece depois da remontagem.
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.exercicio,
            date=timezone.localdate() - timedelta(days=1),
            set_number=1, weight_kg=Decimal("60.00"), reps=8,
        )

    def _remontar_sem_o_exercicio(self):
        """A troca de equipamento do relato, pelo caminho do motor."""
        perfil = self.pessoa.profile
        perfil.equipamento = Equipamento.PESO_CORPORAL
        perfil.save(update_fields=["equipamento"])
        services.sync_active_routine(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        na_ficha = {
            i.exercise_id for s in plano.sessions.all() for i in s.exercises.all()
        }
        self.assertNotIn(
            self.exercicio.pk, na_ficha,
            "o fixture precisa de um exercício que a remontagem tire da ficha",
        )

    def test_a_leitura_abre_para_exercicio_fora_da_ficha_com_serie_registrada(self):
        self._remontar_sem_o_exercicio()
        resposta = self.client.get(
            reverse("workouts:exercicio", args=[self.exercicio.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertIn(self.exercicio.name, html)
        self.assertIn("60", html.split('class="data-list historico"', 1)[1])

    def test_a_leitura_avisa_que_o_exercicio_nao_esta_na_ficha_de_hoje(self):
        self._remontar_sem_o_exercicio()
        html = self.client.get(
            reverse("workouts:exercicio", args=[self.exercicio.pk])
        ).content.decode()
        self.assertIn("não está na sua ficha de hoje", html)

    def test_na_ficha_a_leitura_nao_avisa_nada(self):
        """Controle positivo do aviso: quem está na ficha não recebe."""
        html = self.client.get(
            reverse("workouts:exercicio", args=[self.exercicio.pk])
        ).content.decode()
        self.assertNotIn("não está na sua ficha de hoje", html)

    def test_sem_ficha_nenhuma_a_leitura_ainda_abre_o_que_a_pessoa_fez(self):
        """Quem apagou a rotina não perde o que registrou."""
        TrainingPlan.objects.filter(user=self.pessoa).update(is_active=False)
        resposta = self.client.get(
            reverse("workouts:exercicio", args=[self.exercicio.pk])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_exercicio_de_outra_pessoa_continua_404(self):
        """A porta nova é "série DESTA pessoa", e não "qualquer id"."""
        outro = create_user(email="estranho@exemplo.com", weekdays=dias_incluindo_hoje(3))
        services.create_routine(outro)
        alheio = (
            Exercise.objects.filter(logs__isnull=True)
            .exclude(sessions__session__plan__user=self.pessoa)
            .first()
        )
        self.assertIsNotNone(alheio)
        ExerciseLog.objects.create(
            user=outro, exercise=alheio, date=timezone.localdate(),
            set_number=1, weight_kg=Decimal("40.00"), reps=10,
        )
        self.assertEqual(
            self.client.get(reverse("workouts:exercicio", args=[alheio.pk])).status_code,
            404,
        )

    def test_id_inexistente_continua_404(self):
        self.assertEqual(
            self.client.get(reverse("workouts:exercicio", args=[999999])).status_code,
            404,
        )

    def test_sabotagem_apagar_a_serie_fecha_a_porta_de_novo(self):
        """A prova de que é o REGISTRO que abre a página: sem ele, e fora da
        ficha, o exercício volta a ser 404."""
        self._remontar_sem_o_exercicio()
        self.assertEqual(
            self.client.get(reverse("workouts:exercicio", args=[self.exercicio.pk])).status_code,
            200,
        )
        ExerciseLog.objects.filter(user=self.pessoa, exercise=self.exercicio).delete()
        self.assertEqual(
            self.client.get(reverse("workouts:exercicio", args=[self.exercicio.pk])).status_code,
            404,
        )


class OsExerciciosQueJaFizTests(TestCase):
    """A porta para o que saiu da ficha: uma lista de tudo com histórico."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="lista@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        plano = services.get_active_routine(self.pessoa)
        sessao = services.sessao_do_dia(plano, timezone.localdate())
        linhas = list(sessao.exercises.all())
        self.feitos = [linhas[0].exercise, linhas[1].exercise]
        hoje = timezone.localdate()
        for n, exercicio in enumerate(self.feitos):
            for serie in (1, 2):
                ExerciseLog.objects.create(
                    user=self.pessoa, exercise=exercicio, date=hoje - timedelta(days=n),
                    set_number=serie, weight_kg=Decimal("50.00"), reps=10,
                )

    def test_a_lista_traz_todo_exercicio_com_serie_e_so_eles(self):
        html = self.client.get(reverse("workouts:exercicios_feitos")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        for exercicio in self.feitos:
            self.assertIn(exercicio.name, corpo)
        nunca_feito = (
            Exercise.objects.filter(is_active=True)
            .exclude(pk__in=[e.pk for e in self.feitos])
            .first()
        )
        self.assertNotIn(nunca_feito.name, corpo)

    def test_cada_linha_leva_a_leitura_do_exercicio(self):
        html = self.client.get(reverse("workouts:exercicios_feitos")).content.decode()
        for exercicio in self.feitos:
            self.assertIn(
                reverse("workouts:exercicio", args=[exercicio.pk]), html
            )

    def test_a_lista_diz_quantas_series_e_quando_foi_a_ultima(self):
        html = self.client.get(reverse("workouts:exercicios_feitos")).content.decode()
        corpo = html.split("<main", 1)[1].split("</main>", 1)[0]
        self.assertIn("2 séries", corpo)

    def test_a_lista_e_de_quem_pede(self):
        """Série de outra pessoa não entra — a lista é do histórico DELA."""
        outro = create_user(email="outro@exemplo.com", weekdays=dias_incluindo_hoje(3))
        services.create_routine(outro)
        alheio = (
            Exercise.objects.filter(is_active=True)
            .exclude(pk__in=[e.pk for e in self.feitos])
            .first()
        )
        ExerciseLog.objects.create(
            user=outro, exercise=alheio, date=timezone.localdate(),
            set_number=1, weight_kg=Decimal("30.00"), reps=10,
        )
        corpo = (
            self.client.get(reverse("workouts:exercicios_feitos"))
            .content.decode().split("<main", 1)[1].split("</main>", 1)[0]
        )
        self.assertNotIn(alheio.name, corpo)

    def test_quem_nunca_registrou_nada_ve_o_convite_e_nao_uma_tabela_vazia(self):
        ExerciseLog.objects.filter(user=self.pessoa).delete()
        corpo = (
            self.client.get(reverse("workouts:exercicios_feitos"))
            .content.decode().split("<main", 1)[1].split("</main>", 1)[0]
        )
        self.assertIn("empty-state", corpo)

    def test_a_lista_exige_sessao(self):
        self.client.logout()
        resposta = self.client.get(reverse("workouts:exercicios_feitos"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/entrar/", resposta["Location"])
