from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

#: Precisão usada em todos os campos de macronutriente.
MACRO_FIELD = dict(max_digits=8, decimal_places=2, default=Decimal("0"))

#: Quantidade de referência das tabelas nutricionais (por 100 g ou 100 ml).
REFERENCE_QUANTITY = Decimal("100")


class TagKind(models.TextChoices):
    RESTRICTION = "restriction", "Restrição (filtra o que pode aparecer)"
    PREFERENCE = "preference", "Preferência (só ordena as sugestões)"


class DietaryTag(models.Model):
    """Uma característica que uma refeição atende: vegetariana, sem lactose etc.

    A tag descreve o que a refeição É, não o que ela contém. Assim o filtro
    fica trivial: a refeição precisa ter TODAS as tags de restrição exigidas
    pelo perfil do usuário.
    """

    slug = models.SlugField("identificador", max_length=40, unique=True)
    name = models.CharField("nome", max_length=60)
    kind = models.CharField(
        "tipo", max_length=12, choices=TagKind.choices, default=TagKind.RESTRICTION
    )

    class Meta:
        verbose_name = "restrição / preferência"
        verbose_name_plural = "restrições e preferências"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BaseUnit(models.TextChoices):
    GRAM = "g", "Gramas"
    MILLILITER = "ml", "Mililitros"


class Aisle(models.TextChoices):
    """Onde o alimento fica no supermercado.

    A lista de compras é organizada por isto, e não por grupo nutricional, por
    um motivo prático: quem está no mercado anda por corredor, não por macro.
    Uma lista que manda ir três vezes ao hortifrúti porque separou "fontes de
    carboidrato" de "fontes de fibra" faz a pessoa desistir na metade.
    """

    PRODUCE = "produce", "Hortifrúti"
    BUTCHER = "butcher", "Açougue e ovos"
    DAIRY = "dairy", "Laticínios e frios"
    BAKERY = "bakery", "Padaria"
    GROCERY = "grocery", "Mercearia"


class FoodRole(models.TextChoices):
    """O que o alimento FAZ na refeição.

    Diferente do corredor do supermercado, que é onde ele fica na loja. A
    distinção existe por um defeito concreto: o corredor "hortifrúti" junta
    banana, batata e cebola, e a substituição por macro chegou a oferecer
    467 g de cebola no lugar de 150 g de arroz. Fechava a conta de
    carboidrato e destruía o prato.

    Trocar só faz sentido dentro do mesmo papel — arroz por batata, frango por
    tilápia, azeite por castanha.
    """

    PROTEIN = "protein", "Fonte de proteína"
    STARCH = "starch", "Carboidrato do prato"
    LEGUME = "legume", "Leguminosa"
    FRUIT = "fruit", "Fruta"
    VEGETABLE = "vegetable", "Legume ou verdura"
    FAT = "fat", "Fonte de gordura"
    DAIRY = "dairy", "Laticínio"
    DRINK = "drink", "Bebida"
    OTHER = "other", "Outro"


class FoodSource(models.TextChoices):
    MANUAL = "manual", "Cadastro manual"
    TACO = "taco", "Tabela TACO"
    OFF = "off", "Open Food Facts"


