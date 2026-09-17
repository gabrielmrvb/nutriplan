# -*- coding: utf-8 -*-
"""A corrida registrada entra no saldo do dia — por cima do plano, e visível.

`plans/calculations.py` rejeita MET para o PLANO (o fator de atividade cobre o
dia a dia). A corrida entra por cima, líquida: 0,9 kcal por kg por km (≈1
bruto, descontado o repouso; fonte no CORRIDA.md). Recomendo rever: quem se
declarou "altamente ativo" por correr conta duas vezes.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workouts.corrida import gasto_kcal
from workouts.models import Corrida
from workouts.tests import create_user

from . import services, tracking


class OGastoTests(TestCase):
    def test_a_formula(self):
        self.assertEqual(gasto_kcal(5000, Decimal("80")), 360)   # 0,9 × 80 × 5
        self.assertEqual(gasto_kcal(0, Decimal("80")), 0)
        self.assertEqual(gasto_kcal(5000, None), 0)

    def test_o_saldo_do_dia_soma_a_corrida_e_a_home_diz(self):
        pessoa = create_user(email="gasto@exemplo.com")
        self.client.force_login(pessoa)
        hoje = timezone.localdate()
        # `day_summary` pede o plano ativo — `plans:today` o obtém sozinha
        # via `sync_active_plan`; aqui, fora da view, buscamos o mesmo jeito.
        plano, _ = services.sync_active_plan(pessoa)

        antes = tracking.day_summary(pessoa, plano, hoje)["remaining_kcal"]
        inicio = timezone.make_aware(datetime.combine(hoje, time(7, 0)))
        Corrida.objects.create(
            user=pessoa,
            op_id="g1",
            origem="manual",
            comecou_em=inicio,
            terminou_em=inicio + timedelta(minutes=30),
            distancia_m=5000,
            duracao_s=1800,
        )

        depois = tracking.day_summary(pessoa, plano, hoje)

        self.assertEqual(
            depois["gasto_corrida_kcal"],
            gasto_kcal(5000, pessoa.profile.current_weight),
        )
        self.assertEqual(depois["remaining_kcal"], antes + depois["gasto_corrida_kcal"])

        html = self.client.get(reverse("plans:today")).content.decode()
        self.assertIn("da corrida de hoje", html)

    def test_sem_corrida_a_home_nao_fala_em_corrida(self):
        pessoa = create_user(email="semcorrida@exemplo.com")
        self.client.force_login(pessoa)

        html = self.client.get(reverse("plans:today")).content.decode()

        self.assertNotIn("da corrida de hoje", html)
