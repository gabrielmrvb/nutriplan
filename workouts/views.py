"""A aba de treino: a rotina da semana, a ficha de cada dia e a carga."""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import (
    MINUTOS_POR_DURACAO,
    TETO_POR_DURACAO,
    DuracaoTreino,
    Profile,
    Weekday,
)
from accounts.views import OnboardingRequiredMixin
from achievements import services as conquistas

from . import curva as _curva
from . import doutrina, health_export, services
from .models import (
    EventoDeProduto,
    VersaoDoTreino,
    Exercise,
    ExerciseLog,
    MuscleGroup,
    SessionExercise,
    TrainingSession,
)
from config.acoes import AcaoDeTela


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
        # A OPÇÃO DE REFERÊNCIA, e não `exercises.all()`: desde 15/09/2026 a
        # sessão guarda até duas opções, e somar as duas diria que a pessoa
        # faz os dois treinos no mesmo dia.
        for item in session.da_opcao(session.opcoes[0]):
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


#: Uma linha por série prescrita. Era uma cópia de `estado_do_treino` que
#: divergia dela (esta trazia a série anterior, a outra não); a única versão
#: mora em `services.linhas_de_serie`, e o nome antigo fica para quem chama.
set_rows = services.linhas_de_serie


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
        linhas = list(
            plan.sessions.prefetch_related("exercises__exercise")
        )
        # "Outras formas": as trocas da pessoa vestem as linhas antes de
        # qualquer contagem — a série feita no substituto conta no painel.
        services.aplicar_trocas(user, linhas)
        # A SEMANA VISTA PELA POSIÇÃO NO CICLO (17/09/2026): com a rotação
        # contínua a letra de cada dia muda de semana para semana, e o que o
        # painel desenha é a semana de HOJE — cada dia de treino vestindo a
        # letra da posição dele (`sessoes_da_semana`). No plano antigo são as
        # próprias linhas, presas ao dia da semana.
        hoje_data = timezone.localdate()
        sessions = services.sessoes_da_semana(plan, hoje_data, linhas)

        # O histórico é anexado ao item por `anexar_historico`, que faz UMA
        # consulta para a página inteira. A tela principal já não desenha os
        # formulários, mas o resumo de cada sessão continua lendo `feitas`
        # para dizer quanto do dia já saiu.
        anexar_historico(user, sessions)
        nomear_ocorrencias(sessions)

        marcar_ficha_aberta(sessions)

        # O treino de hoje sai da lista de fichas e passa a ser a tela.
        #
        # Antes ele era a terceira sanfona de uma pilha, e a pessoa rolava
        # 897px — medido a 390x844 — passando por dois treinos que não vai
        # fazer para chegar no que vai. `outras` é o programa: continua
        # inteiro, em sanfona, embaixo.
        hoje = next((s for s in sessions if s.eh_hoje), None)
        if hoje is not None:
            preparar_dia(user, hoje, linhas)
            progresso_do_dia(hoje)

        context.update(
            {
                "nav": "workout",
                "plan": plan,
                "sessions": sessions,
                "letras": agrupar_por_letra(sessions),
                "hoje": hoje,
                "outras": [s for s in sessions if s is not hoje],
                # Só faz sentido perguntar "e quando é o próximo?" no dia em
                # que não há treino. Com treino hoje, o próximo é ruído.
                "proximo": proximo_treino(sessions, plan, hoje_data, linhas) if hoje is None else None,
                "week": week_overview(sessions),
                # O que a pessoa pediu, o que foi aplicado e por quê — só
                # quando divergem. Ver `services.divisao_explicada`.
                #
                # `dias` VEM DO PLANO, e as duas razões andam juntas. A certa:
                # a ressalva explica a divisão DESTE plano, e `days_per_week` é
                # o número congelado nele — plano é retrato. A barata: sem ela
                # a função faz `training_days.count()`, e a tela subia de 21
                # para 22 consultas. `sync_active_routine`, logo acima, já
                # garante que o plano vale para os dias de hoje.
                "divisao": services.divisao_explicada(
                    user, dias=plan.days_per_week
                ),
                "volume": muscle_volume(sessions),
                "total_sets": sum(session.total_sets for session in sessions),
                # O resumo do que foi feito HOJE alimenta duas coisas: o card
                # de compartilhamento e a exportação para o app de saúde. Sai
                # do registro de carga, não da ficha — o que vale é o que
                # aconteceu, não o que estava previsto.
                # A sessão e a escolha de hoje vão junto: o painel já as
                # tem, e refazê-las custava três consultas.
                "resumo_hoje": health_export.resumo_da_sessao(
                    user,
                    sessao=hoje,
                    escolha=hoje.escolha if hoje is not None else health_export.NAO_INFORMADA,
                ),
                # Duracao OBSERVADA, e nao a estimada do resumo: o card
                # so estampa minutos quando existe intervalo real entre a
                # primeira e a ultima serie anotadas. Sem isso, ele
                # apresentaria uma conta como se fosse cronometro.
                "minutos_observados": conquistas.duracao_observada(user),
                # A DURAÇÃO SE ESCOLHE AQUI (16/09/2026, avaliação D4). A
                # pergunta saiu do cadastro em 10/09 porque ninguém calibra
                # "rápido, padrão ou completo" antes de ver uma ficha; a
                # área de Treino é onde a ficha está — e não tinha onde
                # escolher. `teto_completo_de` é o teto que o motor obedece
                # HOJE para esta pessoa (65 para quem nunca respondeu).
                "duracao": {
                    "atual": services.duracao_de(user),
                    "teto": services.teto_completo_de(user),
                    "opcoes": opcoes_de_duracao(),
                },
            }
        )
        return context


def opcoes_de_duracao() -> list:
    """As faixas que a área de Treino oferece: valor, nome curto e teto.

    Lê `DuracaoTreino.escolhas_visiveis` — sem "Sem limite", que continua no
    banco para quem já tem e não é oferecido em formulário nenhum — e o teto
    de `TETO_POR_DURACAO`, o mesmo que o motor obedece. O nome curto é a
    parte do rótulo antes do travessão: "Rápido", "Padrão", "Completo".
    """
    return [
        {
            "valor": faixa.value,
            "nome": faixa.label.split(" — ")[0],
            "teto": TETO_POR_DURACAO[faixa],
        }
        for faixa in DuracaoTreino.escolhas_visiveis()
    ]


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
    itens = list(getattr(session, "itens_do_dia", None) or session.da_opcao(session.opcoes[0]))
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


def preparar_dia(user, sessao, linhas=None) -> None:
    """A sessão de hoje ganha a opção do dia — a pinada pela primeira série,
    senão a variação do ciclo (ficha única por letra, 17/09/2026) — e a
    conta da versão rápida para o painel oferecer "Menos tempo hoje?"."""
    from . import opcoes as motor_de_opcoes

    escolha = services.escolha_do_dia(user)
    if escolha is not None and escolha.session_id != sessao.pk:
        escolha = None
    sessao.escolha = escolha
    dia = getattr(sessao, "data", None) or timezone.localdate()
    sessao.opcao_do_dia = services.opcao_do_dia(user, sessao, dia, linhas, escolha=escolha)
    sessao.versao_do_dia = escolha.versao if escolha else "completo"
    sessao.itens_do_dia = sessao.da_opcao(sessao.opcao_do_dia)
    # A rápida só é oferecida quando muda alguma coisa: um treino que já
    # cabe em 40 minutos não tem versão rápida, e oferecer o mesmo treino
    # com outro nome seria uma escolha falsa.
    itens = sessao.itens_do_dia
    graus = services.prioridades_da_sessao(itens)
    ficam, removidos = motor_de_opcoes.versao_rapida(
        [(item, item.sets, grau) for item, grau in zip(itens, graus)], sessao.main_groups
    )
    sessao.minutos = sessao.minutos_da_opcao(sessao.opcao_do_dia)
    sessao.rapida_muda = bool(removidos) or sum(s for _, s in ficam) != sum(i.sets for i in itens)
    sessao.rapida_minutos = round(
        services.segundos_da_sessao([(s, i.rest_seconds, i.exercise.is_compound) for i, s in ficam]) / 60
    )


