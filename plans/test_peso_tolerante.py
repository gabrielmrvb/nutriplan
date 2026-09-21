# -*- coding: utf-8 -*-
"""Pesar +1 kg não troca o cardápio; +1,6 kg troca.

Avaliação de 16/09 (B17): qualquer peso novo invalidava o plano e
reescolhia A/B. O plano continua um RETRATO — nada nele é editado; a
tolerância só decide se nasce um novo. 1,5 kg movem a TMB em ~15 kcal,
menos que o degrau de 10 g do cardápio.
"""
import dataclasses
import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Goal, WeightEntry
from plans import services
from plans.tests import CatalogFixture, create_complete_user


class APesagemToleranteTests(CatalogFixture):
    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)
        # `create_complete_user` não gera plano sozinho — o teste cria o
        # retrato diretamente pelo serviço, o mesmo caminho que a tela usa.
        self.plano = services.create_plan(self.user)
        self.hoje = timezone.localdate()

    def _pesar(self, peso):
        WeightEntry.objects.update_or_create(
            user=self.user, date=self.hoje, defaults={"weight_kg": Decimal(str(peso))}
        )

    def _opcoes_de_hoje(self):
        html = self.client.get(reverse("plans:today")).content.decode()
        return re.findall(r'class="option__name">([^<]+)<', html)

    def test_um_quilo_a_mais_mantem_o_plano_e_o_cardapio(self):
        antes = self._opcoes_de_hoje()

        self._pesar(Decimal(self.plano.weight_kg) + 1)
        self.client.get(reverse("plans:today"))

        self.assertEqual(services.get_active_plan(self.user).pk, self.plano.pk)
        self.assertEqual(self._opcoes_de_hoje(), antes)

    def test_mais_de_um_e_meio_gera_plano_novo(self):
        self._pesar(Decimal(self.plano.weight_kg) + Decimal("1.6"))

        r = self.client.get(reverse("plans:today"))

        self.assertNotEqual(services.get_active_plan(self.user).pk, self.plano.pk)
        self.assertContains(r, "recalculamos")

    def test_o_plano_nao_e_editado(self):
        """Plano é retrato: a pesagem dentro da faixa não reescreve os
        números do plano ativo, só decide que ele continua servindo."""
        peso_do_retrato = self.plano.weight_kg

        self._pesar(Decimal(self.plano.weight_kg) + 1)
        self.client.get(reverse("plans:today"))

        self.plano.refresh_from_db()
        self.assertEqual(self.plano.weight_kg, peso_do_retrato)

    def test_recalcular_explicito_sempre_regenera(self):
        """"Recalcular" em Dados do cálculo é uma AÇÃO, e não segue a
        tolerância: mesmo 1 kg dentro da faixa, o pedido explícito refaz o
        plano."""
        self._pesar(Decimal(self.plano.weight_kg) + 1)

        self.client.post(reverse("plans:recalculate"))

        self.assertNotEqual(services.get_active_plan(self.user).pk, self.plano.pk)


class ATolerenciaNaoEngoleOAjusteManualTests(CatalogFixture):
    """A tolerância de peso não pode esconder o que move a meta SEM passar pelo peso.

    Achado crítico da revisão final da Fase 3 (17/09/2026): o ramo da
    tolerância devolvia `True` sempre que as seis entradas não-peso batiam e
    |Δpeso| ≤ 1,5 kg — inclusive Δ = 0 — SEM comparar saída nenhuma.
    `kcal_adjustment` vive em `PlanInputs` mas não é campo do plano, então
    "Cortar 150 kcal" gravava o ajuste no perfil,
    chamava `sync_active_plan`, e o plano antigo continuava "atual": a meta
    não mudava, e a mensagem "Cortamos 150 kcal da sua meta" mentia.

    O ramo passa a comparar as SAÍDAS contra o cálculo feito com o peso do
    RETRATO: pesar +1,0 kg continua não regenerando (saídas iguais no peso
    gravado), e qualquer coisa que mova a meta sem passar pelo peso regenera.
    """

    def setUp(self):
        self.user = create_complete_user()
        self.client.force_login(self.user)

    def test_cortar_150_gera_plano_novo_com_a_meta_150_abaixo(self):
        antigo = services.create_plan(self.user)

        self.client.post(reverse("plans:recalibrate"), {"acao": "cortar"})

        novo = services.get_active_plan(self.user)
        self.assertNotEqual(novo.pk, antigo.pk)
        self.assertEqual(novo.target_kcal, antigo.target_kcal - 150)

    def test_somar_150_gera_plano_novo_com_a_meta_150_acima(self):
        # BULK: é para quem ganha massa que `weight_trend` oferece "aumentar",
        # e é o objetivo sem teto manual (revisão final, item 2).
        self.user.profile.goal = Goal.BULK
        self.user.profile.save(update_fields=["goal"])
        antigo = services.create_plan(self.user)

        self.client.post(reverse("plans:recalibrate"), {"acao": "aumentar"})

        novo = services.get_active_plan(self.user)
        self.assertNotEqual(novo.pk, antigo.pk)
        self.assertEqual(novo.target_kcal, antigo.target_kcal + 150)

    def test_ajuste_manual_diferente_com_peso_igual_nao_e_atual(self):
        plano = services.create_plan(self.user)
        inputs = services.build_inputs(self.user)
        # Controle positivo: com as MESMAS entradas o plano é atual — senão o
        # `False` abaixo poderia vir de qualquer outra diferença.
        self.assertTrue(services.plan_is_current(plano, inputs))

        ajustado = dataclasses.replace(inputs, kcal_adjustment=-150)

        self.assertFalse(services.plan_is_current(plano, ajustado))

    def test_um_quilo_a_mais_com_o_mesmo_ajuste_continua_atual(self):
        """CONTROLE: a comparação de saídas é feita no peso do RETRATO, então
        o peso dentro da faixa continua não regenerando — o ajuste manual é o
        que muda, não a tolerância."""
        plano = services.create_plan(self.user)
        inputs = services.build_inputs(self.user)

        um_quilo = dataclasses.replace(inputs, weight_kg=inputs.weight_kg + 1)

        self.assertTrue(services.plan_is_current(plano, um_quilo))
