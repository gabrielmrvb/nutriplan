# -*- coding: utf-8 -*-
"""A ficha da letra que cai HOJE mostra o andamento de hoje — mesmo quando a
linha dela nasceu noutro dia da semana.

Com a rotação contínua (17/09/2026) a sessão de hoje é a linha da LETRA da
posição, vestindo o dia; a linha guarda o `weekday` da primeira semana. Na
quinta-feira 17/09 a suíte inteira reprovou no CI em `main` (verde na
quarta): `anexar_historico` decidia "é hoje?" por `session.weekday ==
hoje.weekday()`, e a ficha de A (linha de segunda) aberta na quinta zerava o
balde "hoje" — a série registrada sumia do "1/4" do item, enquanto o
cabeçalho dizia "com série registrada hoje". Na quarta as linhas
coincidiam com os dias e ninguém viu.

O teste não depende do calendário: `inicio_do_ciclo` é movido até a linha
de hoje ter `weekday` diferente de hoje — num plano de sete dias com três
letras isso sempre existe.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts import services
from workouts.models import Measure
from workouts.tests import create_user, dias_incluindo_hoje


class AFichaDaLetraRepetidaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.pessoa = create_user(email="letra@exemplo.com", weekdays=dias_incluindo_hoje(7))
        self.plano = services.create_routine(self.pessoa)
        self.hoje = timezone.localdate()
        for atras in range(7):
            self.plano.inicio_do_ciclo = self.hoje - timedelta(days=atras)
            self.plano.save(update_fields=["inicio_do_ciclo"])
            self.sessao = services.sessao_do_dia(self.plano, self.hoje)
            linha = self.plano.sessions.get(pk=self.sessao.pk)
            if linha.weekday != self.hoje.weekday():
                break
        else:
            self.fail("nenhuma posição do ciclo põe hoje numa linha de outro dia")
        self.linha = linha
        self.client.force_login(self.pessoa)
        self.item = next(
            i for i in self.sessao.da_opcao(1)
            if i.exercise.equipment != "bodyweight" and i.measure == Measure.REPS
        )

    def test_a_serie_de_hoje_aparece_no_item_da_ficha(self):
        self.client.post(reverse("workouts:record_set"), {
            "exercise_id": self.item.exercise_id, "weight_kg": "60", "reps": "10",
            "op_id": "op-letra", "dia": self.hoje.isoformat(),
        })
        ficha = self.client.get(reverse("workouts:ficha", args=[self.sessao.pk]))
        self.assertEqual(ficha.status_code, 200)
        self.assertContains(ficha, "com série registrada hoje")
        self.assertContains(ficha, "1/%d" % self.item.sets)

    def test_o_controle_a_linha_de_hoje_e_de_outro_dia(self):
        """Controle: o fixture pôs hoje numa linha cujo `weekday` NÃO é hoje —
        senão o teste passaria pelo caminho antigo, por coincidência."""
        self.assertNotEqual(self.linha.weekday, self.hoje.weekday())
        self.assertTrue(services.ciclo_roda(self.plano))