def agrupar_por_letra(sessions) -> list:
    """Um cartão por LETRA — A · B · C —, e não um por dia.

    Desde 15/09/2026 as ocorrências da mesma letra carregam as MESMAS opções,
    então dois cartões "A" seriam a mesma ficha duas vezes; a letra diz os
    dias em que cai. Plano antigo AJUSTADO pela pessoa (`customized_at`) pode
    ter A1 ≠ A2 de verdade — aí a letra não agrupa, e cada sessão continua
    sendo um cartão, com o rótulo numerado de `nomear_ocorrencias`.
    """
    por_letra = {}
    for sessao in sessions:
        assinatura = tuple(
            (item.opcao, item.exercise_id, item.sets) for item in sessao.exercises.all()
        )
        por_letra.setdefault(sessao.label, []).append((sessao, assinatura))
    cartoes = []
    for label, grupo in por_letra.items():
        iguais = len({assinatura for _, assinatura in grupo}) == 1
        if not iguais:
            for sessao, _ in grupo:
                cartoes.append(_cartao_da_letra(sessao.rotulo, [sessao]))
            continue
        cartoes.append(_cartao_da_letra(label, [sessao for sessao, _ in grupo]))
    cartoes.sort(key=lambda c: c["ordem"])
    return cartoes


def _cartao_da_letra(rotulo, sessoes) -> dict:
    hoje = next((s for s in sessoes if getattr(s, "eh_hoje", False)), None)
    referencia = hoje or sessoes[0]
    opcao = referencia.opcoes[0]
    return {
        "rotulo": rotulo,
        "label": referencia.label,
        "sessao": referencia,
        "name": referencia.name,
        "focus": referencia.focus,
        "dias": [s.weekday_display for s in sessoes],
        "eh_hoje": hoje is not None,
        "exercicios": len(referencia.da_opcao(opcao)),
        "series": referencia.series_da_opcao(opcao),
        "minutos": referencia.minutos_da_opcao(opcao),
        "ordem": min(s.order for s in sessoes),
    }


#: "Duas versões disponíveis" — e "Três" quando a letra cai três vezes na
#: semana (uma opção por ocorrência, mínimo duas). Só no cartão.


def nomear_ocorrencias(sessions) -> None:
    """Dá A1 e A2 às sessões que repetem a letra, e deixa A sozinho como A.

    O DEFEITO QUE ISTO FECHA, e ele é de leitura, não de prescrição.

    Cinco dias num ABC viram A, B, C, A, B. As duas ocorrências de A nascem com
    a dose cheia do catálogo, e `aparar_volume_semanal` cede sempre a sessão
    mais cheia — então uma das passagens sai menor que a outra. Quem abre o
    segundo A lê o mesmo título com menos exercícios e conclui que a ficha
    está incompleta.

    Ela não está: o teto é da SEMANA, e a segunda passagem é o que sobrou
    depois de ele ser respeitado. Com A1 e A2 a pessoa vê que são duas
    passagens do mesmo treino, e não duas cópias em que uma deu errado.

    `vezes` VAI JUNTO, e não é enfeite: em sete dias a letra A aparece TRÊS
    vezes, e a frase da ficha dizia "duas" para todo mundo. Contar aqui é de
    graça — o laço já contou para decidir o rótulo.

    E ELA NÃO PROMETE VARIEDADE. Uma versão anterior desta frase afirmava que
    as passagens "trazem exercícios diferentes", com um caso auditado a
    sustentar. O caso existia; a regra, não. Medido em 09/09/2026 nos perfis
    de 4, 5, 6 e 7 dias: em quatro dias a segunda passagem de A é um
    SUBCONJUNTO da primeira, e em sete dias as três são IDÊNTICAS. B e C com
    seis dias realmente divergem. Uma frase verdadeira em parte dos casos, na
    tela de todos eles, é uma frase falsa.

    A LETRA CONTINUA SENDO A LETRA NO BANCO. `TrainingSession.label` não é
    tocado — ele é a identidade que liga a sessão ao modelo do catálogo, e
    gravar "A1" ali quebraria `templates_for`, a conferência de prescrição e o
    histórico. O que nasce aqui é `rotulo`, de exibição, calculado por
    ocorrência e nunca por posição na lista.
    """
    quantas = {}
    for sessao in sessions:
        quantas[sessao.label] = quantas.get(sessao.label, 0) + 1

    # DESDE 15/09/2026 a numeração só existe quando as ocorrências DIFEREM
    # de verdade (plano antigo ajustado à mão). Com as mesmas opções nas duas
    # passagens, "A1" e "A2" diriam dois treinos onde há um.
    conteudos = {}
    for sessao in sessions:
        conteudos.setdefault(sessao.label, set()).add(
            tuple((item.opcao, item.exercise_id, item.sets) for item in sessao.exercises.all())
        )
    vistas = {}
    for sessao in sessions:
        if quantas[sessao.label] > 1 and len(conteudos[sessao.label]) > 1:
            vistas[sessao.label] = vistas.get(sessao.label, 0) + 1
            sessao.rotulo = "%s%d" % (sessao.label, vistas[sessao.label])
            sessao.repetida = True
            sessao.vezes = quantas[sessao.label]
            sessao.vezes_texto = services.VEZES.get(
                sessao.vezes, str(sessao.vezes)
            )
        else:
            sessao.rotulo = sessao.label
            sessao.repetida = False
            sessao.vezes = 1
            sessao.vezes_texto = "uma"


def anexar_historico(user, sessions) -> None:
    """Pendura carga, linhas de série e contagem de hoje em cada item.

    UMA consulta para todas as sessões recebidas — `load_history` resolve o
    lote —, e é por isso que esta função recebe uma LISTA e não uma sessão:
    chamá-la por sessão seria N+1 na tela que desenha a semana.

    Extraída de `WorkoutView` quando a ficha ganhou rota própria. Duas cópias
    desta preparação divergiriam na primeira vez que alguém ajustasse uma —
    e a que fica errada é sempre a que ninguém está olhando.

    O BALDE "HOJE" É DE HOJE, e aplicá-lo às fichas dos outros dias fazia o
    supino anotado hoje aparecer como concluído dentro do card de sexta, com as
    cargas de hoje preenchidas nas séries de lá. `ExerciseLog` sempre teve a
    data certa — era a LEITURA que perdia o dia.

    Só o balde "hoje" é zerado, e a estreiteza é deliberada: "anterior" é
    justamente o que se consulta ao abrir a ficha de outro dia, e o "+5" que
    compara com o último treino responde "evoluí neste exercício?", que não é
    pergunta de um dia da semana.
    """
    exercicios = [
        item.exercise for session in sessions for item in session.exercises.all()
    ]
    historico = services.load_history(user, exercicios)
    hoje_na_semana = timezone.localdate().weekday()

    # A de hoje POR ÚLTIMO: com a rotação, a letra que cai duas vezes na
    # semana é a MESMA linha vestindo dois dias, e os itens são os mesmos
    # objetos — a ocorrência que não é hoje apagaria o "hoje" da que é.
    for session in sorted(sessions, key=lambda s: s.weekday == hoje_na_semana):
        do_dia = session.weekday == hoje_na_semana
        for item in session.exercises.all():
            carga = historico.get(item.exercise_id)
            if carga is not None and not do_dia:
                carga = dict(carga, hoje={})
            item.load = carga
            item.set_rows = set_rows(item, item.load)
            # Quantas séries já saíram hoje. É o que o contador mostra e o que
            # o salvamento em bloco reescreve.
            item.feitas = len((item.load or {}).get("hoje") or {})


