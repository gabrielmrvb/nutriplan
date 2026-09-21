# -*- coding: utf-8 -*-
"""A tarefa dos lembretes, chamada de fora por um agendador que não é nosso.

Nada pago (decisão do dono, 16/09/2026): não há cron no Render. O GitHub
Actions (`.github/workflows/lembretes.yml`) bate em `POST /tarefas/lembretes/`
de 5 em 5 minutos com um token, e este módulo é o que a rota faz — o
`send_meal_reminders` de sempre atrás de um portão, mais UMA regra que o
cron não precisava: **deixar o Neon dormir**.

O banco gratuito hiberna após 5 minutos parado e dá 100 CU-h por mês; uma
consulta a cada 5 minutos o manteria acordado o dia inteiro (182 CU-h — a
cota acabaria por volta do dia 16, `CLAUDE.md` "Monitor externo"). Depois
de rodar, a tarefa pergunta ao banco qual é a PRÓXIMA refeição de quem tem
assinatura ativa e dorme até `REMINDER_LEAD_MINUTES` antes dela — ou até
`PAUSA_MAXIMA`, o que vier primeiro. Nesse intervalo o POST responde
`{"pausada": true}` sem abrir consulta. O teto de 30 minutos é o preço de
não consultar sempre: assinatura nova ou plano novo entram na conta em no
máximo meia hora. A pausa é POR PROCESSO (dois workers, duas pausas) e
some no restart; nada disso é persistido, de propósito — persistir seria
uma consulta.
"""
import hmac
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from .services import (
    REMINDER_LEAD_MINUTES,
    proxima_refeicao_com_assinatura,
    push_is_configured,
    send_meal_reminders,
)

#: Quanto tempo, no máximo, a tarefa fica sem olhar o banco.
PAUSA_MAXIMA = timedelta(minutes=30)

#: O fallback (o `schedule` do Actions, POST) se ABSTÉM quando um disparo
#: EXTERNO pontual (o UptimeRobot, GET) cuidou dos lembretes há menos disto.
#: Como o UptimeRobot bate a cada 5 min, 4 min deixa o fallback dormir quando
#: o pontual está de pé, e assumir quando ele para.
RESERVA_DO_FALLBACK = timedelta(minutes=4)

#: Limite de taxa do disparo externo: dois GETs quase colados (um abuso, ou
#: um retry do monitor) não acordam o Neon duas vezes.
INTERVALO_MINIMO_EXTERNO = timedelta(seconds=30)

_pausa_ate = None
#: O instante do último disparo EXTERNO (pontual). É por processo (dois
#: workers, dois valores) e some no restart, como a pausa — persistir seria
#: uma consulta, e o pior caso de errar é uma rodada redundante, que a
#: idempotência do `NotificationLog` torna inofensiva.
_ultimo_externo = None


def esquecer_pausa():
    """Para os testes e para o restart: a próxima chamada vai ao banco."""
    global _pausa_ate
    _pausa_ate = None


def esquecer_externo():
    """Zera a memória do último disparo externo (testes e restart)."""
    global _ultimo_externo
    _ultimo_externo = None


def pausa_ate():
    return _pausa_ate


def token_de_disparo_confere(token) -> bool:
    """`<token>` da URL do disparo externo contra `NUTRIPLAN_DISPARO_TOKEN`.

    Comparação em tempo constante; sem a variável o disparo externo não
    existe (o chamador recebe 503, não 403). É um token SEPARADO do
    `NUTRIPLAN_TAREFAS_TOKEN` do POST de propósito: ele viaja na URL (o
    UptimeRobot free não manda cabeçalho) e por isso aparece no log de acesso
    do Render — vazá-lo só deixa alguém DISPARAR lembretes já vencidos
    (idempotente, com limite de taxa), nunca ler dado nem usar o Bearer do
    POST.
    """
    esperado = getattr(settings, "NUTRIPLAN_DISPARO_TOKEN", "") or ""
    if not esperado:
        return False
    return hmac.compare_digest((token or "").strip(), esperado)


def disparo_configurado() -> bool:
    return bool(getattr(settings, "NUTRIPLAN_DISPARO_TOKEN", "") or "")


def ultimo_externo():
    return _ultimo_externo


def token_confere(cabecalho) -> bool:
    """`Authorization: Bearer <token>` contra `NUTRIPLAN_TAREFAS_TOKEN`.

    Comparação em tempo constante; sem a variável a tarefa não existe (quem
    chama recebe 503, não 403 — é configuração, não credencial errada).
    """
    esperado = getattr(settings, "NUTRIPLAN_TAREFAS_TOKEN", "") or ""
    if not esperado:
        return False
    recebido = (cabecalho or "").strip()
    if not recebido.startswith("Bearer "):
        return False
    return hmac.compare_digest(recebido[len("Bearer "):].strip(), esperado)


def configurada() -> bool:
    return bool(getattr(settings, "NUTRIPLAN_TAREFAS_TOKEN", "") or "")


def rodar(now=None, externo=False) -> dict:
    """Dispara o que venceu e decide até quando dormir. Devolve o resumo.

    `externo=True` é o disparo PONTUAL (UptimeRobot, no GET com token na URL);
    `externo=False` é o FALLBACK (o `schedule` do Actions, no POST com
    Bearer), que se ABSTÉM quando um externo cuidou dos lembretes há menos de
    `RESERVA_DO_FALLBACK`. Assim o pontual manda, e o fallback só assume
    quando ele para — sem trabalho redundante (que seria inofensivo, mas
    acordaria o Neon à toa).
    """
    global _pausa_ate, _ultimo_externo
    now = now or timezone.localtime()
    if externo:
        anterior = _ultimo_externo
        _ultimo_externo = now
        if anterior is not None and now - anterior < INTERVALO_MINIMO_EXTERNO:
            return {"limitada": True, "agora": now.isoformat(),
                    "enviadas": 0, "puladas": 0, "falhas": 0}
    elif _ultimo_externo is not None and now - _ultimo_externo < RESERVA_DO_FALLBACK:
        return {"fallback_dispensado": True, "agora": now.isoformat(),
                "ultimo_externo": _ultimo_externo.isoformat(),
                "enviadas": 0, "puladas": 0, "falhas": 0}
    if _pausa_ate is not None and now < _pausa_ate:
        return {
            "pausada": True,
            "ate": _pausa_ate.isoformat(),
            "agora": now.isoformat(),
            "enviadas": 0, "puladas": 0, "falhas": 0,
        }

    if not push_is_configured():
        resultado = {"sent": 0, "skipped": 0, "failed": 0, "aviso": "VAPID não configurado"}
    else:
        resultado = send_meal_reminders(now)

    proxima = proxima_refeicao_com_assinatura(now)
    ate = now + PAUSA_MAXIMA
    if proxima is not None:
        janela = proxima - timedelta(minutes=REMINDER_LEAD_MINUTES)
        if janela < ate:
            ate = max(janela, now)
    _pausa_ate = ate

    return {
        "pausada": False,
        "ate": ate.isoformat(),
        "agora": now.isoformat(),
        "enviadas": resultado["sent"],
        "puladas": resultado["skipped"],
        "falhas": resultado["failed"],
        "proxima_refeicao": proxima.isoformat() if proxima else None,
    }
