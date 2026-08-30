from datetime import time, timedelta
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
class SplitPreference(models.TextChoices):
    """Quantos grupos musculares principais a pessoa quer por sessão.

    Os rótulos falam em CONTAGEM porque é assim que a pergunta é feita na
    academia. A primeira versão desta tela dizia "poucos grupos", "superior e
    inferior" e "corpo todo" — vocabulário de quem já sabe a resposta.

    "Principais" é a palavra que carrega a regra: trapézio, antebraço,
    panturrilha e abdômen têm um ou dois exercícios no catálogo e são
    distribuídos nos acoplamentos lógicos sem contar na conta. Um dia de peito
    e tríceps que termina com abdominal continua sendo dois grupos — dizer
    "três" assustaria por causa de três séries no fim do treino.

    É PREFERÊNCIA, e a frequência continua mandando: quem treina duas vezes na
    semana não consegue uma divisão de cinco dias sem deixar três quintos do
    corpo sem treinar nenhuma vez. `split_for()` cruza os dois, e a preferência
    só decide entre as divisões que a frequência comporta.

    Mora aqui e não em `workouts` porque é dado da PESSOA — `workouts` importa
    `accounts`, e o caminho inverso fecharia o ciclo.
    """

    UM = "one", "1 grupo por dia"
    DOIS = "two", "2 grupos por dia"
    TRES = "three", "3 grupos por dia"


class MealStyle(models.TextChoices):
    """O tipo de comida que a pessoa quer que o cardápio proponha.

    Não é restrição — restrição é `DietaryTag` e elimina a receita. Aqui é
    preferência, e entra como PESO na nota: quando o horário não tem nenhuma
    receita simples que feche os macros, a elaborada ainda aparece, porque um
    horário vazio é pior que um horário caro.
    """

    QUICK = "quick", "Rápida e econômica"
    VARIED = "varied", "Variada e elaborada"


ONBOARDING_DONE = 6
ONBOARDING_LAST_STEP = 5


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
    # O padrão de cada uma é o comportamento que o app JÁ tinha, e isso é
    # deliberado: a migração não pode reescrever o plano de quem nunca viu a
    # pergunta. FOCUSED devolve o mesmo ABC que a frequência escolhia sozinha,
    # e VARIED não filtra nada, que é o cardápio de hoje.
    split_preference = models.CharField(
        "divisão de treino",
        max_length=20,
        choices=SplitPreference.choices,
        # TRES é o padrão porque é o ABC, que é o que a frequência escolhia
        # sozinha antes desta pergunta existir. A migração não pode reescrever
        # o plano de quem nunca viu a tela — nem a ficha ajustada à mão de quem
        # já tinha uma.
        default=SplitPreference.TRES,
    )
    meal_style = models.CharField(
        "estilo de cardápio",
        max_length=10,
        choices=MealStyle.choices,
        default=MealStyle.VARIED,
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
    kcal_adjustment = models.SmallIntegerField("ajuste de calorias", default=0)


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

    def advance_onboarding(self, completed_step: int, proximo: int = None):
        """Marca um passo como concluído sem nunca retroceder o progresso.

        Sem o max(), reeditar o passo 1 depois de ter terminado o wizard
        jogaria a pessoa de volta para o começo do fluxo.

        `proximo` existe porque o caminho deixou de ser uma fila fixa na V2.2:
        quem treina até três dias pula a pergunta de divisão, e para essa
        pessoa o passo seguinte ao 3 é o 5, não o 4. Quem chama sabe o
        caminho; este método só registra até onde ela chegou.
        """
        alvo = proximo if proximo is not None else completed_step + 1
        self.onboarding_step = max(self.onboarding_step, alvo)
        if self.onboarding_step >= ONBOARDING_DONE and self.onboarding_completed_at is None:
            self.onboarding_completed_at = timezone.now()
        self.save(update_fields=["onboarding_step", "onboarding_completed_at", "updated_at"])


class SyncedOperation(models.Model):
    """As operações que já foram aplicadas, para reenvio virar consulta.

    Existe por causa de uma assimetria que só aparece quando o app passa a
    funcionar sem rede: **duas das quatro escritas não são idempotentes**. Água
    soma (`ml + ml`) e suplemento alterna. Uma fila que reenvia o que ficou
    parado offline reenviaria essas duas também — e "+500 ml" reenviado duas
    vezes registra um litro que ninguém bebeu, sem erro nenhum aparecer.

    Não dá para resolver "tentando enviar só uma vez": a rede não oferece essa
    garantia. Resolve-se do outro lado — o servidor lembra o que já aplicou,
    por um identificador que o aparelho gera ANTES de enviar.

    A chave é por pessoa e não global: o identificador nasce no navegador, e
    dois aparelhos podem sortear o mesmo.
    """

    #: Depois disso, a chance de um reenvio ainda estar na fila é nula — e a
    #: tabela cresce a cada marcação offline, num banco gratuito com limite de
    #: tamanho.
    VALIDADE_DIAS = 30

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="synced_operations",
        verbose_name="usuário",
    )
    op_id = models.CharField("identificador da operação", max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "operação sincronizada"
        verbose_name_plural = "operações sincronizadas"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "op_id"), name="uma_operacao_por_pessoa"
            )
        ]
        indexes = [models.Index(fields=["created_at"])]

    def __str__(self):
        return self.op_id

    @classmethod
    def ja_aplicada(cls, user, op_id) -> bool:
        """Registra a operação e diz se ela JÁ tinha sido registrada.

        Uma chamada só, e é de propósito: conferir e depois gravar abriria a
        janela em que dois reenvios simultâneos passam os dois. O índice único
        fecha essa janela — quem perde a corrida recebe `created=False`.
        """
        op_id = (op_id or "").strip()
        # Sem identificador não há como saber se repetiu, e tratar o vazio como
        # repetição travaria toda escrita vinda da tela normal.
        if not op_id or len(op_id) > 64:
            return False

        _, criada = cls.objects.get_or_create(user=user, op_id=op_id)
        return not criada

    @classmethod
    def podar(cls) -> int:
        """Remove o que é velho demais para ainda estar numa fila."""
        corte = timezone.now() - timedelta(days=cls.VALIDADE_DIAS)
        removidas, _ = cls.objects.filter(created_at__lt=corte).delete()
        return removidas


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
