"""Acompanhamento diário: marcar refeições e medir aderência.

O registro é sempre por (usuário, dia, horário) — a constraint única no banco
garante isso — e os macros são congelados no momento da marcação. Editar uma
receita amanhã não pode reescrever o que a pessoa comeu hoje.
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import MealLog, MealStatus

#: Quantos dias a tela de histórico mostra.
HISTORY_DAYS = 14

ZERO = Decimal("0")


#: A ÚNICA regra de arredondamento do app, e ela existe por um defeito concreto:
#: o card da refeição mostrava 678 kcal e o total do dia subia 677.
#:
#: Nenhum dos dois calculava errado. `MealOption.kcal` e `MealLog.kcal` guardam
#: `Decimal` com duas casas — 677,50 — e os dois números saíam dali. O que
#: divergia era a conversão para inteiro:
#:
#:     card:  {{ option.kcal|floatformat:0 }}  ->  arredonda  ->  678
#:     dia:   int(totals["kcal"])              ->  trunca     ->  677
#:
#: Duas convenções para o mesmo número, e a pessoa via a diferença: confirmava
#: uma refeição de 678 e o dia subia 677. Um kcal não muda dieta nenhuma; o que
#: ele estraga é a confiança de que os números do app fecham.
#:
#: A regra adotada é a do template, porque é a que a pessoa vê primeiro e a que
#: o Django já aplica sozinho em `floatformat`: meio para cima. O domínio segue
#: com a precisão que tem — arredondar é decisão de APRESENTAÇÃO e acontece
#: aqui, na fronteira, uma vez só.
#:
#: Vale para QUANTIDADE (kcal, gramas). Porcentagem continua truncando logo
#: abaixo, e de propósito: 99,6% de aderência arredondado vira "100%" num dia em
#: que a pessoa não fechou o plano, e essa é uma mentira pior que o 1% perdido.
def arredondar(valor) -> int:
    """Decimal para inteiro, meio para cima — como o `floatformat` do template."""
    return int(Decimal(valor or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


#: Quantos alimentos a pessoa pode descrever numa refeição fora do plano.
#:
#: Três cobre "arroz, feijão e bife", que é a forma de quase todo prato
#: brasileiro fora de casa. Mais linhas na tela viram formulário, e formulário
#: é o que faz a pessoa desistir de registrar — e refeição não registrada some
#: da aderência inteira, que é pior que uma estimada por três itens.
MAX_ITENS_FORA = 3


def macros_de_itens(itens) -> dict:
    """Soma os macros de uma lista de `(Food, gramas)`.

    Devolve zeros para lista vazia, e isso é a resposta certa: quem escreveu
    só "comi na casa da minha mãe" não deve receber caloria nenhuma inventada.
    """
    total = {"kcal": ZERO, "protein_g": ZERO, "carb_g": ZERO, "fat_g": ZERO}
    for food, gramas in itens:
        macros = food.macros_for(gramas)
        for chave in total:
            total[chave] += macros[chave]
    return total


def log_meal(user, slot, status, option=None, day=None, notes="", macros=None) -> MealLog:
    """Registra o que aconteceu numa refeição.

    `update_or_create` porque marcar de novo é corriqueiro: a pessoa clica em
    "pulei", muda de ideia e come. O registro é o estado final do horário
    naquele dia, não um log de auditoria de cliques.

    Só a opção efetivamente comida traz macros do PLANO. "Pulei" zera sempre.

    "Comi outra coisa" agora pode trazer os seus, em `macros`, calculados a
    partir dos alimentos que a pessoa descreveu. Quando ela não descreve
    nenhum, volta a zerar — a regra antiga não mudou, ganhou uma saída. O que
    continua proibido é o app estimar sozinho: número inventado no histórico é
    pior que buraco no histórico, porque o buraco a pessoa vê.
    """
    day = day or timezone.localdate()
    ate_the_plan = status == MealStatus.DONE and option is not None
    fora = macros if (status == MealStatus.OFF_PLAN and macros) else None

    defaults = {
        "chosen_option": option if ate_the_plan else None,
        "status": status,
        "marked_at": timezone.now(),
        "slot_name": slot.name,
        "scheduled_time": slot.time,
        # O nome sai da MESMA fonte dos macros: a opção que o servidor
        # resolveu. Nada aqui vem do request — o formulário manda o id da
        # opção, e é o servidor que a busca dentro do slot do plano ativo do
        # próprio usuário. Aceitar um nome enviado pelo cliente deixaria
        # qualquer pessoa escrever a própria história no histórico.
        #
        # Fora do "comi" fica VAZIO, e vazio é a resposta honesta: "pulei" não
        # tem receita, e "comi outra coisa" tem `notes`, que é a descrição da
        # própria pessoa. Carimbar um rótulo como "Outra refeição" inventaria
        # um nome de receita que não existe — e o status já conta isso.
        "recipe_name": option.template.name if ate_the_plan else "",
        "kcal": option.kcal if ate_the_plan else (fora or {}).get("kcal", ZERO),
        "protein_g": (
            option.protein_g if ate_the_plan else (fora or {}).get("protein_g", ZERO)
        ),
        "carb_g": option.carb_g if ate_the_plan else (fora or {}).get("carb_g", ZERO),
        "fat_g": option.fat_g if ate_the_plan else (fora or {}).get("fat_g", ZERO),
        # O campo existia desde o começo e nunca era escrito. Passou a servir
        # quando a entrada por voz chegou: "comi frango no almoço" não vira
        # macro nenhum — chutar contaminaria o histórico — mas vira a frase
        # guardada, que é o que a pessoa quis registrar.
        "notes": (notes or "")[:200],
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
    consumed = arredondar(totals["kcal"])
    # REGISTRO e ADERÊNCIA são coisas diferentes, e o resumo devolve as duas.
    #
    # A tela dizia "1/5 refeições" para um dia com cinco previstas, DUAS
    # registradas (uma seguindo o plano e uma "comi outra coisa") e três ainda
    # pendentes. Quem registrou as duas lia que tinha feito uma — o número
    # respondia aderência e a pessoa lia como registro. "Comi outra coisa"
    # existe justamente para ser registrável sem ser conforme; somar zero nos
    # dois lugares apaga o registro que a pessoa fez questão de deixar.
    counts = of_the_plan.aggregate(
        done=Count("pk", filter=Q(status=MealStatus.DONE)),
        marked=Count("pk", filter=~Q(status=MealStatus.PENDING)),
        fora_do_plano=Count("pk", filter=Q(status=MealStatus.OFF_PLAN)),
        puladas=Count("pk", filter=Q(status=MealStatus.SKIPPED)),
    )
    total_slots = plan.slots.count()

    return {
        "consumed_kcal": consumed,
        "target_kcal": plan.target_kcal,
        "remaining_kcal": plan.target_kcal - consumed,
        "progress_pct": min(int(consumed * 100 / (plan.target_kcal or 1)), 100),
        "protein_g": arredondar(totals["protein"]),
        "carb_g": arredondar(totals["carb"]),
        "fat_g": arredondar(totals["fat"]),
        # `done`, `marked` e `total` continuam com os nomes antigos: histórico,
        # ofensiva e fila offline leem os três, e renomear aqui seria mexer em
        # tudo isso para não ganhar nada.
        "done": counts["done"],
        "marked": counts["marked"],
        "total": total_slots,
        # Os nomes da TELA, que dizem qual das duas perguntas cada um responde.
        "previstas": total_slots,
        "registradas": counts["marked"],
        "no_plano": counts["done"],
        "fora_do_plano": counts["fora_do_plano"],
        "puladas": counts["puladas"],
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
                "kcal": arredondar(row["kcal"]),
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
        "avg_kcal": arredondar(Decimal(sum(row["kcal"] for row in rows)) / len(rows)),
        "adherence_pct": int(done * 100 / marked) if marked else 0,
    }
