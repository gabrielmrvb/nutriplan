"""Ponte entre o perfil da pessoa e o cálculo puro de `calculations.py`.

Aqui mora tudo que toca no banco: ler o perfil, congelar o snapshot de
entradas, desativar o plano anterior e criar o novo. O `NutritionPlan` é
tratado como imutável — mudou alguma entrada, nasce um plano novo e o antigo
fica no histórico com a meta que valia naquela época.
"""
import dataclasses
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from accounts.models import Profile
from catalog.models import MealTemplateItem

from . import meal_planner
from .calculations import PlanInputs, calculate
from .models import MealLog, MealOption, MealSlot, NutritionPlan


class IncompleteProfile(Exception):
    """Faltam dados para calcular — perfil sem onboarding ou sem peso."""


#: Campos do NutritionPlan que são cópia direta das entradas do cálculo.
_INPUT_FIELDS = (
    "weight_kg",
    "height_cm",
    "age_years",
    "sex",
    "activity_level",
    "goal",
    "training_days_per_week",
    # O QUE ESCOLHE A COMIDA (24/09/2026). Os sete de cima movem a META; estes
    # dois escolhem as RECEITAS, e estavam fora da comparação — marcar "sem
    # peixe" no Perfil não invalidava o cardápio, nem naquele POST nem na
    # visita seguinte à Home.
    "restricoes",
    "meal_style",
)
#: Quanto o peso pode variar sem que o plano seja considerado desatualizado.
#:
#: Avaliação de 16/09 (B17): qualquer peso novo invalidava o plano inteiro e
#: reescolhia o cardápio A/B do zero — pesar de manhã, com o intestino vazio
#: ou cheio, virava um cardápio diferente. 1,5 kg movem a TMB em ~15 kcal,
#: menos que o degrau de 10 g que o próprio cardápio já assume: não é
#: diferença que o prato precisa acompanhar.
TOLERANCIA_DE_PESO_KG = Decimal("1.5")

#: Campos que são resultado do cálculo.
_OUTPUT_FIELDS = (
    "bmr_kcal",
    "tdee_kcal",
    "target_kcal",
    "protein_g",
    "carb_g",
    "fat_g",
    "formula",
)


def build_inputs(user, *, peso_kg=None) -> PlanInputs:
    """Monta o PlanInputs a partir do que está gravado hoje.

    Levanta IncompleteProfile em vez de calcular com dado faltando: uma meta
    calórica errada é pior que uma tela dizendo "termine seu cadastro".

    `peso_kg` é o peso mais recente quando quem chama já o leu (a Home lê as
    últimas pesagens uma vez, para o cálculo e para o convite de pesar); sem
    ele, `profile.current_weight` consulta como sempre.
    """
    profile = _perfil_de(user)
    if profile is None or not profile.onboarding_complete:
        raise IncompleteProfile("Onboarding ainda não foi concluído.")

    weight = peso_kg if peso_kg is not None else profile.current_weight
    if weight is None:
        raise IncompleteProfile("Nenhum registro de peso encontrado.")

    # `.all()` e não `values_list`: com `training_days` já em cache no
    # `user` (a Home o pré-carrega uma vez para o cálculo E para o template),
    # `.all()` devolve a lista em memória e `values_list` abriria outra
    # consulta — a mesma tabela lida duas vezes na mesma tela.
    return PlanInputs(
        restricoes=restricoes_de(profile),
        meal_style=profile.meal_style,
        sex=profile.sex,
        weight_kg=weight,
        height_cm=profile.height_cm,
        age_years=profile.age,
        activity_level=profile.activity_level,
        goal=profile.goal,
        session_minutes=tuple(dia.duration_min for dia in user.training_days.all()),
        kcal_adjustment=profile.kcal_adjustment,
    )


#: Entradas cujo VAZIO no retrato quer dizer "desconhecido", e desconhecido
#: não invalida nada — a mesma doutrina que `TrainingPlan.catalogo`,
#: `nivel` e `duracao` já seguem ("Em branco é desconhecido").
#:
#: Só `meal_style` entra aqui, e a assimetria é a decisão. O perfil SEMPRE
#: tem estilo (o campo nasce com "varied"), então um retrato vazio só pode
#: ser de antes do campo existir — e trocar o cardápio de todo mundo num
#: deploy seria cobrar de quem não pediu nada. `restricoes` vazio é
#: ambíguo — "não marquei nenhuma" e "nasci antes do campo" escrevem a
#: mesma string —, e ali o desempate é o oposto: quem TEM restrição no
#: perfil e um retrato vazio é exatamente quem está vendo sardinha, e
#: precisa do cardápio refeito na primeira visita.
_VAZIO_E_DESCONHECIDO = ("meal_style",)