def proximo_treino(sessions, plan=None, hoje=None, linhas=None):
    """Qual treino vem a seguir, para o dia em que hoje é descanso.

    Sai de `weekday`, que a pessoa escolheu no cadastro — não é previsão. Anda
    os sete dias seguintes e devolve o primeiro que tem sessão, com quantos
    dias faltam, para a tela poder dizer "amanhã" em vez de repetir o nome do
    dia da semana. Com a rotação contínua a letra do próximo dia sai da DATA
    dele (`sessao_do_dia`): a segunda-feira que vem pode ser C, e não a A
    desta semana.
    """
    if not sessions:
        return None

    if services.ciclo_roda(plan):
        hoje_data = hoje or timezone.localdate()
        for adiante in range(1, 8):
            sessao = services.sessao_do_dia(plan, hoje_data + timedelta(days=adiante), linhas)
            if sessao is not None:
                return {"session": sessao, "dias": adiante}
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


class FichaDaSessaoView(OnboardingRequiredMixin, TemplateView):
    """A ficha completa de UMA sessão, em rota própria.

    POR QUE ELA EXISTE. A tela de treino renderizava o cartão completo de todo
    exercício de TODA sessão da semana: sanfona, vídeo, chips de músculo, dica,
    formulário de carga e histórico, multiplicados por trinta e poucos itens.
    Medido no perfil de seis dias: 259 kB de HTML, 22 formulários, 29 sanfonas,
    141 botões e 85 campos, quase todos fora da área visível. A pessoa rolava
    dois paredões — o de hoje e o da semana — para chegar em qualquer coisa.

    A ficha continua inteira, e é isso que separa esta mudança da tentativa
    anterior. Em 09/09/2026 alguém trocou o cartão da semana pela linha
    compacta e vinte e um testes reprovaram, com razão: aquilo APAGAVA registro
    de série, carga, repetições, descanso, progressão e histórico. Aqui nada é
    apagado — o detalhe muda de PÁGINA. Quem abre a ficha recebe tudo o que
    recebia; quem não abre para de pagar por ela.

    A SESSÃO É BUSCADA PELO PLANO ATIVO DA PRÓPRIA PESSOA. Sem esse filtro, um
    id de outra conta abriria a ficha alheia — é o mesmo fechamento de IDOR que
    `MarkMealView` faz com o slot.
    """

    template_name = "workouts/ficha.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        sessao = get_object_or_404(
            TrainingSession.objects.select_related("plan"),
            pk=kwargs["sessao_id"],
            plan__user=user,
            plan__is_active=True,
        )
        # `prefetch` aqui e não no `get_object_or_404`: o filtro precisa bater
        # no banco antes de valer a pena trazer os exercícios.
        sessao = (
            TrainingSession.objects.filter(pk=sessao.pk)
            .prefetch_related("exercises__exercise")
            .first()
        )

        hoje_data = timezone.localdate()
        linhas = list(sessao.plan.sessions.prefetch_related("exercises__exercise"))
        # A sessão pedida e as linhas são objetos distintos (duas consultas):
        # as trocas vestem os dois, para a lista e a contagem concordarem.
        services.aplicar_trocas(user, [sessao, *linhas])
        # COM A ROTAÇÃO, A LINHA DA LETRA VESTE O DIA DE HOJE ANTES DO
        # HISTÓRICO (17/09/2026). `anexar_historico` só aplica o balde "hoje"
        # à sessão cujo `weekday` é o de hoje — e a linha da letra guarda o
        # dia da PRIMEIRA semana: numa quinta em que a letra A (linha de
        # segunda) cai de novo, a ficha de hoje abria sem nenhuma série de
        # hoje ("0/4" depois de registrar uma), enquanto a execução, que passa
        # por `sessao_do_dia`, mostrava a série. Passou despercebido porque os
        # testes rodaram em dias em que letra e linha coincidiam. A mesma
        # cópia vestida que a execução usa resolve os dois lados de uma vez.
        if services.ciclo_roda(sessao.plan) and services.letra_do_dia(sessao.plan, hoje_data, linhas) == sessao.label:
            vestida = services.sessao_do_dia(sessao.plan, hoje_data, linhas)
            if vestida is not None and vestida.pk == sessao.pk:
                sessao = vestida
        # A MESMA preparação da tela principal, pela mesma função. Uma segunda
        # cópia divergiria, e a que fica errada é a que ninguém está olhando.
        anexar_historico(user, [sessao])
        # A NOMEAÇÃO PRECISA DA SEMANA INTEIRA: "A1" só existe porque há um A2,
        # e uma sessão sozinha não sabe disso. Buscar as irmãs custa UMA
        # consulta e é o que faz o título da ficha concordar com o cartão que
        # levou até ela.
        irmas = services.sessoes_da_semana(sessao.plan, hoje_data, linhas)
        nomear_ocorrencias(irmas)
        sessao.rotulo = next(
            (s.rotulo for s in irmas if s.pk == sessao.pk), sessao.label
        )
        sessao.repetida = next(
            (s.repetida for s in irmas if s.pk == sessao.pk), False
        )
        sessao.vezes_texto = next(
            (s.vezes_texto for s in irmas if s.pk == sessao.pk), "uma"
        )
        if services.ciclo_roda(sessao.plan):
            # Com a rotação, "é hoje" é a LETRA de hoje — o dia da semana da
            # linha é o da primeira semana —, e o cabeçalho diz em que dias
            # desta semana a letra cai.
            sessao.eh_hoje = services.letra_do_dia(sessao.plan, hoje_data, linhas) == sessao.label
            sessao.aberta = True
            sessao.dias_texto = " · ".join(
                s.weekday_display for s in irmas if s.label == sessao.label
            ) or sessao.weekday_display
        else:
            marcar_ficha_aberta([sessao])
            sessao.dias_texto = sessao.weekday_display
        if sessao.eh_hoje:
            preparar_dia(user, sessao, linhas)
            progresso_do_dia(sessao)

        context.update({
            "nav": "workout",
            "sessao": sessao,
            "plan": sessao.plan,
        })
        context.update(self.contexto_da_ficha(user, sessao, linhas, irmas, hoje_data))
        return context

    @staticmethod
    def _data_da_ficha(sessao, irmas, hoje_data):
        """A data que a ficha de OUTRO dia representa: a próxima ocorrência
        da letra nesta semana (as cópias vestidas de `sessoes_da_semana`
        trazem `.data`); passada a última, a última. Plano preso ao dia da
        semana: o próprio dia da linha nesta semana."""
        segunda = hoje_data - timedelta(days=hoje_data.weekday())
        datas = sorted(
            getattr(s, "data", None) or (segunda + timedelta(days=s.weekday))
            for s in irmas if s.pk == sessao.pk
        )
        if not datas:
            return segunda + timedelta(days=sessao.weekday)
        return next((d for d in datas if d >= hoje_data), datas[-1])

    def contexto_da_ficha(self, user, sessao, linhas, irmas, hoje_data) -> dict:
        """UMA lista: a variação da letra para a DATA da ficha (ficha única
        por letra, 17/09/2026). Hoje: a opção pinada pela primeira série,
        senão a do ciclo (`preparar_dia` já decidiu). Outro dia: a variação
        da PRÓXIMA ocorrência da letra nesta semana — a linha crua não tem
        data, e usar "hoje" dava a uma ficha de sexta a variação de quarta
        (revisão adversarial de 17/09). O número da opção não sai daqui para
        a tela. Na versão rápida (pinada no painel), a lista marca o que
        fica de fora e quantas séries cada exercício mantém."""
        from . import opcoes as motor_de_opcoes

        eh_hoje = getattr(sessao, "eh_hoje", False)
        escolha = getattr(sessao, "escolha", None) if eh_hoje else None
        if eh_hoje:
            numero = sessao.opcao_do_dia
        else:
            numero = services.variacao_do_dia(sessao.plan, self._data_da_ficha(sessao, irmas, hoje_data), sessao, linhas)
        versao = escolha.versao if escolha else "completo"
        itens = sessao.da_opcao(numero)
        graus = services.prioridades_da_sessao(itens)
        ficam, removidos = motor_de_opcoes.versao_rapida(
            [(item, item.sets, grau) for item, grau in zip(itens, graus)],
            sessao.main_groups,
        )
        rapida_series = {item.exercise_id: series for item, series in ficam}
        for item in itens:
            item.series_rapida = rapida_series.get(item.exercise_id)
            item.fora_da_rapida = item.exercise_id not in rapida_series
        # O selo "Principal": o primeiro composto de cada grupo anunciado.
        services.marcar_quem_abre_o_grupo(itens, sessao.main_groups)
        # "outras formas" na linha, só quando a porta leva a alguma (uma consulta).
        services.contar_outras_formas(
            user, itens, permitidos=doutrina.equipamentos_de(self.perfil_do_dispatch.equipamento),
        )
        equipamentos = sorted({
            item.exercise.get_equipment_display()
            for item in itens if getattr(item.exercise, "equipment", "")
        })
        ficha = {
            "executavel": eh_hoje,
            "itens": itens,
            "principais": sessao.principais_da_opcao(numero),
            "complementares": sessao.complementares_da_opcao(numero),
            "series": sum(item.sets for item in itens),
            "minutos": sessao.minutos_da_opcao(numero),
            "rapida_series": sum(series for _, series in ficam),
            "rapida_minutos": round(
                services.segundos_da_sessao(
                    [(series, item.rest_seconds, item.exercise.is_compound) for item, series in ficam]
                ) / 60
            ),
            "removidos": removidos,
            "equipamentos": equipamentos,
        }
        return {
            "ficha": ficha,
            "escolha": escolha,
            "versao": versao,
            "rapida": versao == "rapido",
        }


