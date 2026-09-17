# -*- coding: utf-8 -*-
"""O cardápio da Home diz a medida caseira, e a grama fica entre parênteses."""
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from catalog.models import FoodPortion, MealTemplate

from .models import MealOption
from .tests import CatalogFixture, create_complete_user


class AHomeMostraMedidaCaseiraTests(CatalogFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # "Aveia com iogurte" é o café da manhã da fixture — com só duas
        # receitas cadastradas em BREAKFAST, as duas viram o repertório
        # inteiro do horário, e o rodízio não tem por onde escolher outra
        # coisa: a aveia SEMPRE aparece na Home gerada aqui.
        FoodPortion.objects.create(
            food=cls.oats,
            label="1 colher de sopa",
            grams=Decimal("15"),
            is_default=True,
            singular="colher de sopa",
            plural="colheres de sopa",
        )

    def test_alimento_com_porcao_sai_como_medida_e_grama(self):
        user = create_complete_user()
        self.client.force_login(user)
        html = self.client.get(reverse("plans:today")).content.decode()
        # Um ingrediente com porção: "<b>7,5 colheres de sopa (116 g)</b>" — o número
        # exato depende do cardápio; a FORMA é o que se prova.
        self.assertRegex(html, r'class="option__ingrediente">[^<]+</span>\s*<b>[0-9]+(,[05])? [a-zç ]+ \([0-9]+ (g|ml)\)</b>')

    def test_alimento_sem_porcao_continua_em_grama(self):
        # Frango e arroz não têm porção nenhuma na fixture: a lista tem de
        # continuar em grama para os dois, sem quebrar e sem inventar medida.
        template = MealTemplate.objects.get(name="Frango com arroz")
        option = MealOption(template=template, scale_factor=Decimal("1.00"))
        itens = option.ingredient_list()
        self.assertTrue(itens)
        for item in itens:
            self.assertIsNone(item["caseira"])

    def test_a_lista_de_ingredientes_nao_multiplica_consulta_por_item(self):
        """Guarda de regressão de verdade para o prefetch de `portions`.

        `plans.test_stress.ScreenQueryBudgetTests` mede o "pior dia" — toda
        refeição de HOJE já marcada — e `today.html` só chama
        `option.ingredient_list` quando a refeição ainda não foi marcada
        (`{% if slot.log %}` esconde a lista de opções nesse caso). Por isso
        aquele teto NUNCA exercita o laço que lê `food.portions`, e não
        pegaria a regressão que o prefetch existe para evitar — um `git
        stash` do `__portions` em `plans/views.py` passa por ele em silêncio.

        Aqui a pessoa não marcou nada ainda (fixture nova), então a lista de
        opções aparece de verdade. Medido em 17/09/2026, nesta mesma fixture:
        34 consultas com o prefetch, 50 sem ele — dezesseis a mais, uma por
        item de ingrediente exibido. O teto fica no meio do caminho: longe o
        bastante de 34 para não pegar ruído, perto o bastante de 50 para
        pegar a regressão.
        """
        user = create_complete_user()
        self.client.force_login(user)
        url = reverse("plans:today")
        self.client.get(url)  # aquece o que é cacheado por processo
        with CaptureQueriesContext(connection) as ctx:
            resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertLessEqual(
            len(ctx.captured_queries),
            40,
            "plans:today fez %d consultas (teto 40) — provável consulta "
            "dentro do laço de ingredient_list" % len(ctx.captured_queries),
        )
