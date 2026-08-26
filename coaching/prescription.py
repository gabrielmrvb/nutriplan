"""O que o profissional escreve na ficha do aluno.

Todas as funções aqui recebem o vínculo — nunca o id cru do aluno — e conferem
o escopo antes de tocar em qualquer linha. Isso é redundante com a checagem que
a view já fez, e a redundância é o ponto: se um dia alguém acrescentar uma view
e esquecer o `vinculo_ativo`, a escrita ainda para aqui.

Toda mutação termina com um `CoachUpdate`. Uma ficha que muda sozinha entre uma
abertura e outra é assustadora — a pessoa acha que perdeu o próprio progresso —
e o aviso é o que transforma "meu treino mudou" em "meu treinador mudou meu
treino".
"""
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from plans import services as plan_services
from plans.meal_planner import scale_for
from workouts.models import SessionExercise

from .models import CoachUpdate, UpdateKind

#: Limites do que um profissional pode prescrever. Não são opinião: abaixo de
#: 1,2 g/kg de proteína não se preserva massa magra em déficit, e acima de 3,0
#: não há literatura que sustente o ganho. A trava existe para o erro de
#: digitação — 18 no lugar de 1,8 — que ninguém revisa.
PROTEINA_MIN = Decimal("1.2")
PROTEINA_MAX = Decimal("3.0")
#: Gordura entre 15% e 45% da energia. O piso de 0,7 g/kg do motor continua
#: valendo por cima disto, e vence quando os dois discordam.
GORDURA_MIN = Decimal("0.15")
GORDURA_MAX = Decimal("0.45")
#: Ajuste calórico manual. O motor já impede a meta de cair abaixo da taxa
#: metabólica basal; isto impede o número absurdo antes de chegar lá.
AJUSTE_MIN = -800
AJUSTE_MAX = 800


class ForaDaFaixa(ValueError):
    """Prescrição fora do que o app aceita — com o motivo em português."""


def _exigir(condicao, mensagem):
    if not condicao:
        raise ForaDaFaixa(mensagem)


def _avisar(link, kind, mensagem):
    return CoachUpdate.objects.create(
        student=link.student,
        professional=link.professional,
        kind=kind,
        message=mensagem,
    )


def _nome(link) -> str:
    perfil = getattr(link.professional, "professional_profile", None)
    if perfil:
        return perfil.display_name
    return link.professional.first_name or "Seu profissional"


# ==========================================================================
# Treino
# ==========================================================================

def _exigir_treino(link):
    if not link.pode_treino:
        raise PermissionDenied("Este vínculo não autoriza mexer no treino.")


def _assumir_ficha(link, plan):
    """Marca a ficha como prescrita, para o gerador parar de reescrevê-la."""
    if plan.prescribed_by_id != link.professional_id:
        plan.prescribed_by = link.professional
        plan.prescribed_at = timezone.now()
        plan.save(update_fields=["prescribed_by", "prescribed_at"])


@transaction.atomic
def ajustar_exercicio(link, item, *, sets, rep_min, rep_max, rest_seconds):
    """Série, repetição e descanso de um exercício da ficha do aluno."""
    _exigir_treino(link)
    _exigir(item.session.plan.user_id == link.student_id, "Exercício de outro aluno.")
    _exigir(1 <= sets <= 10, "Séries fora da faixa de 1 a 10.")
    _exigir(1 <= rep_min <= rep_max <= 50, "Faixa de repetições inválida.")
    _exigir(20 <= rest_seconds <= 300, "Descanso fora da faixa de 20 a 300 segundos.")

    item.sets = sets
    item.rep_min = rep_min
    item.rep_max = rep_max
    item.rest_seconds = rest_seconds
    item.save(update_fields=["sets", "rep_min", "rep_max", "rest_seconds"])

    _assumir_ficha(link, item.session.plan)
    _avisar(
        link,
        UpdateKind.WORKOUT,
        f"{_nome(link)} ajustou {item.exercise.name} no Treino {item.session.label}.",
    )
    return item


