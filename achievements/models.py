"""O que a pessoa já conquistou. Só isso.

O CATÁLOGO de conquistas não mora aqui — mora em `regras.py`, em código. A
razão é que uma conquista não é um dado, é uma regra: "sete dias de ofensiva"
só significa alguma coisa junto da função que sabe contar sequência. Guardar o
catálogo numa tabela obrigaria a manter os dois em sincronia, com um seed a
mais no build, para ganhar a possibilidade de criar conquista pelo admin — que
ninguém quer, porque criar a linha sem escrever o detector produz uma conquista
que nunca desbloqueia.

O que precisa mesmo do banco é o que ACONTECEU, e é o que está aqui.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone



def _plural(quantos, singular, plural):
    """Concordancia de numero para os rotulos das conquistas.

    Seis rotulos precisam disso, e nenhum deles passa por template em todos os
    caminhos — o card de compartilhamento e canvas. Uma funcao de tres linhas
    resolve; `django.utils.translation` inteiro para isto seria trocar um
    problema pequeno por uma dependencia grande.
    """
    return singular if quantos == 1 else plural


class UserAchievement(models.Model):
    """Uma conquista desbloqueada por alguém, uma vez.

    A trava contra duplicata é a CONSTRAINT, e não um `if not exists` antes do
    insert. A diferença aparece exatamente no caso que a fila offline do
    NutriPlan produz de graça: dois POSTs iguais chegando quase juntos passam
    os dois pelo `if`, e sem a constraint o banco aceita as duas linhas. Com
    ela, o segundo insert falha e `get_or_create` devolve a linha do primeiro.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conquistas",
        verbose_name="usuário",
    )

    #: O identificador da REGRA, de `regras.py`. Texto e não FK porque não há
    #: tabela de catálogo: a regra vive no código.
    slug = models.CharField("conquista", max_length=40)

    #: O que distingue duas ocorrências da MESMA regra.
    #:
    #: Vazia nas conquistas que só acontecem uma vez ("primeiro treino"). Nas
    #: repetíveis é o que as separa: a semana, no caso da semana completa; o
    #: exercício e o dia, no caso do recorde.
    #:
    #: Ela existe para a unicidade poder ser sempre a mesma regra — `(user,
    #: slug, chave)` — em vez de um modelo para conquistas únicas e outro para
    #: repetíveis.
    chave = models.CharField("ocorrência", max_length=40, blank=True, default="")

    unlocked_at = models.DateTimeField("desbloqueada em", default=timezone.now)

    #: Os números que a tela e o card precisam mostrar, e SÓ eles.
    #:
    #: Nunca e-mail, nunca peso corporal, nunca restrição alimentar, nunca
    #: carga levantada. O que estiver aqui pode acabar dentro de uma imagem que
    #: a pessoa manda para um grupo de WhatsApp — então o critério não é "cabe
    #: no JSON?", é "eu mostraria isto para os amigos dela?".
    contexto = models.JSONField("contexto", default=dict, blank=True)

    #: Quando o aviso foi mostrado. Nulo = ainda não vista.
    #:
    #: Sem isto, a comemoração teria que sair numa `messages` no mesmo request
    #: que detectou — e a detecção acontece no POST de registrar série, cuja
    #: resposta em muitos casos é um JSON que a página não recarrega. A pessoa
    #: perderia o aviso justamente na tela em que ele importa.
    seen_at = models.DateTimeField("vista em", null=True, blank=True)

    class Meta:
        verbose_name = "conquista"
        verbose_name_plural = "conquistas"
        ordering = ["-unlocked_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug", "chave"], name="conquista_unica_por_pessoa"
            )
        ]
        indexes = [
            # A tela de conquistas e a checagem de "tem coisa nova?" filtram
            # sempre por pessoa e ordenam por data.
            models.Index(fields=["user", "-unlocked_at"], name="idx_conquista_pessoa"),
        ]

    def __str__(self):
        return f"{self.user} · {self.slug}"

    # ------------------------------------------------ o que a tela precisa
    #
    # Derivado da REGRA, e nao guardado numa coluna. Se o texto de uma
    # conquista mudar, ele muda para quem ja a tem — o banco guarda o que
    # aconteceu, e o codigo guarda como isso se chama.

    @property
    def regra(self):
        from .regras import POR_SLUG

        return POR_SLUG.get(self.slug)

    @property
    def titulo(self):
        return self.regra.titulo if self.regra else self.slug

    @property
    def emoji(self):
        return self.regra.emoji if self.regra else "🏅"

    @property
    def familia(self):
        return self.regra.familia if self.regra else ""

    @property
    def frase(self):
        """A frase da regra, com o exercicio quando houver.

        Recorde e a unica que precisa do contexto: "Voce bateu sua maior carga
        num exercicio" fica bem melhor como "Novo recorde no Supino reto". A
        CARGA nao entra — ver `regras._recorde`.
        """
        if not self.regra:
            return ""
        exercicio = (self.contexto or {}).get("exercicio")
        if exercicio:
            # Dois pontos, e nao "no": nome de exercicio tem genero e
            # numero variados ("Puxada", "Supino", "Elevacoes"), e
            # qualquer preposicao fixa erra em metade do catalogo.
            return "Novo recorde: %s." % exercicio
        return self.regra.frase

    # ---------------------------------------------- o que o card precisa
    #
    # O mapeamento de familia para tipo de card mora aqui porque e a mesma
    # pergunta: "que cara esta conquista tem?". Os tipos que faltam
    # (BODY_PROGRESS, RUN_COMPLETE, CHALLENGE_COMPLETE) nao aparecem porque nao
    # existe regra que os produza.

    TIPO_DE_CARD = {
        "ofensiva": "STREAK",
        "treino": "STREAK",
        "meta": "WEEKLY_GOAL",
        "recorde": "PERSONAL_RECORD",
    }

    @property
    def tipo_de_card(self):
        return self.TIPO_DE_CARD.get(self.familia, "WEEKLY_GOAL")

    @property
    def valor(self):
        """O numero grande do card, quando a conquista tem um."""
        contexto = self.contexto or {}
        for chave in ("dias", "treinos"):
            if chave in contexto:
                return contexto[chave]
        return ""

    @property
    def rotulo(self):
        """A unidade do número grande do card, no singular quando for um.

        O rótulo era fixamente plural e aparecia colado em `valor`, então a
        primeira conquista de todo mundo dizia "1 dias de treino". É o tipo de
        erro que não quebra nada e faz o app parecer descuidado exatamente no
        momento em que ele está parabenizando alguém.

        A concordância mora aqui, e não no template, porque `rotulo` é
        consumido também pelo card de compartilhamento — que é canvas, não
        HTML, e não tem `|pluralize`. Deixar a regra no template daria a
        imagem certa na tela e a errada na imagem que sai do app.
        """
        contexto = self.contexto or {}
        quantos = self.valor

        if "dias" in contexto and self.familia == "ofensiva":
            return _plural(quantos, "dia de ofensiva", "dias de ofensiva")
        if "treinos" in contexto:
            return _plural(quantos, "treino", "treinos")
        if "dias" in contexto:
            return _plural(
                quantos, "dia de treino na semana", "dias de treino na semana"
            )
        return ""

    @property
    def destaque(self):
        """O texto grande de quem nao tem numero — recorde e semana."""
        contexto = self.contexto or {}
        if contexto.get("exercicio"):
            return contexto["exercicio"]
        return self.titulo
