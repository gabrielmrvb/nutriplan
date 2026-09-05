"""Acompanhamento diário: marcar refeições e medir aderência.

O registro é sempre por (usuário, dia, horário) — a constraint única no banco
garante isso — e os macros são congelados no momento da marcação. Editar uma
receita amanhã não pode reescrever o que a pessoa comeu hoje.
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import HydrationLog, MealLog, MealStatus, NutritionPlan

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


def metas_por_dia(user, dias) -> dict:
    """A meta que valia em CADA dia, e não a de hoje.

    A barra do histórico comparava todo dia com a meta atual. Numa tela de
    evolução isso distorce exatamente onde mais importa: a meta muda quando o
    peso muda, então o dia em que a pessoa recalibrou é o dia em que a
    comparação passa a mentir para trás. Quem cortou 200 kcal na terça via a
    segunda-feira inteira parecendo excesso.

    `NutritionPlan` é retrato e os antigos ficam — a informação sempre esteve
    no banco. O que faltava era ir buscá-la.

    Uma consulta, e o mapeamento é feito em memória: são poucos planos por
    pessoa, e uma consulta por dia seria N+1 numa tela que mostra trinta.
    """
    planos = list(
        NutritionPlan.objects.filter(user=user)
        .order_by("created_at")
        .values_list("created_at", "target_kcal")
    )
    if not planos:
        return {}

    metas = {}
    for dia in dias:
        # O plano em vigor é o último criado ATÉ o fim daquele dia. Comparar
        # com a data de criação e não com um intervalo evita o caso do plano
        # criado no meio do dia: ele vale para o dia em que nasceu.
        valendo = None
        for criado_em, alvo in planos:
            if timezone.localtime(criado_em).date() <= dia:
                valendo = alvo
            else:
                break
        # Dia anterior ao primeiro plano fica sem meta: comparar o que a pessoa
        # comeu antes de existir plano com uma meta que ainda não existia seria
        # inventar a régua.
        metas[dia] = valendo or planos[0][1]
    return metas


def agua_por_semana(user, hoje=None, semanas=8) -> list:
    """Por semana: em quantos dias houve água registrada, e quanto em média.

    Média sobre os DIAS COM REGISTRO, e não sobre os sete da semana. A
    diferença não é detalhe: dividir por sete transforma "bebi 3 litros nos
    dois dias em que anotei" em "média de 850 ml por dia", que descreve um
    comportamento que não aconteceu. Quem esqueceu de anotar não bebeu zero —
    o app só não sabe.

    Os dois números vão juntos de propósito: a média sozinha esconde quantos
    dias a sustentam, e "4 de 7 dias" é o que diz se dá para confiar nela.

    Só conta linha com `ml > 0`: ela nasce por `get_or_create` quando a tela do
    dia abre, então existir não é ter bebido.
    """
    hoje = hoje or timezone.localdate()
    inicio_atual = hoje - timedelta(days=hoje.weekday())
    primeira = inicio_atual - timedelta(weeks=semanas - 1)

    linhas = (
        HydrationLog.objects.filter(user=user, date__gte=primeira, ml__gt=0)
        .order_by()
        .values("date", "ml")
    )

    por_semana = {}
    for linha in linhas:
        inicio = linha["date"] - timedelta(days=linha["date"].weekday())
        acumulado = por_semana.setdefault(inicio, {"dias": 0, "total": 0})
        acumulado["dias"] += 1
        acumulado["total"] += linha["ml"]

    resultado = []
    for n in range(semanas):
        inicio = primeira + timedelta(weeks=n)
        dados = por_semana.get(inicio, {"dias": 0, "total": 0})
        resultado.append(
            {
                "inicio": inicio,
                "dias": dados["dias"],
                "media_ml": (
                    arredondar(dados["total"] / dados["dias"])
                    if dados["dias"]
                    else 0
                ),
            }
        )
    return resultado


def agua_dos_ultimos_dias(user, meta_ml, hoje=None, dias=7) -> dict:
    """Os últimos dias de água, um a um, e o que dá para dizer sobre eles.

    A visão semanal de `agua_por_semana` responde "como foram as semanas?".
    Esta responde outra pergunta, que é a da tela de hidratação: "como foi
    esta semana, dia a dia?". São duas perguntas diferentes e por isso são
    duas funções — colapsar as duas numa só faria a barra de 0 a 7 dias e a
    barra de mililitros dividirem uma escala que não é a mesma.

    Dia sem linha aparece com zero e é DIA SEM REGISTRO, não dia sem água. A
    diferença está escrita na tela junto do número, porque só aqui no código
    ela não ajuda ninguém.

    `bateu` compara com a meta de HOJE, e não com a meta que valia naquele dia:
    a meta sai do peso, o peso muda, e reconstruir a meta histórica de cada dia
    a partir de `WeightEntry` daria um número que nenhuma tela jamais mostrou.
    A comparação é declarada na tela como "a meta de hoje" pelo mesmo motivo.
    """
    hoje = hoje or timezone.localdate()
    primeiro = hoje - timedelta(days=dias - 1)

    # `date__gte` limita a CONSULTA, não o resultado: quem garante que nada de
    # fora da janela aparece é o laço abaixo, que só procura as sete datas que
    # ele mesmo gera. Medido por sabotagem — tirar o `date__gte` deixa todos os
    # testes verdes, porque a linha antiga volta do banco e nunca é consultada.
    #
    # Fica assim mesmo: sem o filtro, um ano de uso carrega 365 linhas para
    # desenhar 7. É otimização declarada como otimização, e não uma guarda de
    # correção fingindo ser uma.
    registrado = {
        linha["date"]: linha["ml"]
        for linha in HydrationLog.objects.filter(
            user=user, date__gte=primeiro, date__lte=hoje
        )
        .order_by()
        .values("date", "ml")
    }

    linhas = []
    for n in range(dias):
        data = primeiro + timedelta(days=n)
        ml = registrado.get(data, 0)
        linhas.append(
            {
                "data": data,
                "ml": ml,
                # O preenchimento satura em 100: quem bebeu 4 L de uma meta de
                # 3 L não deve desenhar uma barra maior que a caixa. O número
                # ao lado continua sendo o real.
                "pct": min(int(ml * 100 / meta_ml), 100) if meta_ml else 0,
                "bateu": bool(meta_ml) and ml >= meta_ml,
                "tem_registro": ml > 0,
                "e_hoje": data == hoje,
            }
        )

    com_registro = [linha for linha in linhas if linha["tem_registro"]]
    return {
        "linhas": linhas,
        "dias": dias,
        "com_registro": len(com_registro),
        "bateram": sum(1 for linha in linhas if linha["bateu"]),
        # Média sobre os dias COM registro, pela mesma razão de
        # `agua_por_semana`: dividir por sete inventaria um comportamento.
        "media_ml": (
            arredondar(sum(l["ml"] for l in com_registro) / len(com_registro))
            if com_registro
            else 0
        ),
    }
