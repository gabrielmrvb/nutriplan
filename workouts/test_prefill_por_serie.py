# -*- coding: utf-8 -*-
"""Cada série abre com um número que a pessoa já levantou — e com QUAL.

BENCHMARK-2026-09 (c): Hevy, Strong e Fitbod pré-preenchem cada série com a
MESMA série da última sessão. O NutriPlan faz isso na abertura da sessão, e
põe duas coisas na frente, por decisão escrita (`_sugestao_de_carga`, 30/08
e T2.3): a última série de HOJE (ninguém troca de carga entre a 1ª e a 2ª de
propósito) e a sugestão da adaptação (frase == campo). A mais pesada do
último treino é o ÚLTIMO recurso, nunca o primeiro.

Este arquivo pina a ordem — carga e reps lado a lado — para que ninguém a
"corrija" para o comportamento literal do Hevy sem ler o motivo.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog, Measure
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class AOrdemDoPrefillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="prefill@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        self.client.force_login(self.pessoa)
        self.hoje = timezone.localdate()
        sessao = escolher_opcao_de_hoje(self.pessoa)
        self.item = next(
            i for i in sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS and i.sets >= 3
        )

    def _log(self, dias_atras, serie, peso, reps):
        ExerciseLog.objects.create(
            user=self.pessoa, exercise=self.item.exercise,
            date=self.hoje - timedelta(days=dias_atras), set_number=serie,
            weight_kg=Decimal(str(peso)), reps=reps,
        )

    def _campos(self):
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        import re
        carga = re.search(r'name="weight_kg"[^>]*value="([^"]*)"', html)
        reps = re.search(r'name="reps"[^>]*value="([^"]*)"', html)
        return (carga.group(1) if carga else ""), (reps.group(1) if reps else "")

    def test_sem_historico_o_campo_abre_vazio(self):
        self.assertEqual(self._campos(), ("", ""))

    def test_na_abertura_a_serie_1_vem_da_mesma_serie_da_ultima_sessao_quando_nao_ha_sugestao(self):
        # Uma série só na última sessão: sem faixa fechada em todas, a
        # adaptação não sugere, e o que sobra é a mesma série da última vez.
        # `floatformat:'-2'` mantém as duas casas quando há fração — "57,50",
        # não "57,5" (conferido em `test_pastilha.py::…cita_o_mesmo_numero`).
        self._log(7, 1, 57.5, 9)
        self.assertEqual(self._campos(), ("57,50", "9"))

    def test_a_mesma_serie_da_ultima_sessao_vence_a_mais_pesada(self):
        self._log(7, 1, 50, 10)
        self._log(7, 2, 60, 8)   # a mais pesada foi a 2ª
        self.assertEqual(self._campos()[0], "50")  # série 1 abre com a série 1

    def test_a_serie_anterior_de_hoje_vence_tudo(self):
        self._log(7, 1, 60, 10)
        self._log(7, 2, 55, 10)
        self._log(0, 1, 62.5, 8)  # hoje a pessoa subiu
        self.assertEqual(self._campos(), ("62,50", "8"))  # a 2ª abre com a 1ª de hoje, não com 55

    def test_a_pastilha_pendente_mostra_a_mesma_serie_da_ultima_sessao(self):
        self._log(7, 1, 60, 10)
        self._log(7, 2, 55, 8)
        html = self.client.get(reverse("workouts:now") + "?exercicio=%d" % self.item.exercise.pk).content.decode()
        self.assertIn("55", html)
        self.assertIn("60", html)
