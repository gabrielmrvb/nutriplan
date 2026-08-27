"""A aba de treino: a rotina da semana, a ficha de cada dia e a carga."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import Weekday
from accounts.views import OnboardingRequiredMixin

from . import health_export, services
from .models import (
    Exercise,
    ExerciseLog,
    MuscleGroup,
    SessionExercise,
    TrainingSession,
)


def week_overview(sessions) -> list:
    """Os sete dias da semana, marcando quais têm treino.

    A semana inteira, e não só os dias de treino, porque é a visão que responde
    a pergunta que a pessoa faz de manhã: "hoje eu treino o quê?" — e "hoje é
    descanso" é uma resposta tão útil quanto o nome do treino.
    """
    por_dia = {session.weekday: session for session in sessions}
    return [
        {
            "weekday": weekday,
            "short": label[:3],
            "label": label,
            "session": por_dia.get(weekday),
        }
        for weekday, label in Weekday.choices
    ]


def muscle_volume(sessions) -> list:
    """Séries semanais por grupo muscular.

    É o número que diz se a rotina está equilibrada: 10 a 20 séries por semana
    por grupo é a faixa em que a literatura mostra ganho consistente. Deixar
    isso visível é o que permite a pessoa perceber sozinha que está fazendo
    quinze séries de bíceps e três de posterior.
    """
    # Recebe as sessões JÁ carregadas, e não o plano.
    #
    # Com o plano, `plan.sessions.all()` abria um queryset novo — sem o
    # prefetch que a view tinha acabado de montar — e cada `item.exercise`
    # virava uma consulta. Medido com um ano de dados: 44 idas ao banco só
    # daqui, num total de 66 da página.
    totals = {}
    for session in sessions:
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
                "reps": registro.reps if registro else None,
                "previous": passado.weight_kg if passado else None,
                "previous_reps": passado.reps if passado else None,
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
                # O botão de copiar só existe quando há o que copiar — e a data
                # vai junto porque "copiar do último treino" sem dizer de quando
                # é copiar às cegas.
                # Quantas séries já saíram hoje. É o que o contador mostra e
                # o que o salvamento em bloco reescreve.
                item.feitas = len((item.load or {}).get("hoje") or {})

        marcar_ficha_aberta(sessions)

        context.update(
            {
                "nav": "workout",
                "plan": plan,
                "sessions": sessions,
                "week": week_overview(sessions),
                "volume": muscle_volume(sessions),
                "total_sets": sum(session.total_sets for session in sessions),
                # O resumo do que foi feito HOJE alimenta duas coisas: o card
                # de compartilhamento e a exportação para o app de saúde. Sai
                # do registro de carga, não da ficha — o que vale é o que
                # aconteceu, não o que estava previsto.
                "resumo_hoje": health_export.resumo_da_sessao(user),
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

        # Repetições são opcionais: quem só quer anotar a carga continua
        # anotando só a carga.
        reps = None
        bruto_reps = (request.POST.get("reps") or "").strip()
        if bruto_reps:
            try:
                reps = max(1, min(int(bruto_reps), 100))
            except (TypeError, ValueError):
                reps = None

        # Séries feitas: grava de 1 até N com a mesma carga, e APAGA o que
        # passar de N.
        #
        # Apagar é o que torna o contador honesto: baixar de 4 para 3 significa
        # que a quarta não aconteceu, e deixá-la no banco faria o volume do dia
        # mentir para sempre. O formato do histórico não muda — continua uma
        # linha por série, que é o que o cálculo de volume lê.
        feitas = request.POST.get("series_feitas")
        if feitas is not None:
            try:
                feitas = max(0, min(int(feitas), 20))
            except (TypeError, ValueError):
                feitas = 1
            for numero in range(1, feitas + 1):
                services.record_load(
                    request.user, exercise, peso, set_number=numero, reps=reps
                )
            ExerciseLog.objects.filter(
                user=request.user,
                exercise=exercise,
                date=timezone.localdate(),
                set_number__gt=feitas,
            ).delete()
        else:
            services.record_load(
                request.user, exercise, peso, set_number=serie, reps=reps
            )

        # Quem chegou por busca recebe JSON e a página não recarrega: no meio
        # do treino, perder a posição da rolagem a cada série é o que faz a
        # pessoa parar de anotar.
        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse(
                {
                    "ok": True,
                    "serie": serie,
                    "peso": str(peso),
                    "reps": reps,
                    "descanso": _descanso_de(request.user, exercise),
                }
            )
        # A âncora devolve a pessoa para o exercício em que ela estava, em vez
        # de jogá-la no topo da página no meio do treino.
        return redirect(reverse("workouts:routine") + f"#exercicio-{exercise.pk}")


def _descanso_de(user, exercise) -> int:
    """O descanso prescrito para este exercício na ficha ativa.

    Serve ao cronômetro automático: terminada a série, o timer precisa saber
    quantos segundos contar, e a resposta está na prescrição.
    """
    item = (
        SessionExercise.objects.filter(
            session__plan__user=user,
            session__plan__is_active=True,
            exercise=exercise,
        )
        .values_list("rest_seconds", flat=True)
        .first()
    )
    return item or 60


class HealthExportView(OnboardingRequiredMixin, View):
    """O treino do dia em TCX, para importar no app Saúde.

    Uma PWA não escreve no HealthKit — não existe API web para isso, e o
    Health Connect do Android é igual. O caminho honesto é o arquivo.
    """

    def get(self, request, *args, **kwargs):
        resumo = health_export.resumo_da_sessao(request.user)
        if not resumo.tem_dados:
            messages.error(request, "Nenhuma série registrada hoje para exportar.")
            return redirect("workouts:routine")

        conteudo = health_export.tcx(resumo)
        resposta = HttpResponse(conteudo, content_type="application/vnd.garmin.tcx+xml")
        resposta["Content-Disposition"] = (
            f'attachment; filename="nutriplan-{resumo.data:%Y-%m-%d}.tcx"'
        )
        return resposta
