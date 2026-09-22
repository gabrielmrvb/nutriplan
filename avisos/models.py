# -*- coding: utf-8 -*-
"""O que a pessoa quer receber, e o que já recebeu.

Dois modelos, e a divisão é a mesma de `push`: a PREFERÊNCIA é estado da
pessoa (o que ela quer, quando), o LOG é o que aconteceu — e é o log, pela
constraint, que torna todo job seguro de rodar de 5 em 5 minutos ou duas
vezes por engano, como o `NotificationLog` já faz com o lembrete de refeição.
"""
import secrets
from datetime import time

from django.conf import settings
from django.db import models


def _nova_chave():
    """A chave do link de descadastro: 128 bits, própria de cada pessoa.

    O link chega por e-mail e abre SEM login (o cliente de e-mail não tem a
    sessão do app). A chave é o que impede alguém de desligar os avisos de
    outra pessoa por tentativa: 32 hex é o mesmo tamanho de um token de
    sessão.
    """
    return secrets.token_hex(16)


class Preferencia(models.Model):
    """O que a pessoa quer receber. A linha que não existe vale LIGADO — o
    padrão é receber, e ninguém precisa abrir a tela para isso (`de()`)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferencia_de_aviso",
    )
    email_inatividade = models.BooleanField("e-mail quando parar de treinar", default=True)
    email_resumo_semanal = models.BooleanField("resumo semanal por e-mail", default=True)
    push_refeicoes = models.BooleanField("lembrete de refeição no aparelho", default=True)
    #: A hora do dia a partir da qual os e-mails do dia saem. O job roda de 5
    #: em 5 minutos, mas dorme até 30 min para o Neon hibernar (`push/tarefas`):
    #: o e-mail chega em até meia hora depois desta hora.
    hora_email = models.TimeField("hora dos e-mails", default=time(8, 0))
    chave = models.CharField("chave de descadastro", max_length=32, unique=True, default=_nova_chave)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "preferência de aviso"
        verbose_name_plural = "preferências de aviso"

    @classmethod
    def de(cls, user):
        pref, _ = cls.objects.get_or_create(user=user)
        return pref

    def __str__(self):
        return f"avisos de {self.user_id}"


class TipoDeEmail(models.TextChoices):
    BOAS_VINDAS = "boas_vindas", "boas-vindas"
    INATIVIDADE = "inatividade", "sem treinar há 5 dias"
    RESUMO_SEMANAL = "resumo_semanal", "resumo da semana"


class EmailEnviado(models.Model):
    """Um registro por (pessoa, tipo, referência). A referência é o que faz
    a idempotência ter o TAMANHO certo: `conta` para o boas-vindas (uma vez
    na vida), a data da última série para a inatividade (um por pausa, não
    um por dia) e a semana ISO para o resumo (um por semana)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="emails_enviados",
    )
    tipo = models.CharField("tipo", max_length=20, choices=TipoDeEmail.choices)
    referencia = models.CharField("referência", max_length=32)
    enviado_em = models.DateTimeField(auto_now_add=True)
    sucesso = models.BooleanField(default=True)
    erro = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "e-mail enviado"
        verbose_name_plural = "e-mails enviados"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tipo", "referencia"], name="um_email_por_pessoa_tipo_e_referencia",
            ),
        ]

    def __str__(self):
        return f"{self.tipo} {self.referencia} → {self.user_id}"


class EmailBloqueado(models.Model):
    """Endereço em que o Brevo desistiu — hard bounce, denúncia de spam,
    bloqueio — sincronizado de `GET /v3/smtp/blockedContacts`
    (`manage.py sincronizar_brevo`). `enviar()` recusa antes de gravar linha.

    Guardar no banco, e não perguntar ao Brevo a cada envio: o job roda de
    5 em 5 minutos e a lista muda devagar; e o Brevo sozinho já não reenvia
    para quem deu hard bounce — a tabela é a nossa cópia, para a régua ser
    NOSSA e testável. Medido em 21/09/2026: 46,6 % de hard bounce num dia
    (contas de produção com gmail inventado).
    """

    email = models.EmailField("e-mail", unique=True)
    motivo = models.CharField("motivo (código do Brevo)", max_length=40, blank=True)
    bloqueado_em = models.DateTimeField("bloqueado em", null=True, blank=True)
    sincronizado_em = models.DateTimeField("sincronizado em", auto_now=True)

    class Meta:
        verbose_name = "e-mail bloqueado"
        verbose_name_plural = "e-mails bloqueados"

    def __str__(self):
        return "%s (%s)" % (self.email, self.motivo or "bloqueado")


class EmailAberto(models.Model):
    """Endereço que ABRIU algum e-mail nosso — a prova de caixa viva enquanto
    a verificação de e-mail do cadastro não existe (sessão de segurança).
    Sincronizado de `GET /v3/smtp/statistics/events?event=opened`. Quando a
    verificação entrar, `verificado()` em `services` passa a olhar o campo
    dela primeiro e esta tabela vira a segunda prova.
    """

    email = models.EmailField("e-mail", unique=True)
    primeira_abertura = models.DateTimeField("primeira abertura", null=True, blank=True)
    sincronizado_em = models.DateTimeField("sincronizado em", auto_now=True)

    class Meta:
        verbose_name = "e-mail aberto"
        verbose_name_plural = "e-mails abertos"

    def __str__(self):
        return self.email
