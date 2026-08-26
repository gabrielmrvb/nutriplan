"""Auditoria da base nutricional.

Estes testes não olham para uma tabela oficial — não há como embutir a TACO
inteira aqui. Eles conferem o que dá para conferir com certeza: se os quatro
números de cada alimento são compatíveis entre si, e se as substituições
oferecidas mantêm o prato parecido com o que ele era.

A conferência contra TACO/USDA é por amostragem e feita à mão; o que está
travado aqui é a consistência, que é o que pega dado digitado errado.
"""
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Food
from plans import substitutions as sub


class AtwaterTests(TestCase):
    """Caloria não é um dado independente dos macros.

    São 4 kcal por grama de proteína, 4 por carboidrato e 9 por gordura — com
    a ressalva de que a fibra vai contada dentro do carboidrato mas rende só
    ~2 kcal/g. Ignorar a fibra faz tomate e repolho parecerem 17% errados
    quando estão certos; foi o que aconteceu na primeira versão desta
    auditoria.

    Quando os números não fecham, um dos quatro está errado. O teste não diz
    qual — diz que existe.
    """

    #: Leguminosa foge mais que o resto porque parte da fibra fermenta e ainda
    #: rende energia, coisa que a conta simples não modela. Vinte por cento
    #: cobre isso sem deixar passar dígito trocado.
    TOLERANCIA = Decimal("0.20")

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_every_food_has_calories_that_match_its_macros(self):
        for food in Food.objects.all():
            with self.subTest(alimento=food.name):
                liquido = max(Decimal("0"), food.carb_g - food.fiber_g)
                estimado = (
                    4 * food.protein_g + 4 * liquido + 9 * food.fat_g + 2 * food.fiber_g
                )
                if food.kcal < 20:
                    continue  # arredondamento domina em alimento quase sem energia

                desvio = abs(estimado - food.kcal) / food.kcal
                self.assertLessEqual(
                    desvio,
                    self.TOLERANCIA,
                    f"{food.name}: {food.kcal} kcal cadastradas, {estimado:.0f} pela "
                    f"conta ({desvio:.0%} de diferença)",
                )

    def test_macros_never_exceed_the_food_itself(self):
        """Proteína + carboidrato + gordura não cabe em mais de 100 g por 100 g."""
        for food in Food.objects.all():
            with self.subTest(alimento=food.name):
                soma = food.protein_g + food.carb_g + food.fat_g
                self.assertLessEqual(soma, Decimal("100.5"), f"{food.name}: {soma} g")

    def test_fibre_is_part_of_the_carbohydrate(self):
        """Fibra maior que o carboidrato total é dado incoerente."""
        for food in Food.objects.all():
            with self.subTest(alimento=food.name):
                self.assertLessEqual(food.fiber_g, food.carb_g, food.name)


