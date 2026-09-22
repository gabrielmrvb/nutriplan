# -*- coding: utf-8 -*-
"""O envio pelo FCM HTTP v1 para o app instalado (Fase 2 da missão
Capacitor, 22/09/2026).

Um cano só para as duas plataformas: o token que a casca registra é do FCM
nos dois casos, e no iOS é o Firebase quem fala com o APNs (com a chave
`.p8` que o dono sobe no console do Firebase). O servidor autentica com a
CONTA DE SERVIÇO do projeto — o JSON inteiro em `FIREBASE_SERVICE_ACCOUNT_JSON`
(uma variável do painel, nunca arquivo no repositório) — e troca a chave por
um token OAuth de curta duração (`google-auth`), guardado no processo até
vencer.

Sem a variável nada sai e nada quebra: `enviar` devolve `False`, como o Web
Push faz sem VAPID. Token que o FCM declara morto (`UNREGISTERED`, ou 404)
é desativado; falha de rede não é token morto e o aparelho continua ativo.
"""
import json
import logging
import threading

import requests
from django.conf import settings
from django.utils import timezone

from .models import DispositivoNativo

logger = logging.getLogger(__name__)

ESCOPO = "https://www.googleapis.com/auth/firebase.messaging"
CANAL_ANDROID = "lembretes"
TIMEOUT_S = 10

_credenciais = None
_trava = threading.Lock()


def _conta_de_servico() -> dict:
    bruto = getattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", "") or ""
    if not bruto.strip():
        return {}
    try:
        return json.loads(bruto)
    except ValueError:
        logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON não é JSON válido; push nativo desligado")
        return {}


def configurado() -> bool:
    conta = _conta_de_servico()
    return bool(conta.get("project_id") and conta.get("private_key") and conta.get("client_email"))


def _token_de_acesso() -> str:
    """O bearer do FCM, renovado pelo `google-auth` quando vence."""
    global _credenciais
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    with _trava:
        if _credenciais is None:
            _credenciais = service_account.Credentials.from_service_account_info(_conta_de_servico(), scopes=[ESCOPO])
        if not _credenciais.valid:
            _credenciais.refresh(Request())
        return _credenciais.token


def mensagem(dispositivo: DispositivoNativo, payload: dict) -> dict:
    """O corpo v1: título e corpo nativos, a URL de destino em `data` (o
    `nativo.js` navega para ela ao tocar), canal "lembretes" no Android e
    som padrão no iOS."""
    return {
        "message": {
            "token": dispositivo.token,
            "notification": {"title": payload["title"], "body": payload["body"]},
            "data": {"url": payload.get("url", "/"), "tag": payload.get("tag", "")},
            "android": {"notification": {"channel_id": CANAL_ANDROID, "tag": payload.get("tag", "")}},
            "apns": {"payload": {"aps": {"sound": "default", "thread-id": payload.get("tag", "")}}},
        }
    }


def _token_morto(resposta) -> bool:
    if resposta.status_code == 404:
        return True
    try:
        erro = resposta.json().get("error", {})
    except ValueError:
        return False
    detalhes = erro.get("details") or []
    return any(d.get("errorCode") == "UNREGISTERED" for d in detalhes if isinstance(d, dict))


def enviar(dispositivo: DispositivoNativo, payload: dict) -> bool:
    if not configurado():
        return False
    projeto = _conta_de_servico()["project_id"]
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % projeto
    try:
        resposta = requests.post(
            url,
            json=mensagem(dispositivo, payload),
            headers={"Authorization": "Bearer " + _token_de_acesso(), "Content-Type": "application/json"},
            timeout=TIMEOUT_S,
        )
    except Exception as exc:  # rede fora, DNS, credencial recusada
        logger.warning("FCM não saiu para %s: %s", dispositivo.pk, exc)
        return False
    if resposta.status_code >= 400:
        if _token_morto(resposta):
            DispositivoNativo.objects.filter(pk=dispositivo.pk).update(ativo=False)
        logger.warning("FCM recusou %s: %s %s", dispositivo.pk, resposta.status_code, resposta.text[:200])
        return False
    DispositivoNativo.objects.filter(pk=dispositivo.pk).update(visto_em=timezone.now())
    return True
