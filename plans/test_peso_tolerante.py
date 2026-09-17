# -*- coding: utf-8 -*-
"""Pesar +1 kg não troca o cardápio; +1,6 kg troca.

Avaliação de 16/09 (B17): qualquer peso novo invalidava o plano e
reescolhia A/B. O plano continua um RETRATO — nada nele é editado; a
tolerância só decide se nasce um novo. 1,5 kg movem a TMB em ~15 kcal,
menos que o degrau de 10 g do cardápio.
"""
import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import WeightEntry
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
