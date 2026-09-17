# -*- coding: utf-8 -*-
"""O cardápio da Home diz a medida caseira, e a grama fica entre parênteses."""
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import ActivityLevel, Goal, Sex
from catalog.models import FoodPortion, MealCategory, MealTemplate

from . import meal_planner
from .calculations import PlanInputs, calculate
from .meal_planner import scale_for
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
        self.assertRegex(html, r'class="option__ingrediente">[^<]+</span>\s*<b>[0-9]+(,5)? [a-zç ]+ \([0-9]+ (g|ml)\)</b>')

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


# Homem, 82,5 kg, 1,78 m, 30 anos, rotina leve, 5 treinos, ganhando peso — o
# perfil de maior meta calórica que a avaliação da missão usa (BULK puxa o
# alvo do dia para cima, e é aí que a fome do café da manhã aperta mais).
PERFIL_DE_AVALIACAO = PlanInputs(
    sex=Sex.MALE,
    weight_kg=Decimal("82.5"),
    height_cm=178,
    age_years=30,
    activity_level=ActivityLevel.LIGHT,
    goal=Goal.BULK,
    session_minutes=(60, 60, 60, 60, 60),
)


class OCafeNaoEscalaAcimaDeUmEMeioTests(TestCase):
    """"Aveia 116 g · Leite 462 ml" era a receita-base de 50 g/200 ml escalada 2,31×.

    A base dos 15 cafés listados abaixo era pequena demais para o slot de 25 %
    de uma dieta de 2.859 kcal (715 kcal — o perfil de maior meta que a
    avaliação usa): `scale_for` batia no teto `MAX_SCALE` (2,5×) e virava
    "aveia 116 g" — uma quantidade que não parece mais receita nenhuma. Subir
    a base mantém a proporção e deixa o fator perto de 1: a receita continua
    parecendo receita, e `MAX_SCALE` segue existindo para quem pede uma dieta
    de verdade grande (3.500 kcal), não para tapar buraco de receita pequena.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_o_alvo_de_715_kcal_e_25_por_cento_da_meta_de_referencia(self):
        # Documenta de onde vem o 715: não é um número solto no teste, é 25 %
        # da meta calculada para o perfil de referência da avaliação.
        resultado = calculate(PERFIL_DE_AVALIACAO)
        self.assertEqual(resultado.target_kcal, 2859)
        cafe = next(
            blueprint for blueprint in meal_planner.DAY_BLUEPRINT
            if blueprint.category == MealCategory.BREAKFAST
        )
        self.assertEqual(cafe.share, Decimal("0.25"))

    def test_o_catalogo_semeado_tem_os_dezesseis_cafes_esperados(self):
        # Guarda de verdade: sem isso, o teste abaixo passaria sozinho se
        # alguém apagasse receita em vez de recalibrar — "zero café fora da
        # faixa" também é verdade para "zero café cadastrado".
        self.assertEqual(
            MealTemplate.objects.filter(category=MealCategory.BREAKFAST, is_active=True).count(),
            16,
        )

    def test_todo_cafe_fica_entre_0_7_e_1_5_no_perfil_de_referencia(self):
        alvo = 715  # 25 % de 2.859 — o perfil da avaliação
        fora = []
        for template in MealTemplate.objects.filter(category=MealCategory.BREAKFAST, is_active=True):
            fator = scale_for(template, alvo)
            if not (Decimal("0.7") <= fator <= Decimal("1.5")):
                fora.append((template.name, fator))
        self.assertEqual(fora, [])
