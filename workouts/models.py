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


class Equipment(models.TextChoices):
    """O que o exercício ocupa na academia.

    Existe por causa de um pedido só — "a máquina está ocupada" — e é ele que
    define o corte útil: de um lado o que forma fila (máquina, polia), do
    outro o que quase sempre sobra (halteres, peso do corpo). Barra fica no
    meio: costuma ter menos fila que máquina e mais que halter.
    """

    BARBELL = "barbell", "barra"
    DUMBBELL = "dumbbell", "halteres"
    MACHINE = "machine", "máquina"
    CABLE = "cable", "polia"
    BODYWEIGHT = "bodyweight", "peso do corpo"


#: Equipamentos que formam fila numa academia cheia. É a lista que o assistente
#: consulta quando o motivo da troca é equipamento ocupado.
DISPUTADOS = (Equipment.MACHINE, Equipment.CABLE)

#: As articulações que o app sabe nomear, e os termos que a pessoa usa para
#: falar delas. O mapa é de sinônimo para chave — "lombar", "coluna" e "costas
#: baixas" apontam todos para `lower_back`.
ARTICULACOES = {
    "knee": ("joelho", "joelhos", "patela", "menisco"),
    "shoulder": ("ombro", "ombros", "manguito", "deltoide"),
    "elbow": ("cotovelo", "cotovelos", "epicondilite"),
    "wrist": ("punho", "punhos", "pulso", "pulsos"),
    "lower_back": ("lombar", "coluna", "costas baixas", "hérnia"),
    "hip": ("quadril", "quadris", "virilha"),
    "ankle": ("tornozelo", "tornozelos", "calcanhar"),
}


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
    #: As duas fotos da demonstração: começo e fim do movimento.
    #:
    #: Lista e não dois campos porque a origem entrega uma lista, e porque a
    #: tela só alterna o que houver — se um dia vier uma sequência de quatro
    #: quadros, nada aqui muda.
    #:
    #: Preenchido por `manage.py sync_exercise_media`, que confere cada imagem
    #: antes de gravar. Vazio significa "ainda sem demonstração", e a tela cai
    #: no vídeo.
    frames = models.JSONField("quadros da demonstração", default=list, blank=True)

    #: Animação de execução — GIF, WebP, MP4 ou WebM num endereço direto.
    #:
    #: Conteúdo ANATÔMICO: que músculos o movimento recruta.
    #:
    #: O rótulo dizia "animação de execução" e o comentário logo abaixo dizia
    #: "animação anatômica" — a mesma linha se contradizia. A tela acreditou no
    #: rótulo e promoveu este campo a demonstração principal; auditado em
    #: 30/08/2026, metade dos vídeos aqui se chama literalmente "<exercício> -
    #: Músculos Trabalhados", e o supino leva ONZE segundos de diagrama antes
    #: de alguém deitar no banco. Quem apertava "ver execução" recebia aula de
    #: anatomia no meio da série.
    #:
    #: Agora o campo tem um lugar honesto: alimenta "Músculos trabalhados", que
    #: é conteúdo secundário e abre sob demanda. Execução é `video_url`.
    animation_url = models.URLField("animação anatômica", blank=True)

    video_url = models.URLField(
        "vídeo de execução",
        blank=True,
        help_text=(
            "Link de um vídeo demonstrando o movimento. Guardamos o endereço normal "
            "(o que se copia da barra do navegador); a tela converte para embed na hora."
        ),
    )
    equipment = models.CharField(
        "equipamento",
        max_length=12,
        choices=Equipment.choices,
        default=Equipment.MACHINE,
    )

    # As articulações que o movimento carrega de verdade — não toda articulação
    # que se mexe. Listar tudo tornaria a lista inútil: todo exercício teria
    # tudo e o filtro nunca separaria nada. O critério da curadoria é "alguém
    # com dor aqui sentiria neste exercício".
    joints = models.JSONField("articulações exigidas", default=list, blank=True)

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
    def disputa_equipamento(self) -> bool:
        """Costuma ter fila quando a academia enche."""
        return self.equipment in DISPUTADOS

    @property
    def animation_kind(self) -> str:
        """"youtube", "video", "imagem" ou "" — como a tela deve montar.

        O YouTube entra porque é onde as animações anatômicas existem hoje:
        Short de render 3D com destaque muscular. Sai um `<iframe>`, e não um
        `<video>` — o YouTube não serve o arquivo, serve o player.
        """
        if not self.animation_url:
            return ""

        endereco = self.animation_url.lower()
        if "youtube.com" in endereco or "youtu.be" in endereco:
            return "youtube" if self.animation_id else ""

        caminho = endereco.split("?")[0]
        if caminho.endswith((".mp4", ".webm", ".mov")):
            return "video"
        if caminho.endswith((".gif", ".webp", ".apng")):
            return "imagem"
        return ""

    @property
    def animation_id(self) -> str:
        """O identificador do vídeo, ou "" se o endereço não for reconhecido.

        Aceita as três formas em que alguém copia um link do YouTube:
        `watch?v=`, `youtu.be/` e `/shorts/`.
        """
        if not self.animation_url:
            return ""

        parts = urlparse(self.animation_url)
        if parts.netloc.endswith("youtu.be"):
            return parts.path.strip("/").split("/")[0]
        if not parts.netloc.endswith("youtube.com"):
            return ""
        if parts.path == "/watch":
            for pedaco in parts.query.split("&"):
                if pedaco.startswith("v="):
                    return pedaco[2:]
            return ""
        if parts.path.startswith(("/shorts/", "/embed/")):
            return parts.path.split("/")[2]
        return ""

    @property
    def animation_is_vertical(self) -> bool:
        """Short é 9:16; esticado em 16:9 fica com duas tarjas pretas."""
        return "/shorts/" in self.animation_url

    @property
    def animation_embed_url(self) -> str:
        """O endereço do player, já configurado para se comportar como GIF.

        `youtube-nocookie.com` não grava cookie de rastreamento antes do play —
        num app que já sabe peso e objetivo de quem usa, não faz sentido
        entregar o resto para publicidade de terceiro.

        `mute=1` não é preferência: navegador nenhum deixa vídeo com áudio
        começar sozinho, então sem ele o autoplay simplesmente não acontece. E
        `loop` exige `playlist` com o próprio id — é assim que a API do YouTube
        repete um vídeo único.
        """
        video = self.animation_id
        if not video:
            return ""
        return (
            f"https://www.youtube-nocookie.com/embed/{video}"
            f"?autoplay=1&mute=1&loop=1&playlist={video}"
            "&controls=0&modestbranding=1&playsinline=1&rel=0"
        )

    @property
    def has_frames(self) -> bool:
        """Tem demonstração em foto? É o que decide o que o drawer mostra."""
        return bool(self.frames)

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

    # -- o contrato de mídia do modo treino -------------------------------
    #
    # Uma pergunta por propriedade, para o template não precisar decidir nada:
    # `execucao_*` é o que a pessoa vê ao abrir o exercício, `anatomia_*` é o
    # extra. A ordem de qualidade da execução é vídeo, depois fotos — e nunca
    # a animação anatômica, que foi exatamente a troca que quebrou a tela.

    @property
    def execucao_tipo(self) -> str:
        """Como mostrar a execução: "youtube", "video", "gif", "fotos" ou ""."""
        if self.clip_kind:
            return self.clip_kind
        return "fotos" if self.has_frames else ""

    @property
    def execucao_src(self) -> str:
        """O endereço já pronto para o `src` — embed quando é YouTube."""
        if not self.video_url:
            return ""
        return self.video_embed_url if self.clip_kind == "youtube" else self.video_url

    @property
    def execucao_vertical(self) -> bool:
        return self.is_vertical

    @property
    def tem_anatomia(self) -> bool:
        """Só oferece "músculos trabalhados" quando há conteúdo DIFERENTE.

        Abrir um segundo botão que toca o vídeo que já está tocando não informa
        nada — e faz a tela prometer um conteúdo que ela não tem.

        A guarda nasceu porque NOVE exercícios traziam o mesmo endereço nos dois
        campos. A curadoria dos 36 vídeos de execução desfez todos: hoje o
        catálogo tem zero colisões, e há teste exigindo que continue assim. A
        propriedade fica de pé porque a origem dos dois campos é diferente
        (`exercises.json` e `animacoes.json`) e nada impede que voltem a
        coincidir.
        """
        return bool(self.animation_url) and self.animation_url != self.video_url

    @property
    def anatomia_src(self) -> str:
        if not self.tem_anatomia:
            return ""
        return (
            self.animation_embed_url
            if self.animation_kind == "youtube"
            else self.animation_url
        )

    @property
    def anatomia_vertical(self) -> bool:
        return self.animation_is_vertical


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
    ABCDE = "abcde", "ABCDE — o ciclo de quatro mais um dia de pontos fracos"


