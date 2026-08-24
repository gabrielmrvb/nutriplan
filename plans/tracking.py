"""Acompanhamento diário: marcar refeições e medir aderência.

O registro é sempre por (usuário, dia, horário) — a constraint única no banco
garante isso — e os macros são congelados no momento da marcação. Editar uma
receita amanhã não pode reescrever o que a pessoa comeu hoje.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import MealLog, MealStatus

#: Quantos dias a tela de histórico mostra.
HISTORY_DAYS = 14

ZERO = Decimal("0")


def log_meal(user, slot, status, option=None, day=None) -> MealLog:
    """Registra o que aconteceu numa refeição.

    `update_or_create` porque marcar de novo é corriqueiro: a pessoa clica em
    "pulei", muda de ideia e come. O registro é o estado final do horário
    naquele dia, não um log de auditoria de cliques.

    Só a opção efetivamente comida traz macros. "Pulei" zera, e "comi outra
    coisa" também — não sabemos o que foi, e chutar contaminaria o histórico
    com número inventado.
    """
    day = day or timezone.localdate()
    ate_the_plan = status == MealStatus.DONE and option is not None

    defaults = {
        "chosen_option": option if ate_the_plan else None,
        "status": status,
        "marked_at": timezone.now(),
        "slot_name": slot.name,
        "scheduled_time": slot.time,
        "kcal": option.kcal if ate_the_plan else ZERO,
        "protein_g": option.protein_g if ate_the_plan else ZERO,
        "carb_g": option.carb_g if ate_the_plan else ZERO,
        "fat_g": option.fat_g if ate_the_plan else ZERO,
    }
    log, _ = MealLog.objects.update_or_create(
        user=user, date=day, slot=slot, defaults=defaults
    )
    return log


def logs_by_slot(user, day) -> dict:
    """Registros do dia indexados pelo horário, para casar com o cardápio."""
    return {
        log.slot_id: log
        for log in MealLog.objects.filter(user=user, date=day).select_related(
            "chosen_option"
        )
    }


def day_summary(user, plan, day) -> dict:
    """Quanto já foi comido no dia contra o que o plano manda.

    Só refeições marcadas como feitas somam. Pendente não é zero por acaso: o
    dia ainda está acontecendo, e contar refeição futura como falha
    transformaria a tela num sermão às oito da manhã.
    """
    # Só o plano ativo entra na conta. Registro preso a um plano aposentado
    # não aparece na tela, e o que não aparece não pode somar no total.
    of_the_plan = MealLog.objects.filter(user=user, date=day, slot__plan=plan)
    totals = of_the_plan.filter(status=MealStatus.DONE).aggregate(
        kcal=Sum("kcal"), protein=Sum("protein_g"), carb=Sum("carb_g"), fat=Sum("fat_g")
    )
    consumed = int(totals["kcal"] or 0)
    counts = of_the_plan.aggregate(
        done=Count("pk", filter=Q(status=MealStatus.DONE)),
        marked=Count("pk", filter=~Q(status=MealStatus.PENDING)),
    )
    total_slots = plan.slots.count()

    return {
        "consumed_kcal": consumed,
        "target_kcal": plan.target_kcal,
        "remaining_kcal": plan.target_kcal - consumed,
        "progress_pct": min(int(consumed * 100 / (plan.target_kcal or 1)), 100),
        "protein_g": int(totals["protein"] or 0),
        "carb_g": int(totals["carb"] or 0),
        "fat_g": int(totals["fat"] or 0),
        "done": counts["done"],
        "marked": counts["marked"],
        "total": total_slots,
    }


def history(user, days=HISTORY_DAYS) -> list:
    """Um resumo por dia, do mais recente para o mais antigo.

    Dias sem nenhuma marcação não aparecem. Encher a tela com linhas zeradas
    de quando a pessoa nem usava o app não informa nada — e ainda parece
    cobrança.
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = (
        MealLog.objects.filter(user=user, date__gte=start)
        .values("date")
        .annotate(
            kcal=Sum("kcal", filter=Q(status=MealStatus.DONE)),
            done=Count("pk", filter=Q(status=MealStatus.DONE)),
            marked=Count("pk", filter=~Q(status=MealStatus.PENDING)),
        )
        .order_by("-date")
    )

    summary = []
    for row in rows:
        marked = row["marked"] or 0
        summary.append(
            {
                "date": row["date"],
                "kcal": int(row["kcal"] or 0),
                "done": row["done"],
                "marked": marked,
                "adherence_pct": int(row["done"] * 100 / marked) if marked else 0,
                "is_today": row["date"] == today,
            }
        )
    return summary


def adherence(rows) -> dict:
    """Consolidado do período: média de kcal e aderência das refeições marcadas."""
    if not rows:
        return {"days": 0, "avg_kcal": 0, "adherence_pct": 0}
    done = sum(row["done"] for row in rows)
    marked = sum(row["marked"] for row in rows)
    return {
        "days": len(rows),
        "avg_kcal": int(sum(row["kcal"] for row in rows) / len(rows)),
        "adherence_pct": int(done * 100 / marked) if marked else 0,
    }
