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


class OCafeParecePratoDeVerdadeTests(TestCase):
    """A régua de "parece comida" — [0,7; 1,5] no fator não bastava.

    Revisão do Fix round 1 (relatório da Task 2, 17/09/2026): 15 dos 16 cafés
    recalibrados para caber em [0,7; 1,5] entregavam, a 715 kcal, porção que
    não é mais um prato — "Cuscuz com ovo" virava 450 g de cuscuz cozido,
    "Tapioca com ovo" virava 180 g de goma (3 tapiocas), "Mingau de aveia com
    leite e mel" virava 400 ml de leite + 90 g de aveia. O fator da receita
    inteira ficava dentro da faixa porque o desvio se escondia num só
    ingrediente. Esta régua olha a quantidade ENTREGUE
    (`item.scaled_quantity(fator)`) de cada alimento-base contra um teto de
    "ainda parece comida" — por ingrediente, não por receita — e por isso pega
    o que a régua de fator sozinha deixa passar.

    Os tetos são amassados fino (cozido/hidratado) ou líquidos, o que estica
    a quantidade "razoável" numa refeição — os números abaixo refletem isso,
    não uma porção de prato seco.

    Revisão do Fix round 2 (mesmo relatório): a redistribuição do round 1
    corrigiu os alimentos que JÁ estavam no teto acima, mas destravou outros —
    "Tapioca com frango desfiado" passou a entregar 266,7 g de frango,
    "Cuscuz com carne de soja" 130 g de proteína de soja texturizada, e
    "Cuscuz com ovo"/"Tapioca com ovo" 111–116 g de queijo. Nenhum desses
    alimentos tinha teto. `TETO_G_POR_PADRAO` fecha a lacuna por PADRÃO de
    nome (frango, queijo, proteína de soja, pasta de amendoim, iogurte) em vez
    de listar cada corte/marca — sobrevive a um alimento novo do mesmo tipo
    entrar no catálogo depois.
    """

    TETO_G = {
        "Cuscuz de milho cozido": Decimal("250"),
        "Goma de tapioca hidratada": Decimal("120"),
        "Aveia em flocos": Decimal("90"),
        "Leite integral": Decimal("350"),
        "Leite desnatado": Decimal("350"),
        "Ovo de galinha cozido": Decimal("200"),  # 4 unidades de 50 g
        "Pão francês": Decimal("150"),  # 3 unidades de 50 g
        "Pão de forma integral": Decimal("75"),  # 3 fatias de 25 g
    }

    #: Teto por PADRÃO no nome (minúsculo, comparação por substring) — para
    #: famílias de alimento em vez de um item cadastrado por vez. "queijo" não
    #: casa com "requeijão" (a palavra não aparece como substring), de
    #: propósito: requeijão é colher, não fatia, e nunca esteve na faixa
    #: problemática.
    TETO_G_POR_PADRAO = (
        ("frango", Decimal("150")),
        ("queijo", Decimal("60")),  # 3 fatias de ~20 g
        ("proteína de soja", Decimal("80")),
        ("pasta de amendoim", Decimal("40")),  # 2 colheres de sopa
        ("iogurte", Decimal("340")),  # 2 potes
    )

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def _teto_para(self, nome_alimento):
        teto = self.TETO_G.get(nome_alimento)
        if teto is not None:
            return teto
        nome = nome_alimento.lower()
        for padrao, teto_padrao in self.TETO_G_POR_PADRAO:
            if padrao in nome:
                return teto_padrao
        return None

    def test_a_quantidade_entregue_respeita_o_teto_por_alimento(self):
        alvo = 715  # 25 % de 2.859 — o mesmo perfil da avaliação
        fora = []
        templates = (
            MealTemplate.objects.filter(category=MealCategory.BREAKFAST, is_active=True)
            .prefetch_related("items__food")
        )
        for template in templates:
            fator = scale_for(template, alvo)
            for item in template.items.all():
                teto = self._teto_para(item.food.name)
                if teto is None:
                    continue
                entregue = item.scaled_quantity(fator)
                if entregue > teto:
                    fora.append((template.name, item.food.name, entregue, teto))
        self.assertEqual(fora, [])

    def test_nenhum_ingrediente_sozinho_passa_de_60_por_cento_da_caloria(self):
        """A caloria não pode se esconder inteira num só item da receita.

        "Tapioca com frango desfiado" passava no teto de grama por alimento
        (round 1) e ainda assim entregava 61,6 % da caloria da receita só no
        frango — tecnicamente dentro de cada teto individual, mas a receita
        virava "frango com um acompanhamento simbólico de goma", não um prato
        equilibrado. Esta régua é por PORCENTAGEM DA RECEITA, não por grama, e
        por isso pega o desequilíbrio mesmo quando nenhum teto de grama
        isolado é ultrapassado.
        """
        alvo = 715
        fora = []
        templates = (
            MealTemplate.objects.filter(category=MealCategory.BREAKFAST, is_active=True)
            .prefetch_related("items__food")
        )
        for template in templates:
            fator = scale_for(template, alvo)
            total_kcal = template.compute_macros(fator)["kcal"]
            if total_kcal <= 0:
                continue
            for item in template.items.all():
                kcal_item = item.macros_for(fator)["kcal"]
                if kcal_item > total_kcal * Decimal("0.6"):
                    fora.append((template.name, item.food.name, kcal_item, total_kcal))
        self.assertEqual(fora, [])
