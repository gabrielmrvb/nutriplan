# -*- coding: utf-8 -*-
"""AVISO, NUNCA BLOQUEIO (24/09/2026): escolher uma letra cujo grupo foi
treinado nas últimas 48h ganha uma linha de aviso — e a pessoa faz assim
mesmo. O app orienta, não decide por ela."""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase

from config import relogio
from workouts import services
from workouts.test_sequencia import QUINTA, _pessoa, fazer


class AvisoDeTreinoRepetidoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("aviso@exemplo.com")
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))

    def test_escolher_a_recomendada_nao_avisa(self):
        fazer(self.user, self.plan, "A", QUINTA - timedelta(days=1))  # recomendado hoje = B
        self.assertIsNone(services.aviso_de_treino_repetido(self.user, self.plan, "B"))

    def test_escolher_letra_com_grupo_treinado_ontem_avisa_e_aponta_o_recomendado(self):
        fazer(self.user, self.plan, "A", QUINTA - timedelta(days=1))  # A ontem; recomendado B
        aviso = services.aviso_de_treino_repetido(self.user, self.plan, "A")
        self.assertIsNotNone(aviso)
        self.assertIn("ontem", aviso)
        nome_b = next(s.name for s in self.linhas if s.label == "B")
        self.assertIn(nome_b, aviso)

    def test_grupo_treinado_ha_muitos_dias_nao_avisa(self):
        """A foi há 5 dias — fora da janela de 48h —, então escolher A de novo
        não avisa, mesmo sendo diferente do recomendado."""
        fazer(self.user, self.plan, "A", QUINTA - timedelta(days=5))
        self.assertIsNone(services.aviso_de_treino_repetido(self.user, self.plan, "A"))
