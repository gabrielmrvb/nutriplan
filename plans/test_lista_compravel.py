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
from django.test import TestCase

from catalog.models import Food, MealTemplateItem
from plans import compra

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
