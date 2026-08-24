"""Envio de Web Push e o lembrete de refeição.

A regra que governa este módulo é uma só: **notificação repetida é a forma mais
rápida de alguém desinstalar o app**. Por isso o registro de envio tem
unicidade (usuário, refeição, dia) no banco, e é a tentativa de criar esse
registro — não uma verificação prévia — que decide se o envio acontece.
"""
import json
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from pywebpush import WebPushException, webpush

from plans.models import MealSlot, MealStatus

from .models import NotificationLog, PushSubscription

logger = logging.getLogger(__name__)

#: Quanto antes do horário da refeição o lembrete sai.
REMINDER_LEAD_MINUTES = 10
#: Tolerância do job. Se ele roda de 5 em 5 minutos, uma janela maior que o
#: intervalo garante que nenhum horário passa batido quando um ciclo atrasa —
#: e a constraint no banco cuida de não duplicar por causa da sobreposição.
REMINDER_WINDOW_MINUTES = 10

#: Códigos que o serviço de push devolve quando a assinatura morreu (app
#: desinstalado, permissão revogada). Nesses casos ela é desativada.
GONE_STATUS = {404, 410}


def push_is_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_to_subscription(subscription: PushSubscription, payload: dict) -> bool:
    """Envia para um dispositivo. Devolve se deu certo.

    Assinatura morta é desativada em vez de apagada: o histórico de qual
    dispositivo recebeu o quê continua legível.
    """
    if not push_is_configured():
        return False

    try:
        webpush(
            subscription_info=subscription.as_subscription_info(),
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in GONE_STATUS:
            PushSubscription.objects.filter(pk=subscription.pk).update(is_active=False)
        logger.warning("Push falhou para %s: %s", subscription.pk, exc)
        return False
    except Exception as exc:  # rede fora, DNS, timeout
        # Um dispositivo com problema não pode derrubar o envio dos outros: o
        # comando roda para todo mundo de uma vez, e uma exceção aqui deixaria
        # metade das pessoas sem lembrete.
        logger.warning("Push não saiu para %s: %s", subscription.pk, exc)
        return False

    PushSubscription.objects.filter(pk=subscription.pk).update(
        last_used_at=timezone.now()
    )
    return True


def notify_user(user, payload: dict) -> int:
    """Manda para todos os dispositivos ativos da pessoa. Devolve quantos deram certo."""
    subscriptions = PushSubscription.objects.filter(user=user, is_active=True)
    return sum(send_to_subscription(sub, payload) for sub in subscriptions)


def meal_payload(slot) -> dict:
    """O conteúdo da notificação de uma refeição."""
    options = list(slot.options.select_related("template")[:2])
    if options:
        body = " ou ".join(option.template.name for option in options)
    else:
        body = f"{slot.target_kcal} kcal · {slot.target_protein_g} g de proteína"
    return {
        "title": f"{slot.name} — {slot.time:%H:%M}",
        "body": body,
        "url": "/",
        "tag": f"meal-{slot.pk}",
    }


def due_slots(now=None):
    """Refeições cujo lembrete cai agora, em todos os planos ativos.

    A janela é calculada em minutos desde a meia-noite para o filtro sair
    direto no SQL, sem trazer todos os horários para a memória.
    """
    now = now or timezone.localtime()
    target = (now + timedelta(minutes=REMINDER_LEAD_MINUTES)).time()
    start = (
        datetime.combine(now.date(), target) - timedelta(minutes=REMINDER_WINDOW_MINUTES)
    ).time()

    window = Q(time__gt=start, time__lte=target)
    if start > target:
        # A janela cruzou a meia-noite: vira "depois de start OU até target".
        window = Q(time__gt=start) | Q(time__lte=target)

    return (
        MealSlot.objects.filter(plan__is_active=True)
        .filter(window)
        .select_related("plan", "plan__user")
    )


def send_meal_reminders(now=None) -> dict:
    """Dispara os lembretes das refeições que estão chegando.

    Pula quem já marcou a refeição (não faz sentido lembrar de algo que a
    pessoa já comeu) e quem já recebeu o aviso hoje. O segundo caso é
    garantido pela constraint: criamos o NotificationLog ANTES de enviar e, se
    o banco recusar por duplicidade, é porque outro ciclo do job já cuidou
    dele. É isso que torna o comando seguro de rodar de 5 em 5 minutos, ou
    duas vezes por engano.
    """
    now = now or timezone.localtime()
    today = now.date()
    sent = skipped = failed = 0

    for slot in due_slots(now):
        user = slot.plan.user
        already_logged = slot.logs.filter(
            user=user, date=today
        ).exclude(status=MealStatus.PENDING).exists()
        if already_logged:
            skipped += 1
            continue

        try:
            with transaction.atomic():
                log = NotificationLog.objects.create(user=user, slot=slot, date=today)
        except IntegrityError:
            skipped += 1  # já avisado hoje
            continue

        delivered = notify_user(user, meal_payload(slot))
        if delivered:
            sent += 1
        else:
            failed += 1
            NotificationLog.objects.filter(pk=log.pk).update(
                success=False, error="nenhum dispositivo recebeu"
            )

    return {"sent": sent, "skipped": skipped, "failed": failed}
