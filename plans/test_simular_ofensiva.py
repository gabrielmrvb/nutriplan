# -*- coding: utf-8 -*-
"""`manage.py simular_ofensiva` dá a mesma resposta em qualquer dia em que rode.

O comando simula uma semana FIXA (seg 21/09 → dom 27/09/2026). A pessoa
descartável nascia com `date_joined = agora`, e desde 22/09/2026 a ofensiva
não olha para antes do cadastro (`plans.streaks.primeiro_dia_da_conta`): em
qualquer dia depois de 21/09 a semana inteira ficava ANTES da conta e a
"regra de hoje" saía `0 0 0 0 0 0 0`. O gate congela 16/09 — antes da
semana — e não via; a noturna, no relógio real, reprovava todo dia
(04/10/2026).
"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from config import relogio
from plans.tests import CatalogFixture

ESPERADA = "regra de hoje (treino previsto + dieta ou água): 0 0 1 2 3 4 5  → dia 7: 5 dias"


class ASimulacaoNaoDependeDeQuandoRodaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogFixture.setUpTestData()
        call_command("seed_workouts", verbosity=0)

    def test_rodada_depois_da_semana_simulada_a_regra_de_hoje_da_cinco(self):
        saida = StringIO()
        with relogio.congelado_em(date(2027, 1, 4)):
            call_command("simular_ofensiva", stdout=saida)
        self.assertIn(ESPERADA, saida.getvalue())
