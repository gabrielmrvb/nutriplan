"""Ponte entre o perfil da pessoa e o cálculo puro de `calculations.py`.

Aqui mora tudo que toca no banco: ler o perfil, congelar o snapshot de
entradas, desativar o plano anterior e criar o novo. O `NutritionPlan` é
tratado como imutável — mudou alguma entrada, nasce um plano novo e o antigo
fica no histórico com a meta que valia naquela época.
"""
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile

from . import meal_planner
from .calculations import PlanInputs, calculate
from .models import MealLog, MealOption, NutritionPlan


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
)
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


def build_inputs(user) -> PlanInputs:
    """Monta o PlanInputs a partir do que está gravado hoje.

    Levanta IncompleteProfile em vez de calcular com dado faltando: uma meta
    calórica errada é pior que uma tela dizendo "termine seu cadastro".
    """
    profile = Profile.objects.filter(user=user).first()
    if profile is None or not profile.onboarding_complete:
        raise IncompleteProfile("Onboarding ainda não foi concluído.")

    weight = profile.current_weight
    if weight is None:
        raise IncompleteProfile("Nenhum registro de peso encontrado.")

    return PlanInputs(
        sex=profile.sex,
        weight_kg=weight,
        height_cm=profile.height_cm,
        age_years=profile.age,
        activity_level=profile.activity_level,
        goal=profile.goal,
        session_minutes=tuple(
            user.training_days.values_list("duration_min", flat=True)
        ),
    )


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


def plan_is_current(plan, inputs) -> bool:
    """O plano ativo ainda corresponde aos dados de hoje?

    Comparamos entradas E saídas. As entradas pegam mudança de peso, objetivo
    ou rotina; as saídas pegam o que não vira campo do plano — trocar a duração
    do treino mantém `training_days_per_week` igual, mas move o TDEE.
    """
    if plan is None:
        return False
    if not plan.slots.exists():
        # Plano criado antes da etapa 4 (ou por um erro na geração): os números
        # podem estar certos, mas sem cardápio ele não serve para nada.
        return False
    if MealOption.objects.filter(slot__plan=plan, template__is_active=False).exists():
        # O cardápio aponta para receita aposentada — normalmente porque o
        # catálogo mudou. Os números seguem certos, mas mandar a pessoa comprar
        # o que saiu do catálogo não serve; o plano é refeito na próxima visita.
        return False
    result = calculate(inputs)
    same_inputs = all(
        getattr(plan, field) == getattr(inputs, field) for field in _INPUT_FIELDS
    )
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
