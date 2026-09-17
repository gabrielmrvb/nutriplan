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
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote_plus, urlparse

from django.conf import settings
from django.utils import timezone
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
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

    NASCEU PARA O ASSISTENTE DE TROCA, QUE NÃO EXISTE MAIS. O corte — de um
    lado o que forma fila (máquina, polia), do outro o que quase sempre sobra
    (halteres, peso do corpo) — servia a um pedido só: "a máquina está
    ocupada". O assistente entrou em `7819b30` e saiu em `d86d9c7`, e junto com
    ele foi embora o único leitor deste campo. `DISPUTADOS` e
    `disputa_equipamento` sobreviveram à remoção como código morto por três
    campanhas, e saíram em 10/09/2026.

    DESDE 17/09/2026 O MOTOR LÊ ESTE CAMPO: `services.substituir_por_equipamento`
    troca, antes de prescrever, o item do modelo cujo equipamento está fora do
    perfil da pessoa (`accounts.models.Equipamento`, mapa no `TREINO.md`) por
    um exercício ativo do mesmo `padrao` e grupo dentro do perfil. Por
    substituição, e não por filtro: um filtro abriria buraco nos modelos
    curados — `workouts/test_capacidade_de_ambiente.py` mediu isso em
    10/09/2026 e mede hoje o que cada perfil ainda perde.
    """

    BARBELL = "barbell", "barra"
    DUMBBELL = "dumbbell", "halteres"
    MACHINE = "machine", "máquina"
    CABLE = "cable", "polia"
    BODYWEIGHT = "bodyweight", "peso do corpo"


class Padrao(models.TextChoices):
    """O PADRÃO DE MOVIMENTO — o que uma troca de exercício preserva.

    Um nível só, 22 valores (16/09/2026). Ângulo e pegada ficam no NOME:
    supino reto, inclinado e flexão de braço são a mesma pressão de peito;
    elevação lateral e frontal a mesma elevação; rosca direta e martelo a
    mesma rosca. Se um dia isso precisar de distinção, é um campo
    `variante`, não um padrão novo — separar reto de inclinado deixaria
    "Peito e tríceps" sem duas opções com o catálogo de hoje, por um
    detalhe que nenhuma troca de exercício invalida.

    Quem lê isto é a régua de equivalência das opções
    (`workouts.opcoes.equivalentes`): duas opções da mesma letra precisam
    dos MESMOS padrões COMPOSTOS em cada grupo anunciado — três supinos
    contra três crucifixos não são intercambiáveis —, e podem diferir nos
    isoladores. `PADROES_COMPOSTOS` diz quais são compostos; `is_compound`
    continua decidindo série e descanso, e os dois têm de concordar (há
    teste).
    """

    PRESSAO_DE_PEITO = "pressao_de_peito", "pressão de peito"
    CRUCIFIXO = "crucifixo", "crucifixo"
    PUXADA_VERTICAL = "puxada_vertical", "puxada vertical"
    REMADA_HORIZONTAL = "remada_horizontal", "remada horizontal"
    PRESSAO_VERTICAL = "pressao_vertical", "pressão vertical"
    ELEVACAO = "elevacao", "elevação de ombro"
    DELTOIDE_POSTERIOR = "deltoide_posterior", "deltoide posterior"
    AGACHAMENTO = "agachamento", "agachamento"
    EXTENSAO_DE_JOELHO = "extensao_de_joelho", "extensão de joelho"
    EXTENSAO_DE_QUADRIL = "extensao_de_quadril", "extensão de quadril"
    FLEXAO_DE_JOELHO = "flexao_de_joelho", "flexão de joelho"
    FLEXAO_PLANTAR = "flexao_plantar", "flexão plantar"
    ROSCA = "rosca", "rosca"
    EXTENSAO_DE_COTOVELO = "extensao_de_cotovelo", "extensão de cotovelo"
    PRESSAO_FECHADA = "pressao_fechada", "pressão fechada"
    ANTI_EXTENSAO = "anti_extensao", "anti-extensão"
    FLEXAO_DE_TRONCO = "flexao_de_tronco", "flexão de tronco"
    FLEXAO_DE_QUADRIL = "flexao_de_quadril", "flexão de quadril"
    ELEVACAO_ESCAPULAR = "elevacao_escapular", "elevação escapular"
    REMADA_ALTA = "remada_alta", "remada alta"
    FLEXAO_DE_PUNHO = "flexao_de_punho", "flexão de punho"
    EXTENSAO_DE_PUNHO = "extensao_de_punho", "extensão de punho"


#: Os padrões que são MOVIMENTO COMPOSTO — o que as duas opções de uma letra
#: têm de cobrir igualmente. O resto é isolamento, e pode diferir entre elas.
PADROES_COMPOSTOS = frozenset({
    Padrao.PRESSAO_DE_PEITO,
    Padrao.PUXADA_VERTICAL,
    Padrao.REMADA_HORIZONTAL,
    Padrao.PRESSAO_VERTICAL,
    Padrao.AGACHAMENTO,
    Padrao.EXTENSAO_DE_QUADRIL,
    Padrao.PRESSAO_FECHADA,
    Padrao.REMADA_ALTA,
})


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

    #: O segundo em que a EXECUÇÃO começa dentro do vídeo.
    #:
    #: A demonstração quase nunca começa no zero: há apresentação, conversa,
    #: preparação e posicionamento antes de alguém levantar o peso. Quem abre
    #: "ver execução" no meio da série não quer nada disso — quer o movimento.
    #:
    #: `null` significa "ninguém conferiu este vídeo ainda", e o player começa
    #: do zero, que é exatamente o comportamento de antes deste campo existir.
    #: NÃO é o mesmo que zero: zero é "conferido, e começa no início".
    video_start_seconds = models.PositiveSmallIntegerField(
        "início da execução (s)",
        null=True,
        blank=True,
        help_text=(
            "Segundo em que a demonstração do movimento começa de verdade. "
            "Deixe vazio se você não assistiu ao vídeo para conferir."
        ),
    )

    #: O segundo em que a execução termina. Opcional mesmo com `start`
    #: preenchido: saber onde começa é útil sozinho.
    video_end_seconds = models.PositiveSmallIntegerField(
        "fim da execução (s)",
        null=True,
        blank=True,
        help_text="Opcional. Precisa ser maior que o início.",
    )

    #: Os músculos que o movimento TAMBÉM recruta, além do principal.
    #:
    #: O principal continua sendo `muscle_group`, e não foi renomeado: ele está
    #: em `muscle_volume`, na geração da ficha, nos filtros e no histórico.
    #: Trocar o nome do campo para agradar a simetria custaria uma migração de
    #: dados em cima de tudo isso, para não melhorar nada.
    #:
    #: O CRITÉRIO DA CURADORIA, no mesmo molde de `joints`: entra o músculo
    #: que o movimento carrega DE VERDADE, não todo músculo que se contrai.
    #: Listar tudo em tudo tornaria a informação inútil — todo exercício teria
    #: quase todos os grupos e a tela deixaria de dizer alguma coisa. Para o
    #: antebraço, que é o caso limite, a régua é "a pega é o que falha antes":
    #: ela entra nas puxadas e nas roscas, e não no stiff, em que a barra é
    #: segurada por poucos segundos por série.
    #:
    #: JSONField com valores de `MuscleGroup`, no mesmo molde de `joints` — e
    #: não uma tabela `Muscle` com `ManyToMany`. A taxonomia JÁ existe como
    #: `TextChoices`; criar a tabela seria uma SEGUNDA taxonomia, com dois
    #: lugares para dizer "peito" e a garantia de que um dia eles divergem.
    #: O que faz disto relação estruturada, e não texto livre, é a validação:
    #: `clean()` recusa valor fora da taxonomia e recusa repetir o principal.
    secondary_muscles = models.JSONField(
        "músculos secundários",
        default=list,
        blank=True,
        help_text="Lista de grupos musculares auxiliares, da mesma taxonomia.",
    )
    equipment = models.CharField(
        "equipamento",
        max_length=12,
        choices=Equipment.choices,
        default=Equipment.MACHINE,
    )
    #: O padrão de movimento (`Padrao`). Sem padrão o exercício não entra:
    #: `padrao_nao_vazio` é constraint de banco, porque é o que a régua de
    #: equivalência lê — e um exercício sem padrão tornaria duas opções
    #: "equivalentes" por omissão. O `default=""` existe só para a migration
    #: que acrescenta a coluna; o `RunPython` dela preenche os 36 e a
    #: constraint entra depois.
    padrao = models.CharField(
        "padrão de movimento", max_length=24, choices=Padrao.choices, default="",
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
        constraints = [
            # Nenhum exercício sem padrão nem sem equipamento — e é o banco
            # quem garante, pela mesma razão de
            # `prioridade_pertence_aos_interesses`: `clean()` não roda no
            # `update_or_create` do seed.
            models.CheckConstraint(
                condition=~models.Q(padrao=""), name="padrao_nao_vazio",
            ),
            models.CheckConstraint(
                condition=~models.Q(equipment=""), name="equipment_nao_vazio",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """As três regras que fazem os campos novos serem dado, e não texto.

        ONDE ELAS RODAM DE VERDADE — e a primeira versão desta docstring
        mentia sobre isto. O Django NÃO chama `clean()` em `save()`, então
        quem passa por aqui é o ADMIN (via `ModelForm`) e quem chamar
        `full_clean()` de propósito. O seed usa `update_or_create`, que não
        valida; o `shell` também não.

        A rede do catálogo é, portanto, um TESTE:
        `OCatalogoSemeadoEValidoTests.test_todo_exercicio_do_catalogo_passa_no_full_clean`
        chama `full_clean()` em todos os 36, e um "gluteos" digitado em
        `exercises.json` aparece ali — não em produção.

        Constraint de banco resolveria de vez, e não dá: o PostgreSQL não sabe
        ler `MuscleGroup`, e um `CHECK` sobre JSON seria uma segunda cópia da
        taxonomia dentro do banco — exatamente o que esta fase não pode criar.
        É a diferença para `prioridade_pertence_aos_interesses`, em `accounts`,
        que compara colunas e por isso pôde virar `CheckConstraint`.
        """
        super().clean()
        erros = {}

        validos = {escolha.value for escolha in MuscleGroup}
        secundarios = self.secondary_muscles or []
        if not isinstance(secundarios, list):
            erros["secondary_muscles"] = "Precisa ser uma lista."
        else:
            fora = [m for m in secundarios if m not in validos]
            if fora:
                erros["secondary_muscles"] = (
                    "Fora da taxonomia: %s. Use os valores de MuscleGroup."
                    % ", ".join(map(str, fora))
                )
            elif len(set(secundarios)) != len(secundarios):
                erros["secondary_muscles"] = "Há grupo repetido na lista."
            elif self.muscle_group in secundarios:
                # Um músculo é principal OU auxiliar, não os dois: repetido, ele
                # apareceria duas vezes na tela e sugeriria estímulo duplo.
                erros["secondary_muscles"] = (
                    "%s já é o grupo principal deste exercício."
                    % self.get_muscle_group_display()
                )

        inicio, fim = self.video_start_seconds, self.video_end_seconds
        if fim is not None and inicio is not None and fim <= inicio:
            erros["video_end_seconds"] = "O fim precisa ser depois do início."
        if fim is not None and inicio is None:
            # Fim sem início é recorte pela metade: o player abriria no zero e
            # pararia no meio, que é pior que não recortar.
            erros["video_end_seconds"] = "Informe também o início da execução."

        if erros:
            raise ValidationError(erros)

    @property
    def secondary_muscle_labels(self) -> list:
        """Os nomes de tela dos auxiliares, na ordem da taxonomia.

        Ordem da taxonomia e não a de digitação: duas pessoas cadastrando o
        mesmo exercício em ordens diferentes produziriam duas telas diferentes
        para o mesmo fato.
        """
        rotulos = {escolha.value: escolha.label for escolha in MuscleGroup}
        return [
            rotulos[escolha.value]
            for escolha in MuscleGroup
            if escolha.value in (self.secondary_muscles or [])
        ]

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

        # O RECORTE DA EXECUÇÃO.
        #
        # `start` e `end` são parâmetros do próprio player do YouTube. Eles
        # entram só quando há valor conferido: sem eles a URL sai byte a byte
        # igual à de antes deste campo existir, que é o que mantém os 36
        # exercícios já cadastrados funcionando sem tocar em nenhum.
        #
        # `end` sozinho não existe — `clean()` recusa —, então não há caminho
        # que produza um corte pela metade.
        #
        # UMA LIMITAÇÃO REAL, e ela é do player: com `loop=1`, o YouTube
        # reinicia do começo do vídeo, não do `start`. A segunda volta perde o
        # recorte. Trocar o loop por um controlador de tempo exigiria a API
        # `iframe_api`, que é script de terceiro carregado em toda abertura do
        # drawer — caro para um ganho que só aparece na repetição. Fica assim,
        # e fica escrito.
        recorte = ""
        if self.video_start_seconds is not None:
            recorte += f"&start={self.video_start_seconds}"
            if self.video_end_seconds is not None:
                recorte += f"&end={self.video_end_seconds}"

        return (
            f"https://www.youtube-nocookie.com/embed/{video}"
            f"?autoplay=1&mute=1&loop=1&playlist={video}"
            "&controls=0&modestbranding=1&playsinline=1&rel=0"
            f"{recorte}"
        )

    @property
    def sem_carga(self) -> bool:
        """Peso do corpo: não há anilha para anotar nem para subir.

        É a pergunta que a execução e a progressão fazem, e ela mora aqui — e
        não em `services.py` — de propósito: `test_o_motor_nao_le_equipamento`
        proíbe o motor de ler `equipment`, porque a prescrição não filtra por
        equipamento (ver `test_capacidade_de_ambiente.py`). "Tem anilha?" é
        uma propriedade do exercício; o motor lê a propriedade, não o campo.
        """
        return self.equipment == "bodyweight"

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
    ABC2 = "abc2", "ABC de dois grupos — peito/tríceps, costas/bíceps e pernas/ombros"
    ABCD = "abcd", "ABCD — peito/tríceps, costas/bíceps, ombro/perna e complementares"
    ABCDE = "abcde", "ABCDE — peito, costas, pernas, ombros e braços, um por dia"


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

#: Chegar, trocar de roupa não conta — mas subir a frequência cardíaca, soltar
#: o quadril e o ombro, sim. Cinco minutos é o que uma preparação honesta leva,
#: e ela acontece uma vez por sessão.
AQUECIMENTO_GERAL_SEGUNDOS = 300

#: Séries de aproximação num exercício COMPOSTO, que não são séries de trabalho.
#:
#: Ninguém deita no supino direto na carga de trabalho. Duas aproximações, cada
#: uma com execução curta e um descanso menor que o da série pesada: 2 × (20s de
#: execução + 45s de pausa) = 130s. Elas não entram em `sets` — `sets` é volume
#: de trabalho, e contá-las ali inflaria o histórico de carga — mas ocupam o
#: relógio e por isso entram AQUI.
AQUECIMENTO_DO_COMPOSTO_SEGUNDOS = 130


def segundos_da_sessao(itens) -> int:
    """Quanto a sessão leva, em segundos. A ÚNICA conta de duração do projeto.

    `itens` são tuplas `(séries, descanso, é_composto)` na ordem da ficha.

    Existia em duas cópias — aqui e em `services._segundos_da_sessao` —, uma
    sobre linhas gravadas e outra sobre tuplas, porque o gerador precisa da
    conta ANTES de gravar. O comentário de lá admitia a duplicação e dizia que
    um teste prendia as duas. Prender duas cópias é melhor que nada e pior que
    ter uma; agora as duas chamam esta.

    A conta é série a série, e não uma média por exercício, porque o descanso é
    o que domina: agachamento com séries pesadas custa mais tempo que quatro
    isolados somados.

    O QUE MUDOU EM 08/09/2026, e cada item é um minuto que a estimativa
    escondia:

    - **aquecimento**, geral e de aproximação nos compostos. A versão anterior
      começava a contar na primeira série de trabalho;
    - **a troca entre exercícios é o MAIOR entre o descanso e a caminhada.**
      Antes eram 45 segundos fixos, e quem descansa 80 entre séries não troca de
      aparelho em 45. É também onde o descanso depois da última série de cada
      exercício voltou a ser contado: ele existe, e se confunde com a troca —
      por isso um `max`, e não uma soma;
    - nada depois do último exercício: ali a pessoa vai embora.
    """
    if not itens:
        return 0

    segundos = AQUECIMENTO_GERAL_SEGUNDOS
    ultimo = len(itens) - 1
    for posicao, (series, descanso, composto) in enumerate(itens):
        if composto:
            segundos += AQUECIMENTO_DO_COMPOSTO_SEGUNDOS
        segundos += series * SEGUNDOS_POR_SERIE
        segundos += max(series - 1, 0) * descanso
        if posicao < ultimo:
            segundos += max(descanso, SEGUNDOS_ENTRE_EXERCICIOS)
    return segundos


class DurationMixin:
    """Estimativa de quanto a sessão leva, em minutos.

    A conta mora em `segundos_da_sessao`, e este mixin só a alimenta com as
    linhas que ele tem. Uma fonte, dois chamadores.
    """

    @property
    def estimated_minutes(self) -> int:
        itens = list(self.items.all() if hasattr(self, "items") else self.exercises.all())
        return minutos_de(itens)


def minutos_de(itens) -> int:
    """Minutos de uma lista de linhas (modelo ou ficha), pela conta única."""
    return round(
        segundos_da_sessao(
            [(item.sets, item.rest_seconds, item.exercise.is_compound) for item in itens]
        )
        / 60
    )


class WorkoutTemplate(DurationMixin, models.Model):
    """Um dia de treino dentro de uma divisão: o "A" do ABC, por exemplo."""

    split = models.CharField("divisão", max_length=6, choices=Split.choices)
    label = models.CharField("letra", max_length=1)
    name = models.CharField("nome", max_length=60)
    focus = models.CharField("foco", max_length=120, blank=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)
    #: Os grupos que o NOME desta sessão promete. É curadoria, não dedução.
    #:
    #: O que está na ficha e não está aqui é COMPLEMENTAR — panturrilha no dia
    #: de perna, abdômen no fim, trapézio junto das costas. A distinção decide
    #: duas coisas concretas: complementar é o primeiro a ceder quando falta
    #: tempo (`escolher_para_o_tempo`) e não entra na conta do título honesto
    #: (`titulo_honesto`), porque o título não o prometeu.
    #:
    #: DEDUZIR ISSO SERIA PIOR. "Grupo com poucos exercícios" chamaria o ombro
    #: de complementar no `abcd C`, que se chama "Pernas e ombros"; "grupo de
    #: isoladores" chamaria o trapézio de complementar no `abcd D`, que existe
    #: para ele. Quem sabe o que o nome promete é quem escreveu o nome.
    main_groups = models.JSONField("grupos anunciados", default=list, blank=True)

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
        """Quão perto da falha levar cada série, sem saber qual série é.

        É o texto NEUTRO — sem série e sem nível — para quem lê a prescrição
        fora da execução. A execução usa `instrucao_de_esforco`, que sabe a
        série da vez e a experiência da pessoa. Ver a função, logo abaixo.
        """
        return instrucao_de_esforco(self, None, "")

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


#: Até este `rep_max` a última série de composto diz "mesmo passando de N":
#: a faixa é alvo de progressão, não teto — quem fecha 10 com 1 a 2 sobrando
#: faz 11 (Helms 2016: RIR governa, o número é orientação). Acima disso
#: (15, 20) a faixa já é longa e o aviso vira ruído.
REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO = 12

#: A partir desta idade nenhuma série pede falha, nem o isolador: em quem
#: tem 65 ou mais a recuperação e o risco articular pesam mais que a última
#: repetição (Fragala 2019, posição da NSCA para idosos).
IDADE_CAUTELOSA = 65


def instrucao_de_esforco(item, serie, experiencia, cauteloso=False) -> str:
    """Quão perto da falha levar ESTA série, para ESTA pessoa.

    Existia como `intensidade` — "1 a 2 na reserva" no composto, "até a
    falha" no isolador — e era renderizada no cartão do exercício. Saiu da
    tela no redesenho de 12/09/2026 sem constar na lista do que mudou de
    lugar; a pesquisa de 13/09 achou zero ocorrências em `templates/`. Volta
    aqui, e volta sabendo duas coisas que o texto antigo não sabia (Refalo
    2023/2024, Helms 2016):

    - o ISOLADOR só vai à falha na ÚLTIMA série. Falhar em toda série
      acrescenta fadiga, não estímulo; nas anteriores fica 1 a 2 na reserva;
    - o INICIANTE nunca lê "até a falha" em composto e para com 2 sobrando:
      em quem ainda aprende o movimento, técnica vale mais que a última
      repetição.

    `serie=None` é o texto neutro (sem "última"); `experiencia == ""` é "ainda
    não respondeu" e recebe o texto do intermediário — o mesmo critério de
    `teto_semanal_de`: a tela nunca afirma nível que a pessoa não declarou.
    Segundos (prancha) não têm repetição para reservar: o limite é a técnica.

    T2.2 (17/09/2026), duas coisas a mais:

    - a ÚLTIMA série de composto com `rep_max` até 12 diz "mesmo passando de
      N": a faixa de reps é alvo de progressão, não teto — quem chega em 10
      com 1 a 2 sobrando continua. Com faixa longa (15+) o aviso não entra;
    - `cauteloso` (65 anos ou mais, `IDADE_CAUTELOSA`) nunca lê "falha", nem
      no isolador: a última série pede 1 na reserva e técnica limpa.

    É função pura, sem consulta, para a execução chamá-la por série e o
    teste medi-la sem banco.
    """
    # Frases de UMA LINHA A 320PX, de propósito: cada linha a mais aqui
    # empurra "Concluir série" para baixo. Medido em 13/09/2026: a versão de
    # duas orações custava 61px a 390 e 44 a 360; estas custam 26 em todas.
    # Quem for reescrever mede a altura de `.series__esforco` a 320 antes.
    if item.measure == Measure.SECONDS:
        return "Segure até a técnica ceder."
    iniciante = experiencia == "iniciante"
    ultima = serie is not None and serie >= item.sets
    rep_max = getattr(item, "rep_max", None) or 0
    if item.exercise.is_compound:
        conservador = iniciante or cauteloso
        if ultima and 0 < rep_max <= REP_MAX_EM_QUE_A_FAIXA_NAO_E_TETO:
            # Medido a 320px em 17/09: "Pare com 1–2 sobrando, mesmo passando
            # de 10." (44 caracteres) quebrava em duas linhas; esta cabe em uma.
            return "%s sobrando, mesmo passando de %d." % ("2" if conservador else "1 a 2", rep_max)
        if conservador:
            return "2 sobrando: técnica antes de peso."
        return "1 a 2 repetições na reserva, sem falhar."
    if cauteloso:
        if ultima:
            return "Última série: 1 na reserva, técnica limpa."
        return "1 a 2 na reserva, técnica limpa."
    if ultima:
        return "Última série: até a falha, na faixa."
    return "1 a 2 na reserva; falha só na última série."


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
    #: Quando a pessoa dispensou o aviso "Seu treino pode ficar mais completo —
    #: regenerar?" (17/09/2026). No plano, e não no navegador: um aviso que
    #: volta em cada aparelho é ruído. `None` é "nunca dispensou".
    aviso_dispensado_em = models.DateTimeField("aviso de regenerar dispensado em", null=True, blank=True)
    #: RETRATO DAS ENTRADAS (17/09/2026): com que catálogo (a impressão
    #: digital de `exercises.json`, `splits.json` e `TREINO.md` —
    #: `services.versao_do_catalogo`), que nível e que faixa de duração a
    #: ficha foi montada. Nível ou faixa diferentes do perfil de hoje: a
    #: pessoa mexeu na PRÓPRIA entrada, a ficha ficou inválida e é remontada
    #: como sempre foi. Catálogo diferente: a ficha fica — plano é retrato —
    #: e a Home pergunta. Vazio é "montada antes de 17/09", desconhecido, e
    #: desconhecido não invalida nada: o catálogo vazio cai na conferência
    #: exata da prescrição, que é como o aviso chega a quem já tinha ficha.
    catalogo = models.CharField("catálogo de origem", max_length=64, blank=True, default="")
    nivel = models.CharField("nível de origem", max_length=20, blank=True, default="")
    duracao = models.CharField("faixa de duração de origem", max_length=10, blank=True, default="")
    #: O perfil de equipamento com que a ficha nasceu (`accounts.models.
    #: Equipamento`, 17/09/2026). Default "completa" e NÃO vazio, ao contrário
    #: de nível e faixa: toda ficha anterior à pergunta foi montada com o
    #: catálogo inteiro, então "completa" é a verdade dela — e igual ao
    #: default do perfil, nada é remontado pela pergunta nova. Mudou no
    #: perfil, a ficha ficou inválida e remonta.
    equipamento = models.CharField("equipamento de origem", max_length=15, default="completa")
    #: O CICLO RODA CONTÍNUO (17/09/2026): a posição zero é o primeiro dia de
    #: treino do plano, e a letra de qualquer data é a da posição dela na
    #: sequência de dias de treino — A B C A B, depois C A B C A, depois
    #: B C A B C. As linhas de `sessions` continuam uma por dia da semana (o
    #: retrato de dias, horários e durações) com a letra da PRIMEIRA semana;
    #: `services.sessao_do_dia` é quem diz a letra de hoje. Em branco é plano
    #: de antes da rotação: preso ao dia da semana, como sempre foi — a Home
    #: pergunta, o painel não remonta (política da Fase 5).
    inicio_do_ciclo = models.DateField("início do ciclo", null=True, blank=True)

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
    #: Cópia congelada de `WorkoutTemplate.main_groups`, pela mesma razão que
    #: `name` e `focus` são cópias: plano é RETRATO. Mudar o catálogo não pode
    #: reescrever a ficha de quem já treina com ela.
    main_groups = models.JSONField("grupos anunciados", default=list, blank=True)
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

    # ---------------------------------------------------------------- opções
    #
    # UMA LETRA, ATÉ DUAS VERSÕES (15/09/2026). Cada linha da ficha diz a que
    # opção pertence (`SessionExercise.opcao`); a sessão guarda as duas, e a
    # pessoa escolhe qual faz no dia (`EscolhaDeTreino`). "Todas as linhas"
    # (`exercises.all()`) NÃO é uma sessão — é a soma de duas — e é por isso
    # que total, duração e listas passam por `da_opcao`. Plano antigo tem
    # tudo em `opcao=1` e continua sendo lido pelas mesmas propriedades.

    @property
    def opcoes(self) -> list:
        """Os números das opções desta sessão, em ordem — `[1]` ou `[1, 2]`."""
        return sorted({item.opcao for item in self.exercises.all()}) or [1]

    @property
    def tem_duas_opcoes(self) -> bool:
        return len(self.opcoes) > 1

    def da_opcao(self, opcao) -> list:
        """As linhas da ficha de UMA opção, na ordem da ficha."""
        return [item for item in self.exercises.all() if item.opcao == opcao]

    def series_da_opcao(self, opcao) -> int:
        return sum(item.sets for item in self.da_opcao(opcao))

    def minutos_da_opcao(self, opcao) -> int:
        return minutos_de(self.da_opcao(opcao))

    @property
    def total_sets(self) -> int:
        """As séries de UMA sessão: a opção 1 é a referência para a semana.

        As duas opções são equivalentes por construção (diferença ≤ 1 série
        por grupo), então a referência vale para qualquer escolha — e somar
        as duas diria que a pessoa faz os dois treinos no mesmo dia."""
        return self.series_da_opcao(self.opcoes[0])

    @property
    def estimated_minutes(self) -> int:
        return self.minutos_da_opcao(self.opcoes[0])

    def _particiona(self, opcao=None):
        """A ficha em duas listas: o que o título promete, e o resto.

        Uma passagem só sobre `exercises`, porque a tela pede as duas e
        `prefetch_related` já trouxe tudo — pedir duas vezes custaria consulta
        em cada cartão da semana.
        """
        anunciados = set(self.main_groups or ())
        principais, complementares = [], []
        linhas = self.da_opcao(opcao) if opcao is not None else self.da_opcao(self.opcoes[0])
        for item in linhas:
            alvo = (
                complementares
                if anunciados and item.exercise.muscle_group not in anunciados
                else principais
            )
            alvo.append(item)
        return principais, complementares

    @property
    def exercicios_principais(self) -> list:
        return self._particiona()[0]

    def principais_da_opcao(self, opcao) -> list:
        return self._particiona(opcao)[0]

    def complementares_da_opcao(self, opcao) -> list:
        return self._particiona(opcao)[1]

    @property
    def exercicios_complementares(self) -> list:
        """O que entra além do que o título promete.

        Existe para a ficha poder DIZER isso — "Complementares desta sessão" —
        em vez de misturar panturrilha com agachamento numa lista só e deixar
        a pessoa achar que o dia perdeu um exercício de perna quando o que
        saiu foi a panturrilha.
        """
        return self._particiona()[1]


class SessionExercise(PrescriptionFields):
    """Um exercício da ficha, com os números congelados no dia da montagem."""

    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name="exercises"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="sessions")
    order = models.PositiveSmallIntegerField("ordem", default=0)
    #: A que VERSÃO da letra esta linha pertence. Uma letra tem até duas
    #: opções completas e equivalentes; a pessoa faz UMA por dia. Plano
    #: anterior a 15/09/2026 tem tudo em 1 — uma opção só, e continua lido
    #: pelas mesmas telas.
    opcao = models.PositiveSmallIntegerField("opção", default=1)

    class Meta(PrescriptionFields.Meta):
        abstract = False
        verbose_name = "exercício da ficha"
        verbose_name_plural = "exercícios da ficha"
        ordering = ["opcao", "order", "id"]

    def __str__(self):
        return f"{self.exercise} — {self.sets}x{self.rep_range}"


class VersaoDoTreino(models.TextChoices):
    COMPLETO = "completo", "Treino completo"
    RAPIDO = "rapido", "Versão rápida"


class EventoDeProduto(models.Model):
    """Um uso de uma feature que está EM AVALIAÇÃO — o dado que decide se
    ela fica (17/09/2026). Um por pessoa, nome e dia: é contagem de adoção,
    não telemetria de toque. Hoje só `versao_rapida` ("Menos tempo hoje?"
    no painel), a decidir em 30 dias; `medir_progressao` conta."""

    VERSAO_RAPIDA = "versao_rapida"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="eventos_de_produto",
        verbose_name="usuário",
    )
    nome = models.CharField("evento", max_length=40)
    date = models.DateField("dia", default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evento de produto"
        verbose_name_plural = "eventos de produto"
        constraints = [
            models.UniqueConstraint(fields=("user", "nome", "date"), name="um_evento_por_pessoa_e_dia"),
        ]

    def __str__(self):
        return "%s · %s" % (self.nome, self.date)


class TrocaDeExercicio(models.Model):
    """"Outras formas" (17/09/2026): a pessoa trocou UM exercício da ficha
    por outro do mesmo padrão e grupo, dentro do que ela tem para treinar.

    É customização POR EXERCÍCIO — vale em toda letra, toda semana e toda
    opção em que `original` apareça —, e NÃO toca em `SessionExercise` nem
    em `customized_at`: a ficha continua retrato, a rotação continua, e
    `rotina_invalida`/`_prescricao_bate` não enxergam a troca. A aplicação é
    em memória (`services.aplicar_trocas`): o item passa a apontar para o
    substituto com a MESMA dose (séries, faixa, descanso), então trocar não
    altera séries nem volume da sessão. `ExerciseLog` grava no exercício
    FEITO (o substituto); a leitura mostra "no lugar de <original>" com o
    histórico do original ao lado. Estado absoluto, uma por (pessoa,
    original): trocar de novo atualiza, desfazer apaga.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trocas_de_exercicio",
        verbose_name="usuário",
    )
    original = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="trocas_como_original", verbose_name="original",
    )
    substituto = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="trocas_como_substituto", verbose_name="substituto",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "troca de exercício"
        verbose_name_plural = "trocas de exercício"
        constraints = [
            models.UniqueConstraint(fields=("user", "original"), name="uma_troca_por_exercicio_e_pessoa"),
            models.CheckConstraint(condition=~models.Q(original=models.F("substituto")), name="troca_muda_de_exercicio"),
        ]

    def __str__(self):
        return "%s → %s" % (self.original_id, self.substituto_id)