def _entrada_bate(plan, inputs, field) -> bool:
    gravado = getattr(plan, field)
    if field in _VAZIO_E_DESCONHECIDO and not gravado:
        return True
    return gravado == getattr(inputs, field)


def restricoes_de(profile) -> str:
    """As restrições do perfil como o RETRATO as guarda: slugs ordenados,
    separados por vírgula.

    Ordenados é a decisão, e ela não é cosmética: a ordem do `values_list` de
    um ManyToMany não é estável, e duas leituras da MESMA pessoa podem sair
    em ordens diferentes. Sem ordenar, `plan_is_current` leria "restrição
    diferente" e o cardápio seria remontado em toda abertura da Home — uma
    receita nova a cada visita, sem ninguém ter pedido.

    Só `RESTRICTION`: `DietaryTag` também guarda preferência, que pesa mas
    não elimina, e não é o que o cardápio filtra (`meal_planner`).
    """
    from catalog.models import TagKind

    return ",".join(
        sorted(
            profile.dietary_tags.filter(kind=TagKind.RESTRICTION).values_list(
                "slug", flat=True
            )
        )
    )


def _perfil_de(user):
    """O perfil pelo descritor — em cache quando a tela já o leu — ou `None`.

    `Profile.objects.filter(user=user).first()` abria uma consulta nova a cada
    chamada e não deixava nada em cache; o descritor deixa, e é isso que faz
    a Home ler o perfil UMA vez (21/09/2026)."""
    try:
        return user.profile
    except Profile.DoesNotExist:
        return None


def get_active_plan(user):
    return NutritionPlan.objects.filter(user=user, is_active=True).first()


@transaction.atomic
def create_plan(user, inputs=None) -> NutritionPlan:
    """Cria o plano ativo da pessoa, com refeições, aposentando o anterior.

    A ordem dentro da transação importa: o banco tem um índice único parcial
    de um plano ativo por usuário, então é preciso desativar o antigo ANTES de
    inserir o novo. Fazer isso numa transação é o que garante que nunca existe
    um instante com dois planos ativos nem nenhum — e que um erro na geração
    das refeições não deixa um plano sem cardápio salvo pela metade.
    """
    profile = Profile.objects.get(user=user)
    inputs = inputs or build_inputs(user)
    result = calculate(inputs)

    NutritionPlan.objects.filter(user=user, is_active=True).update(is_active=False)

    plan = NutritionPlan.objects.create(
        user=user,
        is_active=True,
        weight_kg=inputs.weight_kg,
        height_cm=inputs.height_cm,
        age_years=inputs.age_years,
        sex=inputs.sex,
        activity_level=inputs.activity_level,
        goal=inputs.goal,
        training_days_per_week=inputs.training_days_per_week,
        restricoes=inputs.restricoes,
        meal_style=inputs.meal_style,
        formula=result.formula,
        bmr_kcal=result.bmr_kcal,
        tdee_kcal=result.tdee_kcal,
        target_kcal=result.target_kcal,
        protein_g=result.protein_g,
        carb_g=result.carb_g,
        fat_g=result.fat_g,
        notes=result.notes,
    )

    warnings = meal_planner.generate(plan, profile)
    carry_today_logs(user, plan)
    if warnings:
        # O aviso do cardápio mora no mesmo campo que o aviso do cálculo: para
        # quem lê a tela é tudo "coisa que você precisa saber sobre este plano".
        plan.notes = " ".join(filter(None, [plan.notes, *warnings]))
        plan.save(update_fields=["notes"])
    return plan


