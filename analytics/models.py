"""O que o produto registra sobre o próprio uso.

Dois níveis, e a diferença é a razão de existirem dois modelos:

- `Event` é o dado BRUTO — uma linha por acontecimento, com as propriedades
  inteiras. É caro (uma linha por toque) e por isso tem prazo: 90 dias, depois
  o `podar_analytics` apaga. O painel lê bruto para os últimos dias, quando a
  pessoa quer olhar um evento com todas as suas propriedades.

- `DailyAggregate` é o dado ROLADO — uma linha por (dia, evento, propriedade,
  valor), com a contagem. É barato e não tem prazo, porque não guarda ninguém:
  é só "quantas vezes X aconteceu no dia D". O painel lê agregado para períodos
  longos, onde ler bruto seria varrer milhões de linhas.

**Nada aqui carrega PII.** Nome e e-mail nunca entram; peso vira faixa. O
`anon_id` é um sorteio de primeira parte (cookie), não identidade. A régua está
em `analytics/catalogo.py` e é cobrada por teste — ver `analytics.taxonomia`.

**Exclusão de conta apaga o rastro bruto da pessoa** (`identidade.py`): as
linhas de `Event` com aquele usuário somem; os agregados, que já não guardam
usuário nenhum, ficam. É a LGPD resolvida sem perder a série histórica.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Event(models.Model):
    """Um acontecimento no produto. Bruto, com prazo de 90 dias."""

    name = models.CharField("evento", max_length=64)
    props = models.JSONField("propriedades", default=dict, blank=True)

    #: Nula por dois motivos que se somam: o evento pode ser anônimo (antes do
    #: login), e a exclusão de conta corta o vínculo. `SET_NULL` guarda o
    #: primeiro; o segundo é a poda de `identidade.esquecer`.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eventos_analytics",
    )
    #: Cookie de primeira parte, sorteado no servidor. Liga os toques de um
    #: aparelho ANTES do login; o `alias` os costura ao usuário depois.
    anon_id = models.CharField("id anônimo", max_length=36, blank=True)
    session_id = models.CharField("sessão", max_length=36, blank=True)

    route = models.CharField("rota", max_length=200, blank=True)
    referrer = models.CharField("origem", max_length=300, blank=True)

    #: Contexto do aparelho, tudo não-identificável.
    device = models.CharField("dispositivo", max_length=12, blank=True)
    width = models.PositiveIntegerField("largura", null=True, blank=True)
    theme = models.CharField("tema", max_length=8, blank=True)
    pwa = models.BooleanField("PWA instalada", default=False)

    #: Versão do app quando o evento aconteceu — o commit (7 caracteres).
    app_version = models.CharField("versão", max_length=20, blank=True)

    ts = models.DateTimeField("quando", default=timezone.now)

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"
        indexes = [
            # As duas perguntas que o painel faz o tempo todo: "este evento ao
            # longo do tempo" e "tudo de um usuário ao longo do tempo".
            models.Index(fields=["name", "ts"], name="ev_nome_ts"),
            models.Index(fields=["user", "ts"], name="ev_user_ts"),
            # A linha do tempo de um aparelho anônimo, e o alvo do alias.
            models.Index(fields=["anon_id", "ts"], name="ev_anon_ts"),
        ]

    def __str__(self):
        return f"{self.name} @ {self.ts:%Y-%m-%d %H:%M}"


class DailyAggregate(models.Model):
    """Uma contagem por (dia, evento, propriedade, valor). Sem prazo, sem PII.

    `prop_key=""` e `prop_value=""` é o TOTAL do evento no dia — a linha que o
    painel usa para "quantas vezes X por dia". Uma linha por valor de
    propriedade dá o agrupamento ("refeicao_registrada por opcao") sem varrer o
    bruto.
    """

    day = models.DateField("dia")
    name = models.CharField("evento", max_length=64)
    prop_key = models.CharField("propriedade", max_length=64, blank=True)
    prop_value = models.CharField("valor", max_length=200, blank=True)

    count = models.PositiveIntegerField("contagem", default=0)
    #: Usuários DISTINTOS (identificados ou anônimos) naquele dia/recorte.
    users = models.PositiveIntegerField("pessoas", default=0)

    class Meta:
        verbose_name = "agregado diário"
        verbose_name_plural = "agregados diários"
        constraints = [
            models.UniqueConstraint(
                fields=["day", "name", "prop_key", "prop_value"],
                name="um_agregado_por_dia_evento_propriedade",
            )
        ]
        indexes = [
            models.Index(fields=["name", "day"], name="ag_nome_dia"),
        ]

    def __str__(self):
        alvo = f" {self.prop_key}={self.prop_value}" if self.prop_key else ""
        return f"{self.day} {self.name}{alvo}: {self.count}"
