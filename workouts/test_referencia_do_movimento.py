# -*- coding: utf-8 -*-
"""A referência do MOVIMENTO na execução (auditoria de 20/09/2026, upgrade 4).

Conferido no banco da semana simulada: a opção 1 e a opção 2 da mesma letra
não têm NENHUM exercício em comum, então um exercício só repete de duas em
duas semanas — e "última carga", SUBIR/MANTER e recorde ficam mudos por 14
dias. Quando o exercício em foco não tem histórico próprio, a execução
conta o que a pessoa fez no mesmo `padrao` ("Primeira vez neste. Na última
pressão de peito (supino reto com barra, 21/09): 20 kg × 10"). É dica, não
número no campo: barra e máquina não pesam igual.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import Exercise, ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje, sem_scripts


class AReferenciaDoMovimentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="movimento@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )
        # Outro exercício ATIVO do mesmo padrão e grupo — o que a outra opção
        # da letra teria no lugar deste.
        self.irmao = (
            Exercise.objects.filter(is_active=True, padrao=self.item.exercise.padrao)
            .exclude(pk=self.item.exercise_id).order_by("pk").first()
        )
        self.assertIsNotNone(self.irmao, "o catálogo tem de ter dois exercícios do padrão %s" % self.item.exercise.padrao)

    def _html(self):
        return sem_scripts(self.client.get(
            "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        ).content.decode())

    def _fez_o_irmao(self, dias_atras=3, peso="20", reps=10):
        for n in (1, 2, 3):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.irmao, date=self.hoje - timedelta(days=dias_atras),
                set_number=n, weight_kg=Decimal(peso), reps=reps,
            )

    def test_sem_historico_do_padrao_a_tela_nao_inventa_referencia(self):
        html = self._html()
        self.assertNotIn("Primeira vez neste", html)
        self.assertNotIn("agora__anterior", html)

    def test_sem_historico_proprio_a_tela_conta_a_ultima_vez_do_movimento(self):
        self._fez_o_irmao(dias_atras=3, peso="22.5", reps=9)
        html = self._html()
        self.assertIn("Primeira vez neste", html)
        trecho = html.split("Primeira vez neste", 1)[1].split("</p>", 1)[0]
        self.assertIn(self.item.exercise.get_padrao_display(), trecho)
        self.assertIn(self.irmao.name.lower(), trecho)
        self.assertIn("22,50 kg", trecho)  # `floatformat:-2`, como toda carga desta tela
        self.assertIn("× 9", trecho)
        self.assertIn((self.hoje - timedelta(days=3)).strftime("%d/%m"), trecho)
        # É dica: o campo de carga continua em branco.
        import re

        self.assertEqual(re.search(r'name="weight_kg"[^>]*value="([^"]*)"', html).group(1), "")

    def test_com_historico_proprio_a_referencia_e_a_de_sempre(self):
        self._fez_o_irmao()
        for n in (1, 2, 3):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=7),
                set_number=n, weight_kg=Decimal("60"), reps=8,
            )
        html = self._html()
        self.assertNotIn("Primeira vez neste", html)
        self.assertIn("Última carga", html)

    def test_a_referencia_custa_uma_consulta_e_so_quando_falta_historico(self):
        """Uma consulta a mais, só neste caso; com histórico próprio, zero."""
        url = "%s?exercicio=%d" % (reverse("workouts:now"), self.item.exercise_id)
        self.client.get(url)
        with CaptureQueriesContext(connection) as sem:
            self.client.get(url)
        self._fez_o_irmao()
        with CaptureQueriesContext(connection) as com_irmao:
            self.client.get(url)
        self.assertEqual(len(com_irmao.captured_queries), len(sem.captured_queries))
        for n in (1, 2, 3):
            ExerciseLog.objects.create(
                user=self.pessoa, exercise=self.item.exercise, date=self.hoje - timedelta(days=7),
                set_number=n, weight_kg=Decimal("60"), reps=8,
            )
        with CaptureQueriesContext(connection) as com_proprio:
            self.client.get(url)
        self.assertEqual(len(com_proprio.captured_queries), len(sem.captured_queries) - 1)

    def test_a_referencia_e_a_serie_mais_recente_e_mais_pesada_do_padrao(self):
        self._fez_o_irmao(dias_atras=10, peso="30", reps=8)
        self._fez_o_irmao(dias_atras=2, peso="25", reps=10)
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.irmao, date=self.hoje - timedelta(days=2),
            set_number=4, weight_kg=Decimal("27.5"), reps=6,
        )
        ref = services.ultima_vez_do_movimento(self.pessoa, self.item.exercise)
        self.assertEqual(ref["data"], self.hoje - timedelta(days=2))
        self.assertEqual(ref["peso"], Decimal("27.5"))
        self.assertEqual(ref["reps"], 6)
        self.assertEqual(ref["exercicio"].pk, self.irmao.pk)
