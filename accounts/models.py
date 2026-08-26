from datetime import time
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractUser):
    """Usuário identificado por e-mail em vez de username."""

    username = None
    email = models.EmailField("e-mail", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.get_full_name() or self.email


class Sex(models.TextChoices):
    MALE = "M", "Masculino"
    FEMALE = "F", "Feminino"


class ActivityLevel(models.TextChoices):
    """Como é o dia da pessoa, **já contando a academia**.

    Mudou de significado em 24/08/2026. Antes o nível descrevia só a rotina
    fora do treino e o gasto da musculação era somado à parte, por MET. Na
    prática isso inflava a conta de quem treina — a fórmula do MET trata uma
    hora de musculação como uma hora de esforço contínuo, quando metade dela é
    descanso entre séries, e o resultado eram metas altas demais para quem
    queria emagrecer.

    Agora o fator cobre rotina e treino juntos, com valores conservadores. É a
    troca certa para um app de dieta: errar para baixo faz a pessoa emagrecer
    um pouco mais rápido do que o previsto; errar para cima faz ela não
    emagrecer e concluir que dieta não funciona.
    """

    # Os rótulos seguem a nomenclatura usual de taxa metabólica basal, porque
    # é a que a pessoa reencontra em qualquer calculadora — e a que um
    # nutricionista reconhece se ela levar a tela para a consulta. O "+
    # academia" saiu do texto: os treinos já entram na conta pela frequência
    # declarada no passo seguinte, e repetir aqui fazia parecer que era
    # preciso somar duas vezes.
    SEDENTARY = "sedentary", "Sedentário / pouco ativo"
    LIGHT = "light", "Moderadamente ativo"
    ACTIVE = "active", "Altamente ativo"


#: Faixa do multiplicador aplicado sobre a TMB, por nível: (piso, teto).
#:
#: É faixa, e não número único, porque dentro do mesmo dia a dia existe quem
#: treina uma vez por semana e quem treina cinco — e a diferença entre os dois
#: cabe exatamente aqui dentro. `calculations.activity_factor()` escolhe o
#: ponto da faixa pela frequência de treino que a pessoa informou.
ACTIVITY_FACTORS = {
    ActivityLevel.SEDENTARY: (Decimal("1.25"), Decimal("1.35")),
    ActivityLevel.LIGHT: (Decimal("1.40"), Decimal("1.45")),
    ActivityLevel.ACTIVE: (Decimal("1.50"), Decimal("1.60")),
}

#: Frequência que leva o fator ao teto da faixa. Acima de cinco sessões o ganho
#: adicional é pequeno demais para justificar mais calorias na conta.
FULL_TRAINING_WEEK = 5


class Goal(models.TextChoices):
    """O que a pessoa quer do corpo dela agora.

    RECOMP é o caso de quem quer as duas coisas ao mesmo tempo — perder gordura
    e ganhar músculo. Existe como objetivo próprio, e não como uma marcação a
    mais em cima de CUT, porque a prescrição dele é diferente das duas: déficit
    pequeno (o corte agressivo derruba o ganho de massa) e proteína mais alta
    (é ela que sustenta a síntese muscular enquanto falta energia). Espremer
    isso em "emagrecer" entregaria a dieta errada para quem treina há pouco
    tempo, voltou de uma pausa ou está acima do peso — justamente quem mais
    consegue recompor.
    """

    CUT = "cut", "Emagrecer"
    BULK = "bulk", "Ganhar massa"
    RECOMP = "recomp", "Emagrecer e ganhar massa ao mesmo tempo"
    MAINTAIN = "maintain", "Manter o peso"


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Segunda-feira"
    TUESDAY = 1, "Terça-feira"
    WEDNESDAY = 2, "Quarta-feira"
    THURSDAY = 3, "Quinta-feira"
    FRIDAY = 4, "Sexta-feira"
    SATURDAY = 5, "Sábado"
    SUNDAY = 6, "Domingo"


#: Número do passo seguinte ao último do wizard — significa "onboarding concluído".
ONBOARDING_DONE = 5
ONBOARDING_LAST_STEP = 4


class Profile(models.Model):
    """Dados estáveis da pessoa.

    O que muda com frequência (peso) mora em WeightEntry; o que é resultado
    de cálculo (meta calórica, macros) mora em plans.NutritionPlan.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    sex = models.CharField("sexo", max_length=1, choices=Sex.choices)
    birth_date = models.DateField("data de nascimento")
    height_cm = models.PositiveSmallIntegerField(
        "altura (cm)",
        validators=[MinValueValidator(100), MaxValueValidator(250)],
    )
    activity_level = models.CharField(
        "nível de atividade",
        max_length=20,
        choices=ActivityLevel.choices,
        default=ActivityLevel.SEDENTARY,
    )
    goal = models.CharField(
        "objetivo", max_length=10, choices=Goal.choices, default=Goal.MAINTAIN
    )
    dietary_tags = models.ManyToManyField(
        "catalog.DietaryTag",
        blank=True,
        related_name="profiles",
        verbose_name="restrições e preferências",
        help_text="Refeições sugeridas precisam atender a todas as restrições marcadas.",
    )
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")
    wake_time = models.TimeField("horário que acorda", default=time(7, 0))
    sleep_time = models.TimeField("horário que dorme", default=time(23, 0))

    # Wizard de onboarding: guarda o PRÓXIMO passo a ser preenchido. Persistir
    # isso no banco (em vez de na sessão) faz a pessoa retomar de onde parou
    # mesmo trocando de dispositivo ou fechando o app no meio.
    #: Ajuste manual sobre a meta calculada, em kcal.
    #:
    #: Existe porque a fórmula é uma estimativa e o corpo é o dado real: duas
    #: pessoas com os mesmos números gastam diferente. Quando a média de peso
    #: empaca por três semanas, o app oferece cortar 150 kcal, e é aqui que o
    #: corte fica. Sempre negativo ou zero na prática — a meta desce, não sobe.
    # Para onde o peso deveria estar indo. Nulo ate alguem definir: o app
    # sozinho nunca precisou disso — ele trabalha com direcao (perder, ganhar,
    # recompor), nao com numero de chegada. Quem prescreve um numero de chegada
    # e o profissional, e e o que o grafico de acompanhamento compara.
    target_weight_kg = models.DecimalField(
        "peso-alvo (kg)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    kcal_adjustment = models.SmallIntegerField("ajuste de calorias", default=0)

    # Prescricao do nutricionista vinculado. Nulo = o motor usa a regra padrao,
    # que e o caso da esmagadora maioria dos planos. Ficam no perfil, e nao no
    # NutritionPlan, porque sao ENTRADAS do calculo: gravadas no plano seriam
    # descartadas na proxima sincronizacao, que refaz o plano sempre que os
    # numeros gravados divergem do que o motor calcula hoje.
    protein_g_per_kg = models.DecimalField(
        "proteina prescrita (g/kg)",
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
    )
    fat_kcal_share = models.DecimalField(
        "gordura prescrita (fracao das calorias)",
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
    )

    #: Quando a pessoa respondeu ao último aviso de estagnação. Evita
    #: perguntar de novo na semana seguinte para quem já disse "vou me mexer
    #: mais" — o aviso repetido é o que faz a pessoa parar de ler avisos.
    recalibrated_at = models.DateTimeField("recalibrado em", null=True, blank=True)

    onboarding_step = models.PositiveSmallIntegerField("passo do onboarding", default=2)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfis"

    def __str__(self):
        return f"Perfil de {self.user}"

    @property
    def age(self) -> int:
        """Idade em anos completos, calculada na hora (nunca armazenada)."""
        today = timezone.localdate()
        born = self.birth_date
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    @property
    def activity_factor(self) -> Decimal:
        """O multiplicador desta pessoa, já posicionado pela frequência de treino."""
        from plans.calculations import activity_factor

        return activity_factor(self.activity_level, self.training_days_per_week)

    @property
    def current_weight(self):
        """Peso mais recente registrado, ou None se ainda não houver nenhum."""
        entry = self.user.weight_entries.first()
        return entry.weight_kg if entry else None

    @property
    def training_days_per_week(self) -> int:
        return self.user.training_days.count()

    @property
    def onboarding_complete(self) -> bool:
        return self.onboarding_step >= ONBOARDING_DONE

    def advance_onboarding(self, completed_step: int):
        """Marca um passo como concluído sem nunca retroceder o progresso.

        Sem o max(), reeditar o passo 1 depois de ter terminado o wizard
        jogaria a pessoa de volta para o começo do fluxo.
        """
        self.onboarding_step = max(self.onboarding_step, completed_step + 1)
        if self.onboarding_step >= ONBOARDING_DONE and self.onboarding_completed_at is None:
            self.onboarding_completed_at = timezone.now()
        self.save(update_fields=["onboarding_step", "onboarding_completed_at", "updated_at"])


class WeightEntry(models.Model):
    """Histórico de peso. O peso atual é o registro mais recente."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weight_entries"
    )
    date = models.DateField("data", default=timezone.localdate)
    weight_kg = models.DecimalField(
        "peso (kg)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("20")), MaxValueValidator(Decimal("400"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "registro de peso"
        verbose_name_plural = "registros de peso"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_weight_per_day")
        ]

    def __str__(self):
        return f"{self.weight_kg} kg em {self.date:%d/%m/%Y}"


class TrainingDay(models.Model):
    """Um dia fixo de treino na semana.

    A frequência semanal é derivada da contagem destes registros, então não
    existe um campo de frequência que possa ficar dessincronizado.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_days"
    )
    weekday = models.PositiveSmallIntegerField("dia da semana", choices=Weekday.choices)
    start_time = models.TimeField("horário de início")
    duration_min = models.PositiveSmallIntegerField(
        "duração (min)",
        default=60,
        validators=[MinValueValidator(15), MaxValueValidator(300)],
    )

    class Meta:
        verbose_name = "dia de treino"
        verbose_name_plural = "dias de treino"
        ordering = ["weekday", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "weekday"], name="unique_training_day_per_weekday"
            )
        ]

    def __str__(self):
        return f"{self.get_weekday_display()} às {self.start_time:%H:%M}"
