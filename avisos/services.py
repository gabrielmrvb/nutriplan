# -*- coding: utf-8 -*-
"""Renderizar e enviar um e-mail do app, uma vez por chave.

`enviar()` é o único caminho: grava o `EmailEnviado` ANTES de mandar (a
constraint é a idempotência), renderiza os três templates do tipo
(`email/<tipo>.assunto.txt`, `.txt`, `.html`), põe os cabeçalhos de
descadastro (`List-Unsubscribe` + `List-Unsubscribe-Post`, RFC 8058 — é o que
faz o Gmail mostrar "Cancelar inscrição" ao lado do remetente) e nunca
levanta: a falha de SMTP fica no log com o erro. Quem chama — o cadastro, o
job — segue a vida. O e-mail de senha continua sendo do Django
(`PasswordResetView`): ele já tem o próprio caminho, e não é opt-out.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse

from .models import EmailEnviado, Preferencia, TipoDeEmail

logger = logging.getLogger("nutriplan.avisos")

#: Domínio RESERVADO (RFC 2606): nunca entrega. É o e-mail do demo
#: (`carlos.demo@nutriplan.invalid`), da conta do E2E noturno e a convenção
#: da conta de QA. Medido no Brevo em 21/09/2026: 19 soft bounces num dia,
#: todos `.invalid` — o resumo do Carlos e o boas-vindas do E2E. Nada sai
#: para quem não existe: `enviar()` responde "pulado" sem gravar linha.
TLD_QUE_NAO_ENTREGA = ".invalid"


def url_base():
    """A raiz pública do app, sem barra no fim. Vem de `NUTRIPLAN_URL_BASE`:
    o job não tem request para perguntar o domínio (o e-mail de senha tem)."""
    return (getattr(settings, "NUTRIPLAN_URL_BASE", "") or "").rstrip("/")


def link_de_descadastro(pref, tipo):
    return url_base() + reverse("avisos:descadastro", kwargs={"chave": pref.chave}) + f"?tipo={tipo}"


def _nome(user):
    return (user.first_name or "").strip()


def enviar(user, tipo, referencia, contexto, descadastro_de="tudo"):
    """Devolve `"enviado"`, `"pulado"` (já saiu, ou endereço que não
    entrega) ou `"falhou"`."""
    if (user.email or "").lower().endswith(TLD_QUE_NAO_ENTREGA):
        return "pulado"
    try:
        with transaction.atomic():
            registro = EmailEnviado.objects.create(user=user, tipo=tipo, referencia=referencia)
    except IntegrityError:
        return "pulado"

    pref = Preferencia.de(user)
    contexto = {
        **contexto,
        "nome": _nome(user),
        "url_base": url_base(),
        "descadastro": link_de_descadastro(pref, descadastro_de),
        "preferencias": url_base() + reverse("avisos:preferencias"),
    }
    assunto = " ".join(render_to_string(f"email/{tipo}.assunto.txt", contexto).split())
    texto = render_to_string(f"email/{tipo}.txt", contexto)
    html = render_to_string(f"email/{tipo}.html", contexto)
    msg = EmailMultiAlternatives(
        subject=assunto, body=texto, to=[user.email],
        headers={
            "List-Unsubscribe": f"<{contexto['descadastro']}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    msg.attach_alternative(html, "text/html")
    try:
        msg.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 — o e-mail nunca derruba quem chamou
        logger.warning("e-mail %s para %s falhou: %s", tipo, user.pk, exc)
        EmailEnviado.objects.filter(pk=registro.pk).update(sucesso=False, erro=str(exc)[:255])
        return "falhou"
    return "enviado"


def boas_vindas(user):
    """O e-mail de boas-vindas, uma vez por conta (`referencia="conta"`).

    Hoje é chamado no cadastro (senha e Google). Quando a verificação de
    e-mail existir, é ESTA chamada que muda de lugar — para depois da
    confirmação —, e nada mais.
    """
    return enviar(user, TipoDeEmail.BOAS_VINDAS, "conta", {})
