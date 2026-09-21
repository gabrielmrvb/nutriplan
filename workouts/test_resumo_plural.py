# -*- coding: utf-8 -*-
"""O resumo de hoje no painel concorda em número.

Achado de passagem na prova em produção do #43 (21/09/2026): com uma série
registrada o cartão dizia "1 séries · 1 exercícios" e "1 minutos". Um
plural fixo ao lado de um número que a pessoa acabou de produzir é o app
não lendo o próprio número; `pluralize` resolve nos três rótulos.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import ExerciseLog
from workouts.tests import create_user, dias_incluindo_hoje, escolher_opcao_de_hoje


class OResumoDeHojeConcordaEmNumeroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="plural@exemplo.com", weekdays=dias_incluindo_hoje(5))
        services.create_routine(self.pessoa)
        escolher_opcao_de_hoje(self.pessoa)
        self.client.force_login(self.pessoa)
        estado = services.estado_do_treino(self.pessoa)
        self.exercicio = estado.itens[0].exercise

    def _registrar(self, series):
        for n in range(1, series + 1):
            ExerciseLog.objects.create(user=self.pessoa, exercise=self.exercicio, date=timezone.localdate(),
                                       set_number=n, weight_kg=Decimal("40"), reps=10)

    def _painel(self):
        resposta = self.client.get(reverse("workouts:routine"))
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        return html.split('data-minutos="')[1].split("</div>\n        </div>")[0]  # o cartão do resumo

    def test_uma_serie_e_um_exercicio_no_singular(self):
        self._registrar(1)
        cartao = self._painel()
        self.assertIn(">1</strong>\n            <span class=\"tile__label\">série</span>", cartao)
        self.assertIn("1 exercício</span>", cartao)
        self.assertNotIn("1 séries", cartao)
        self.assertNotIn("1 exercícios", cartao)

    def test_duas_series_no_plural(self):
        self._registrar(2)
        cartao = self._painel()
        self.assertIn(">2</strong>\n            <span class=\"tile__label\">séries</span>", cartao)
        self.assertIn("1 exercício</span>", cartao)

    def test_o_minuto_tambem_concorda(self):
        """A conta única dá 8 minutos para uma série; o rótulo é lido do número,
        não escrito à mão — com 1 minuto seria "minuto"."""
        self._registrar(1)
        cartao = self._painel()
        minutos = int(cartao.split('"')[0])  # o cartão começa logo depois de data-minutos="
        rotulo = "minuto" if minutos == 1 else "minutos"
        self.assertIn('<span class="tile__label">%s</span>' % rotulo, cartao)
