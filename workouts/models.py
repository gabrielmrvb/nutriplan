"""Catálogo de exercícios, divisões de treino e a rotina de cada pessoa.

A modelagem repete o mesmo desenho do app `plans`, de propósito:

    catálogo estável           ->  snapshot da pessoa
    Exercise / WorkoutTemplate ->  TrainingPlan / TrainingSession / SessionExercise

Ou seja: o catálogo é o que o time de conteúdo mantém, e a rotina da pessoa é
uma cópia congelada dele no dia em que foi montada. Trocar a série de um
exercício no catálogo amanhã não reescreve a ficha que alguém está seguindo
hoje — e quando a rotina precisa mudar (mudou a frequência de treino), nasce
uma rotina nova e a antiga é aposentada, exatamente como o NutritionPlan.
"""
from decimal import Decimal
from urllib.parse import quote_plus, urlparse

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class MuscleGroup(models.TextChoices):
    CHEST = "chest", "Peito"
    BACK = "back", "Costas"
    QUADS = "quads", "Quadríceps"
    HAMSTRINGS = "hamstrings", "Posterior de coxa e glúteo"
    CALVES = "calves", "Panturrilha"
    SHOULDERS = "shoulders", "Ombros"
    BICEPS = "biceps", "Bíceps"
    TRICEPS = "triceps", "Tríceps"
    CORE = "core", "Abdômen e core"
    # Trapézio e antebraço saíram de dentro de "costas" e "bíceps" quando o
    # ABCD ganhou um dia próprio para eles. Separados, o volume semanal de
    # cada um passa a ser contável — antes, encolhimento aparecia somado a
    # costas e a ficha dizia que a pessoa fazia mais puxe do que fazia.
    TRAPS = "traps", "Trapézio"
    FOREARMS = "forearms", "Antebraço"


class Measure(models.TextChoices):
    """Como a série é contada: repetições ou tempo.

    Prancha não tem repetição, e fingir que tem ("3 x 12 de prancha") é a forma
    mais rápida de a ficha perder credibilidade com quem treina.
    """

    REPS = "reps", "Repetições"
    SECONDS = "seconds", "Segundos"