@transaction.atomic
def trocar_exercicio(link, item, novo):
    """Substitui o exercício mantendo a prescrição de séries e descanso."""
    _exigir_treino(link)
    _exigir(item.session.plan.user_id == link.student_id, "Exercício de outro aluno.")
    _exigir(novo.is_active, "Exercício fora do catálogo ativo.")

    anterior = item.exercise.name
    item.exercise = novo
    item.save(update_fields=["exercise"])

    _assumir_ficha(link, item.session.plan)
    _avisar(
        link,
        UpdateKind.WORKOUT,
        f"{_nome(link)} trocou {anterior} por {novo.name} no Treino {item.session.label}.",
    )
    return item


@transaction.atomic
def remover_exercicio(link, item):
    _exigir_treino(link)
    _exigir(item.session.plan.user_id == link.student_id, "Exercício de outro aluno.")
    _exigir(
        item.session.exercises.count() > 1,
        "A ficha ficaria vazia — troque o exercício em vez de remover o último.",
    )

    sessao, nome = item.session, item.exercise.name
    item.delete()
    _assumir_ficha(link, sessao.plan)
    _avisar(
        link,
        UpdateKind.WORKOUT,
        f"{_nome(link)} tirou {nome} do Treino {sessao.label}.",
    )
    return sessao


@transaction.atomic
def adicionar_exercicio(link, session, exercise):
    _exigir_treino(link)
    _exigir(session.plan.user_id == link.student_id, "Sessão de outro aluno.")
    _exigir(exercise.is_active, "Exercício fora do catálogo ativo.")
    _exigir(
        not session.exercises.filter(exercise=exercise).exists(),
        f"{exercise.name} já está neste treino.",
    )

    ultimo = session.exercises.order_by("-order").first()
    item = SessionExercise.objects.create(
        session=session,
        exercise=exercise,
        order=(ultimo.order + 1) if ultimo else 0,
    )
    _assumir_ficha(link, session.plan)
    _avisar(
        link,
        UpdateKind.WORKOUT,
        f"{_nome(link)} incluiu {exercise.name} no Treino {session.label}.",
    )
    return item


@transaction.atomic
def clonar_modelo(link, session, template):
    """Substitui a sessão inteira pelos exercícios de um modelo do acervo.

    O acervo é o próprio catálogo de modelos do app (Treino A, B, C de cada
    divisão) — não uma biblioteca paralela por treinador. Um acervo particular
    seria a próxima coisa a construir, mas começar por ele significaria entregar
    "clonar ficha" com zero fichas para clonar.
    """
    _exigir_treino(link)
    _exigir(session.plan.user_id == link.student_id, "Sessão de outro aluno.")
    itens = list(template.items.select_related("exercise").order_by("order"))
    _exigir(itens, "Esse modelo não tem exercícios cadastrados.")

    session.exercises.all().delete()
    SessionExercise.objects.bulk_create(
        [
            SessionExercise(
                session=session,
                exercise=item.exercise,
                sets=item.sets,
                rep_min=item.rep_min,
                rep_max=item.rep_max,
                measure=item.measure,
                rest_seconds=item.rest_seconds,
                order=item.order,
            )
            for item in itens
        ]
    )
    session.name = template.name
    session.focus = template.focus
    session.save(update_fields=["name", "focus"])

    _assumir_ficha(link, session.plan)
    _avisar(
        link,
        UpdateKind.WORKOUT,
        f"{_nome(link)} montou o Treino {session.label} com o modelo {template.name}.",
    )
    return session


# ==========================================================================
# Dieta
# ==========================================================================

def _exigir_dieta(link):
    if not link.pode_dieta:
        raise PermissionDenied("Este vínculo não autoriza mexer na dieta.")