class Food(models.Model):
    """Um alimento com valores nutricionais por 100 g (ou 100 ml)."""

    name = models.CharField("nome", max_length=120)
    brand = models.CharField("marca", max_length=80, blank=True)
    base_unit = models.CharField(
        "unidade base", max_length=2, choices=BaseUnit.choices, default=BaseUnit.GRAM
    )

    kcal = models.DecimalField("calorias (por 100)", **MACRO_FIELD)
    protein_g = models.DecimalField("proteína g (por 100)", **MACRO_FIELD)
    carb_g = models.DecimalField("carboidrato g (por 100)", **MACRO_FIELD)
    fat_g = models.DecimalField("gordura g (por 100)", **MACRO_FIELD)
    fiber_g = models.DecimalField("fibra g (por 100)", **MACRO_FIELD)

    source = models.CharField(
        "fonte", max_length=10, choices=FoodSource.choices, default=FoodSource.MANUAL
    )
    role = models.CharField(
        "papel no prato",
        max_length=10,
        choices=FoodRole.choices,
        default=FoodRole.OTHER,
        help_text=(
            "O que este alimento faz na refeição. É o que limita a "
            "substituição: só entra troca do mesmo papel."
        ),
    )
    aisle = models.CharField(
        "corredor do mercado",
        max_length=10,
        choices=Aisle.choices,
        default=Aisle.GROCERY,
        help_text="Usado para agrupar a lista de compras na ordem em que se anda no mercado.",
    )
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "alimento"
        verbose_name_plural = "alimentos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "brand"], name="unique_food_name_brand")
        ]

    def __str__(self):
        return f"{self.name} ({self.brand})" if self.brand else self.name

    def clean(self):
        """Confere se as calorias batem com os macros (4/4/9 kcal por grama).

        Erro de digitação em tabela nutricional é silencioso e contamina todos
        os planos gerados depois. Uma tolerância de 20% cobre fibra, álcool e
        arredondamento das tabelas sem gerar falso positivo.
        """
        estimated = self.protein_g * 4 + self.carb_g * 4 + self.fat_g * 9
        if estimated == 0 and self.kcal == 0:
            return
        limit = max(estimated, self.kcal) * Decimal("0.20")
        if abs(estimated - self.kcal) > limit:
            raise ValidationError(
                {
                    "kcal": (
                        f"As calorias informadas ({self.kcal}) não batem com os macros "
                        f"(estimativa: {estimated:.0f} kcal). Confira os valores."
                    )
                }
            )

    def macros_for(self, grams) -> dict:
        """Macros deste alimento para uma quantidade em gramas/ml."""
        factor = Decimal(grams) / REFERENCE_QUANTITY
        return {
            "kcal": self.kcal * factor,
            "protein_g": self.protein_g * factor,
            "carb_g": self.carb_g * factor,
            "fat_g": self.fat_g * factor,
            "fiber_g": self.fiber_g * factor,
        }