def carry_today_logs(user, new_plan) -> int:
    """Traz para o plano novo as marcações de hoje que ficaram em planos velhos.

    Recalcular no meio do dia é comum (registrou o peso da manhã, mudou de
    objetivo). Sem essa transferência as refeições já marcadas ficariam presas
    ao plano aposentado: a tela mostraria o dia zerado e, ao marcar de novo, o
    mesmo almoço contaria duas vezes no total do dia.

    O filtro é "tudo de hoje que não está no plano novo", e não "o que está no
    plano anterior": quem recalculou duas vezes no mesmo dia teria registros
    presos num plano ainda mais antigo, invisíveis na tela e somando no total.

    O casamento é por `order`, que é a posição da refeição no dia — o café da
    manhã do plano velho vira o café da manhã do novo, mesmo que o horário
    tenha mudado junto com a rotina.
    """
    today = timezone.localdate()
    new_slots = {slot.order: slot for slot in new_plan.slots.all()}
    # Dois recálculos no mesmo dia podem deixar duas marcações apontando para a
    # mesma posição. Só a mais recente é adotada — a outra viraria violação da
    # constraint (usuário, dia, horário).
    taken = set(
        MealLog.objects.filter(user=user, date=today, slot__plan=new_plan).values_list(
            "slot__order", flat=True
        )
    )
    moved = 0
    for log in (
        MealLog.objects.filter(user=user, date=today, slot__isnull=False)
        .exclude(slot__plan=new_plan)
        .select_related("slot")
        .order_by("-marked_at")
    ):
        target = new_slots.get(log.slot.order)
        if target is None or target.order in taken:
            continue
        taken.add(target.order)
        log.slot = target
        log.slot_name = target.name
        log.scheduled_time = target.time
        log.save(update_fields=["slot", "slot_name", "scheduled_time"])
        moved += 1
    return moved


def plan_is_current(plan, inputs, slots=None) -> bool:
    """O plano ativo ainda corresponde aos dados de hoje?

    Comparamos entradas E saídas. As entradas pegam mudança de peso, objetivo
    ou rotina; as saídas pegam o que não vira campo do plano — hoje,
    `kcal_adjustment` ("Cortar/Somar 150 kcal" grava no perfil, não no plano).
    A duração do treino (`session_minutes`) também não é campo do plano, mas o
    motor só conta os dias; se um dia ela pesar no TDEE, cai neste mesmo
    caminho sem mexer aqui.

    PESO É A EXCEÇÃO, e o motivo é "plano é retrato": nada dentro de um plano
    ativo é editado — a tolerância só decide se nasce um retrato novo. Se toda
    entrada MENOS o peso bate, e o peso de hoje está a até
    `TOLERANCIA_DE_PESO_KG` do peso gravado no plano, as SAÍDAS são comparadas
    contra o cálculo feito COM O PESO DO RETRATO — o peso é a única entrada
    que a tolerância perdoa, então ele é neutralizado antes de comparar, e o
    que sobra é tudo o que move a meta sem passar por ele. Pesar +1,0 kg
    continua não regenerando (saídas iguais no peso gravado; 1,5 kg de
    diferença é ruído de balança, não progresso); "Cortar 150 kcal"
    (`kcal_adjustment`) regenera, porque não é campo do plano e move a meta.

    A primeira versão do ramo devolvia `True` sem olhar saída nenhuma
    (revisão final da Fase 3, 17/09/2026): "Cortar 150" gravava o ajuste no
    perfil, `sync_active_plan` achava o plano velho "atual", e a meta não
    mudava — com a mensagem "Cortamos 150 kcal da sua meta" na tela.

    Fora da faixa, ou com qualquer outra entrada diferente, roda o caminho de
    sempre: recalcular e comparar entradas e saídas contra o resultado de hoje.
    """
    if plan is None:
        return False
    if slots is not None:
        # O cardápio já veio carregado (`slots_com_cardapio`): as duas
        # perguntas abaixo — tem cardápio? alguma receita foi aposentada ou
        # teve os ingredientes recriados depois do plano? — são respondidas
        # em memória. A Home lia slots e opções aqui e de novo para desenhar.
        if not slots:
            return False
        if any(
            not option.template.is_active
            or (
                option.template.items_changed_at is not None
                and option.template.items_changed_at > plan.created_at
            )
            for slot in slots
            for option in slot.options.all()
        ):
            return False
    elif not plan.slots.exists():
        # Plano criado antes da etapa 4 (ou por um erro na geração): os números
        # podem estar certos, mas sem cardápio ele não serve para nada.
        return False
    elif (
        MealOption.objects.filter(slot__plan=plan)
        .filter(
            Q(template__is_active=False)
            | Q(template__items_changed_at__gt=plan.created_at)
        )
        .exists()
    ):
        # O cardápio aponta para receita aposentada — normalmente porque o
        # catálogo mudou. Os números seguem certos, mas mandar a pessoa comprar
        # o que saiu do catálogo não serve; o plano é refeito na próxima visita.
        #
        # Ou para receita cujos INGREDIENTES o seed recriou depois de o plano
        # nascer (`MealTemplate.items_changed_at`): o `scale_factor` da opção
        # foi calculado sobre a base velha, e aplicá-lo à base nova entrega
        # outra comida — 2,5× sobre uma base que dobrou é o dobro do prato.
        # As duas condições moram na MESMA consulta de propósito: o orçamento
        # de `plans:today` (`plans/test_stress.py`) não sobe por isto.
        return False

    outras_entradas_batem = all(
        _entrada_bate(plan, inputs, field)
        for field in _INPUT_FIELDS
        if field != "weight_kg"
    )
    if outras_entradas_batem:
        variacao_de_peso = abs(Decimal(plan.weight_kg) - Decimal(inputs.weight_kg))
        if variacao_de_peso <= TOLERANCIA_DE_PESO_KG:
            no_peso_do_retrato = calculate(
                dataclasses.replace(inputs, weight_kg=plan.weight_kg)
            )
            return all(
                getattr(plan, field) == getattr(no_peso_do_retrato, field)
                for field in _OUTPUT_FIELDS
            )

    result = calculate(inputs)
    same_inputs = all(_entrada_bate(plan, inputs, field) for field in _INPUT_FIELDS)
    same_outputs = all(
        getattr(plan, field) == getattr(result, field) for field in _OUTPUT_FIELDS
    )
    return same_inputs and same_outputs


