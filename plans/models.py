from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import ActivityLevel, Goal, Sex
from catalog.models import MACRO_FIELD, MealCategory, MealTemplate


class NutritionPlan(models.Model):
    """Snapshot imutável do cálculo de dieta feito num dado momento.

    Guardamos tanto as ENTRADAS (peso, idade, objetivo na época) quanto as
    SAÍDAS (meta calórica, macros). Quando a pessoa muda de peso ou objetivo,
    criamos um plano novo e desativamos o anterior — nunca editamos o antigo.
    Assim o histórico de aderência continua sendo julgado contra a meta que
    valia naquela semana, e sobra de brinde a evolução das metas ao longo do tempo.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plans"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField("ativo", default=True)

    # --- Entradas congeladas ---
    weight_kg = models.DecimalField("peso na criação (kg)", max_digits=5, decimal_places=2)
    height_cm = models.PositiveSmallIntegerField("altura (cm)")
    age_years = models.PositiveSmallIntegerField("idade")
    sex = models.CharField(max_length=1, choices=Sex.choices)
    activity_level = models.CharField(max_length=20, choices=ActivityLevel.choices)
    goal = models.CharField(max_length=10, choices=Goal.choices)
    training_days_per_week = models.PositiveSmallIntegerField(default=0)
    formula = models.CharField(max_length=30, default="mifflin_st_jeor")

    # --- Saídas do cálculo ---
    bmr_kcal = models.PositiveIntegerField("taxa metabólica basal")
    tdee_kcal = models.PositiveIntegerField("gasto energético total")
    target_kcal = models.PositiveIntegerField("meta calórica")
    protein_g = models.PositiveSmallIntegerField("proteína (g)")
    carb_g = models.PositiveSmallIntegerField("carboidrato (g)")
    fat_g = models.PositiveSmallIntegerField("gordura (g)")

    notes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "plano nutricional"
        verbose_name_plural = "planos nutricionais"
        ordering = ["-created_at"]
        constraints = [
            # Garante no banco que existe no máximo um plano ativo por pessoa.
            # Deixar isso só na regra de negócio é convite para dados corrompidos.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="unique_active_plan_per_user",
            )
        ]

    def __str__(self):
        return f"{self.target_kcal} kcal ({self.get_goal_display()}) - {self.created_at:%d/%m/%Y}"

    @property
    def macro_split(self) -> dict:
        """Percentual de calorias vindo de cada macro."""
        total = self.target_kcal or 1
        return {
            "protein": round(self.protein_g * 4 * 100 / total),
            "carb": round(self.carb_g * 4 * 100 / total),
            "fat": round(self.fat_g * 9 * 100 / total),
        }


class MealSlot(models.Model):
    """Um horário de refeição dentro do plano, com o alvo nutricional dele.

    O slot define o ALVO; cada MealOption é uma receita escalada para atingir
    esse alvo. É isso que faz as opções serem equivalentes por construção, e
    não por o cadastro ter sido feito com cuidado.
    """

    plan = models.ForeignKey(NutritionPlan, on_delete=models.CASCADE, related_name="slots")
    name = models.CharField("nome", max_length=60)
    category = models.CharField("categoria", max_length=12, choices=MealCategory.choices)
    time = models.TimeField("horário")
    order = models.PositiveSmallIntegerField("ordem")

    target_kcal = models.PositiveIntegerField("meta de calorias")
    target_protein_g = models.PositiveSmallIntegerField("meta de proteína (g)")
    target_carb_g = models.PositiveSmallIntegerField("meta de carboidrato (g)")
    target_fat_g = models.PositiveSmallIntegerField("meta de gordura (g)")

    class Meta:
        verbose_name = "horário de refeição"
        verbose_name_plural = "horários de refeição"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "order"], name="unique_slot_order_per_plan")
        ]

    def __str__(self):
        return f"{self.name} às {self.time:%H:%M}"


class OptionLabel(models.TextChoices):
    """Os rótulos possíveis de uma opção — e, por tabela, quantas existem.

    São duas, e a lista é a fonte da verdade disso: o gerador oferece uma opção
    por rótulo (veja `meal_planner.OPTIONS_PER_SLOT`), então não há como o
    cardápio crescer sem alguém acrescentar um rótulo aqui de propósito.

    Duas não é limitação técnica, é decisão de produto: a pessoa abre o app com
    fome e precisa escolher, não comparar. Com três ou mais a tela vira cardápio
    de restaurante, a decisão custa mais do que cozinhar, e quem está começando
    pula a refeição. Duas opções mantêm a escolha ("tenho frango ou tenho ovo")
    sem transformar o almoço num problema.
    """

    A = "A", "Opção A"
    B = "B", "Opção B"


class MealOption(models.Model):
    """Uma receita escalada para caber no alvo de um slot."""

    slot = models.ForeignKey(MealSlot, on_delete=models.CASCADE, related_name="options")
    template = models.ForeignKey(
        MealTemplate, on_delete=models.PROTECT, related_name="plan_options"
    )
    label = models.CharField(max_length=1, choices=OptionLabel.choices)
    scale_factor = models.DecimalField(
        "fator de escala",
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.25"))],
    )

    kcal = models.DecimalField(**MACRO_FIELD)
    protein_g = models.DecimalField(**MACRO_FIELD)
    carb_g = models.DecimalField(**MACRO_FIELD)
    fat_g = models.DecimalField(**MACRO_FIELD)

    class Meta:
        verbose_name = "opção de refeição"
        verbose_name_plural = "opções de refeição"
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(fields=["slot", "label"], name="unique_label_per_slot"),
            models.UniqueConstraint(
                fields=["slot", "template"], name="unique_template_per_slot"
            ),
        ]

    def __str__(self):
        return f"{self.label}: {self.template.name}"

    def ingredient_list(self):
        """Ingredientes com as quantidades já escaladas, para exibir na tela.

        Usa `.all()` de propósito: assim a chamada aproveita o
        prefetch_related("options__template__items__food") da view em vez de
        disparar uma consulta por opção exibida.
        """
        return [
            {
                "food": item.food,
                "quantity": item.scaled_quantity(self.scale_factor),
                "unit": item.food.base_unit,
            }
            for item in self.template.items.all()
        ]


class MealStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    DONE = "done", "Concluída"
    SKIPPED = "skipped", "Pulada"
    OFF_PLAN = "off_plan", "Comi outra coisa"


class MealLog(models.Model):
    """O que aconteceu de fato numa refeição, num dia.

    Os macros são copiados no momento em que a pessoa marca a refeição. Se você
    editar a receita no admin três meses depois, o histórico de agosto não muda:
    log é fato consumado, não uma view do plano.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_logs"
    )
    # SET_NULL: apagar um plano antigo não pode apagar o histórico da pessoa.
    # Os campos de snapshot abaixo mantêm o log legível mesmo sem o slot.
    slot = models.ForeignKey(
        MealSlot, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"
    )
    chosen_option = models.ForeignKey(
        MealOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"
    )
    date = models.DateField("data", default=timezone.localdate)
    status = models.CharField(
        max_length=10, choices=MealStatus.choices, default=MealStatus.PENDING
    )
    marked_at = models.DateTimeField("marcada em", null=True, blank=True)

    # Snapshot para o histórico sobreviver a mudanças no plano
    slot_name = models.CharField(max_length=60, blank=True)
    scheduled_time = models.TimeField(null=True, blank=True)
    kcal = models.DecimalField(**MACRO_FIELD)
    protein_g = models.DecimalField(**MACRO_FIELD)
    carb_g = models.DecimalField(**MACRO_FIELD)
    fat_g = models.DecimalField(**MACRO_FIELD)

    notes = models.CharField("observação", max_length=200, blank=True)

    class Meta:
        verbose_name = "refeição do dia"
        verbose_name_plural = "refeições do dia"
        ordering = ["-date", "scheduled_time"]
        indexes = [models.Index(fields=["user", "date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date", "slot"], name="unique_log_per_slot_per_day"
            )
        ]

    def __str__(self):
        return f"{self.slot_name} em {self.date:%d/%m} - {self.get_status_display()}"

    @property
    def is_counted(self) -> bool:
        """Refeições pendentes de um dia futuro não devem pesar na aderência."""
        return self.status != MealStatus.PENDING