class FoodPortion(models.Model):
    """Medida caseira de um alimento: 1 ovo médio = 50 g.

    Sem isso a interface manda a pessoa pesar tudo, o que é a forma mais rápida
    de fazer alguém abandonar a dieta.
    """

    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name="portions")
    label = models.CharField("medida", max_length=60)
    grams = models.DecimalField(
        "equivale a (g/ml)",
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_default = models.BooleanField("medida padrão", default=False)

    class Meta:
        verbose_name = "medida caseira"
        verbose_name_plural = "medidas caseiras"
        ordering = ["-is_default", "grams"]
        constraints = [
            models.UniqueConstraint(fields=["food", "label"], name="unique_portion_per_food")
        ]

    def __str__(self):
        return f"{self.label} = {self.grams:.0f} {self.food.base_unit}"


class MealCategory(models.TextChoices):
    """Categoria ampla de refeição.

    Deliberadamente ampla: MAIN cobre almoço E jantar, então um template de
    'frango com arroz e salada' serve os dois horários sem cadastro duplicado.
    """

    BREAKFAST = "breakfast", "Café da manhã"
    MAIN = "main", "Refeição principal (almoço/jantar)"
    SNACK = "snack", "Lanche"
    SUPPER = "supper", "Ceia"


class MealTemplate(models.Model):
    """Uma receita: a base de uma opção de refeição.

    Os macros são a soma dos itens, mas ficam guardados nos campos *_cache para
    permitir filtrar e ordenar por caloria direto no banco. Os itens continuam
    sendo a fonte da verdade; o cache é recalculado por sinal sempre que um
    item ou um alimento muda (veja signals.py).
    """

    name = models.CharField("nome", max_length=120, unique=True)
    category = models.CharField("categoria", max_length=12, choices=MealCategory.choices)
    tags = models.ManyToManyField(
        DietaryTag, blank=True, related_name="meal_templates", verbose_name="atende a"
    )
    prep_minutes = models.PositiveSmallIntegerField("tempo de preparo (min)", default=10)
    everyday = models.BooleanField(
        "comida do dia a dia",
        default=True,
        help_text=(
            "Marque para receitas de ingrediente barato e preparo direto (arroz com "
            "feijão e ovo, sanduíche de frango). Desmarque para as mais elaboradas ou "
            "caras — elas só entram no cardápio quando nenhuma simples serve."
        ),
    )
    instructions = models.TextField("modo de preparo", blank=True)
    is_active = models.BooleanField("ativa", default=True)

    kcal_cache = models.DecimalField("calorias", **MACRO_FIELD)
    protein_g_cache = models.DecimalField("proteína (g)", **MACRO_FIELD)
    carb_g_cache = models.DecimalField("carboidrato (g)", **MACRO_FIELD)
    fat_g_cache = models.DecimalField("gordura (g)", **MACRO_FIELD)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "refeição (modelo)"
        verbose_name_plural = "refeições (modelos)"
        ordering = ["category", "name"]

    def __str__(self):
        return self.name

    def compute_macros(self, scale=Decimal("1")) -> dict:
        """Soma os macros dos itens, aplicando o fator de escala onde couber."""
        scale = Decimal(scale)
        totals = {"kcal": Decimal("0"), "protein_g": Decimal("0"),
                  "carb_g": Decimal("0"), "fat_g": Decimal("0"), "fiber_g": Decimal("0")}
        for item in self.items.select_related("food"):
            for key, value in item.macros_for(scale).items():
                totals[key] += value
        return totals

    def refresh_macros(self, save=True):
        """Recalcula os campos de cache a partir dos itens."""
        totals = self.compute_macros()
        self.kcal_cache = totals["kcal"]
        self.protein_g_cache = totals["protein_g"]
        self.carb_g_cache = totals["carb_g"]
        self.fat_g_cache = totals["fat_g"]
        if save:
            MealTemplate.objects.filter(pk=self.pk).update(
                kcal_cache=self.kcal_cache,
                protein_g_cache=self.protein_g_cache,
                carb_g_cache=self.carb_g_cache,
                fat_g_cache=self.fat_g_cache,
            )
        return totals


class MealTemplateItem(models.Model):
    """Um ingrediente dentro de uma receita."""

    template = models.ForeignKey(
        MealTemplate, on_delete=models.CASCADE, related_name="items"
    )
    # PROTECT: apagar um alimento que já está em receitas quebraria os planos
    # que apontam para elas. O caminho certo é marcar is_active=False.
    food = models.ForeignKey(Food, on_delete=models.PROTECT, related_name="template_items")
    quantity_g = models.DecimalField(
        "quantidade (g/ml)",
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    scalable = models.BooleanField(
        "escalável",
        default=True,
        help_text=(
            "Marque para itens que podem crescer/diminuir junto com a meta calórica "
            "(arroz, frango). Desmarque para itens fixos (1 ovo, 1 fatia, tempero)."
        ),
    )
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "ingrediente"
        verbose_name_plural = "ingredientes"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "food"], name="unique_food_per_template"
            )
        ]

    def __str__(self):
        return f"{self.quantity_g:.0f}{self.food.base_unit} de {self.food.name}"

    def scaled_quantity(self, scale=Decimal("1")) -> Decimal:
        """Quantidade após aplicar a escala — itens não escaláveis ignoram o fator."""
        return self.quantity_g * Decimal(scale) if self.scalable else self.quantity_g

    def macros_for(self, scale=Decimal("1")) -> dict:
        return self.food.macros_for(self.scaled_quantity(scale))
