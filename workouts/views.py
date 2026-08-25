"""A aba de treino: a rotina da semana, a ficha de cada dia e a carga."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import Weekday
from accounts.views import OnboardingRequiredMixin

from . import services
from .models import Exercise, MuscleGroup


def week_overview(plan) -> list:
    """Os sete dias da semana, marcando quais têm treino.

    A semana inteira, e não só os dias de treino, porque é a visão que responde
    a pergunta que a pessoa faz de manhã: "hoje eu treino o quê?" — e "hoje é
    descanso" é uma resposta tão útil quanto o nome do treino.
    """
    sessions = {session.weekday: session for session in plan.sessions.all()}
    return [
        {
            "weekday": weekday,
            "short": label[:3],
            "label": label,
            "session": sessions.get(weekday),
        }
        for weekday, label in Weekday.choices
    ]


def muscle_volume(plan) -> list:
    """Séries semanais por grupo muscular.

    É o número que diz se a rotina está equilibrada: 10 a 20 séries por semana
    por grupo é a faixa em que a literatura mostra ganho consistente. Deixar
    isso visível é o que permite a pessoa perceber sozinha que está fazendo
    quinze séries de bíceps e três de posterior.
    """
    totals = {}
    for session in plan.sessions.all():
        for item in session.exercises.all():
            grupo = item.exercise.muscle_group
            totals[grupo] = totals.get(grupo, 0) + item.sets

    rows = [
        {
            "name": MuscleGroup(grupo).label,
            "sets": total,
            "slug": grupo,
        }
        for grupo, total in totals.items()
    ]
    rows.sort(key=lambda row: row["sets"], reverse=True)
    maior = rows[0]["sets"] if rows else 1
    for row in rows:
        row["pct"] = round(row["sets"] * 100 / maior)
    return rows


def set_rows(item, load) -> list:
    """Uma linha por série prescrita, com o que já foi anotado nela.

    Montado aqui e não no template porque a linguagem de template não sabe
    contar nem indexar por variável — e a alternativa seria um filtro
    personalizado só para isso.
    """
    hoje = (load or {}).get("hoje") or {}
    anterior = (load or {}).get("anterior") or {}
    linhas = []
    for numero in range(1, item.sets + 1):
        registro = hoje.get(numero)
        passado = anterior.get(numero)
        linhas.append(
            {
                "number": numero,
                "weight": registro.weight_kg if registro else None,
                "previous": passado.weight_kg if passado else None,
            }
        )
    return linhas


class WorkoutView(OnboardingRequiredMixin, TemplateView):
    """A rotina semanal, remontada sozinha quando os dias de treino mudam."""

    template_name = "workouts/routine.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if not services.has_training_days(user):
            # Sem dia de treino não existe rotina, e a tela vira um convite para
            # cadastrar — não um erro.
            context.update({"nav": "workout", "plan": None})
            return context

        plan, _ = services.sync_active_routine(user)
        sessions = list(
            plan.sessions.prefetch_related("exercises__exercise")
        )

        # Uma consulta só para a página inteira: o histórico é anexado ao item
        # da ficha para o template não precisar de filtro de dicionário.
        exercicios = [item.exercise for session in sessions for item in session.exercises.all()]
        historico = services.load_history(user, exercicios)
        for session in sessions:
            for item in session.exercises.all():
                item.load = historico.get(item.exercise_id)
                item.set_rows = set_rows(item, item.load)

        marcar_ficha_aberta(sessions)

        context.update(
            {
                "nav": "workout",
                "plan": plan,
                "sessions": sessions,
                "week": week_overview(plan),
                "volume": muscle_volume(plan),
                "total_sets": sum(session.total_sets for session in sessions),
            }
        )
        return context


def marcar_ficha_aberta(sessions) -> None:
    """Decide qual ficha da semana já vem aberta na tela.

    As cinco fichas empilhadas somavam uma página de rolagem infinita, e a
    pessoa passava por quatro treinos que não vai fazer hoje para chegar no
    que vai. Só uma abre: a de hoje.

    Quando hoje é dia de descanso não há ficha do dia, e aí abre a primeira —
    é melhor que abrir nenhuma e deixar a tela parecendo vazia. Quem quiser
    outra toca no cabeçalho.
    """
    if not sessions:
        return

    hoje = timezone.localdate().weekday()
    do_dia = next((s for s in sessions if s.weekday == hoje), None)
    escolhida = do_dia or sessions[0]

    for session in sessions:
        session.aberta = session is escolhida
        session.eh_hoje = session is do_dia


class RecordLoadView(OnboardingRequiredMixin, View):
    """Salva a carga usada num exercício. Só POST — isso muda estado."""

    def post(self, request, exercise_id, *args, **kwargs):
        exercise = get_object_or_404(Exercise, pk=exercise_id, is_active=True)
        bruto = (request.POST.get("weight_kg") or "").replace(",", ".").strip()
        try:
            peso = Decimal(bruto)
        except (InvalidOperation, TypeError):
            messages.error(request, "Carga inválida — use números, como 42,5.")
            return redirect("workouts:routine")

        if peso < 0 or peso > 999:
            messages.error(request, "Carga fora do que uma barra aguenta.")
            return redirect("workouts:routine")

        try:
            serie = int(request.POST.get("set_number", 1))
        except (TypeError, ValueError):
            serie = 1
        serie = max(1, min(serie, 20))

        services.record_load(request.user, exercise, peso, set_number=serie)
        # A âncora devolve a pessoa para o exercício em que ela estava, em vez
        # de jogá-la no topo da página no meio do treino.
        return redirect(reverse("workouts:routine") + f"#exercicio-{exercise.pk}")