class Exercise(models.Model):
    """Um exercício de academia comum.

    O catálogo é deliberadamente de academia de bairro: barra, halter, polia e
    as máquinas que existem em qualquer lugar. Exercício que depende de
    equipamento específico não entra — ficha que a pessoa não consegue executar
    é igual a dieta que ela não consegue comprar.
    """

    name = models.CharField("nome", max_length=80, unique=True)
    muscle_group = models.CharField("grupo muscular", max_length=12, choices=MuscleGroup.choices)
    #: Multiarticular (agachamento, supino) x isolado (rosca, elevação lateral).
    #: É o que decide série, faixa de repetição e descanso padrão.
    is_compound = models.BooleanField("multiarticular", default=False)
    cue = models.CharField(
        "dica de execução",
        max_length=200,
        blank=True,
        help_text="Uma frase com o erro mais comum ou o ponto que garante a técnica.",
    )
    video_url = models.URLField(
        "vídeo de execução",
        blank=True,
        help_text=(
            "Link de um vídeo demonstrando o movimento. Guardamos o endereço normal "
            "(o que se copia da barra do navegador); a tela converte para embed na hora."
        ),
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "exercício"
        verbose_name_plural = "exercícios"
        ordering = ["muscle_group", "name"]

    def __str__(self):
        return self.name

    @property
    def video_id(self) -> str:
        """O identificador do vídeo no YouTube, ou "" se não der para extrair.

        Aceita os três formatos que aparecem quando alguém copia um link:
        `watch?v=`, `youtu.be/` e `/shorts/`. Qualquer outra coisa devolve
        vazio, e a tela cai no plano B em vez de montar um embed quebrado.
        """
        if not self.video_url:
            return ""
        parts = urlparse(self.video_url)
        if parts.netloc.endswith("youtu.be"):
            return parts.path.strip("/").split("/")[0]
        if not parts.netloc.endswith("youtube.com"):
            return ""
        if parts.path == "/watch":
            for chunk in parts.query.split("&"):
                if chunk.startswith("v="):
                    return chunk[2:]
            return ""
        if parts.path.startswith("/shorts/") or parts.path.startswith("/embed/"):
            return parts.path.split("/")[2]
        return ""

    @property
    def clip_kind(self) -> str:
        """Que tipo de mídia está cadastrada: "gif", "video", "youtube" ou "".

        O campo aceita os três porque a demonstração ideal é um clipe de dez
        segundos em loop, e isso pode chegar como GIF, como MP4 hospedado por
        nós ou como um Short do YouTube. Quem decide como renderizar é a tela,
        a partir daqui — não o seed.
        """
        if not self.video_url:
            return ""
        caminho = urlparse(self.video_url).path.lower()
        if caminho.endswith(".gif"):
            return "gif"
        if caminho.endswith((".mp4", ".webm", ".mov")):
            return "video"
        return "youtube" if self.video_id else ""

    @property
    def is_vertical(self) -> bool:
        """Short do YouTube é vertical; forçar 16:9 nele deixa tarja preta."""
        return "/shorts/" in self.video_url

    @property
    def video_embed_url(self) -> str:
        """Endereço para o iframe, já configurado como clipe de demonstração.

        `youtube-nocookie.com` é o domínio de privacidade reforçada do próprio
        YouTube: ele não grava cookie de rastreamento antes de a pessoa dar play.
        Num app de saúde, que já sabe peso e objetivo de quem usa, não faz
        sentido entregar o resto para a publicidade de terceiro.

        Os parâmetros fazem o vídeo se comportar como GIF: começa sozinho, sem
        som e repetindo. `mute=1` não é preferência — navegador nenhum deixa um
        vídeo com áudio começar sozinho, então sem ele o autoplay simplesmente
        não acontece. E `loop` exige `playlist` com o próprio id: é assim que a
        API do YouTube repete um vídeo único.
        """
        video = self.video_id
        if not video:
            return ""
        return (
            f"https://www.youtube-nocookie.com/embed/{video}"
            f"?autoplay=1&mute=1&loop=1&playlist={video}"
            "&controls=0&modestbranding=1&playsinline=1&rel=0"
        )

    @property
    def video_search_url(self) -> str:
        """Plano B: busca pelo nome do exercício.

        Vídeo de terceiro sai do ar, vira privado, some. Quando isso acontecer,
        o botão continua levando a pessoa a uma demonstração em vez de abrir uma
        tela preta — e ninguém precisa correr para atualizar o seed.
        """
        return (
            "https://www.youtube.com/results?search_query="
            + quote_plus(f"{self.name} execução correta")
        )


class Split(models.TextChoices):
    """A divisão semanal, escolhida pela frequência de treino da pessoa.

    Não é preferência estética: a divisão existe para distribuir volume com a
    frequência que a pessoa realmente tem. Quem treina duas vezes não pode
    gastar um dia inteiro só em bíceps, e quem treina cinco não precisa fazer
    corpo inteiro toda vez.
    """

    FULL = "full", "Corpo inteiro"
    AB = "ab", "AB — superior e inferior"
    ABC = "abc", "ABC — empurrar, puxar e pernas"
    ABCD = "abcd", "ABCD — peito/tríceps, costas/bíceps, ombro/perna e complementares"


class WorkoutTemplate(models.Model):
    """Um dia de treino dentro de uma divisão: o "A" do ABC, por exemplo."""

    split = models.CharField("divisão", max_length=6, choices=Split.choices)
    label = models.CharField("letra", max_length=1)
    name = models.CharField("nome", max_length=60)
    focus = models.CharField("foco", max_length=120, blank=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "treino (modelo)"
        verbose_name_plural = "treinos (modelos)"
        ordering = ["split", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["split", "label"], name="unique_label_per_split"
            )
        ]

    def __str__(self):
        return f"{self.get_split_display()} · {self.label} — {self.name}"


class PrescriptionFields(models.Model):
    """Séries, repetições e descanso — os três números de uma ficha.

    Abstrato porque os mesmos campos descrevem o modelo do catálogo e a cópia
    congelada na ficha da pessoa. Repetir a definição nos dois lugares é como
    duas tabelas de macro que discordam entre si.
    """

    sets = models.PositiveSmallIntegerField(
        "séries", default=3, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    rep_min = models.PositiveSmallIntegerField("repetições (mín)", default=8)
    rep_max = models.PositiveSmallIntegerField("repetições (máx)", default=12)
    measure = models.CharField(max_length=8, choices=Measure.choices, default=Measure.REPS)
    rest_seconds = models.PositiveSmallIntegerField(
        "descanso (s)", default=60, validators=[MinValueValidator(15), MaxValueValidator(300)]
    )

    class Meta:
        abstract = True

    @property
    def rep_range(self) -> str:
        unidade = "s" if self.measure == Measure.SECONDS else ""
        if self.rep_min == self.rep_max:
            return f"{self.rep_min}{unidade}"
        return f"{self.rep_min}-{self.rep_max}{unidade}"

    @property
    def rest_display(self) -> str:
        if self.rest_seconds >= 60 and self.rest_seconds % 60 == 0:
            return f"{self.rest_seconds // 60} min"
        if self.rest_seconds > 60:
            return f"{self.rest_seconds // 60}min{self.rest_seconds % 60:02d}"
        return f"{self.rest_seconds}s"


class WorkoutTemplateItem(PrescriptionFields):
    """Um exercício dentro de um dia de treino do catálogo."""

    template = models.ForeignKey(
        WorkoutTemplate, on_delete=models.CASCADE, related_name="items"
    )
    # PROTECT: apagar um exercício que está em fichas quebraria o histórico.
    # O caminho certo é marcar is_active=False.
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="template_items")
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta(PrescriptionFields.Meta):
        abstract = False
        verbose_name = "exercício do treino"
        verbose_name_plural = "exercícios do treino"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "exercise"], name="unique_exercise_per_template"
            )
        ]

    def __str__(self):
        return f"{self.exercise} — {self.sets}x{self.rep_range}"


