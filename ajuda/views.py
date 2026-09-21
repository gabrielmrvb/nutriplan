# -*- coding: utf-8 -*-
"""`/ajuda/`: a FAQ, "Reportar um problema" e "O que mudou".

As três telas são PÚBLICAS de propósito: quem não consegue entrar também
precisa de ajuda, e a página de perguntas é o lugar para descobrir o que o
app faz antes de criar conta. Nada aqui lê dado de saúde de ninguém.
"""
import logging
import os

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts import limites
from accounts.models import PedidoDeRecuperacao

from .forms import ReportarForm
from .mudancas import mudancas

logger = logging.getLogger("nutriplan.ajuda")

#: Abuso do formulário de problema: por IP e no total, na janela de uma hora.
#: Reusa a tabela de `accounts.limites` (contadores com HMAC, sem IP em
#: claro) com tipos próprios — o formulário é público e sem login.
LIMITE_POR_IP = 5
LIMITE_GLOBAL = 60


def versao() -> str:
    """Sete caracteres do commit em produção (`RENDER_GIT_COMMIT`), ou
    "local" — o mesmo que `/saude/` publica."""
    return os.environ.get("RENDER_GIT_COMMIT", "")[:7] or "local"


def _pode_reportar(ip: str) -> bool:
    desde = timezone.now() - timezone.timedelta(minutes=limites.JANELA_MINUTOS)
    if PedidoDeRecuperacao.objects.filter(tipo="ajd-glob", criado_em__gte=desde).count() >= LIMITE_GLOBAL:
        return False
    chave = limites._hmac(ip)
    return PedidoDeRecuperacao.objects.filter(tipo="ajd-ip", chave=chave, criado_em__gte=desde).count() < LIMITE_POR_IP


def _registrar(ip: str) -> None:
    PedidoDeRecuperacao.objects.bulk_create([
        PedidoDeRecuperacao(tipo="ajd-ip", chave=limites._hmac(ip)),
        PedidoDeRecuperacao(tipo="ajd-glob", chave=limites.CHAVE_GLOBAL),
    ])


class AjudaView(TemplateView):
    template_name = "ajuda/index.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["versao"] = versao()
        contexto["ultima_mudanca"] = (mudancas() or [{}])[0].get("data")
        return contexto


class MudancasView(TemplateView):
    template_name = "ajuda/mudancas.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["secoes"] = mudancas()
        return contexto


class ReportarView(View):
    """O formulário chega PREENCHIDO: rota (de onde a pessoa veio), versão e
    aparelho. O que ela escreve é só o que aconteceu. O e-mail vai para o
    dono (`NUTRIPLAN_SUPORTE_EMAIL`) com `Reply-To` da pessoa, quando ela
    deu o e-mail."""

    template_name = "ajuda/reportar.html"

    def _inicial(self, request):
        rota = request.GET.get("de") or ""
        if not rota:
            referer = request.META.get("HTTP_REFERER", "")
            host = request.get_host()
            if referer and ("://" + host) in referer:
                rota = referer.split(host, 1)[1] or "/"
        return {
            "rota": rota[:200],
            "versao": versao(),
            "dispositivo": (request.META.get("HTTP_USER_AGENT") or "")[:200],
            "email": request.user.email if request.user.is_authenticated else "",
        }

    def get(self, request):
        return render(request, self.template_name, {"form": ReportarForm(initial=self._inicial(request))})

    def post(self, request):
        form = ReportarForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)
        dados = form.cleaned_data
        ip = limites.ip_do_pedido(request)
        if dados["site"]:
            # Pote de mel: campo escondido que gente não preenche. Bot cai
            # aqui e recebe a MESMA resposta, para não aprender.
            return redirect(reverse("ajuda:reportado"))
        if not _pode_reportar(ip):
            return redirect(reverse("ajuda:reportado"))
        quem = request.user.email if request.user.is_authenticated else (dados["email"] or "anônimo")
        corpo = (
            f"Rota: {dados['rota'] or '(não informada)'}\n"
            f"Versão: {dados['versao']}\n"
            f"Aparelho: {dados['dispositivo'] or '(não informado)'}\n"
            f"Quem: {quem}\n"
            f"Quando: {timezone.localtime():%d/%m/%Y %H:%M}\n\n"
            f"{dados['descricao']}\n"
        )
        msg = EmailMessage(
            subject=f"[NutriPlan] Problema em {dados['rota'] or '?'} · {dados['versao']}",
            body=corpo,
            to=[settings.NUTRIPLAN_SUPORTE_EMAIL],
            reply_to=[dados["email"]] if dados["email"] else None,
        )
        try:
            msg.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 — a pessoa não paga pelo SMTP
            logger.warning("relato de problema não enviado: %s", exc)
            messages.error(request, "Não conseguimos enviar agora. Tente de novo em alguns minutos.")
            return render(request, self.template_name, {"form": form}, status=503)
        _registrar(ip)
        return redirect(reverse("ajuda:reportado"))


class ReportadoView(TemplateView):
    template_name = "ajuda/reportado.html"
