# -*- coding: utf-8 -*-
"""O login NATIVO da casca (Fase 2 da missão Capacitor, 22/09/2026).

Dentro do app instalado o Google recusa o OAuth por WebView
(`disallowed_useragent`), então a casca usa o SDK nativo — Google no Android
e no iOS, Apple no iOS — e manda ao servidor só o `id_token` assinado. Esta
view verifica a assinatura com o MESMO `provider.verify_token` do allauth
que o One Tap usa (emissor, audiência = client id, validade, chaves públicas
do provedor) e entrega o resto a `complete_social_login`: é a mesma política
do `NutriPlanSocialAccountAdapter` — conta nova nasce, `uid` conhecido
entra, e-mail com senha utilizável PEDE A SENHA (caso 4). Nenhuma regra de
vínculo é reescrita aqui; a view só troca o transporte.

CSRF é o da página, como qualquer formulário (o `login_by_token` do allauth
é `csrf_exempt` com double-submit próprio, para o One Tap; aqui não há
motivo). A resposta é o redirect do allauth, e o JavaScript da casca o
segue.
"""
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.helpers import complete_social_login
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest
from django.views import View

from .adapters import recusa

PROVEDORES = ("google", "apple")


def provedores_habilitados() -> tuple:
    return tuple(
        p for p in PROVEDORES
        if (p == "google" and settings.GOOGLE_LOGIN_ENABLED) or (p == "apple" and settings.APPLE_LOGIN_ENABLED)
    )


class LoginNativoView(View):
    def post(self, request):
        provedor = (request.POST.get("provedor") or "").strip()
        id_token = (request.POST.get("id_token") or "").strip()
        if provedor not in provedores_habilitados() or not id_token:
            return HttpResponseBadRequest("provedor ou token ausente")
        provider = get_adapter().get_provider(request, provedor)
        try:
            login = provider.verify_token(request, {"id_token": id_token})
        except (ValidationError, PermissionDenied, Exception):
            # A razão fica no log do allauth; para quem está do outro lado é
            # a mesma frase de sempre — dizer "assinatura", "audiência" ou
            # "expirado" ensina o que ajustar para tentar de novo.
            resposta = recusa(request)
            resposta.status_code = 403
            return resposta
        nome = (request.POST.get("nome") or "").strip()
        if nome and not login.user.first_name:
            # A Apple só manda o nome UMA vez, no primeiro consentimento, e só
            # ao aparelho — nunca dentro do token. O SDK o entrega ao app, e o
            # app o entrega aqui. Só entra em conta nova (o `user` do login
            # ainda não foi salvo); conta existente não é renomeada por isso.
            login.user.first_name = nome[:150]
        try:
            return complete_social_login(request, login)
        except ImmediateHttpResponse as desvio:
            return desvio.response