#: Quanto tempo uma série leva executando, em segundos.
#:
#: Doze repetições a dois segundos de subida e dois de descida dão 48; seis
#: repetições pesadas com pausa dão perto de 30. Quarenta é a média que
#: descreve as duas pontas sem prometer precisão que não existe — a estimativa
#: serve para a pessoa saber se cabe antes do compromisso da noite, não para
#: cronometrar a sessão.
SEGUNDOS_POR_SERIE = 40

#: Trocar de aparelho, ajustar carga, esperar liberar. Some rápido: numa ficha
#: de nove exercícios são seis minutos que ninguém contabiliza e todo mundo
#: gasta.
SEGUNDOS_ENTRE_EXERCICIOS = 45


class DurationMixin:
    """Estimativa de quanto a sessão leva, em minutos.

    A conta é série a série, e não uma média por exercício, porque o descanso
    é o que domina: agachamento com três minutos entre séries pesadas custa
    mais tempo que quatro exercícios de isolado somados.

    O último descanso de cada exercício não é contado — ele se confunde com a
    troca para o próximo, e contar os dois inflaria a estimativa em vários
    minutos numa ficha longa.
    """

    @property
    def estimated_minutes(self) -> int:
        itens = list(self.items.all() if hasattr(self, "items") else self.exercises.all())
        if not itens:
            return 0

        segundos = 0
        for item in itens:
            segundos += item.sets * SEGUNDOS_POR_SERIE
            segundos += max(item.sets - 1, 0) * item.rest_seconds
        segundos += max(len(itens) - 1, 0) * SEGUNDOS_ENTRE_EXERCICIOS

        return round(segundos / 60)


