# -*- coding: utf-8 -*-
"""Nenhum item da lista sai em fração de unidade de venda.

"Repolho 40 g", "Alface 60 g", "Azeite 20 ml", "Café coado 300 ml",
"Presunto 50 g", "Couve refogada 250 g", "Carne moída refogada 600 g" — 33 dos
50 alimentos de receita ativa saíam sem forma de compra (avaliação de
16/09/2026, B16). Ninguém pede "40 gramas de repolho" no hortifrúti.

Todo alimento de receita ativa precisa de UMA forma de compra: unidade,
embalagem, mínimo de venda, ou cru em kg. Alimento novo sem forma cai
vermelho aqui — antes de chegar à tela de alguém.

A varredura usa o catálogo REAL do seed, não `plans.tests.CatalogFixture`
(cinco alimentos sintéticos): as tarefas 1 e 2 desta missão mexeram nas
porções e no café da manhã, e o conjunto de alimentos ativos só se prova
varrendo o que o seed grava agora — não uma fixture congelada.
"""
import re
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from catalog.models import Food, MealTemplateItem
from plans import compra, services, shopping
from plans.tests import create_complete_user

#: "40 g" ou "20 ml" sozinhos — nada de estado, unidade ou embalagem em volta.
#: Um `humanize()` puro produz exatamente isto para quem não tem tabela.
SOLTO = re.compile(r"^\d+(,\d+)? (g|ml)$")


class ARéguaDaCompraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_todo_alimento_de_receita_ativa_tem_forma_de_compra(self):
        """A varredura que a avaliação de 16/09 fez à mão, automatizada.

        `MealTemplateItem.objects.filter(template__is_active=True)` é a MESMA
        consulta que decide o que entra na lista de compras de alguém
        (`shopping.weekly_quantities`); alimento que passa aqui sem forma
        de compra é alimento que vai aparecer solto pra essa pessoa.
        """
        nomes = sorted(
            {
                item.food.name
                for item in MealTemplateItem.objects.filter(
                    template__is_active=True
                ).select_related("food")
            }
        )
        self.assertGreater(len(nomes), 0, "o seed não gravou receita ativa nenhuma")

        soltos = []
        for nome in nomes:
            texto, _ = compra.converter(nome, Decimal("40"), "g")
            if SOLTO.match(texto):
                soltos.append((nome, texto))

        self.assertEqual(soltos, [], "sem forma de compra: %s" % soltos)

    def test_o_minimo_nunca_fraciona(self):
        """A avaliação mediu exatamente estes três: nenhum se compra assim.

        "Azeite 20 ml", "Café coado 300 ml" e "Repolho 40 g" (B16, 16/09) —
        e "0,5 garrafa" seria uma mentira pior que a que já existia, porque
        parece precisa.
        """
        self.assertEqual(
            compra.converter("Azeite de oliva extra virgem", Decimal("20"), "ml"),
            ("1 garrafa (500 ml)", True),
        )
        self.assertEqual(
            compra.converter("Café coado sem açúcar", Decimal("300"), "ml"),
            ("1 pacote de café (250 g)", True),
        )
        self.assertEqual(
            compra.converter("Repolho", Decimal("40"), "g"),
            ("1 unidade", True),
        )

    def test_o_minimo_arredonda_para_cima_quando_passa_de_um(self):
        """Duas garrafas quando a semana pede mais que uma — nunca "1,4 garrafa"."""
        texto, aproximado = compra.converter(
            "Azeite de oliva extra virgem", Decimal("600"), "ml"
        )

        self.assertEqual(texto, "2 garrafas (1 L)")
        self.assertTrue(aproximado)

    def test_carne_sai_crua(self):
        """600 g de carne moída REFOGADA voltam pro peso de açougue.

        600 × 1,3 = 780; o degrau de compra (`shopping.round_up`) arredonda
        para o múltiplo de 50 mais próximo pra cima: 800. O que importa
        medir é a FORMA — "cru"/"crua" marcando que é açougue, não prato
        pronto — porque o degrau exato pode mudar sem que a forma mude.
        """
        texto, aproximado = compra.converter(
            "Carne moída (patinho) refogada", Decimal("600"), "g"
        )

        self.assertIn("cru", texto)
        self.assertTrue(aproximado)
        numero = int(re.match(r"\d+", texto).group())
        self.assertGreaterEqual(numero, 780)

    def test_a_banana_usa_a_porcao_do_catalogo(self):
        """`POR_UNIDADE` dizia 90 g; `FoodPortion` diz 70 g — a mesma banana
        com dois pesos diferentes, um deles inventado. A porção vence porque
        é o número que a pessoa já vê no cardápio de hoje: dois valores para
        a mesma coisa é o tipo de coisa que faz alguém desconfiar do app
        inteiro, não só da lista de compras.
        """
        banana = Food.objects.get(name="Banana prata")

        texto, aproximado = compra.converter(
            "Banana prata", Decimal("210"), "g", food=banana
        )

        self.assertEqual(texto, "3 bananas")
        self.assertTrue(aproximado)

    def test_sem_food_a_tabela_estatica_continua_valendo(self):
        """Compatibilidade: quem ainda chama com três argumentos (os testes
        antigos de `test_lista_de_compras.py`, e qualquer chamador futuro sem
        acesso ao `Food`) não pode quebrar — a porção é um refinamento, não
        um requisito."""
        texto, _ = compra.converter("Banana prata", Decimal("210"), "g")

        self.assertEqual(texto, "3 bananas")

    def test_todo_minimo_sai_aproximado(self):
        """Mesma varredura que `FATOR_CRU`/`POR_UNIDADE`/`EMBALAGEM` já
        tinham: a tabela é o dado, o teste percorre a tabela inteira."""
        for nome, (minimo, unidade_base, singular, plural) in compra.MINIMO_DE_COMPRA.items():
            with self.subTest(alimento=nome):
                unidade = unidade_base if unidade_base in ("g", "ml") else "g"
                _texto, aproximado = compra.converter(nome, minimo, unidade)
                self.assertTrue(aproximado)

    def test_a_tabela_de_encolhimento_tem_o_fator_na_direcao_certa(self):
        """`FATOR_DE_ENCOLHIMENTO` é o `FATOR_CRU` ao contrário: aqui o CRU
        pesa MAIS, então o fator também tem de ficar > 1 (é multiplicador,
        não divisor) — mas por um motivo diferente do de `FATOR_CRU`, e por
        isso mora numa tabela separada em vez de reaproveitar aquele
        invariante."""
        for nome, (fator, rotulo) in compra.FATOR_DE_ENCOLHIMENTO.items():
            with self.subTest(alimento=nome):
                self.assertGreater(fator, 1, "cru pesa MENOS que cozido")
                self.assertLess(fator, 2, "fator absurdo: %s" % fator)
                self.assertTrue(rotulo, "sem rótulo de compra")

    def test_a_tabela_de_minimo_tem_forma_valida(self):
        for nome, valor in compra.MINIMO_DE_COMPRA.items():
            with self.subTest(alimento=nome):
                minimo, unidade_base, singular, plural = valor
                self.assertGreater(minimo, 0, "mínimo zero ou negativo")
                self.assertIn(unidade_base, ("g", "ml", "unidade"))
                self.assertTrue(singular, "sem rótulo no singular")
                self.assertTrue(plural, "sem rótulo no plural")

    def test_todo_fator_de_encolhimento_sai_aproximado(self):
        """A mesma varredura que `test_todo_minimo_sai_aproximado` já faz
        para `MINIMO_DE_COMPRA`, agora para `FATOR_DE_ENCOLHIMENTO` — a
        tabela irmã de `FATOR_CRU` que o achado de design deste relatório
        criou. `test_toda_conversao_sai_MARCADA_como_aproximada`, em
        `test_lista_de_compras.py`, varre `FATOR_CRU`/`POR_UNIDADE`/
        `EMBALAGEM`; as duas tabelas que nasceram na tarefa 3
        (`MINIMO_DE_COMPRA` e esta) precisam da mesma prova — sem ela, um
        alimento que entrasse na tabela sem marcar `aproximado=True` passaria
        sem teto nenhum enxergar.
        """
        for nome in compra.FATOR_DE_ENCOLHIMENTO:
            with self.subTest(alimento=nome):
                _texto, aproximado = compra.converter(nome, Decimal("500"), "g")
                self.assertTrue(aproximado)

    def test_nenhum_alimento_esta_nas_duas_tabelas_de_cru(self):
        """`FATOR_CRU` divide, `FATOR_DE_ENCOLHIMENTO` multiplica — e
        `converter()` decide qual delas usar com `if nome in FATOR_CRU: ...
        elif nome in FATOR_DE_ENCOLHIMENTO: ...` (ordem de `if`/`elif`, não
        duas checagens independentes). Um alimento presente nas DUAS tabelas
        sempre cairia no primeiro ramo (`FATOR_CRU`) e a fórmula da segunda
        nunca rodaria — silenciosamente errado pro alimento que perde água,
        não incha. Este teste é o que impede a próxima pessoa de resolver
        "carne também precisa desse fator" copiando a entrada para a tabela
        errada.
        """
        repetidos = set(compra.FATOR_CRU) & set(compra.FATOR_DE_ENCOLHIMENTO)
        self.assertEqual(
            repetidos,
            set(),
            "alimento nas duas tabelas de cru — o if/elif de converter() "
            "vai ignorar uma delas em silêncio: %s" % repetidos,
        )