class TrocarExercicioView(AcaoDeTela, OnboardingRequiredMixin, View):
    """"Outras formas": troca `original` por `substituto` na ficha da pessoa
    (`services.registrar_troca`), ou desfaz (`desfazer=1`). Estado
    absoluto, sem `op_id`: repetir o pedido não muda nada. Volta para a
    leitura do exercício que ficou na ficha, com a mesma volta (`?de=`)."""

    tela_da_acao = "workouts:routine"

    def post(self, request, *args, **kwargs):
        try:
            original = Exercise.objects.get(pk=int(request.POST.get("original") or ""), is_active=True)
        except (TypeError, ValueError, Exercise.DoesNotExist):
            raise Http404("exercício ilegível")
        de = request.POST.get("de") if request.POST.get("de") in ExercicioView.ORIGENS else None
        sessao = request.POST.get("sessao") if (request.POST.get("sessao") or "").isdigit() else None
        query = ""
        if de:
            query = "?de=%s" % de + ("&sessao=%s" % sessao if de == "ficha" and sessao else "")
        if request.POST.get("desfazer"):
            if services.desfazer_troca(request.user, original):
                messages.success(request, "De volta ao original: %s." % original.name)
            return redirect(reverse("workouts:exercicio", args=[original.pk]) + query)
        try:
            substituto = Exercise.objects.get(pk=int(request.POST.get("substituto") or ""), is_active=True)
        except (TypeError, ValueError, Exercise.DoesNotExist):
            raise Http404("exercício ilegível")
        try:
            services.registrar_troca(request.user, original, substituto)
        except services.TrocaInvalida as erro:
            messages.error(request, str(erro))
            return redirect(reverse("workouts:exercicio", args=[original.pk]) + query)
        messages.success(request, "Trocado: %s no lugar de %s. Séries e descanso continuam os mesmos." % (substituto.name, original.name))
        return redirect(reverse("workouts:exercicio", args=[substituto.pk]) + query)


class VersaoRapidaHojeView(AcaoDeTela, OnboardingRequiredMixin, View):
    """"Menos tempo hoje?" — pina a versão rápida no registro do dia (a mesma
    escolha que a primeira série grava; `completo=1` desfaz) e anota UM
    `EventoDeProduto` por pessoa e dia. A ação é só POST; o GET volta ao
    painel (`config/acoes.py`)."""

    tela_da_acao = "workouts:routine"

    def post(self, request, *args, **kwargs):
        dia = timezone.localdate()
        plan = services.get_active_routine(request.user)
        sessao = services.sessao_do_dia(plan, dia)
        if sessao is None:
            messages.info(request, "Hoje não é dia de treino.")
            return redirect("workouts:routine")
        escolha = services.escolha_do_dia(request.user, dia)
        opcao = services.opcao_do_dia(request.user, sessao, dia, escolha=escolha)
        if request.POST.get("completo"):
            services.registrar_escolha(request.user, sessao, opcao, versao=VersaoDoTreino.COMPLETO, dia=dia)
            return redirect("workouts:routine")
        services.registrar_escolha(request.user, sessao, opcao, versao=VersaoDoTreino.RAPIDO, dia=dia)
        EventoDeProduto.objects.get_or_create(
            user=request.user, nome=EventoDeProduto.VERSAO_RAPIDA, date=dia
        )
        return redirect("workouts:routine")