class WorkoutTemplate(DurationMixin, models.Model):
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
    def prescricao(self) -> str:
        """A prescrição escrita por extenso.

        "4 × 6-10" é notação de planilha: quem treina há anos lê de relance e
        quem está começando não lê. O cartão passa a dizer a frase inteira, e
        a notação some — o espaço custa uma linha e a clareza vale mais.
        """
        series = f"{self.sets} série" + ("s" if self.sets != 1 else "")
        if self.measure == Measure.SECONDS:
            if self.rep_min == self.rep_max:
                return f"{series} de {self.rep_min} segundos"
            return f"{series} de {self.rep_min} a {self.rep_max} segundos"
        if self.rep_min == self.rep_max:
            return f"{series} de {self.rep_min} repetições"
        return f"{series} de {self.rep_min} a {self.rep_max} repetições"

    @property
    def intensidade(self) -> str:
        """Quão perto da falha levar cada série.

        Depende do exercício, e não é detalhe. Levar agachamento e supino à
        falha em toda série é onde o risco de lesão mora e onde a fadiga
        acumulada come o treino seguinte — a recomendação usual em movimento
        multiarticular pesado é parar com uma ou duas repetições na reserva. No
        isolado o custo de falhar é baixo e o estímulo compensa.

        Um app que manda ir à falha em tudo está dando um conselho que um bom
        treinador não daria.
        """
        if self.exercise.is_compound:
            return (
                "Pare com 1 a 2 repetições na reserva — em movimento pesado, "
                "falhar toda série cobra caro no treino seguinte."
            )
        return "Leve até a falha na última série, com carga que permita a faixa."

    @property
    def rest_display(self) -> str:
        """O descanso como se lê num relógio: "1 min", "1:20 min", "45s".

        A forma anterior escrevia 80 segundos como "1min20", que na etiqueta
        lia como erro de digitação — a badge dizia "descanso 1min20" e o
        número, que ESTÁ certo (a prescrição desceu de 3 min para a faixa de
        1:00 a 1:20), parecia truncado. Dois pontos é a notação que todo
        cronômetro usa, inclusive o desta tela.
        """
        if self.rest_seconds >= 60 and self.rest_seconds % 60 == 0:
            return f"{self.rest_seconds // 60} min"
        if self.rest_seconds > 60:
            return f"{self.rest_seconds // 60}:{self.rest_seconds % 60:02d} min"
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

    # Quando o assistente ajusta a ficha, ela deixa de ser gerada e passa a ser
    # ajustada — e o gerador para de reescrevê-la. Sem isto, mudar o horário do
    # treino de terça remontaria a ficha inteira a partir do catálogo e
    # apagaria a troca de ontem sem aviso nenhum.
    customized_at = models.DateTimeField("ajustada em", null=True, blank=True)

    @property
    def is_customized(self) -> bool:
        return self.customized_at is not None

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


