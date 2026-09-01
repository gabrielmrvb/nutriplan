"""A aba de treino: a rotina da semana, a ficha de cada dia e a carga."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import Weekday
from accounts.views import OnboardingRequiredMixin
from achievements import services as conquistas

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

        # O balde "hoje" do histórico é de HOJE — e esta página desenha a
        # semana inteira. Aplicá-lo às fichas dos OUTROS dias fazia o supino
        # anotado hoje aparecer como concluído dentro do card de sexta, com as
        # cargas de hoje preenchidas nas séries de lá. O exercício se repete
        # entre fichas, então bastava um em comum para a ficha inteira mentir.
        #
        # Nada disso era gravado errado: `ExerciseLog` sempre teve a data certa.
        # Era a LEITURA que perdia o dia, e a tela afirmava um estado que o
        # banco não sustentava.
        #
        # Só o balde "hoje" é zerado, e a estreiteza é deliberada. A primeira
        # versão desta correção zerava também `delta` e `melhor_hoje`, e a
        # suíte pegou: o "+5" que compara a carga de hoje com a do último
        # treino sumia da tela inteira nos dias em que ninguém treina. Aquilo
        # responde "evoluí neste EXERCÍCIO?", que não é pergunta de um dia da
        # semana — e é comportamento que já existia e não estava quebrado.
        #
        # "anterior" também continua para todos: a carga do último treino
        # daquele exercício é justamente o que se consulta ao abrir a ficha de
        # outro dia.
        hoje_na_semana = timezone.localdate().weekday()
        for session in sessions:
            do_dia = session.weekday == hoje_na_semana
            for item in session.exercises.all():
                carga = historico.get(item.exercise_id)
                if carga is not None and not do_dia:
                    carga = dict(carga, hoje={})
                item.load = carga
                item.set_rows = set_rows(item, item.load)
                # O botão de copiar só existe quando há o que copiar — e a data
                # vai junto porque "copiar do último treino" sem dizer de quando
                # é copiar às cegas.
                # Quantas séries já saíram hoje. É o que o contador mostra e
                # o que o salvamento em bloco reescreve.
                item.feitas = len((item.load or {}).get("hoje") or {})

        marcar_ficha_aberta(sessions)

        # O treino de hoje sai da lista de fichas e passa a ser a tela.
        #
        # Antes ele era a terceira sanfona de uma pilha, e a pessoa rolava
        # 897px — medido a 390x844 — passando por dois treinos que não vai
        # fazer para chegar no que vai. `outras` é o programa: continua
        # inteiro, em sanfona, embaixo.
        hoje = next((s for s in sessions if s.eh_hoje), None)
        if hoje is not None:
            progresso_do_dia(hoje)

        context.update(
            {
                "nav": "workout",
                "plan": plan,
                "sessions": sessions,
                "hoje": hoje,
                "outras": [s for s in sessions if s is not hoje],
                # Só faz sentido perguntar "e quando é o próximo?" no dia em
                # que não há treino. Com treino hoje, o próximo é ruído.
                "proximo": proximo_treino(sessions) if hoje is None else None,
                "week": week_overview(sessions),
                "volume": muscle_volume(sessions),
                "total_sets": sum(session.total_sets for session in sessions),
                # O resumo do que foi feito HOJE alimenta duas coisas: o card
                # de compartilhamento e a exportação para o app de saúde. Sai
                # do registro de carga, não da ficha — o que vale é o que
                # aconteceu, não o que estava previsto.
                "resumo_hoje": health_export.resumo_da_sessao(user),
                # Duracao OBSERVADA, e nao a estimada do resumo: o card
                # so estampa minutos quando existe intervalo real entre a
                # primeira e a ultima serie anotadas. Sem isso, ele
                # apresentaria uma conta como se fosse cronometro.
                "minutos_observados": conquistas.duracao_observada(user),
            }
        )
        return context


def progresso_do_dia(session) -> None:
    """O avanço de hoje, derivado do que foi registrado — e só disso.

    O único fato que o banco guarda é `ExerciseLog`: uma linha por série
    anotada, com data. `item.feitas` é a contagem dessas linhas hoje, a mesma
    que o botão "OK 3/4" já mostra. Daqui saem três números derivados e o
    próximo exercício sem nenhuma série.

    O que este progresso NÃO é: "treino concluído". Não existe `TrainingSession`
    persistente, então ninguém pode afirmar que a pessoa terminou — ela pode
    ter anotado os nove e continuado, ou anotado três e ido embora. A tela diz
    o que aconteceu ("3 de 9 exercícios com série registrada hoje") e para aí.
    Trocar essa frase por "treino concluído" seria a interface afirmando um
    estado que nenhuma tabela sustenta.
    """
    itens = list(session.exercises.all())
    session.total_exercicios = len(itens)
    session.feitos_hoje = sum(1 for item in itens if item.feitas)
    session.pct_hoje = round(session.feitos_hoje * 100 / len(itens)) if itens else 0

    # Onde a pessoa retoma: o primeiro com série FALTANDO — e não o primeiro
    # sem nenhuma.
    #
    # A regra era `not item.feitas`, e ela discordava do modo treino: quem
    # anotasse uma de quatro séries em todos os exercícios não tinha mais
    # "próximo" aqui, o botão sumia, e o caminho para a tela guiada — que ainda
    # tinha 27 séries pela frente — desaparecia da lista. Uma regra só nos dois
    # lugares, e é esta.
    session.proximo = next(
        (item for item in itens if item.feitas < item.sets), None
    )
    for item in itens:
        item.eh_o_proximo = item is session.proximo


def proximo_treino(sessions):
    """Qual treino vem a seguir, para o dia em que hoje é descanso.

    Sai de `weekday`, que a pessoa escolheu no cadastro — não é previsão. Anda
    os sete dias seguintes e devolve o primeiro que tem sessão, com quantos
    dias faltam, para a tela poder dizer "amanhã" em vez de repetir o nome do
    dia da semana.
    """
    if not sessions:
        return None

    hoje = timezone.localdate().weekday()
    for adiante in range(1, 8):
        alvo = (hoje + adiante) % 7
        sessao = next((s for s in sessions if s.weekday == alvo), None)
        if sessao is not None:
            return {"session": sessao, "dias": adiante}
    return None


def marcar_ficha_aberta(sessions) -> None:
    """Decide qual ficha da semana já vem aberta na tela.

    As cinco fichas empilhadas somavam uma página de rolagem infinita, e a
    pessoa passava por quatro treinos que não vai fazer hoje para chegar no
    que vai. Só uma abre.

    Com o treino de hoje promovido a topo da tela, esta função passou a
    responder por um caso só: o dia de descanso. Aí quem abre é o PRÓXIMO
    treino — e não o primeiro da lista — porque é dele que o cabeçalho da tela
    acabou de falar, e abrir outro faria topo e corpo tratarem de dias
    diferentes. Sem nenhum dia à frente (plano vazio de futuro), cai no
    primeiro: abrir nenhuma deixaria a tela parecendo vazia.
    """
    if not sessions:
        return

    hoje = timezone.localdate().weekday()
    do_dia = next((s for s in sessions if s.weekday == hoje), None)
    seguinte = proximo_treino(sessions)
    escolhida = do_dia or (seguinte["session"] if seguinte else sessions[0])

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

        # As conquistas sao avaliadas AQUI, depois de o `ExerciseLog` estar
        # gravado, e so aqui.
        #
        # Nao no painel, nao em refeicao, nao em agua: as conquistas da V1 sao
        # todas de treino, e pendurar a avaliacao em toda escrita do app
        # cobraria consultas o dia inteiro por um evento que acontece algumas
        # vezes por semana. Este e o unico ponto do fluxo em que um dia de
        # treino passa a existir.
        novas = conquistas.avaliar(request.user)
        ids_novos = conquistas.anunciar(request, novas)

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
                    # A pagina nao recarrega, entao o aviso precisa vir por
                    # aqui — senao a conquista so apareceria na proxima visita.
                    "conquistas": [
                        {
                            "id": c.pk,
                            "titulo": c.titulo,
                            "frase": c.frase,
                            "emoji": c.emoji,
                            "tipo": c.tipo_de_card,
                            "valor": c.valor,
                            "rotulo": c.rotulo,
                            "destaque": c.destaque,
                        }
                        for c in novas
                    ],
                    "conquistas_ids": ids_novos,
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


class ModoTreinoView(OnboardingRequiredMixin, TemplateView):
    """Uma tela, uma pergunta: o que eu faço agora?

    A lista inteira continua existindo em `/treino/` — ela é ótima para
    conferir e revisar. O que ela não faz é responder, entre uma série e outra,
    com o celular na mão e o braço tremendo, qual é o próximo movimento: para
    isso a pessoa rolava a página procurando onde tinha parado.

    Aqui nada é guardado a mais. O exercício atual, a série atual e o descanso
    que falta são calculados de `ExerciseLog` a cada carregamento — ver
    `services.estado_do_treino`.
    """

    template_name = "workouts/agora.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["nav"] = "workout"

        if not services.has_training_days(user):
            context["estado"] = services.EstadoDoTreino()
            return context

        services.sync_active_routine(user)
        # `estado` já traz o intervalo entre o primeiro e o último registro,
        # calculado de `created_at`. Esta view NÃO chama
        # `health_export.resumo_da_sessao`: o `inicio` e o `fim` de lá são
        # estimativa (horário da ficha mais uma duração de fórmula), e foi
        # exatamente essa chamada que fez a tela mostrar "47 min" para um
        # treino cujos registros distavam 1,1 minuto. Quem precisar do resumo
        # estimado é o TCX, em `HealthExportView`.
        context["estado"] = services.estado_do_treino(user)
        return context


class ConcluirSerieView(OnboardingRequiredMixin, View):
    """Grava UMA série do modo treino, ou desfaz a última.

    O formulário manda `set_number` explícito, calculado pelo servidor e
    escrito no HTML — e não "mais uma". A diferença importa: `record_load` faz
    `update_or_create` naquela série, então mandar duas vezes corrige em vez de
    duplicar. Um contador ("incremente") transformaria toque duplo, botão
    voltar e reenvio de formulário em séries que ninguém fez, e é exatamente o
    que o CLAUDE.md manda não fazer com a fila offline.
    """

    def post(self, request, *args, **kwargs):
        destino = redirect("workouts:now")
        # O id é convertido ANTES de ir ao banco: `pk=""` e `pk="abc"` levantam
        # ValueError dentro do ORM, e ValueError numa view é 500. Formulário
        # corrompido merece 404, não página de erro.
        try:
            exercise_id = int(request.POST.get("exercise_id") or "")
        except (TypeError, ValueError):
            raise Http404("exercício inválido")
        exercise = get_object_or_404(Exercise, pk=exercise_id, is_active=True)

        if request.POST.get("acao") == "desfazer":
            ultima = (
                ExerciseLog.objects.filter(
                    user=request.user, exercise=exercise, date=timezone.localdate()
                )
                .order_by("-set_number")
                .first()
            )
            if ultima is not None:
                ultima.delete()
            return destino

        bruto = (request.POST.get("weight_kg") or "").replace(",", ".").strip()
        try:
            peso = Decimal(bruto)
        except (InvalidOperation, TypeError):
            messages.error(request, "Carga inválida — use números, como 42,5.")
            return destino
        if peso < 0 or peso > 999:
            messages.error(request, "Carga fora do que uma barra aguenta.")
            return destino

        try:
            serie = int(request.POST.get("set_number", 1))
        except (TypeError, ValueError):
            serie = 1
        serie = max(1, min(serie, 20))

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
        return destino