class RecordLoadView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Salva a carga usada num exercício. A AÇÃO é só POST — isso muda
    estado; o GET devolve a ficha da semana (`config/acoes.py`)."""

    #: A carga é anotada na ficha da semana, e é para lá que um GET volta.
    tela_da_acao = "workouts:routine"

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
        # gravado — e SÓ QUANDO HÁ MOTIVO (T2.4, 17/09/2026): na primeira
        # série do dia (um dia de treino passa a existir) ou quando a carga
        # supera o recorde — a mesma guarda de `ConcluirSerieView`. O
        # catálogo inteiro custa dezenas de consultas, e esta rota pagava em
        # toda carga anotada; abaixo do recorde, no meio do treino, nenhuma
        # regra muda de resposta.
        hoje = timezone.localdate()
        primeira_do_dia = not (
            ExerciseLog.objects.filter(user=request.user, date=hoje)
            .exclude(exercise=exercise, set_number=serie)
            .exists()
        )
        if primeira_do_dia or services.supera_recorde(request.user, exercise, peso, dia=hoje):
            novas = conquistas.avaliar(request.user)
        else:
            novas = []
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


class RegenerarTreinoView(OnboardingRequiredMixin, View):
    """A pessoa pediu: a ficha é remontada com o catálogo de hoje. O plano
    antigo fica inativo — é retrato, e o histórico de carga não aponta para
    ele (`ExerciseLog` é por exercício e data).

    O GET leva de volta à Home, onde o aviso mora: é ali que o `next` do
    login aterrissa quando a sessão expira no meio do toque
    (`config/test_acoes_com_tela.py` — nenhuma ação responde 405 em branco).
    """

    def get(self, request, *args, **kwargs):
        return redirect("plans:today")

    def post(self, request, *args, **kwargs):
        services.create_routine(request.user)
        messages.success(request, "Treino regenerado com o catálogo de hoje.")
        return redirect("workouts:routine")


class DuracaoDoTreinoView(OnboardingRequiredMixin, View):
    """Rápido · Padrão · Completo, escolhido na área de Treino (D4, 16/09/2026).

    Grava `Profile.duracao_treino`, deriva `TrainingDay.duration_min` (o
    contrato do cardápio — `plans/meal_planner.py` soma `start_time +
    duration_min`; é o que `TrainingForm.save` já fazia quando a pergunta
    morava no cadastro) e deixa `sync_active_routine` decidir: faixa
    diferente da que a ficha guarda é `rotina_invalida`, e remonta. As travas
    de sempre valem e a tela DIZ qual valeu — com série registrada hoje a
    ficha muda amanhã; ficha ajustada à mão não é remontada, e a faixa fica
    gravada para a próxima remontagem.

    Lista fechada: só `escolhas_visiveis`. "Sem limite" não entra por aqui —
    quem tem continua tendo, e ninguém passa a ter.

    O GET leva ao painel, onde a escolha mora — é onde o `next` do login
    aterrissa quando a sessão expira no meio do toque.
    """

    def get(self, request, *args, **kwargs):
        return redirect("workouts:routine")

    def post(self, request, *args, **kwargs):
        pedido = request.POST.get("duracao_treino", "")
        visiveis = {f.value: f for f in DuracaoTreino.escolhas_visiveis()}
        if pedido not in visiveis:
            messages.error(request, "Escolha uma das três durações.")
            return redirect("workouts:routine")
        faixa = visiveis[pedido]
        teto = TETO_POR_DURACAO[faixa]

        perfil = Profile.objects.filter(user=request.user).first()
        if perfil is None:
            return redirect("workouts:routine")
        if perfil.duracao_treino == faixa:
            messages.info(request, "Sua ficha já é montada para até %d minutos." % teto)
            return redirect("workouts:routine")

        # `update_fields` restrito, como em `TrainingForm.save`: esta ação não
        # é dona do resto do Profile.
        perfil.duracao_treino = faixa
        perfil.save(update_fields=["duracao_treino", "updated_at"])
        request.user.training_days.update(duration_min=MINUTOS_POR_DURACAO[faixa])

        plano = services.get_active_routine(request.user)
        if plano is not None and plano.is_customized:
            messages.info(
                request,
                "Duração gravada: até %d minutos. Você ajustou a ficha à mão, "
                "então ela não é remontada — a duração vale na próxima remontagem." % teto,
            )
            return redirect("workouts:routine")
        if plano is not None and services.treino_em_andamento(request.user):
            messages.info(
                request,
                "Duração gravada: até %d minutos. Há série registrada hoje, "
                "então a ficha muda amanhã." % teto,
            )
            return redirect("workouts:routine")
        _, mudou = services.sync_active_routine(request.user)
        if mudou:
            messages.success(request, "Ficha remontada para até %d minutos por sessão." % teto)
        else:
            messages.info(request, "Duração gravada: até %d minutos." % teto)
        return redirect("workouts:routine")


class DispensarAvisoView(OnboardingRequiredMixin, View):
    """"Agora não": o aviso some deste plano, em todo aparelho. O GET volta
    à Home, pela mesma razão de `RegenerarTreinoView`."""

    def get(self, request, *args, **kwargs):
        return redirect("plans:today")

    def post(self, request, *args, **kwargs):
        plan = services.get_active_routine(request.user)
        if plan is not None:
            plan.aviso_dispensado_em = timezone.now()
            plan.save(update_fields=["aviso_dispensado_em"])
        return redirect("plans:today")


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
        # `no-store` PELO MESMO MOTIVO da exportação de dados.
        #
        # Este arquivo carrega o treino do dia, e o clique num link é
        # `mode: "navigate"` — o service worker o trata pela estratégia de
        # navegação, e `podeGuardar` só recusa quem manda `no-store`. Sem este
        # cabeçalho o TCX entrava em `CACHE_PAGINAS` como se fosse uma tela.
        resposta["Cache-Control"] = "no-store"
        return resposta


class ExercicioView(OnboardingRequiredMixin, TemplateView):
    """A leitura de UM exercício: como é o movimento, e onde ele cai na semana.

    A quarta tela da área de Treino, e ela responde uma pergunta só — "como é
    este movimento?" —, em QUALQUER dia. Existe porque fora da sessão de hoje
    não havia caminho nenhum até a demonstração: a linha da ficha de outro dia
    era um `<div>` inerte e `?exercicio=` fora do dia dá 404. A decisão de
    10/09/2026 fechou o REGISTRO fora do dia e levou junto o VER, sem que
    isso tivesse sido decidido (pesquisa de 13/09/2026).

    VER NÃO É EXECUTAR: esta view não grava nada, e o template não tem
    formulário nem cronômetro — a régua é a mesma da ficha. O exercício é
    buscado pelo PLANO ATIVO da própria pessoa (IDOR fechado como
    `FichaDaSessaoView`), e não "de hoje": senão reproduz o defeito.
    """

    template_name = "workouts/exercicio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        plano = services.get_active_routine(user)
        if plano is None:
            raise Http404("sem ficha")
        # O exercício da ficha — ou o SUBSTITUTO que a pessoa pôs no lugar de
        # um deles ("outras formas"): a linha da ficha aponta para ele.
        exercicio = get_object_or_404(
            Exercise.objects.filter(
                Q(sessions__session__plan=plano)
                | Q(trocas_como_substituto__user=user, trocas_como_substituto__original__sessions__session__plan=plano),
                is_active=True,
            ).distinct(),
            pk=kwargs["exercise_id"],
        )
        # As ocorrências na semana, com a letra que a ficha mostra (A1/A2) —
        # a semana de HOJE pela posição no ciclo, na ordem dos dias.
        # `exercises` sem `__exercise`: a leitura só precisa dos ids das
        # linhas; `aplicar_trocas` busca o exercício só das linhas trocadas.
        linhas = list(plano.sessions.prefetch_related("exercises"))
        services.aplicar_trocas(user, linhas)
        sessoes = sorted(
            services.sessoes_da_semana(plano, timezone.localdate(), linhas),
            key=lambda s: s.weekday,
        )
        nomear_ocorrencias(sessoes)
        itens = []
        for sessao in sessoes:
            for item in sessao.exercises.all():
                if item.exercise_id == exercicio.pk and not any(
                    i.session is sessao for i in itens
                ):
                    # Uma linha por sessão: o exercício pode estar nas duas
                    # opções da letra, e "Segunda (A), Segunda (A)" é ruído.
                    item.session = sessao
                    itens.append(item)
        hoje = timezone.localdate().weekday()
        # "Fazer este exercício" só existe se ele está na OPÇÃO do dia — a
        # execução só abre a opção escolhida (ou a recomendada), e um link
        # para a outra opção daria 404.
        item_de_hoje = None
        sessao_de_hoje = next((s for s in sessoes if s.weekday == hoje), None)
        if sessao_de_hoje is not None:
            opcao = services.opcao_do_dia(user, sessao_de_hoje, timezone.localdate(), sessoes)
            item_de_hoje = next(
                (i for i in sessao_de_hoje.da_opcao(opcao) if i.exercise_id == exercicio.pk), None
            )
            if item_de_hoje is not None:
                item_de_hoje.session = sessao_de_hoje
        if item_de_hoje is not None:
            # Só a contagem de hoje deste exercício — UMA consulta — para o
            # botão dizer "Fazer agora" ou "Continuar de onde parou".
            item_de_hoje.feitas = ExerciseLog.objects.filter(
                user=user, exercise=exercicio, date=timezone.localdate()
            ).count()
        historico = services.historico_do_exercicio(user, exercicio)
        # "OUTRAS FORMAS": as alternativas do mesmo padrão no equipamento da
        # pessoa, fora do que já está nas sessões em que ele cai; e, se este
        # exercício está no lugar de outro, o original com o histórico dele.
        original = next((i.original for i in itens if getattr(i, "original", None) is not None), None)
        # Fora do que já está na MESMA LISTA (sessão + opção): duplicata só é
        # problema dentro do mesmo treino; a outra opção é outro dia. É a
        # mesma régua de `contar_outras_formas` na ficha — a linha anuncia
        # "outras formas" e a leitura lista as mesmas (achado do QA de 17/09).
        listas = {
            (i.session_id, i.opcao)
            for sessao in sessoes for i in sessao.exercises.all() if i.exercise_id == exercicio.pk
        }
        na_sessao = {
            i.exercise_id
            for sessao in sessoes for i in sessao.exercises.all() if (i.session_id, i.opcao) in listas
        }
        context.update({
            "nav": "workout",
            "exercicio": exercicio,
            "historico": historico,
            "original": original,
            "historico_do_original": services.historico_do_exercicio(user, original) if original is not None else [],
            # O perfil do `dispatch` poupa a consulta do perfil.
            "alternativas": services.alternativas_de(
                user, exercicio, na_sessao, permitidos=doutrina.equipamentos_de(self.perfil_do_dispatch.equipamento),
            ),
            # O `original` do formulário: quem já está no lugar de outro
            # troca DE NOVO a partir do original (estado absoluto).
            "original_da_troca": original if original is not None else exercicio,
            "volta_query": self._volta_query(),
            # `historico` vem do mais RECENTE ao mais antigo (é assim que a
            # lista "Como fui" quer ler); a curva precisa do sentido contrário
            # — `reversed()`, não uma segunda consulta. Exercício sem carga não
            # tem o que desenhar.
            "curva_carga": (
                _curva.curva([s["carga"] for s in reversed(historico)])
                if not exercicio.sem_carga else None
            ),
            "prescricao": itens[0],
            "dias": [
                "%s (%s)" % (i.session.weekday_display, i.session.rotulo)
                for i in itens
            ],
            "item_de_hoje": item_de_hoje,
            "volta": self._de_onde_veio(exercicio, itens),
        })
        return context

    #: De onde a pessoa pode ter vindo. LISTA FECHADA, como `?exercicio=`.
    ORIGENS = ("ficha", "agora", "painel")

    def _volta_query(self) -> str:
        """`?de=...&sessao=...` para o formulário de troca devolver a pessoa
        à MESMA leitura com a mesma volta — só valores que `_de_onde_veio`
        já aceitou; nada é montado a partir do pedido cru."""
        de = self.request.GET.get("de")
        if de not in self.ORIGENS:
            return ""
        partes = ["de=%s" % de]
        sessao = self.request.GET.get("sessao")
        if de == "ficha" and sessao and sessao.isdigit():
            partes.append("sessao=%s" % sessao)
        return "?" + "&".join(partes)

    def _de_onde_veio(self, exercicio, itens):
        """A volta certa: para a ficha de onde veio, para a execução, ou o painel.

        Quem abria a leitura a partir da ficha A1 lia "← Treino" e voltava
        ao painel — dois toques para estar de novo onde estava (UX NOVO-03).
        `?de=` diz a origem em lista fechada; valor desconhecido é 404, e o
        `href` nunca é montado a partir do pedido: é `reverse()` da tela
        nomeada. `sessao=` acompanha `ficha` e tem de ser uma sessão em que
        o exercício está — senão, 404 —, porque o mesmo exercício pode
        aparecer em A1 e A2 e a volta é para a ficha CERTA.
        """
        pedidos = self.request.GET.getlist("de")
        if not pedidos:
            return {"href": reverse("workouts:routine"), "rotulo": "← Treino"}
        if len(pedidos) > 1 or pedidos[0] not in self.ORIGENS:
            raise Http404("origem ilegível")
        origem = pedidos[0]
        if origem == "painel":
            return {"href": reverse("workouts:routine"), "rotulo": "← Treino"}
        if origem == "agora":
            return {
                "href": "%s?exercicio=%d" % (reverse("workouts:now"), exercicio.pk),
                "rotulo": "← Execução",
            }
        sessoes = {i.session.pk: i.session for i in itens}
        bruto = self.request.GET.get("sessao")
        if bruto is None:
            sessao = itens[0].session
        else:
            try:
                sessao = sessoes[int(bruto)]
            except (TypeError, ValueError, KeyError):
                raise Http404("sessão não tem este exercício")
        return {
            "href": reverse("workouts:ficha", args=[sessao.pk]),
            "rotulo": "← Ficha %s" % sessao.rotulo,
        }


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
        # A EXECUÇÃO NASCE EM FERRO SEMPRE (DESIGN.md, "Dois regimes"): a
        # classe é escrita pelo servidor — nunca por `:has()` nem por JS — e
        # liga o regime escuro por cima da preferência clara do aparelho.
        # Luz baixa de academia: é a decisão de produto da direção CORTE, e
        # até 16/09/2026 estava escrita no contrato sem nenhuma view a
        # cumprir (só a vitrine escrevia a classe).
        context["body_class"] = "modo-foco"

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
        # QUAL EXERCÍCIO — a ficha manda, e a execução obedece.
        #
        # `?exercicio=` é o que liga a ficha a esta tela: a pessoa vê a lista
        # inteira, escolhe, e cai aqui com aquele movimento em foco. Sem o
        # parâmetro vale a escolha automática de sempre — o primeiro pendente —,
        # que é o caminho de quem chega por "Continuar de onde parou".
        #
        # PARÂMETRO PRESENTE E INVÁLIDO É 404, e nunca "abre outro". Três
        # formas de inválido caem aqui, e as três pelo mesmo motivo — o pedido
        # nomeia algo que não existe para esta pessoa hoje:
        #
        #   - REPETIDO (`?exercicio=1&exercicio=2`): `get()` devolveria o
        #     último em silêncio, e o pedido é ambíguo, não claro;
        #   - MALFORMADO (`?exercicio=abc`, vazio, negativo);
        #   - INEXISTENTE, de outra sessão ou de outra conta — este último é o
        #     mesmo fechamento de IDOR que `FichaDaSessaoView` faz, e vem de
        #     graça: `estado_do_treino` só enxerga a sessão de hoje do próprio
        #     usuário.
        #
        # 404 e não redirecionamento silencioso porque é o padrão do projeto
        # para "não é seu ou não existe", e porque um link velho que continua
        # abrindo ALGUMA tela nunca é consertado. A página de erro não tem
        # iframe, não grava série e não move progresso.
        escolhido = None
        pedidos = self.request.GET.getlist("exercicio")
        if pedidos:
            if len(pedidos) > 1:
                raise Http404("exercício pedido mais de uma vez")
            try:
                escolhido = int(pedidos[0])
            except (TypeError, ValueError):
                raise Http404("exercício ilegível")
            if escolhido <= 0:
                raise Http404("exercício inválido")
        try:
            context["estado"] = services.estado_do_treino(
                user, escolhido=escolhido
            )
        except services.ExercicioForaDaSessao:
            raise Http404("exercício não é do treino de hoje")
        estado = context["estado"]
        # `?extra=1` reabre o formulário num exercício já concluído — a série
        # a mais, que `append_set` sempre aceitou (até 20). LISTA FECHADA,
        # como `?exercicio=`: valor desconhecido é 404, e não "ignora e abre
        # a tela normal" — link quebrado que funciona nunca é consertado.
        extras = self.request.GET.getlist("extra")
        if extras and extras != ["1"]:
            raise Http404("pedido de série extra ilegível")
        context["extra"] = bool(extras)
        # UM IDENTIFICADOR POR RENDERIZAÇÃO, e dois porque são dois
        # formulários — registrar e desfazer não podem compartilhar identidade,
        # senão desfazer logo depois de gravar seria recusado como repetição do
        # próprio registro.
        #
        # É isto que protege o toque duplo e o botão voltar agora que a série
        # não vem mais numerada do HTML: reenviar a MESMA página repete o mesmo
        # `op_id`, e a segunda escrita é recusada. Offline vale o contrário, e
        # `fila.js` troca este valor por um novo a cada toque — lá a identidade
        # é do toque, porque a página não recarrega entre eles.
        context["op_registro"] = uuid.uuid4().hex
        context["op_desfazer"] = uuid.uuid4().hex
        context["dia_da_sessao"] = timezone.localdate()
        # TELA CRÍTICA: aqui não entra convite de instalação. A execução do
        # treino é uma tela de uma coisa só — a pessoa está de pé, entre uma
        # série e outra —, e um cartão fixo cobrindo o rodapé atrapalha a
        # tarefa. Ver `data-sem-convite` no `base.html`.
        context["sem_convite"] = True
        return context


class ConcluirSerieView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Grava UMA série do modo treino, ou desfaz a última.

    O NÚMERO DA SÉRIE É DO SERVIDOR, decidido na hora de aplicar. O formulário
    não manda contador nenhum — e essa é a diferença que devolveu esta rota à
    fila offline.

    A versão anterior mandava `set_number` escrito no HTML. Online aquilo estava
    certo: o número nascia milissegundos antes. Offline, não: a página não
    recarrega entre um toque e outro, então três séries seguidas sem rede
    enfileiravam TRÊS pedidos com o MESMO número, e as três gravariam a mesma
    linha. A pessoa terminaria o treino com uma série de três que fez.

    O que substitui o contador é o `op_id`:

    - **online** ele vem do HTML, um por renderização. Toque duplo, botão
      voltar e reenvio do formulário repetem o mesmo identificador e a segunda
      escrita é recusada — a mesma proteção que o `update_or_create` dava;
    - **offline** `fila.js` o SUBSTITUI por um novo a cada captura, porque ali
      a identidade é do TOQUE e não da página. Sem isso, os três toques
      voltariam a colapsar num só.
    """

    #: A serie e concluida DENTRO do modo treino, com a pessoa de pe entre
    #: uma serie e outra. Mandar para o dia de hoje a tiraria do treino.
    tela_da_acao = "workouts:now"

    def post(self, request, *args, **kwargs):
        # O id é convertido ANTES de ir ao banco: `pk=""` e `pk="abc"` levantam
        # ValueError dentro do ORM, e ValueError numa view é 500. Formulário
        # corrompido merece 404, não página de erro.
        try:
            exercise_id = int(request.POST.get("exercise_id") or "")
        except (TypeError, ValueError):
            raise Http404("exercício inválido")
        exercise = get_object_or_404(Exercise, pk=exercise_id, is_active=True)

        op_id = (request.POST.get("op_id") or "").strip()[:64]
        dia = self._dia_do_toque(request)

        if request.POST.get("acao") == "desfazer":
            numero, aplicou = services.remove_last_set(
                request.user, exercise, op_id=op_id, day=dia
            )
            # A tela diz QUAL série de QUAL exercício saiu (UX TR-03): o
            # desfazer segue a última série anotada, que pode ser de outro
            # exercício, e "desfiz" sem sujeito era adivinhação.
            if aplicou and numero:
                messages.info(
                    request, "Série %d de %s desfeita." % (numero, exercise.name)
                )
            return self._de_volta_ao_foco(request, dia)

        bruto = (request.POST.get("weight_kg") or "").replace(",", ".").strip()
        # Peso do corpo sem carga é 0 — e SÓ peso do corpo: num supino, campo
        # esquecido continua sendo erro, senão gravaria 0 kg em silêncio.
        if not bruto and exercise.sem_carga:
            bruto = "0"
        try:
            peso = Decimal(bruto)
        except (InvalidOperation, TypeError):
            messages.error(request, "Carga inválida — use números, como 42,5.")
            return self._de_volta_ao_foco(request, dia)
        if peso < 0 or peso > 999:
            messages.error(request, "Carga fora do que uma barra aguenta.")
            return self._de_volta_ao_foco(request, dia)

        reps = None
        bruto_reps = (request.POST.get("reps") or "").strip()
        if bruto_reps:
            # RECUSA, e não aparo: `max(1, min(int(x), 100))` gravava 100 para
            # quem digitou 999 e 1 para quem digitou 0 — um número que a
            # pessoa não fez (UX TR-08). O teto continua o mesmo; o que
            # muda é que fora dele nada é gravado, e a tela diz por quê —
            # o mesmo PRG da carga inválida, logo acima. Reps em branco
            # continua aceito: quem anota só a carga não é barrado.
            try:
                reps = int(bruto_reps)
            except (TypeError, ValueError):
                reps = None
            if reps is None or not 1 <= reps <= 100:
                messages.error(request, "Repetições fora de 1 a 100 — a série não foi gravada.")
                return self._de_volta_ao_foco(request, dia)

        try:
            log, criada = services.append_set(
                request.user, exercise, peso, reps=reps, op_id=op_id, day=dia
            )
        except ValueError:
            # Vinte séries no mesmo exercício num dia. Não é treino, é dedo
            # preso no botão ou fila reproduzindo algo corrompido — e recusar
            # em silêncio deixaria a pessoa tocando sem entender.
            messages.error(request, "Limite de séries deste exercício hoje.")
        else:
            self._garantir_escolha(request, dia)
            # As conquistas rodam AQUI, na escrita — é o que a doutrina de
            # `achievements.services` promete e o que esta rota não fazia:
            # só `RecordLoadView`, a rota do cartão que saiu da tela em
            # 10/09/2026, chamava `avaliar`. Como a chave do recorde é
            # `exercício:data`, o recorde de hoje só nascia se a pessoa
            # abrisse /conquistas/ no mesmo dia. Com o DIA DO TOQUE, e não
            # `localdate()`: a fila pode drenar amanhã, e a conquista é de
            # quando a série aconteceu. Só no ramo que gravou — desfazer não
            # cria conquista.
            #
            # E só na PRIMEIRA SÉRIE DO DIA ou QUANDO HÁ RECORDE: o catálogo
            # inteiro custa 43 consultas (medido), e a fila reenvia séries em
            # rajada. A primeira série é o momento em que um dia de treino
            # passa a existir — `dias_treinados`, a ofensiva, a semana
            # completa e os treinos-N mudam AÍ, e só aí —; até 16/09/2026 só
            # o recorde avaliava, e "Primeiro treino" nunca nascia na hora,
            # porque estreia não é recorde (avaliação B5). Reenvio da fila
            # (`criada=False`) não é dia novo. Uma consulta decide cada um.
            primeira_do_dia = criada and not (
                ExerciseLog.objects.filter(user=request.user, date=dia)
                .exclude(pk=log.pk)
                .exists()
            )
            if primeira_do_dia or services.supera_recorde(
                request.user, exercise, peso, reps=reps, dia=dia
            ):
                novas = conquistas.avaliar(request.user, hoje=dia)
                conquistas.anunciar(request, novas)
            # Fechou a última série: a tela seguinte já é outro exercício, e
            # sem esta frase a pessoa não sabia que o anterior tinha fechado
            # (UX TR-02). Só no fechamento — uma frase por série seria ruído.
            fechadas, prescritas = services.series_de_hoje(
                request.user, exercise, dia=dia
            )
            if prescritas and fechadas == prescritas:
                messages.success(
                    request,
                    "%s concluído · %d/%d." % (exercise.name, fechadas, prescritas),
                )
            # A mesma contagem responde "ainda tem série pendente?" para o
            # redirect — sem repetir as três consultas de `serie_pendente`.
            # O orçamento do POST é medido (`test_recorde_na_hora`).
            return self._de_volta_ao_foco(
                request, dia, pendente=(exercise.pk, bool(prescritas) and fechadas < prescritas)
            )
        # DEPOIS da escrita: a contagem de séries pendentes já inclui esta,
        # e é isso que faz fechar a última devolver sem parâmetro.
        return self._de_volta_ao_foco(request, dia)

    def _garantir_escolha(self, request, dia) -> None:
        """A primeira série do dia grava qual opção está sendo feita.

        O formulário da execução traz `sessao`, `opcao` e `versao` (escritos
        pelo servidor); item antigo da fila offline não traz, e aí a escolha
        cai na opção 1 da sessão do dia. Idempotente: uma escolha por dia.
        """
        if services.escolha_do_dia(request.user, dia) is not None:
            return
        try:
            sessao_id = int(request.POST.get("sessao") or "")
        except (TypeError, ValueError):
            sessao_id = None
        sessao = None
        if sessao_id:
            sessao = TrainingSession.objects.filter(
                pk=sessao_id, plan__user=request.user, plan__is_active=True
            ).prefetch_related("exercises").first()
        if sessao is None:
            sessao = services.sessao_do_dia(services.get_active_routine(request.user), dia)
        if sessao is None:
            return
        try:
            opcao = int(request.POST.get("opcao") or "1")
        except ValueError:
            opcao = 1
        services.registrar_escolha(
            request.user, sessao, opcao, versao=request.POST.get("versao") or "completo", dia=dia
        )

    def _de_volta_ao_foco(self, request, dia, pendente=None):
        """Para o exercício EM FOCO, enquanto ele tiver série pendente.

        `pendente` é `(exercise_id, bool)` quando quem chama JÁ contou as
        séries daquele exercício — evita repetir as consultas de
        `serie_pendente` no caminho que grava.

        `estado_do_treino` documenta que a pessoa escolhe por onde começar, e
        esta view descartava a escolha: os três ramos voltavam para
        `workouts:now` sem parâmetro, e a tela reabria o primeiro pendente —
        quem começou pelo décimo exercício era levado ao primeiro a cada
        série. O foco viaja no campo `exercicio` (e não em `exercise_id`, que
        no desfazer é o exercício que RECEBEU a última série, não o que está
        na tela). O campo vai no corpo como qualquer outro, então a fila
        offline o reenvia sem mudança de contrato.

        Ausente, ilegível ou de um exercício sem série pendente hoje, o
        parâmetro fica de fora e a tela escolhe sozinha — nunca 404: a série
        já foi gravada, e item antigo da fila não tem o campo.

        Chamada DEPOIS da escrita: a contagem de pendentes já inclui a série
        de agora, e é por isso que fechar a última devolve sem parâmetro.
        """
        bruto = (request.POST.get("exercicio") or "").strip()
        try:
            foco = int(bruto)
        except (TypeError, ValueError):
            return redirect("workouts:now")
        if foco <= 0:
            return redirect("workouts:now")
        if pendente is not None and pendente[0] == foco:
            tem_pendente = pendente[1]
        else:
            tem_pendente = services.serie_pendente(request.user, foco, dia=dia)
        if not tem_pendente:
            return redirect("workouts:now")
        # `#registro` (U7, 16/09/2026): a página seguinte abre com o BLOCO DE
        # REGISTRO em foco — `tabindex="-1"` no alvo faz o navegador pousar o
        # foco nele —, e não no topo: a cada série a pessoa descia de novo
        # até a carga, e o teclado/leitor de tela recomeçava da marca.
        # `scroll-margin-top` no bloco deixa "Série N de M" e o descanso
        # visíveis acima. Só na MESMA página: exercício novo abre pelo nome.
        return redirect("%s?exercicio=%d#registro" % (reverse("workouts:now"), foco))

    #: Quantos dias para trás um evento da fila ainda pode escrever.
    #:
    #: Sete porque a fila drena na primeira abertura com rede, e uma semana sem
    #: abrir o app com sinal é o limite do plausível. Mais que isso não é
    #: "sincronizou tarde": é corpo antigo em aparelho esquecido, e escrever um
    #: treino de mês passado seria pior que descartar a data.
    JANELA_DE_ATRASO = 7

    def _dia_do_toque(self, request):
        """O dia em que a pessoa TOCOU, e não o dia em que a fila drenou.

        Sem isto, quem fecha a última série às 23h50 e só recupera sinal ao sair
        da academia vê o treino inteiro cair no dia seguinte: some do dia certo,
        aparece como sessão fantasma no outro, e a ofensiva conta os dois
        errados. A tela escreve a data no formulário, e ela viaja no corpo
        enfileirado como qualquer outro campo.

        O que o servidor NÃO faz é confiar cegamente: data ilegível, futura ou
        mais velha que a janela cai em hoje. Futura é o caso que importa —
        relógio de celular adiantado escreveria num dia que ainda não existe, e
        aquele registro ficaria invisível para toda tela que pergunta "e hoje?".
        """
        hoje = timezone.localdate()
        bruto = (request.POST.get("dia") or "").strip()
        if not bruto:
            return hoje
        try:
            dia = datetime.strptime(bruto, "%Y-%m-%d").date()
        except ValueError:
            return hoje
        if dia > hoje or (hoje - dia).days > self.JANELA_DE_ATRASO:
            return hoje
        return dia