class TrainingSession(DurationMixin, models.Model):
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


class Corrida(models.Model):
    """Uma corrida registrada: distância, tempo e parciais.

    O TRAÇADO MORA EM `TracoDaCorrida`, E É OPCIONAL.

    Guardar coordenada é guardar onde a pessoa mora e a que horas ela sai de
    casa — dado de natureza diferente do peso, que diz quanto ela pesa. Foi por
    isso que ele ficou de fora enquanto não existia tela que o usasse: guardar
    "para quando o mapa existir" seria coletar o dado mais sensível do app por
    antecipação, que é o que este projeto recusou em outros três lugares.

    A condição que esta docstring nomeava chegou. O mapa e o resumo
    compartilhável são o produto agora, e nenhum dos dois existe sem percurso —
    então o traçado veio junto, em tabela separada, com o corte das pontas da
    rota declarado como trabalho que vem com ele e não depois dele. Ver
    `docs/running-analise.md` e `TracoDaCorrida`.

    CORRIDA SEM TRAÇADO CONTINUA VÁLIDA, e é o caso de quem sincroniza só os
    números — a PWA publicada faz exatamente isso. `traco` é `OneToOne` e pode
    não existir: toda leitura precisa tratar a ausência, e nenhuma tela pode
    supor mapa.

    `teve_lacuna` existe por causa do teto da plataforma. Uma PWA não tem
    geolocalização em segundo plano: com a tela bloqueada as leituras param.
    Marcar a corrida é o que permite a tela dizer "houve um trecho não
    registrado" em vez de mostrar uma distância menor como se fosse a real.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="corridas",
        verbose_name="usuário",
    )
    #: Gerado no navegador ANTES de enviar. Corrida é registro que a fila
    #: offline pode reenviar, e reenvio sem chave duplica a corrida — o mesmo
    #: problema que `SyncedOperation` resolve para água e suplemento. Por
    #: pessoa e não global, porque dois aparelhos podem sortear o mesmo.
    op_id = models.CharField("identificador da operação", max_length=64)

    comecou_em = models.DateTimeField("começou em")
    terminou_em = models.DateTimeField("terminou em")

    #: Metros. Inteiro porque o GPS de celular não distingue centímetros, e
    #: guardar casas decimais sugeriria uma precisão que não existe.
    distancia_m = models.PositiveIntegerField("distância (m)")

    #: Segundos EM MOVIMENTO: o tempo parado não conta. Quem para no sinal não
    #: piorou o pace.
    duracao_s = models.PositiveIntegerField("duração (s)")

    teve_lacuna = models.BooleanField("teve trecho não registrado", default=False)

    #: `[{"km": 1, "segundos": 312.0}, ...]`. Fica aqui e não em tabela própria
    #: porque nenhuma consulta precisa de uma parcial isolada: elas são lidas
    #: sempre inteiras, junto da corrida.
    parciais = models.JSONField("parciais", default=list, blank=True)

    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "corrida"
        verbose_name_plural = "corridas"
        ordering = ["-comecou_em"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "op_id"), name="uma_corrida_por_operacao"
            )
        ]
        indexes = [models.Index(fields=["user", "-comecou_em"])]

    def __str__(self):
        return f"{self.distancia_m / 1000:.2f} km em {self.duracao_s}s"

    @property
    def pace_s_km(self):
        """Segundos por quilômetro, ou `None` quando não há o que dividir.

        Propriedade e não coluna: é derivada de dois campos que já estão aqui,
        e uma terceira cópia do mesmo fato é uma cópia para ficar errada.
        """
        if not self.distancia_m or not self.duracao_s:
            return None
        return self.duracao_s * 1000 / self.distancia_m


class TracoDaCorrida(models.Model):
    """O percurso de uma corrida — em tabela própria, e isso é o desenho.

    POR QUE EXISTE AGORA, DEPOIS DE TER SIDO RECUSADO

    `Corrida` recusou o traçado enquanto não havia mapa, e a razão continua
    inteira: guardar coordenada é guardar onde a pessoa mora e a que horas ela
    sai de casa. O que mudou é exatamente a condição que aquele docstring
    nomeava — "quando o mapa for desenhado, o traçado vem com ele". Coletar por
    antecipação continua proibido; coletar para uma tela que existe é outra
    coisa, e sem percurso não há mapa nem resumo compartilhável.

    POR QUE EM TABELA SEPARADA, E NÃO NUM CAMPO DE `Corrida`

    `parciais` mora dentro da corrida porque ninguém consulta uma parcial
    isolada, e o traçado tem a mesma propriedade. A diferença é o TAMANHO: duas
    horas a uma leitura por segundo são ~7.200 pontos, e a tela de histórico
    LISTA corridas. Um `JSONField` em `Corrida` faria
    `Corrida.objects.filter(user=...)` arrastar o percurso inteiro de cada uma
    para uma tela que desenha só distância e tempo.

    Aqui o traçado só é lido quando alguém abre UMA corrida.

    O QUE É GUARDADO, E O QUE ISSO FECHA

    Os pontos ACEITOS pelo motor, não as leituras cruas. As recusadas são
    justamente as de precisão ruim e as de teleporte: guardá-las seria guardar
    mais dado sensível para desenhar um mapa pior.

    O preço está declarado em vez de descoberto depois: mudar
    `PRECISAO_MAXIMA_M` amanhã NÃO recalcula corrida antiga, porque a leitura
    que o filtro novo aceitaria já não existe. Recalcular parcial em outra
    distância continua possível — isso só depende dos pontos aceitos.

    PRIVACIDADE

    `CASCADE` a partir da corrida, que é `CASCADE` a partir do usuário: excluir
    a conta apaga o percurso junto, que é o contrato deste repositório para
    todo dado pessoal.

    Separar é também o que torna possível, depois, apagar só o traçado e manter
    a estatística — uma retenção não precisa escolher entre perder a corrida e
    guardar o endereço de casa. E o corte das pontas da rota, que impede uma
    imagem compartilhada de publicar onde a pessoa mora, opera só aqui.
    """

    corrida = models.OneToOneField(
        Corrida,
        on_delete=models.CASCADE,
        related_name="traco",
        verbose_name="corrida",
    )

    #: `[{"lat": -23.5, "lon": -46.6, "t": 0.0, "acumulado_m": 0.0}, ...]`,
    #: na ordem em que o motor aceitou. `acumulado_m` vem junto porque é o que
    #: permite redesenhar a parcial sem repetir o haversine ponto a ponto.
    pontos = models.JSONField("pontos", default=list)

    #: Quantas leituras o motor recusou. Fica porque é o que explica um mapa
    #: com buraco: sem este número, um traçado picotado parece defeito de
    #: desenho quando é a rua que estava sem sinal.
    descartadas = models.PositiveIntegerField("leituras descartadas", default=0)

    class Meta:
        verbose_name = "traçado da corrida"
        verbose_name_plural = "traçados das corridas"

    def __str__(self):
        return f"{len(self.pontos)} pontos"