def sync_active_plan(user) -> tuple:
    """Garante um plano ativo coerente com os dados atuais.

    Devolve (plano, mudou). Chamado na entrada da tela: enquanto nada muda é
    só uma comparação em memória, e quando a pessoa edita o peso ou o objetivo
    — pelo wizard, pelo admin, por onde for — o plano novo aparece sozinho.
    """
    inputs = build_inputs(user)
    plan = get_active_plan(user)
    if plan_is_current(plan, inputs):
        return plan, False
    return create_plan(user, inputs), True


def _com_cardapio(slots_qs):
    """Os horários com o cardápio inteiro em memória — opções com o modelo,
    itens com o alimento, porções — em QUATRO consultas. O
    `prefetch_related("options__template__items__food__portions")` de antes
    eram seis: modelo e alimento são chaves diretas e entram por JOIN."""
    return slots_qs.prefetch_related(
        Prefetch("options", queryset=MealOption.objects.select_related("template")),
        Prefetch(
            "options__template__items",
            queryset=MealTemplateItem.objects.select_related("food"),
        ),
        "options__template__items__food__portions",
    )


def slots_com_cardapio(plan) -> list:
    return list(_com_cardapio(plan.slots.all()))


def plano_ativo_com_cardapio(user) -> tuple:
    """(plano ativo, slots com cardápio) numa leitura só: os horários trazem
    o plano por JOIN (`select_related("plan")`), então a consulta ao plano
    e a aos horários viram uma. Plano ativo SEM horário (criado antes da
    etapa 4, ou por erro na geração) não aparece por aqui — o caminho
    lento o encontra, e `plan_is_current` o recusa como sempre."""
    slots = list(
        _com_cardapio(
            MealSlot.objects.filter(plan__user=user, plan__is_active=True).select_related("plan")
        )
    )
    if slots:
        plan = slots[0].plan
        for slot in slots:
            slot.plan = plan  # UMA instância, para `slot.plan is plan` valer em toda linha
        return plan, slots
    return get_active_plan(user), []


def plano_do_dia(user, *, peso_kg=None) -> tuple:
    """`sync_active_plan` para a tela que também vai desenhar o cardápio:
    devolve (plano, slots, mudou) lendo o cardápio UMA vez — a conferência de
    `plan_is_current` e a tela usam a mesma lista (21/09/2026; antes a Home
    lia slots e opções para conferir e de novo para desenhar)."""
    inputs = build_inputs(user, peso_kg=peso_kg)
    plan, slots = plano_ativo_com_cardapio(user)
    if plan_is_current(plan, inputs, slots=slots):
        return plan, slots, False
    plan = create_plan(user, inputs)
    return plan, slots_com_cardapio(plan), True
