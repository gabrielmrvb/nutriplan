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

from . import assistant, health_export, services
from .models import Exercise, MuscleGroup, SessionExercise, TrainingSession


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

        marcar_ficha_aberta(sessions)

        context.update(
            {
                "nav": "workout",
                "plan": plan,
                "sessions": sessions,
                "week": week_overview(plan),
                "volume": muscle_volume(plan),
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
        # anotando só a carga. Mas quando vêm, elas são o que transforma o
        # histórico em volume — carga sozinha não diz se o treino cresceu.
        reps = None
        bruto_reps = (request.POST.get("reps") or "").strip()
        if bruto_reps:
            try:
                reps = max(1, min(int(bruto_reps), 100))
            except (TypeError, ValueError):
                reps = None

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


# ==========================================================================
# Assistente de ajuste
# ==========================================================================

def _sessao_do_usuario(request, session_id):
    """A sessão pedida, se ela for da rotina ativa de quem está pedindo.

    O filtro é por `plan__user` e não só por id: id de sessão é sequencial e
    adivinhável, e sem o dono na consulta qualquer pessoa logada editaria a
    ficha de qualquer outra trocando um número na URL.
    """
    return get_object_or_404(
        TrainingSession.objects.select_related("plan"),
        pk=session_id,
        plan__user=request.user,
        plan__is_active=True,
    )


def _mudancas_do_post(request, session):
    """Reconstrói as mudanças a partir dos campos escondidos do formulário.

    E revalida tudo. Os campos vieram do navegador, então são entrada hostil:
    o exercício precisa existir, estar ativo e ser do mesmo grupo muscular, e
    o item precisa ser desta sessão. Confiar no que voltou da tela seria
    entregar ao formulário o poder de trocar supino por rosca — ou de editar a
    ficha de outra pessoa.
    """
    itens = request.POST.getlist("item")
    tipos = request.POST.getlist("tipo")
    valores = request.POST.getlist("valor")

    mudancas = []
    for bruto_item, tipo, valor in zip(itens, tipos, valores):
        item = SessionExercise.objects.filter(
            pk=bruto_item, session=session
        ).select_related("exercise", "session__plan").first()
        if item is None:
            continue

        if tipo == "troca":
            novo = Exercise.objects.filter(
                pk=valor,
                is_active=True,
                muscle_group=item.exercise.muscle_group,
            ).first()
            if novo is None:
                continue
            mudancas.append(
                assistant.Mudanca(item=item, tipo="troca", porque="", novo_exercicio=novo)
            )
        elif tipo == "ajuste":
            try:
                sets, rest = (int(parte) for parte in valor.split(","))
            except (ValueError, TypeError):
                continue
            if not (1 <= sets <= 10 and 20 <= rest <= 300):
                continue
            mudancas.append(
                assistant.Mudanca(
                    item=item, tipo="ajuste", porque="", sets=sets, rest_seconds=rest
                )
            )
        elif tipo == "reordenar":
            parceiro = SessionExercise.objects.filter(
                pk=valor, session=session
            ).first()
            if parceiro is None or parceiro.pk == item.pk:
                continue
            mudancas.append(
                assistant.Mudanca(
                    item=item, tipo="reordenar", porque="", parceiro=parceiro
                )
            )
        elif tipo == "remocao":
            mudancas.append(assistant.Mudanca(item=item, tipo="remocao", porque=""))

    return mudancas


class AssistantView(OnboardingRequiredMixin, View):
    """Monta a proposta e devolve o corpo do drawer.

    Só GET, e nada é gravado: esta view responde "o que eu faria", e a resposta
    vira uma tela com um botão de confirmar. Ficha de treino é coisa que a
    pessoa decorou — mudar sem perguntar assusta mais do que ajuda.
    """

    def get(self, request, session_id, *args, **kwargs):
        session = _sessao_do_usuario(request, session_id)
        motivo = request.GET.get("motivo") or ""
        pedido = (request.GET.get("pedido") or "").strip()

        # "Ver outra opção" reenvia o mesmo pedido carregando o que já foi
        # recusado. Sem isso o botão devolveria eternamente a mesma sugestão.
        excluir = [int(x) for x in request.GET.getlist("excluir") if x.isdigit()]

        item = None
        if request.GET.get("item"):
            item = SessionExercise.objects.filter(
                pk=request.GET["item"], session=session
            ).select_related("exercise").first()

        contexto = {
            "session": session,
            "exercicios": session.exercises.select_related("exercise").order_by("order"),
            "motivo": motivo,
            "pedido": pedido,
            "excluir": excluir,
        }

        # Passo 1: a pessoa escolheu "trocar exercício" e ainda não disse qual.
        if motivo == assistant.TROCA and item is None and not pedido:
            contexto["escolher_exercicio"] = True
            return render(request, "workouts/partials/assistente_escolha.html", contexto)

        if pedido:
            sugestao = assistant.sugerir_do_texto(session, pedido)
            if excluir and sugestao.mudancas:
                intencao = assistant.interpretar(pedido, session=session)
                sugestao = assistant.sugerir(
                    session,
                    intencao.motivo,
                    item=intencao.item,
                    articulacao=intencao.articulacao,
                    excluir=excluir,
                )
        elif motivo in assistant.MOTIVOS:
            sugestao = assistant.sugerir(session, motivo, item=item, excluir=excluir)
        else:
            return render(request, "workouts/partials/assistente_menu.html", contexto)

        contexto["sugestao"] = sugestao
        contexto["recusados"] = excluir + [
            m.novo_exercicio.pk for m in sugestao.mudancas if m.novo_exercicio
        ]
        return render(request, "workouts/partials/assistente_previa.html", contexto)


class AssistantApplyView(OnboardingRequiredMixin, View):
    """Grava o que foi confirmado. Nunca toca no histórico de carga."""

    def post(self, request, session_id, *args, **kwargs):
        session = _sessao_do_usuario(request, session_id)
        mudancas = _mudancas_do_post(request, session)

        if not mudancas:
            messages.error(request, "Não consegui aplicar esse ajuste.")
            return redirect("workouts:routine")

        aplicadas = assistant.aplicar(session, mudancas)
        if aplicadas:
            messages.success(
                request,
                f"Treino {session.label} ajustado. Suas cargas anotadas continuam lá.",
            )
        else:
            messages.error(request, "Nada mudou — o ajuste não pôde ser aplicado.")
        return redirect("workouts:routine")


def _descanso_de(user, exercise) -> int:
    """O descanso prescrito para este exercício na ficha ativa.

    Serve ao cronômetro automático: terminada a série, o timer precisa saber
    quantos segundos contar, e a resposta está na prescrição — não num valor
    fixo igual para agachamento e rosca.
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
    return item or 90


class HealthExportView(OnboardingRequiredMixin, View):
    """O treino do dia em TCX, para importar no app Saúde.

    Uma PWA não escreve no HealthKit — não existe API web para isso, e o
    Health Connect do Android é igual. O caminho honesto é o arquivo: a pessoa
    exporta e abre no importador que já usa. `health_export.resumo_da_sessao()`
    é a mesma camada que um invólucro nativo chamaria, sem tocar em arquivo.
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