class TrainingPlan(models.Model):
    """A rotina semanal ativa de uma pessoa. Snapshot, como o NutritionPlan."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_plans"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField("ativa", default=True)

    split = models.CharField("divisão", max_length=6, choices=Split.choices)
    days_per_week = models.PositiveSmallIntegerField("dias por semana")
    notes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "rotina de treino"
        verbose_name_plural = "rotinas de treino"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True),
                name="unique_active_routine_per_user",
            )
        ]

    def __str__(self):
        return f"{self.get_split_display()} ({self.days_per_week}x/semana)"


class TrainingSession(models.Model):
    """Um treino marcado num dia da semana da pessoa."""

    plan = models.ForeignKey(TrainingPlan, on_delete=models.CASCADE, related_name="sessions")
    weekday = models.PositiveSmallIntegerField("dia da semana")
    label = models.CharField("letra", max_length=1)
    name = models.CharField("nome", max_length=60)
    focus = models.CharField("foco", max_length=120, blank=True)
    start_time = models.TimeField("horário", null=True, blank=True)
    duration_min = models.PositiveSmallIntegerField("duração (min)", default=60)
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "treino da semana"
        verbose_name_plural = "treinos da semana"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "weekday"], name="unique_session_per_weekday"
            )
        ]

    def __str__(self):
        return f"{self.label} — {self.name}"

    @property
    def weekday_display(self) -> str:
        from accounts.models import Weekday

        return Weekday(self.weekday).label

    @property
    def total_sets(self) -> int:
        return sum(item.sets for item in self.exercises.all())


class SessionExercise(PrescriptionFields):
    """Um exercício da ficha, com os números congelados no dia da montagem."""

    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name="exercises"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="sessions")
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta(PrescriptionFields.Meta):
        abstract = False
        verbose_name = "exercício da ficha"
        verbose_name_plural = "exercícios da ficha"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exercise} — {self.sets}x{self.rep_range}"


class ExerciseLog(models.Model):
    """A carga que a pessoa usou numa série de um exercício, num dia.

    É o registro que transforma a ficha em treino de verdade: sem histórico de
    carga não existe progressão, e sem progressão a ficha é só uma lista de
    nomes.

    O registro é POR SÉRIE (`set_number`) desde 24/08/2026. A versão anterior
    guardava um número por exercício por dia, apostando que ninguém anota seis
    linhas no meio do treino — mas quem usa a ficha de verdade faz série pesada
    e série leve no mesmo exercício, e um número só apagava justamente a
    informação que importa. Nada obriga a preencher todas: quem quiser anotar
    só a série mais pesada preenche uma linha.

    O vínculo é com o EXERCÍCIO, não com a sessão da ficha: a rotina é refeita
    toda vez que a pessoa muda de frequência, e o histórico de carga não pode
    morrer junto. Supino é supino em qualquer divisão.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exercise_logs"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="logs")
    date = models.DateField("data")
    set_number = models.PositiveSmallIntegerField(
        "série",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    weight_kg = models.DecimalField(
        "carga (kg)",
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("999"))],
    )
    reps = models.PositiveSmallIntegerField(
        "repetições da melhor série",
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "carga registrada"
        verbose_name_plural = "cargas registradas"
        ordering = ["-date", "set_number"]
        constraints = [
            # Um registro por série por dia: anotou de novo na mesma série,
            # corrigiu. Sem isso, cada toque no botão viraria uma linha nova e o
            # "quanto eu levantei na semana passada" ficaria ambíguo.
            models.UniqueConstraint(
                fields=["user", "exercise", "date", "set_number"],
                name="unique_load_per_set_per_day",
            )
        ]
        indexes = [models.Index(fields=["user", "exercise", "-date"])]

    def __str__(self):
        return f"{self.exercise} série {self.set_number} — {self.weight_kg} kg em {self.date:%d/%m}"