class CookedStateTests(TestCase):
    """Arroz pesa três vezes mais cozido que cru.

    Um alimento que muda muito de peso no preparo e não diz o estado no nome
    é divergência garantida na balança de quem for seguir a dieta.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    #: Alimentos em que crua e pronta são coisas muito diferentes na balança.
    EXIGEM_ESTADO = (
        "arroz", "feijão", "macarrão", "lentilha", "grão-de-bico", "batata",
        "frango", "carne", "patinho", "alcatra", "lombo", "peixe", "tilápia",
        "ovo", "quinoa", "inhame", "mandioca", "ervilha", "vagem",
    )

    ESTADOS = (
        "cozid", "cru", "crua", "grelhad", "assad", "refogad", "frit",
        "desidratad", "seco", "seca", "drenad", "hidratad", "em pó", "torrad",
        "conserva", "defumad", "pronto",
    )

    def test_foods_that_change_weight_when_cooked_say_so(self):
        for food in Food.objects.all():
            nome = food.name.lower()
            if not any(chave in nome for chave in self.EXIGEM_ESTADO):
                continue
            with self.subTest(alimento=food.name):
                self.assertTrue(
                    any(estado in nome for estado in self.ESTADOS),
                    f"{food.name}: o nome não diz se é cru ou pronto",
                )


class SubstitutionFidelityTests(TestCase):
    """Uma troca não pode reescrever o prato pelas costas.

    A regra igualava o macro dominante e a caloria total, e isso deixava
    passar coisas como oferecer proteína de soja no lugar de patinho: proteína
    igual, calorias perto, e o carboidrato saindo de 0 g para 30 g. Metade das
    trocas do catálogo tinha algum macro mais de 50% fora do original; o pior
    caso deslocava 43 g de um macro só.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", verbosity=0)

    def test_no_substitution_moves_a_secondary_macro_too_far(self):
        base = Decimal("100")
        pior = Decimal("0")
        pior_troca = ""

        for original in Food.objects.filter(is_active=True):
            dominante = sub.dominant_macro(original)
            if dominante == "mixed":
                continue
            alvo = original.macros_for(base)
            secundarios = [m for m in sub.KCAL_PER_G if m != dominante]

            for opcao in sub.substitutes_for(original, base):
                macros = opcao["food"].macros_for(opcao["quantity"])
                for m in secundarios:
                    desvio = abs(macros[m] - alvo[m])
                    if desvio > pior:
                        pior, pior_troca = desvio, f"{original.name} -> {opcao['food'].name} ({m})"

        self.assertLessEqual(
            pior,
            sub.MAX_SECONDARY_DRIFT_G,
            f"pior deslocamento: {pior} g em {pior_troca}",
        )

    def test_the_feature_still_answers_for_almost_every_food(self):
        """Filtro apertado demais devolve "não há substituto" e mata o recurso.

        A medida é feita com a PORÇÃO PADRÃO de cada alimento, e não com 100 g
        para todos. Cem gramas de azeite são 884 kcal — nenhuma troca fecha
        isso, e a pergunta nunca é feita na vida real. Perguntar por uma
        colher de azeite é a pergunta de verdade.
        """
        elegiveis = []
        for food in Food.objects.filter(is_active=True):
            porcao = food.portions.filter(is_default=True).first()
            gramas = porcao.grams if porcao else Decimal("100")
            if sub.substitutes_for(food, gramas):
                elegiveis.append(food.name)

        self.assertGreaterEqual(len(elegiveis), 50, f"só {len(elegiveis)} com alternativa")

    def test_a_swap_never_leaves_the_role_it_belongs_to(self):
        """O defeito que o papel no prato veio consertar.

        Casar macro e caloria fazia o app oferecer 467 g de cebola no lugar de
        150 g de arroz e 240 g de cenoura no lugar de uma banana. A conta
        fechava e a refeição virava outra coisa — cebola e arroz dividem o
        corredor do mercado, mas não dividem função nenhuma no prato.
        """
        for food in Food.objects.filter(is_active=True):
            porcao = food.portions.filter(is_default=True).first()
            gramas = porcao.grams if porcao else Decimal("100")
            for opcao in sub.substitutes_for(food, gramas):
                with self.subTest(de=food.name, para=opcao["food"].name):
                    self.assertEqual(opcao["food"].role, food.role)

    def test_no_swap_asks_for_more_than_four_portions(self):
        """Um teto em gramas é cego ao alimento.

        Quatrocentos gramas de arroz é um prato grande; 400 g de clara de ovo
        são treze claras. E foi isso que o app ofereceu no lugar de um filé de
        frango — 423 g, dentro do teto de 600 e fora da realidade de quem vai
        cozinhar.
        """
        for food in Food.objects.filter(is_active=True):
            porcao_origem = food.portions.filter(is_default=True).first()
            gramas = porcao_origem.grams if porcao_origem else Decimal("100")

            for opcao in sub.substitutes_for(food, gramas):
                destino = opcao["food"].portions.filter(is_default=True).first()
                if destino is None or destino.grams <= 0:
                    continue
                with self.subTest(de=food.name, para=opcao["food"].name):
                    self.assertLessEqual(
                        opcao["quantity"] / destino.grams,
                        sub.MAX_PORTIONS,
                        f"{opcao['quantity']}g é mais de {sub.MAX_PORTIONS} "
                        f"x {destino.label}",
                    )

    def test_every_food_declares_what_it_does_in_a_meal(self):
        sem_papel = [
            f.name
            for f in Food.objects.filter(is_active=True)
            if f.role == "other" and f.name not in ("Mel", "Açúcar mascavo")
        ]
        self.assertEqual(sem_papel, [], "alimentos sem papel definido")

    def test_a_substitution_keeps_the_dominant_macro(self):
        """O que a troca promete entregar, ela entrega."""
        for original in Food.objects.filter(is_active=True)[:20]:
            dominante = sub.dominant_macro(original)
            if dominante == "mixed":
                continue
            alvo = original.macros_for(Decimal("100"))
            for opcao in sub.substitutes_for(original, Decimal("100")):
                with self.subTest(de=original.name, para=opcao["food"].name):
                    entregue = opcao["food"].macros_for(opcao["quantity"])[dominante]
                    esperado = alvo[dominante]
                    if esperado <= 0:
                        continue
                    self.assertLessEqual(
                        abs(entregue - esperado) / esperado,
                        Decimal("0.06"),
                        f"{dominante}: {entregue} contra {esperado}",
                    )


class SeedRetirementTests(TestCase):
    """Renomear um alimento não pode duplicá-lo.

    O seed casa por nome. Sem aposentar o que saiu do JSON, renomear "Clara de
    ovo" para "Clara de ovo cozida" criava a nova e deixava a velha ativa —
    duas entradas quase idênticas competindo nas substituições. Aconteceu em
    produção: o catálogo foi de 102 para 103 itens sem ninguém adicionar nada.
    """

    def test_a_food_that_left_the_json_is_deactivated_not_deleted(self):
        call_command("seed_catalog", verbosity=0)

        fantasma = Food.objects.create(
            name="Alimento que já não existe",
            kcal=Decimal("100"),
            protein_g=Decimal("10"),
            carb_g=Decimal("10"),
            fat_g=Decimal("2"),
            fiber_g=Decimal("0"),
        )
        self.assertTrue(fantasma.is_active)

        call_command("seed_catalog", verbosity=0)

        fantasma.refresh_from_db()
        self.assertFalse(fantasma.is_active, "deveria ter sido aposentado")
        # Apagado, não: cardápio antigo e histórico apontam para o registro.
        self.assertTrue(Food.objects.filter(pk=fantasma.pk).exists())

    def test_running_the_seed_twice_does_not_grow_the_catalogue(self):
        call_command("seed_catalog", verbosity=0)
        antes = Food.objects.count()

        call_command("seed_catalog", verbosity=0)

        self.assertEqual(Food.objects.count(), antes)