@transaction.atomic
def ajustar_metas(
    link,
    *,
    activity_level=None,
    goal=None,
    kcal_adjustment=None,
    protein_g_per_kg=None,
    fat_kcal_share=None,
    target_weight_kg=None,
):
    """Recalibra as metas do aluno e devolve o plano já refeito.

    Nada é gravado no plano: tudo entra no perfil, e `sync_active_plan` refaz
    os números a partir dele. É o que garante que a prescrição sobreviva — e
    também que as travas de segurança do motor continuem por cima dela.

    A taxa metabólica basal não está na lista, e a ausência é proposital: ela é
    a saída de uma fórmula sobre sexo, altura, idade e peso. Um campo para
    editá-la seria um campo para mentir ao resto do motor, que usa a TMB como
    piso da meta calórica.
    """
    _exigir_dieta(link)
    profile = link.student.profile
    campos = []

    if activity_level is not None and activity_level != profile.activity_level:
        profile.activity_level = activity_level
        campos.append("activity_level")

    if goal is not None and goal != profile.goal:
        profile.goal = goal
        campos.append("goal")

    if kcal_adjustment is not None:
        _exigir(
            AJUSTE_MIN <= kcal_adjustment <= AJUSTE_MAX,
            f"Ajuste calórico fora da faixa de {AJUSTE_MIN} a {AJUSTE_MAX} kcal.",
        )
        profile.kcal_adjustment = kcal_adjustment
        campos.append("kcal_adjustment")

    if protein_g_per_kg is not None:
        protein_g_per_kg = Decimal(protein_g_per_kg)
        _exigir(
            PROTEINA_MIN <= protein_g_per_kg <= PROTEINA_MAX,
            f"Proteína fora da faixa de {PROTEINA_MIN} a {PROTEINA_MAX} g/kg.",
        )
        profile.protein_g_per_kg = protein_g_per_kg
        campos.append("protein_g_per_kg")

    if fat_kcal_share is not None:
        fat_kcal_share = Decimal(fat_kcal_share)
        _exigir(
            GORDURA_MIN <= fat_kcal_share <= GORDURA_MAX,
            f"Gordura fora da faixa de {int(GORDURA_MIN * 100)}% a "
            f"{int(GORDURA_MAX * 100)}% das calorias.",
        )
        profile.fat_kcal_share = fat_kcal_share
        campos.append("fat_kcal_share")

    if target_weight_kg is not None:
        target_weight_kg = Decimal(target_weight_kg)
        _exigir(
            Decimal("35") <= target_weight_kg <= Decimal("300"),
            "Peso-alvo fora de qualquer faixa plausível.",
        )
        profile.target_weight_kg = target_weight_kg
        campos.append("target_weight_kg")

    if campos:
        profile.recalibrated_at = timezone.now()
        profile.save(update_fields=campos + ["recalibrated_at", "updated_at"])

    plan, mudou = plan_services.sync_active_plan(link.student)
    if campos:
        _avisar(
            link,
            UpdateKind.NUTRITION,
            f"{_nome(link)} atualizou suas metas: {plan.target_kcal} kcal, "
            f"{plan.protein_g} g de proteína.",
        )
    return plan, mudou


@transaction.atomic
def trocar_opcao(link, option, template):
    """Troca a receita de uma opção A/B, reescalada para o alvo do horário.

    Reescalar é obrigatório e não é detalhe: a mesma receita serve 400 kcal no
    lanche e 700 no almoço, e uma troca que só apontasse para outro
    `MealTemplate` deixaria o cardápio somando um total diferente da meta.
    """
    _exigir_dieta(link)
    _exigir(option.slot.plan.user_id == link.student_id, "Opção de outro aluno.")
    _exigir(template.is_active, "Receita fora do catálogo ativo.")
    _exigir(
        template.category == option.slot.category,
        "Essa receita é de outra categoria de refeição.",
    )

    slot = option.slot
    escala = scale_for(template, slot.target_kcal)
    macros = template.compute_macros(escala)

    option.template = template
    option.scale_factor = escala
    option.kcal = macros["kcal"].quantize(Decimal("0.01"))
    option.protein_g = macros["protein_g"].quantize(Decimal("0.01"))
    option.carb_g = macros["carb_g"].quantize(Decimal("0.01"))
    option.fat_g = macros["fat_g"].quantize(Decimal("0.01"))
    option.save(
        update_fields=[
            "template",
            "scale_factor",
            "kcal",
            "protein_g",
            "carb_g",
            "fat_g",
        ]
    )

    _avisar(
        link,
        UpdateKind.NUTRITION,
        f"{_nome(link)} trocou a opção {option.label} de {slot.name} "
        f"por {template.name}.",
    )
    return option