class ONMaisUmDaLeituraDePorcaoTests(TestCase):
    """`_porcao_padrao` lia `food.portions.filter(is_default=True).first()`
    por alimento — uma consulta NOVA a cada chamada, mesmo com
    `weekly_quantities` já tendo prefetchado `options__template__items__food`.
    `.filter()` monta queryset nova e ignora o cache de `prefetch_related`;
    só `.all()` lê o que já veio junto. Cada alimento único de `POR_UNIDADE`
    presente na lista da semana (tomate, cenoura, ovo, banana, maçã, laranja,
    pão francês, presunto, três queijos…) pagava uma ida a mais ao banco a
    cada carregamento — o mesmo formato de N+1 que
    `plans.test_cardapio_cozinhavel.AHomeMostraMedidaCaseiraTests
    .test_a_lista_de_ingredientes_nao_multiplica_consulta_por_item` já mede
    para `ingredient_list`.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def setUp(self):
        self.user = create_complete_user()
        self.plan = services.create_plan(self.user)
        self.client.force_login(self.user)

    #: Medido em 17/09/2026 com o catálogo real (`seed_catalog`): 19
    #: consultas com `__food__portions` no prefetch de `weekly_quantities` e
    #: `_porcao_padrao` lendo `food.portions.all()`; 27 com a sabotagem
    #: (tirar `__portions` da string do `prefetch_related` em
    #: `plans/shopping.py`, deixando `_porcao_padrao` cair de volta numa
    #: consulta por alimento). O teto fica no meio do caminho: longe o
    #: bastante de 19 para não pegar ruído de outra consulta pontual, perto o
    #: bastante de 27 para pegar a regressão de verdade (remover o prefetch,
    #: ou trocar `_porcao_padrao` de volta para `.filter()`).
    TETO = 23

    def test_a_lista_de_compras_nao_multiplica_consulta_por_alimento_de_unidade(self):
        url = reverse("plans:shopping")
        self.client.get(url)  # aquece o que é cacheado por processo
        with CaptureQueriesContext(connection) as ctx:
            resposta = self.client.get(url)

        self.assertEqual(resposta.status_code, 200)
        self.assertLessEqual(
            len(ctx.captured_queries),
            self.TETO,
            "plans:shopping fez %d consultas (teto %d) — provável consulta "
            "dentro do laço de _porcao_padrao" % (len(ctx.captured_queries), self.TETO),
        )
