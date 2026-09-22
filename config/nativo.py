# -*- coding: utf-8 -*-
"""Quem está pedindo é a CASCA NATIVA (`nativo/`, Capacitor)? (22/09/2026)

`capacitor.config.ts` acrescenta `NutriPlanNativo/<versão>` ao User-Agent
do WebView nas duas plataformas (`appendUserAgent`). É a marca que o servidor
lê para não oferecer o que não faz sentido dentro do app instalado — o
convite "Instale o NutriPlan" (já está instalado), o login com Google por
OAuth na web (o Google recusa WebView: `disallowed_useragent`) — e para o
`<html>` dizer a plataforma (`data-app-nativo`), de onde CSS e JS leem o
mesmo fato sem esperar o `Capacitor.isNativePlatform()` da página carregar.

Ler o User-Agent é decisão de SERVIDOR, e por isso vale no primeiro byte:
esconder o convite por JavaScript depois de a página abrir seria um piscar.
Não é segurança — a marca é falsificável por qualquer cliente —, e nada
aqui concede coisa alguma: só deixa de OFERECER.
"""
MARCA = "NutriPlanNativo/"
ANDROID = "android"
IOS = "ios"


def _user_agent(request) -> str:
    return (getattr(request, "META", {}) or {}).get("HTTP_USER_AGENT") or ""


def e_app_nativo(request) -> bool:
    return MARCA in _user_agent(request)


def plataforma_nativa(request) -> str:
    """`"android"`, `"ios"` ou `""` (não é a casca)."""
    ua = _user_agent(request)
    if MARCA not in ua:
        return ""
    if "Android" in ua:
        return ANDROID
    if "iPhone" in ua or "iPad" in ua or "iPod" in ua:
        return IOS
    return ""


def contexto(request):
    return {"app_nativo": e_app_nativo(request), "plataforma_nativa": plataforma_nativa(request)}