class EscolhaDeTreino(models.Model):
    """Qual opção (e qual versão) a pessoa fez num dia.

    É o único estado que a execução guarda além de `ExerciseLog`, e existe
    por uma razão só: a letra tem duas versões, e "qual delas eu fiz na
    terça" não se deduz das séries — as duas podem ter o supino. A recomendação
    ("a menos usada recentemente") lê daqui; o histórico e o compartilhamento
    também.

    Uma por pessoa por dia: o app não tem dois treinos no mesmo dia, e a
    unicidade é o que faz o duplo toque em "Começar esta opção" ser
    idempotente. Trocar de opção DEPOIS da primeira série é permitido com
    confirmação e não apaga registro nenhum — `ExerciseLog` é por exercício e
    data, e o exercício continua tendo sido feito.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="escolhas_de_treino"
    )
    date = models.DateField("data")
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name="escolhas"
    )
    opcao = models.PositiveSmallIntegerField("opção", default=1)
    versao = models.CharField(
        "versão", max_length=8, choices=VersaoDoTreino.choices, default=VersaoDoTreino.COMPLETO
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "escolha de treino"
        verbose_name_plural = "escolhas de treino"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="uma_escolha_de_treino_por_dia")
        ]

    def __str__(self):
        return f"{self.session.label} · opção {self.opcao} · {self.date:%d/%m}"


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

    class Origem(models.TextChoices):
        GPS = "gps", "GPS"
        MANUAL = "manual", "à mão"

    class Sensacao(models.TextChoices):
        LEVE = "leve", "leve"
        NORMAL = "normal", "normal"
        PESADA = "pesada", "pesada"

    #: De onde veio o número. O GPS traz parciais e traço; o registro à mão traz
    #: só distância e tempo — e por isso só ele se edita (BENCHMARK-2026-09, d).
    origem = models.CharField(max_length=8, choices=Origem.choices, default=Origem.GPS)
    #: Como foi. Vazio para o GPS (a tela do GPS não pergunta — ainda).
    sensacao = models.CharField(max_length=8, choices=Sensacao.choices, blank=True, default="")

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


class PlanoDeCorrida(models.Model):
    """O plano de 5K ou 10K que a pessoa escolheu seguir.

    NÃO GUARDA O CONTEÚDO DA SEMANA — só plano, nível e a data de início.
    O que cada semana pede (`workouts/doutrina_corrida.py::sessoes`) vem de
    `docs/briefs/corrida/CORRIDA.md`, lido toda vez: é a mesma decisão de
    `TrainingPlan` não guardar as tabelas do `TREINO.md`, uma linha a mais
    dela — aqui nem cabe "plano é retrato", porque a doutrina de corrida não
    tem entrada nenhuma da pessoa para mudar (peso, nível de atividade...): o
    plano é só "5K iniciante, começou no dia X", e a semana atual é aritmética
    sobre essa data.

    UM ATIVO POR PESSOA, como `TrainingPlan` — a constraint parcial é a mesma
    forma, e `PlanoDeCorridaView` desativa o antigo antes de criar o novo,
    dentro da mesma transação, pela mesma razão de `services.create_routine`:
    o índice único parcial não deixa os dois ativos coexistirem nem por um
    instante.
    """

    class Plano(models.TextChoices):
        CINCO_K = "5k", "5K"
        DEZ_K = "10k", "10K"

    class Nivel(models.TextChoices):
        INICIANTE = "iniciante", "iniciante"
        INTERMEDIARIO = "intermediario", "intermediário"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="planos_de_corrida",
        verbose_name="usuário",
    )
    plano = models.CharField("plano", max_length=3, choices=Plano.choices)
    nivel = models.CharField("nível", max_length=14, choices=Nivel.choices)
    comecou_em = models.DateField("começou em")
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    #: As oito semanas do plano — mesmo número em CORRIDA.md, mas fixo aqui
    #: também: `semana_atual` não pode ler o documento (círculo: modelo
    #: importando `doutrina_corrida`, que é módulo puro por decisão, no mesmo
    #: espírito do que `workouts/doutrina.py` diz sobre `accounts.models`) e
    #: as quatro combinações do documento têm todas oito semanas hoje.
    SEMANAS = 8

    class Meta:
        verbose_name = "plano de corrida"
        verbose_name_plural = "planos de corrida"
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(ativo=True),
                name="um_plano_de_corrida_ativo",
            )
        ]

    def __str__(self):
        return f"{self.get_plano_display()} {self.nivel} ({self.comecou_em})"

    def semana_atual(self, hoje):
        """1 a 8, ou `None` depois da 8ª — o plano está concluído.

        Dia 0 (o dia em que começou) é semana 1; dia 7 é semana 2; dia 56
        (a 9ª semana de calendário) já passou da 8ª e devolve `None`. Uma
        data ANTES de `comecou_em` também devolve `None` — não deveria
        acontecer (a view sempre grava `comecou_em=hoje`), mas um plano
        futuro não é semana negativa.
        """
        dias = (hoje - self.comecou_em).days
        if dias < 0:
            return None
        semana = dias // 7 + 1
        return semana if semana <= self.SEMANAS else None

    def _inicio_da_semana_atual(self, hoje):
        semana = self.semana_atual(hoje)
        if semana is None:
            return None
        return self.comecou_em + timedelta(days=(semana - 1) * 7)

    def sessoes_feitas(self, hoje) -> int:
        """Quantas corridas (GPS ou à mão) a pessoa já fez na semana atual.

        Não filtra por distância nem por origem — a sessão do plano é
        "correu" ou "não correu", e uma corrida à mão conta tanto quanto uma
        do GPS: o plano não sabe (nem precisa saber) qual das três sessões da
        semana aquela corrida cumpriu, só QUANTAS já aconteceram, e a tela
        marca as `k` primeiras como feitas — a mesma lógica do dia de treino,
        que marca a série pela contagem e não pelo exercício exato.
        """
        inicio = self._inicio_da_semana_atual(hoje)
        if inicio is None:
            return 0
        return Corrida.objects.filter(
            user=self.user,
            comecou_em__date__gte=inicio,
            comecou_em__date__lte=hoje,
        ).count()
