# -*- coding: utf-8 -*-
"""FAZER OUTRO TREINO (24/09/2026): a pessoa escolhe qual letra fazer hoje.

O recomendado é uma sugestão, não uma imposição. "Fazer outro treino" grava a
escolha do dia na letra pedida, um toque, sem confirmação — a não ser que já
tenha registrado série hoje e a letra seja outra: aí pede confirmação e não
apaga nada (`ExerciseLog` é por exercício e data)."""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from workouts import services
from workouts.models import EscolhaDeTreino, ExerciseLog
from workouts.test_sequencia import QUINTA, _pessoa, fazer


class EscolherLetraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_workouts", verbosity=0)

    def setUp(self):
        from config import relogio

        self.relogio = relogio.Relogio(QUINTA).ligar()
        self.addCleanup(self.relogio.desligar)
        self.user = _pessoa("escolher@exemplo.com")
        from plans import services as plan_services

        plan_services.create_plan(self.user)
        self.plan = services.create_routine(self.user)
        self.linhas = list(self.plan.sessions.prefetch_related("exercises__exercise"))
        self.client.force_login(self.user)

    def _linha(self, letra):
        return next(s for s in self.linhas if s.label == letra)

    def test_um_toque_grava_a_letra_escolhida_e_ela_vira_o_treino_de_hoje(self):
        """Sem série hoje, escolher B grava a escolha na linha de B e o treino
        de hoje passa a ser B — mesmo com o recomendado sendo A."""
        self.assertEqual(services.sessao_do_dia(self.plan, QUINTA, self.linhas, user=self.user).label, "A")
        resposta = self.client.post(reverse("workouts:escolher_letra"), {"letra": "B"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], reverse("workouts:routine"))
        escolha = EscolhaDeTreino.objects.get(user=self.user, date=QUINTA)
        self.assertEqual(escolha.session_id, self._linha("B").pk)
        self.assertEqual(services.sessao_do_dia(self.plan, QUINTA, self.linhas, user=self.user).label, "B")

    def test_trocar_de_letra_depois_de_treinar_pede_confirmacao_e_nao_grava(self):
        fazer(self.user, self.plan, "A", QUINTA)  # treinou A hoje
        resposta = self.client.post(reverse("workouts:escolher_letra"), {"letra": "B"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], reverse("workouts:routine") + "?trocar=B")
        # nada mudou: a escolha do dia continua em A
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user, date=QUINTA).session_id, self._linha("A").pk)

    def test_confirmar_a_troca_grava_e_nao_apaga_a_serie_da_letra_anterior(self):
        fazer(self.user, self.plan, "A", QUINTA)
        antes = ExerciseLog.objects.filter(user=self.user, date=QUINTA).count()
        resposta = self.client.post(reverse("workouts:escolher_letra"), {"letra": "B", "confirmar": "1"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], reverse("workouts:routine"))
        self.assertEqual(EscolhaDeTreino.objects.get(user=self.user, date=QUINTA).session_id, self._linha("B").pk)
        # a série de A continua lá — trocar de letra não apaga nada
        self.assertEqual(ExerciseLog.objects.filter(user=self.user, date=QUINTA).count(), antes)

    def test_ficar_na_mesma_letra_depois_de_treinar_nao_pede_confirmacao(self):
        fazer(self.user, self.plan, "A", QUINTA)
        escolha, precisa = services.registrar_escolha_de_letra(self.user, self.plan, "A", dia=QUINTA)
        self.assertFalse(precisa)
        self.assertIsNotNone(escolha)

    def test_letra_inexistente_nao_grava(self):
        resposta = self.client.post(reverse("workouts:escolher_letra"), {"letra": "Z"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(EscolhaDeTreino.objects.filter(user=self.user, date=QUINTA).exists())

    def test_o_get_volta_ao_painel(self):
        resposta = self.client.get(reverse("workouts:escolher_letra"))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], reverse("workouts:routine"))
