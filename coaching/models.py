"""O vínculo entre profissional e aluno, e o que ele autoriza.

Este app guarda uma coisa só: *quem pode ler e escrever a ficha de quem*. Todo
o resto — treino, cardápio, peso — continua morando nos apps de sempre, e o
profissional escreve exatamente nas mesmas linhas que o aluno escreveria.

Essa escolha é deliberada. A alternativa seria uma cópia paralela dos dados
"prescritos pelo profissional", sincronizada com a do aluno; é o desenho que
parece mais seguro e é, na prática, o que produz duas verdades que divergem no
primeiro erro de sincronização. Aqui existe uma ficha só, e a pergunta "quem
pode mexer nela" é respondida por uma tabela de três colunas.
"""
from datetime import timedelta
from secrets import choice

from django.conf import settings
from django.db import models
from django.utils import timezone

#: Sem I, O, 0 e 1: o código é ditado por voz e digitado à mão na academia, e
#: essas quatro são as que a pessoa erra.
ALFABETO_CONVITE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TAMANHO_CONVITE = 6

#: Um convite aberto é uma autorização de leitura e escrita sobre dados de
#: saúde esperando alguém apanhá-la. Sete dias é tempo de sobra para o aluno
#: aceitar e curto o bastante para um link vazado envelhecer sozinho.
VALIDADE_CONVITE = timedelta(days=7)


def gerar_codigo() -> str:
    return "".join(choice(ALFABETO_CONVITE) for _ in range(TAMANHO_CONVITE))


class LinkRole(models.TextChoices):
    """O que o vínculo autoriza.

    Não é um cargo, é um escopo de escrita: o treinador mexe em série,
    repetição e descanso; o nutricionista mexe em meta calórica, macro e
    cardápio. Quem é as duas coisas escolhe `BOTH` e assume os dois.
    """

    TRAINER = "trainer", "treinador"
    NUTRITIONIST = "nutritionist", "nutricionista"
    BOTH = "both", "treinador e nutricionista"


class LinkStatus(models.TextChoices):
    PENDING = "pending", "pendente"
    ACTIVE = "active", "ativo"
    REVOKED = "revoked", "revogado"


class ProfessionalProfile(models.Model):
    """Quem pode abrir o painel.

    Existe como tabela separada, e não como um `is_professional` no usuário,
    porque carrega dados que só fazem sentido para profissional — o registro no
    conselho, que é o que o aluno olha antes de aceitar um convite de alguém
    que vai mexer na dieta dele.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="professional_profile",
    )
    display_name = models.CharField("nome de exibição", max_length=80)
    default_role = models.CharField(
        "atuação",
        max_length=12,
        choices=LinkRole.choices,
        default=LinkRole.TRAINER,
    )
    council_id = models.CharField(
        "registro no conselho",
        max_length=40,
        blank=True,
        help_text="CREF para educação física, CRN para nutrição.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "perfil profissional"
        verbose_name_plural = "perfis profissionais"

    def __str__(self):
        return self.display_name


class LinkQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(status=LinkStatus.ACTIVE)

    def da_carteira(self, professional):
        return (
            self.ativos()
            .filter(professional=professional)
            .select_related("student", "student__profile")
        )


class ProfessionalStudentLink(models.Model):
    """Um profissional, um aluno, um escopo.

    O aluno fica nulo enquanto o convite não é aceito: o código é gerado antes
    de existir destinatário, que é o que permite mandá-lo por WhatsApp sem
    pedir e-mail antes.
    """

    professional = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_links",
        verbose_name="profissional",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="professional_links",
        verbose_name="aluno",
        null=True,
        blank=True,
    )
    role = models.CharField("escopo", max_length=12, choices=LinkRole.choices)
    status = models.CharField(
        "situação", max_length=10, choices=LinkStatus.choices, default=LinkStatus.PENDING
    )
    invite_code = models.CharField(
        "código do convite", max_length=TAMANHO_CONVITE, unique=True, default=gerar_codigo
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField("aceito em", null=True, blank=True)
    revoked_at = models.DateTimeField("revogado em", null=True, blank=True)

    objects = LinkQuerySet.as_manager()

    class Meta:
        verbose_name = "vínculo profissional"
        verbose_name_plural = "vínculos profissionais"
        ordering = ("-created_at",)
        constraints = [
            # Um vínculo ativo por par. Sem isto, dois convites aceitos pela
            # mesma pessoa criariam dois vínculos, e revogar um deixaria o
            # outro em pé — o aluno clica em "revogar" e o acesso continua.
            models.UniqueConstraint(
                fields=("professional", "student"),
                condition=models.Q(status=LinkStatus.ACTIVE),
                name="um_vinculo_ativo_por_par",
            ),
        ]

    def __str__(self):
        alvo = self.student.email if self.student_id else f"convite {self.invite_code}"
        return f"{self.professional.email} → {alvo}"

    # ----------------------------------------------------------- escopo
    @property
    def pode_treino(self) -> bool:
        return self.role in (LinkRole.TRAINER, LinkRole.BOTH)

    @property
    def pode_dieta(self) -> bool:
        return self.role in (LinkRole.NUTRITIONIST, LinkRole.BOTH)

    # ---------------------------------------------------------- convite
    @property
    def expira_em(self):
        return self.created_at + VALIDADE_CONVITE

    @property
    def convite_expirado(self) -> bool:
        """Convite pendente vence; vínculo já aceito não tem prazo."""
        if self.status != LinkStatus.PENDING:
            return False
        return timezone.now() > self.expira_em

    @property
    def convite_aberto(self) -> bool:
        return self.status == LinkStatus.PENDING and not self.convite_expirado

    def aceitar(self, student):
        self.student = student
        self.status = LinkStatus.ACTIVE
        self.accepted_at = timezone.now()
        self.save(update_fields=["student", "status", "accepted_at"])
        return self

    def revogar(self):
        self.status = LinkStatus.REVOKED
        self.revoked_at = timezone.now()
        self.save(update_fields=["status", "revoked_at"])
        return self


class UpdateKind(models.TextChoices):
    WORKOUT = "workout", "treino"
    NUTRITION = "nutrition", "dieta"


class CoachUpdate(models.Model):
    """O aviso que o aluno vê quando a ficha dele muda sem ele ter mexido.

    Uma ficha que muda sozinha entre uma abertura e outra é assustadora — a
    pessoa acha que perdeu o progresso. O aviso não é notificação de sistema:
    é uma linha na própria tela onde a mudança aconteceu, dizendo quem mexeu e
    no quê.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coach_updates",
        verbose_name="aluno",
    )
    professional = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="updates_sent",
        verbose_name="profissional",
    )
    kind = models.CharField("assunto", max_length=10, choices=UpdateKind.choices)
    message = models.CharField("mensagem", max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField("visto em", null=True, blank=True)

    class Meta:
        verbose_name = "aviso do profissional"
        verbose_name_plural = "avisos do profissional"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["student", "seen_at"])]

    def __str__(self):
        return f"{self.student_id}: {self.message}"
