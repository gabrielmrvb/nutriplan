"""A aba de treino: a rotina da semana, a ficha de cada dia e a carga."""
import uuid
import copy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial

from django.contrib import messages
from django.db.models import Count, Exists, Max, OuterRef
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View

from accounts.models import (
    MINUTOS_POR_DURACAO,
    TETO_POR_DURACAO,
    DuracaoTreino,
    Musculacao,
    Weekday,
)
from accounts.views import OnboardingRequiredMixin
from achievements import services as conquistas

from . import curva as _curva
from . import doutrina, health_export, services, telas
from analytics import servidor as analytics
from .models import (
    EscolhaDeTreino,
    ExerciseLog,
    EventoDeProduto,
    VersaoDoTreino,
    Exercise,
    MuscleGroup,
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
            # cadastrar — não um erro. E quem DISSE que não faz musculação
            # (22/09/2026) não é convidado a cadastrar dias: a tela repete a
            # resposta e aponta a corrida e o Perfil. O perfil vem do
            # `dispatch`, sem consulta a mais.
            perfil = self.perfil_do_dispatch or getattr(user, "profile", None)
            context.update({
                "nav": "workout",
                "plan": None,
                "nao_faz_musculacao": bool(perfil) and perfil.musculacao == Musculacao.NAO,
            })
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
        # SEQUÊNCIA POR PRESENÇA (24/09/2026), lida UMA vez: dela saem a letra
        # recomendada de hoje, a projeção da semana (a tira) e o próximo treino.
        seq = services.sequencia_do_treino(user, plan, ate=hoje_data, sessoes=linhas)
        # A escolha do dia, lida UMA vez e passada adiante — sem ela cada uma
        # de `letra_do_dia`, `sessao_do_dia` e `sessoes_da_semana` a consultaria.
        escolha_hoje = services.escolha_do_dia(user, hoje_data)
        letras_ciclo = services.letras_do_ciclo(linhas)
        letra_escolhida = (
            escolha_hoje.session.label
            if escolha_hoje is not None
            and escolha_hoje.session.plan_id == plan.pk
            and escolha_hoje.session.label in letras_ciclo
            else None
        )

        # O PROGRAMA e o VOLUME saem da ESTRUTURA (as linhas, o retrato dos
        # dias), NÃO da projeção: a projeção reordena as letras por presença e
        # contaria a letra de hoje duas vezes e omitiria a que ainda não caiu —
        # "séries por semana" e o volume têm de ser da semana inteira.
        sessions = sorted(linhas, key=lambda s: s.order)
        nomear_ocorrencias(sessions)
        # O treino de HOJE é a letra RECOMENDADA (ou a escolhida) vestida em
        # hoje. `anexar_historico` decide o balde "hoje" pelo weekday, e é por
        # isso que ele recebe a sessão JÁ vestida no dia — o histórico de hoje
        # cai na letra certa (o mesmo cuidado da ficha). A letra de hoje sai
        # DELA, e não de `letra_do_dia`: é a mesma resposta, e no descanso com
        # "treinar mesmo assim" (R4, 28/09/2026) só ela sabe da escolha.
        hoje = services.sessao_do_dia(
            plan, hoje_data, linhas, user=user, seq=seq, escolha=escolha_hoje
        )
        recomendada = hoje.label if hoje is not None else None
        # eh_hoje é por LETRA na presença (o cartão da letra recomendada, caia
        # ela em quantos dias for), mas por DIA no plano customizado à mão —
        # onde a mesma letra pode cair em dois dias com conteúdos diferentes.
        presenca = services.usa_presenca(plan)
        for s in sessions:
            s.eh_hoje = (
                recomendada is not None
                and s.label == recomendada
                and (presenca or s.weekday == hoje_data.weekday())
            )
        letras_cartoes = agrupar_por_letra(sessions)

        if hoje is not None:
            anexar_historico(user, [hoje])
            preparar_dia(user, hoje, linhas, seq=seq, escolha=escolha_hoje)
            progresso_do_dia(hoje)
            # "recomendado" (sem escolha) ou a escolha da pessoa — muda o selo.
            hoje.recomendado = letra_escolhida is None
            # "Fazer outro treino": as OUTRAS letras do programa.
            hoje.outras_letras = [
                {"letra": c["label"], "nome": c["name"]}
                for c in letras_cartoes if c["label"] != hoje.label
            ]
            # Aviso, nunca bloqueio: escolheu uma letra cujo grupo caiu <48h.
            aviso_treino = services.aviso_de_treino_repetido(
                user, plan, hoje.label, hoje_data, seq=seq, sessoes=linhas
            )
        else:
            aviso_treino = None

        # A TIRA é a PROJEÇÃO da semana (feito/pulado/hoje/futuro).
        tira = services.sessoes_da_semana(
            plan, hoje_data, linhas, user=user, seq=seq, escolha_hoje=letra_escolhida
        )
        # Os dias do cartão da letra saem DAQUI, depois dos cartões: a tira
        # veste as linhas (`pulado` é a própria linha, com `eh_hoje=False`), e
        # montá-los depois dela apagaria o "hoje" do cartão.
        dias_da_tira(letras_cartoes, tira)

        context.update(
            {
                "nav": "workout",
                "plan": plan,
                "sessions": sessions,
                "letras": letras_cartoes,
                "hoje": hoje,
                # A letra a confirmar quando a troca depois de treinar precisa
                # de confirmação (`EscolherLetraView` redireciona com `?trocar=`).
                "trocar_pendente": self.request.GET.get("trocar", ""),
                "aviso_treino": aviso_treino,
                # Só faz sentido perguntar "e quando é o próximo?" no dia em
                # que não há treino. Com treino hoje, o próximo é ruído.
                "proximo": proximo_treino(tira, plan, hoje_data, linhas, user=user, seq=seq) if hoje is None else None,
                "week": week_overview(tira),
                # A tira é a PROJEÇÃO por presença (feito/pulado/hoje/futuro), e
                # a legenda que a explica segue a MESMA régua da projeção:
                # `presenca` (`usa_presenca`), não `ciclo_roda`. As duas divergem
                # no plano de antes da rotação (`inicio_do_ciclo` em branco, não
                # customizado): ele projeta por presença mas não "gira" no sentido
                # antigo — e sem a legenda o painel marcava feito/pulado sem dizer
                # por quê (visto em produção, d965c07, no demo antigo). Só o plano
                # CUSTOMIZADO fica preso ao dia da semana, e aí a legenda some,
                # porque "continua de onde você parou" seria mentira.
                "ciclo_continuo": presenca,
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
                    # O teto que MONTOU a ficha: o corpo inteiro de uma vez
                    # por semana nasce com pelo menos 75 (27/09/2026, dono).
                    "teto": services.teto_da_ficha(user, plan),
                    # Corpo inteiro de uma vez por semana: nenhuma faixa
                    # abaixo de 75 é oferecida, e a regra se lê aqui
                    # (28/09/2026, decisão do dono).
                    "opcoes": opcoes_de_duracao(services.minimo_da_ficha(plan)),
                    "regra": services.REGRA_DO_CORPO_INTEIRO if services.minimo_da_ficha(plan) else "",
                },
            }
        )
        return context


def opcoes_de_duracao(minimo=0) -> list:
    """As faixas que a área de Treino oferece: valor, nome curto e teto.

    Lê `DuracaoTreino.escolhas_visiveis` — sem "Sem limite", que continua no
    banco para quem já tem e não é oferecido em formulário nenhum — e o teto
    de `TETO_POR_DURACAO`, o mesmo que o motor obedece. O nome curto é a
    parte do rótulo antes do travessão: "Rápido", "Padrão", "Completo".

    `minimo` tira as faixas de teto menor (28/09/2026, decisão do dono): o
    corpo inteiro de uma vez por semana não recebe oferta abaixo de 75
    (`services.minimo_da_ficha`), porque os dez grupos não cabem nela. É a
    mesma lista que o envio aceita (`DuracaoDoTreinoView`).
    """
    return [
        {
            "valor": faixa.value,
            "nome": faixa.label.split(" — ")[0],
            "teto": TETO_POR_DURACAO[faixa],
        }
        for faixa in DuracaoTreino.escolhas_visiveis()
        if TETO_POR_DURACAO[faixa] >= minimo
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
    # A PORCENTAGEM É EM SÉRIES, pela função da execução (28/09/2026, M3): o
    # anel dizia "14 %" (1 de 7 exercícios) ao lado de uma execução em "2/25
    # séries". Na versão rápida a base é a dose cortada — a mesma de lá.
    session.series_feitas, session.series_previstas, session.pct_hoje = services.progresso_em_series(
        getattr(session, "pares_do_dia", None) or [(item, item.sets) for item in itens]
    )

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


def preparar_dia(user, sessao, linhas=None, seq=None, escolha=services._NAO_INFORMADO) -> None:
    """A sessão de hoje ganha a opção do dia — a pinada pela primeira série,
    senão a variação por presença — e a conta da versão rápida para o painel
    oferecer "Menos tempo hoje?". `seq`/`escolha` já carregados evitam
    reconsultar a sequência e a escolha do dia."""
    from . import opcoes as motor_de_opcoes

    if escolha is services._NAO_INFORMADO:
        escolha = services.escolha_do_dia(user)
    if escolha is not None and escolha.session_id != sessao.pk:
        escolha = None
    sessao.escolha = escolha
    # "Encerrar treino" hoje (BA22): o botão deixa de dizer "Continuar".
    sessao.encerrado = escolha is not None and escolha.encerrado_em is not None
    dia = getattr(sessao, "data", None) or timezone.localdate()
    sessao.opcao_do_dia = services.opcao_do_dia(user, sessao, dia, linhas, escolha=escolha, seq=seq)
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
    # Os números do cartão de HOJE são os da opção do dia, não os da
    # referência da semana (`total_sets`/`estimated_minutes`, a opção 1). Eles
    # discordavam por construção num dia de variação 2: medido no `abc2` do
    # intermediário de cinco dias, a letra B fecha em 57 min na opção 1 e 60
    # na 2 — o painel prometia 57 e a ficha do mesmo dia dizia 60
    # (`workouts/test_minutos_do_dia.py`).
    sessao.minutos = sessao.minutos_da_opcao(sessao.opcao_do_dia)
    sessao.series_do_dia = sessao.series_da_opcao(sessao.opcao_do_dia)
    sessao.rapida_muda = bool(removidos) or sum(s for _, s in ficam) != sum(i.sets for i in itens)
    # A base do progresso na rápida é a dose cortada, como na execução.
    sessao.pares_do_dia = ficam if sessao.versao_do_dia == "rapido" else None
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


def dias_da_tira(cartoes, tira) -> None:
    """Os dias do cartão da LETRA são os da TIRA — feito, hoje e futuro —, e
    não os das linhas (BA4, caça-bugs de 27/09; 28/09/2026). Com a sequência
    por presença a letra muda de dia de semana para semana, e o cartão dizia
    "A · Segunda · Quinta" ao lado de uma tira com A na segunda e na sexta. O
    dia `pulado` não entra: ninguém treinou nada nele. Plano ajustado à mão
    tem a tira igual às linhas, então nada muda ali; e o cartão numerado
    (A1 ≠ A2, uma sessão cada) continua com o dia da própria sessão."""
    dias = {}
    for sessao in tira:
        if sessao.projecao != "pulado":
            dias.setdefault(sessao.label, []).append(sessao.weekday_display)
    for cartao in cartoes:
        if cartao["rotulo"] == cartao["label"]:
            cartao["dias"] = dias.get(cartao["label"], [])


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
            # A ÚLTIMA VEZ, PARA A FICHA DECIDIR A ANILHA (22/09/2026). Era
            # informação só da execução — "peso da última vez é de quem está
            # escolhendo a anilha, não de quem lê o treino" —, e a auditoria
            # do dono mostrou o custo dessa separação: para saber com quanto
            # começar, a pessoa abria os nove exercícios um a um. Sai do
            # balde "anterior" que `load_history` já trouxe: ZERO consulta a
            # mais. A série é a mais PESADA daquele dia, que é a que se
            # procura (a ordem de anotar varia).
            item.ultima_vez = services.ultima_serie_anterior(item.load)


#: `proximo_treino` mora em `workouts/services.py` desde 22/09/2026: o cartão
#: de Treino da Home precisa dele para dizer "Descanso · próximo: amanhã, B", e
#: uma view de outro app não importa a view deste. O nome fica aqui como alias
#: para quem já o chamava.
proximo_treino = services.proximo_treino


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

        # Programa anterior abre como HISTÓRICO; id alheio é 404 (`telas`).
        sessao, linhas, historico = telas.ficha_da_pessoa(user, kwargs["sessao_id"])
        hoje_data = timezone.localdate()
        services.aplicar_trocas(user, [sessao, *linhas])
        # SEQUÊNCIA e ESCOLHA do dia, lidas UMA vez e passadas a todas as
        # resoluções de letra/opção desta ficha — sem elas cada chamada de
        # `letra_do_dia`/`sessao_do_dia`/`sessoes_da_semana`/`variacao_do_dia`
        # reconsultaria a sequência (a ficha estourou o teto: 21 > 17).
        seq = services.sequencia_do_treino(user, sessao.plan, ate=hoje_data, sessoes=linhas)
        escolha_hoje = services.escolha_do_dia(user, hoje_data)
        letras_ciclo = services.letras_do_ciclo(linhas)
        letra_escolhida = (
            escolha_hoje.session.label
            if escolha_hoje is not None
            and escolha_hoje.session.plan_id == sessao.plan_id
            and escolha_hoje.session.label in letras_ciclo
            else None
        )
        # A letra de hoje sai da SESSÃO de hoje (a mesma resposta de
        # `letra_do_dia`), porque só ela conhece a escolha feita num dia de
        # descanso — "treinar mesmo assim" (R4, 28/09/2026).
        do_dia = services.sessao_do_dia(
            sessao.plan, hoje_data, linhas, user=user, seq=seq, escolha=escolha_hoje
        )
        letra_hoje = do_dia.label if do_dia is not None else None
        # COM A ROTAÇÃO, A LINHA DA LETRA VESTE O DIA DE HOJE ANTES DO
        # HISTÓRICO (17/09/2026). `anexar_historico` só aplica o balde "hoje"
        # à sessão cujo `weekday` é o de hoje — e a linha da letra guarda o
        # dia da PRIMEIRA semana: numa quinta em que a letra A (linha de
        # segunda) cai de novo, a ficha de hoje abria sem nenhuma série de
        # hoje ("0/4" depois de registrar uma), enquanto a execução, que passa
        # por `sessao_do_dia`, mostrava a série. Passou despercebido porque os
        # testes rodaram em dias em que letra e linha coincidiam. A mesma
        # cópia vestida que a execução usa resolve os dois lados de uma vez.
        if services.usa_presenca(sessao.plan) and do_dia is not None and do_dia.pk == sessao.pk:
            sessao = do_dia
        # A MESMA preparação da tela principal, pela mesma função. Uma segunda
        # cópia divergiria, e a que fica errada é a que ninguém está olhando.
        anexar_historico(user, [sessao])
        # A NOMEAÇÃO PRECISA DA SEMANA INTEIRA: "A1" só existe porque há um A2,
        # e uma sessão sozinha não sabe disso. Buscar as irmãs custa UMA
        # consulta e é o que faz o título da ficha concordar com o cartão que
        # levou até ela.
        irmas = services.sessoes_da_semana(
            sessao.plan, hoje_data, linhas, user=user, seq=seq, escolha_hoje=letra_escolhida
        )
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
        if services.usa_presenca(sessao.plan):
            # Por presença, "é hoje" é a LETRA recomendada (ou escolhida) de
            # hoje — o dia da semana da linha é o da primeira semana —, e o
            # cabeçalho diz em que dias desta semana a letra cai: os da TIRA,
            # sem o `pulado` (BA4, 28/09/2026) — a linha pulada é a da letra na
            # estrutura, e "Quarta · Quinta" ao lado de uma tira com "·" na
            # quarta anunciava um treino que não caiu ali. Letra que não cai
            # nesta semana fica sem dia — o dia da linha seria o mesmo mapa fixo.
            sessao.eh_hoje = letra_hoje == sessao.label
            sessao.aberta = True
            sessao.dias_texto = " · ".join(
                s.weekday_display for s in irmas
                if s.label == sessao.label and s.projecao != "pulado"
            )
        else:
            marcar_ficha_aberta([sessao])
            sessao.dias_texto = sessao.weekday_display
        if historico:
            # Ficha de programa anterior: ela CONTA o que aconteceu, não
            # oferece o que fazer. "Hoje" pertence ao programa vigente.
            sessao.eh_hoje = False
            sessao.aberta = False
        if sessao.eh_hoje:
            preparar_dia(user, sessao, linhas, seq=seq, escolha=escolha_hoje)
            progresso_do_dia(sessao)

        context.update({
            "nav": "workout",
            # DUAS COLUNAS SÓ AQUI (22/09/2026): a classe no <html> é o que
            # permite a ficha ter outra largura no desktop sem `:has()`, que
            # é proibido neste projeto para CSS estrutural (ele derrubou a
            # navegação uma vez). O app continua em uma coluna de 30rem.
            "body_class": "tela-ficha",
            "sessao": sessao,
            "plan": sessao.plan,
            "historico": historico,
            # A ficha antiga diz por que ainda importa — "4 séries registradas
            # hoje" — em vez de ser uma página morta. Só no histórico.
            "series_de_hoje": telas.series_anotadas_hoje(
                user, [i.exercise_id for i in sessao.exercises.all()]
            ) if historico else 0,
        })
        context.update(self.contexto_da_ficha(user, sessao, linhas, irmas, hoje_data, seq=seq, historico=historico))
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

    def contexto_da_ficha(self, user, sessao, linhas, irmas, hoje_data, seq=None, historico=False) -> dict:
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
        elif historico:
            # PROGRAMA ANTERIOR: a opção FEITA — a da última escolha desta
            # sessão com série registrada, a régua de "feito" da sequência por
            # presença —, e não a "próxima vez" de um plano que não terá
            # próxima vez (M19, 28/09/2026). Só a ficha legada tem duas
            # opções, e só ela paga a consulta; nada feito, a primeira.
            feita = (
                EscolhaDeTreino.objects.filter(user=user, session_id=sessao.pk)
                .filter(Exists(ExerciseLog.objects.filter(user=user, date=OuterRef("date"))))
                .order_by("-date").values_list("opcao", flat=True).first()
                if len(sessao.opcoes) > 1 else None
            )
            numero = feita if feita in sessao.opcoes else sessao.opcoes[0]
        elif services.usa_presenca(sessao.plan):
            # Por presença, a ficha de OUTRA letra mostra a PRÓXIMA vez que ela
            # cai — a variação para hoje (a contagem da letra até agora). Não é
            # mais a "próxima ocorrência no calendário": a semana não fixa mais
            # a letra a um dia.
            numero = services.variacao_do_dia(sessao.plan, hoje_data, sessao, linhas, user=user, seq=seq)
        else:
            numero = services.variacao_do_dia(sessao.plan, self._data_da_ficha(sessao, irmas, hoje_data), sessao, linhas, user=user)
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
            # "POR QUE ESSA FICHA" (22/09/2026): o diferencial do NutriPlan
            # sobre um caderno é que ele EXPLICA a ficha, e a explicação
            # estava atrás de um `<details>` na OUTRA tela ("Detalhes do
            # programa", no painel) — ninguém chegava lá. O que entra aqui é
            # só o desta sessão, e sai dos itens já carregados: zero
            # consulta.
            "volume_por_grupo": _volume_por_grupo(itens),
        }
        return {
            "ficha": ficha,
            "escolha": escolha,
            "versao": versao,
            "rapida": versao == "rapido",
        }


def _volume_por_grupo(itens) -> list:
    """[(grupo, séries)] desta ficha, do maior para o menor. Em memória."""
    por_grupo = {}
    for item in itens:
        nome = item.exercise.get_muscle_group_display()
        por_grupo[nome] = por_grupo.get(nome, 0) + item.sets
    return sorted(por_grupo.items(), key=lambda par: (-par[1], par[0]))


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
        analytics.evento(request, "treino.troca",
                         {"de": original.name, "para": substituto.name})
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
        sessao = services.sessao_do_dia(plan, dia, user=request.user)
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


class EscolherLetraView(AcaoDeTela, OnboardingRequiredMixin, View):
    """"Fazer outro treino" — a pessoa escolhe qual letra fazer hoje
    (24/09/2026). Estado absoluto por dia, sem `op_id`. Trocar depois de já ter
    registrado série hoje pede confirmação (`?trocar=<letra>` reabre o painel
    com o convite) e NÃO apaga nada. A ação é só POST; o GET volta ao painel."""

    tela_da_acao = "workouts:routine"

    def post(self, request, *args, **kwargs):
        dia = timezone.localdate()
        plan = services.get_active_routine(request.user)
        if plan is None:
            messages.info(request, "Hoje não é dia de treino.")
            return redirect("workouts:routine")
        letra = (request.POST.get("letra") or "").strip().upper()
        confirmar = bool(request.POST.get("confirmar"))
        escolha, precisa_confirmar = services.registrar_escolha_de_letra(
            request.user, plan, letra, dia=dia, confirmar=confirmar
        )
        if precisa_confirmar:
            return redirect(reverse("workouts:routine") + "?trocar=" + letra)
        if escolha is None:
            messages.info(request, "Treino não encontrado.")
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
        # passar de N (`telas.anotar_carga` diz por quê).
        feitas = request.POST.get("series_feitas")
        if feitas is not None:
            try:
                feitas = max(0, min(int(feitas), 20))
            except (TypeError, ValueError):
                feitas = 1
        primeira_do_dia = telas.anotar_carga(
            request.user, exercise, peso, serie, reps=reps, feitas=feitas
        )

        # As conquistas sao avaliadas AQUI, depois de o `ExerciseLog` estar
        # gravado — e SÓ QUANDO HÁ MOTIVO (T2.4, 17/09/2026): na primeira
        # série do dia (um dia de treino passa a existir) ou quando a carga
        # supera o recorde — a mesma guarda de `ConcluirSerieView`. O
        # catálogo inteiro custa dezenas de consultas, e esta rota pagava em
        # toda carga anotada; abaixo do recorde, no meio do treino, nenhuma
        # regra muda de resposta.
        hoje = timezone.localdate()
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
                    "descanso": telas.descanso_de(request.user, exercise),
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
        _, adiado = services.pedir_para_regenerar(request.user)
        if adiado:
            messages.info(
                request,
                "Anotado: você já registrou série hoje, então a ficha nova entra amanhã "
                "— o treino de hoje continua como está.",
            )
        else:
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
        # A lista fechada é a da tela: o corpo inteiro de uma vez por semana
        # não aceita faixa abaixo de 75 (28/09/2026, decisão do dono) — um
        # formulário velho não grava o que a tela deixou de oferecer.
        plano = services.get_active_routine(request.user)
        if TETO_POR_DURACAO[faixa] < services.minimo_da_ficha(plano):
            messages.error(request, services.REGRA_DO_CORPO_INTEIRO)
            return redirect("workouts:routine")
        teto = TETO_POR_DURACAO[faixa]

        # O perfil pelo descritor, e não por `Profile.objects.filter(...)`:
        # o `dispatch` já o deixou em cache em `request.user.profile`, e o
        # motor (`sync_active_routine` → `teto_de_minutos`) lê ESSE cache.
        # Gravar por outra instância deixava o cache com a faixa velha e a
        # ficha remontava para "padrão" (achado da suíte, 21/09/2026).
        perfil = self.perfil_do_dispatch or getattr(request.user, "profile", None)
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

        if plano is not None and plano.is_customized:
            messages.info(
                request,
                "Duração salva: até %d minutos. Você ajustou a ficha à mão, "
                "então ela não é remontada — a duração vale na próxima remontagem." % teto,
            )
            return redirect("workouts:routine")
        if plano is not None and services.treino_em_andamento(request.user):
            messages.info(
                request,
                "Duração salva: até %d minutos. Há série registrada hoje, "
                "então a ficha muda amanhã." % teto,
            )
            return redirect("workouts:routine")
        _, mudou = services.sync_active_routine(request.user)
        if mudou:
            messages.success(request, "Ficha remontada para até %d minutos por sessão." % teto)
        else:
            messages.info(request, "Duração salva: até %d minutos." % teto)
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


class EncerrarTreinoView(AcaoDeTela, OnboardingRequiredMixin, View):
    """"Encerrar treino": a pessoa diz que acabou, e o placar abre.

    O app não tinha fecho. "Concluído" só existia com toda série prescrita
    registrada — quem parava no sexto de nove exercícios ficava em
    "Exercício 6/9" para sempre, sem resumo nenhum do que fez, e "Ver o
    treino completo" não era isso (leva à ficha).

    COM MENOS DA METADE DAS SÉRIES, PERGUNTA ANTES. Encerrar é reversível
    ("Retomar treino" no placar) e não apaga nada, mas fechar sem querer no
    meio do terceiro exercício esconderia a ficha do resto do dia — e a
    confirmação é uma tela, não um `confirm()`: a execução reabre com o
    bloco de confirmação em cima, que funciona sem JavaScript.
    """

    tela_da_acao = "workouts:now"
    #: Abaixo disto o fecho pede confirmação. Metade porque é a régua que a
    #: pessoa reconhece — "fiz menos da metade do que estava na ficha".
    FRACAO_QUE_PERGUNTA = 0.5

    def post(self, request, *args, **kwargs):
        estado = services.estado_do_treino(request.user)
        if not estado.tem_treino:
            return redirect("workouts:now")
        parcial = (
            estado.total_series
            and estado.series_feitas < estado.total_series * self.FRACAO_QUE_PERGUNTA
        )
        if parcial and request.POST.get("confirmado") != "1":
            return redirect(reverse("workouts:now") + "?encerrar=confirmar")
        services.encerrar_treino(request.user, estado.sessao)
        # `treino.concluido` também estava na taxonomia sem nunca ser
        # disparado. A duração é a MEDIDA (`minutos_do_treino`), que desde
        # hoje vai da primeira série ao encerramento — o mesmo número que o
        # placar mostra, para a gestão e a tela não discordarem.
        analytics.evento(
            request, "treino.concluido", {"duracao": estado.minutos_do_treino}
        )
        if estado.series_feitas:
            messages.success(
                request,
                "Treino encerrado · %d de %d séries registradas."
                % (estado.series_feitas, estado.total_series),
            )
        else:
            # Sem nenhuma série não há o que celebrar, e dizer "treino
            # encerrado" para um dia em branco seria o app afirmando o que
            # não aconteceu.
            messages.info(request, "Treino encerrado sem séries registradas hoje.")
        return redirect("workouts:now")


class RetomarTreinoView(AcaoDeTela, OnboardingRequiredMixin, View):
    """Encerrou sem querer: o carimbo sai e o treino continua de onde parou.

    Nada foi apagado para ser desfeito — `ExerciseLog` continua intacto —,
    então retomar é tirar uma data da escolha do dia."""

    tela_da_acao = "workouts:now"

    def post(self, request, *args, **kwargs):
        if services.retomar_treino(request.user) is not None:
            messages.info(request, "Treino retomado.")
        return redirect("workouts:now")


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

    E DESDE 24/09/2026 HÁ UMA SEGUNDA PORTA, mais forte que a primeira: o
    exercício em que ESTA pessoa registrou série é dela, esteja ele na ficha
    de hoje ou não. MEDIDO no navegador: três séries registradas pela
    execução, equipamento trocado no Perfil, ficha remontada no dia seguinte
    — e a leitura passava a responder 404 com as séries intactas no banco.
    O histórico só existia na exportação.

    A porta nova não afrouxa o IDOR: ela é uma condição sobre `logs__user`,
    que é a própria pessoa. Id de exercício que ela nunca fez e que não está
    na ficha dela continua 404, e `test_sabotagem_apagar_a_serie_fecha_a_
    porta_de_novo` prova que é o REGISTRO que abre a página.

    `is_active` também deixou de ser exigido por essa porta: exercício
    aposentado nunca é apagado (`ExerciseLog` é `CASCADE`), então quem
    treinou um que saiu do catálogo continua podendo ler o que fez.
    """

    template_name = "workouts/exercicio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        plano = services.get_active_routine(user)
        # O exercício da ficha — ou o SUBSTITUTO que a pessoa pôs no lugar de
        # um deles ("outras formas") —, ou um em que ela já registrou série.
        exercicio = telas.exercicio_legivel(user, plano, kwargs["exercise_id"])

        # As ocorrências na semana, com a letra que a ficha mostra (A1/A2) —
        # a semana de HOJE pela posição no ciclo, na ordem dos dias.
        # A escolha do dia, lida UMA vez: a projeção da pessoa (BA4) e a opção
        # de hoje, logo abaixo, usam a mesma. Sem plano (a leitura "fora da
        # ficha") não há semana nem opção, e a consulta seria à toa.
        escolha = services.escolha_do_dia(user) if plano is not None else None
        sessoes = telas.semana_do_plano(user, plano, escolha=escolha)
        nomear_ocorrencias(sessoes)
        itens = []
        for sessao in sessoes:
            for item in sessao.exercises.all():
                if item.exercise_id == exercicio.pk and not any(
                    i.session is sessao for i in itens
                ):
                    # Uma linha por sessão: o exercício pode estar nas duas
                    # opções da letra, e "Segunda (A), Segunda (A)" é ruído.
                    #
                    # CÓPIA RASA, e não a linha em si (18/09/2026): as
                    # ocorrências da letra na semana são cópias vestidas da
                    # MESMA linha (`sessoes_da_semana`), que compartilham as
                    # linhas pré-carregadas. Gravar `session` na linha
                    # compartilhada fazia a última ocorrência vencer — a
                    # leitura dizia "Quinta-feira (A), Quinta-feira (A)" e
                    # a segunda sumia (achado na prova em produção).
                    ocorrencia = copy.copy(item)
                    ocorrencia.session = sessao
                    itens.append(ocorrencia)
        hoje = timezone.localdate().weekday()
        # "Fazer este exercício" só existe se ele está na OPÇÃO do dia — a
        # execução só abre a opção escolhida (ou a recomendada), e um link
        # para a outra opção daria 404.
        item_de_hoje = None
        sessao_de_hoje = next((s for s in sessoes if s.weekday == hoje), None)
        if sessao_de_hoje is not None:
            opcao = services.opcao_do_dia(user, sessao_de_hoje, timezone.localdate(), sessoes, escolha=escolha)
            item_de_hoje = next(
                (i for i in sessao_de_hoje.da_opcao(opcao) if i.exercise_id == exercicio.pk), None
            )
            if item_de_hoje is not None:
                item_de_hoje.session = sessao_de_hoje
        if item_de_hoje is not None:
            # Só a contagem de hoje deste exercício — UMA consulta — para o
            # botão dizer "Fazer agora" ou "Continuar de onde parou".
            item_de_hoje.feitas = telas.series_anotadas_hoje(user, [exercicio.pk])
        historico = services.historico_do_exercicio(user, exercicio)
        # "OUTRAS FORMAS": as alternativas do mesmo padrão no equipamento da
        # pessoa, fora do que já está nas sessões em que ele cai; e, se este
        # exercício está no lugar de outro, o original com o histórico dele.
        # Varre TODAS as linhas, e não só a primeira por sessão: o substituto
        # pode ser também uma linha crua da outra opção da mesma letra (a
        # flexão da opção 1 posta no lugar do supino da opção 2), e a linha
        # crua vinha primeiro — a leitura perdia o "No lugar de" (ensaio da
        # prova em produção, 17/09).
        original = next(
            (
                i.original for sessao in sessoes for i in sessao.exercises.all()
                if i.exercise_id == exercicio.pk and getattr(i, "original", None) is not None
            ),
            None,
        )
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
            # A escada de progressão do movimento (peso do corpo): do mais
            # fácil ao mais difícil, com o atual marcado. Vazia para quem não
            # pertence a uma escada.
            "escada": services.escada_de(exercicio),
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
            "prescricao": itens[0] if itens else None,
            # Sem o dia `pulado` (BA4, 28/09/2026): a linha pulada é a da
            # letra na estrutura, e "Quarta-feira (C)" numa semana em que C
            # caiu na quinta era o mapa fixo dia↔letra de antes da presença.
            "dias": [
                "%s (%s)" % (i.session.weekday_display, i.session.rotulo)
                for i in itens if getattr(i.session, "projecao", None) != "pulado"
            ],
            # Os dias acima são os desta semana (rotação); com o ciclo girando, a
            # letra cai em dias diferentes na semana seguinte, e sem dizer isso o
            # "Quando" é lido como fixo (avaliação de UX, 20/09/2026).
            "ciclo_continuo": services.ciclo_roda(plano) if plano is not None else False,
            "item_de_hoje": item_de_hoje,
            # FORA DA FICHA (24/09/2026): a pessoa chegou aqui pelo histórico
            # — a ficha foi remontada, ou ela apagou a rotina. A tela abre
            # com o que ela fez e DIZ que este exercício não está na ficha de
            # hoje; sem a frase, "Quando" vazio pareceria defeito.
            "fora_da_ficha": not itens,
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


class ExerciciosFeitosView(OnboardingRequiredMixin, TemplateView):
    """"Exercícios que já fiz" — a porta para o que saiu da ficha.

    A leitura de um exercício passou a abrir para qualquer um em que a pessoa
    tenha registrado série (24/09/2026), e sem esta lista aquela porta não
    tem maçaneta: o exercício que a remontagem tirou da ficha não aparece em
    tela nenhuma, e só quem tivesse guardado o endereço chegaria lá.

    UMA consulta: o filtro por `logs__user` e as duas agregações
    compartilham a mesma junção, então `series` e `ultima` já vêm contadas
    só das séries DESTA pessoa. `is_active` não entra — exercício aposentado
    nunca é apagado, e quem treinou um deles continua tendo o que ler.
    """

    template_name = "workouts/exercicios_feitos.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        perfil = self.perfil_do_dispatch or getattr(self.request.user, "profile", None)
        context.update({
            "nav": "workout",
            # #138: quem não faz musculação não é mandado "ver a semana" de
            # uma ficha que não tem — o vazio dela é a porta de começar.
            "nao_faz_musculacao": bool(perfil) and perfil.musculacao == Musculacao.NAO,
            "feitos": list(
                Exercise.objects.filter(logs__user=self.request.user)
                .annotate(series=Count("logs"), ultima=Max("logs__date"))
                .order_by("-ultima", "name")
            ),
        })
        return context


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
        # DESCANSO COM PORTA (R4, 28/09/2026): a letra do "treinar mesmo
        # assim" é a do próximo treino — a recomendada, a seguinte à última
        # feita —, a mesma que o painel oferece. Só no descanso (uma consulta).
        if estado.plan is not None and estado.sessao is None:
            proximo = services.proximo_treino(
                estado.linhas, estado.plan, timezone.localdate(), estado.linhas, user=user
            )
            context["treinar_mesmo_assim"] = proximo["session"].label if proximo else None
        # `?extra=1` reabre o formulário num exercício já concluído — a série
        # a mais, que `append_set` sempre aceitou (até 20). LISTA FECHADA,
        # como `?exercicio=`: valor desconhecido é 404, e não "ignora e abre
        # a tela normal" — link quebrado que funciona nunca é consertado.
        extras = self.request.GET.getlist("extra")
        if extras and extras != ["1"]:
            raise Http404("pedido de série extra ilegível")
        # `?encerrar=confirmar` é a volta de `EncerrarTreinoView` quando o
        # treino está pela metade: a tela reabre com o bloco de confirmação
        # em cima. LISTA FECHADA, como `?exercicio=` e `?extra=`.
        encerrar = self.request.GET.getlist("encerrar")
        if encerrar and encerrar != ["confirmar"]:
            raise Http404("pedido de encerramento ilegível")
        context["encerrar_confirmar"] = bool(encerrar) and not estado.concluido
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
        # MODO TREINO É MODO FOCO DE VERDADE (22/09/2026). A barra de abas
        # (Alimentação · Treino · Progresso · Áreas) e o rodapé legal
        # continuavam na tela entre uma série e outra: quatro destinos para
        # sair de uma tarefa que se faz de pé, ocupando 5,9rem do único
        # aparelho que a pessoa tem na mão. As saídas desta tela são as duas
        # que ela usa — "← Ficha" no topo e "Encerrar treino" no fim.
        #
        # E desligar a barra conserta, de graça, o salto de layout do campo
        # de carga: `.teclado-aberto .container` devolvia o espaço reservado
        # para a barra ao focar um campo de texto, a página encolhia ~100 px
        # (MEDIDO: `scrollHeight` 1026 → 923) e o "Concluir série" fugia do
        # dedo. Sem barra não há espaço a devolver.
        context["sem_tabbar"] = True
        # O rodapé legal (Política · Termos) fica nas outras telas — a
        # LGPD pede acesso FACILITADO, e ele está a um toque daqui, na ficha
        # e no Perfil. Aqui ele é o terceiro bloco de links num treino.
        context["sem_rodape_legal"] = True
        # A REFERÊNCIA DO MOVIMENTO (auditoria de 20/09/2026, upgrade 4,
        # aprovado pelo dono): as duas opções da letra têm exercícios
        # DIFERENTES, então um exercício só repete de
        # duas em duas semanas — e a "última carga", o SUBIR e o recorde
        # ficam mudos por 14 dias. Quando ESTE exercício não tem histórico,
        # a tela conta o que a pessoa fez no mesmo MOVIMENTO (mesmo
        # `padrao`): "Na última pressão de peito (supino reto com barra,
        # 21/09) você usou 20 kg × 10". UMA consulta, só neste caso, só para
        # o exercício em foco; é dica, não sugestão de número — a barra e a
        # máquina não pesam igual.
        atual = getattr(estado, "atual", None)
        context["movimento_anterior"] = None
        if atual is not None and not atual.exercise.sem_carga:
            # `item.load` é o dicionário de `load_history`: sem `melhor_anterior`
            # não há "última carga" própria, e é aí que a referência entra.
            historico = getattr(atual, "load", None) or {}
            if not historico.get("melhor_anterior"):
                context["movimento_anterior"] = services.ultima_vez_do_movimento(user, atual.exercise)
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

        # A OBSERVAÇÃO E A FALHA (22/09/2026): campos comuns do mesmo POST,
        # então a fila offline os reenvia sem contrato novo. A nota é
        # cortada em 120 (o tamanho da coluna) em vez de recusada: o toque
        # que registra a série não pode ser perdido por causa do texto.
        nota = (request.POST.get("nota") or "").strip()[:120]
        falhou = request.POST.get("falhou") == "1"
        # A SÉRIE ALÉM DA FICHA SÓ QUANDO PEDIDA (M14, 28/09/2026). Duas abas
        # no mesmo exercício diziam "Série 3 de 3"; a segunda fechava a
        # terceira e a VELHA gravava uma quarta por cima, muda. A contagem
        # vem ANTES da escrita (é a mesma consulta que vinha depois, para
        # "concluído · 4/4" — o orçamento do POST não muda) e vira o teto que
        # `append_set` confere dentro da transação, depois do `op_id`: o
        # reenvio da MESMA série continua aceito. "Registrar uma série a
        # mais" manda `extra=1` e não tem teto além dos vinte de sempre.
        feitas, prescritas = services.series_de_hoje(request.user, exercise, dia=dia)
        extra = request.POST.get("extra") == "1"
        try:
            criada, primeira_do_dia = telas.concluir_serie(
                request.user, exercise, peso, dia, reps=reps, op_id=op_id,
                nota=nota, falhou=falhou, evento=partial(analytics.evento, request),
                teto=None if extra else (prescritas or None),
            )
        except services.SerieAlemDaPrescrita:
            messages.error(
                request,
                "As %d séries de %s já estavam registradas — esta não foi gravada. "
                "Se fez uma a mais, toque em Registrar uma série a mais."
                % (prescritas, exercise.name),
            )
            return redirect("%s?exercicio=%d" % (reverse("workouts:now"), exercise.pk))
        except ValueError:
            # Vinte séries no mesmo exercício num dia. Não é treino, é dedo
            # preso no botão ou fila reproduzindo algo corrompido — e recusar
            # em silêncio deixaria a pessoa tocando sem entender.
            messages.error(request, "Limite de séries deste exercício hoje.")
        else:
            self._avisar_se_o_programa_mudou(request)
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
            # (`criada=False`) não é dia novo. Uma consulta decide cada um
            # (`primeira_do_dia` vem de `telas.concluir_serie`).
            if primeira_do_dia:
                # O dia de treino passa a existir na primeira série; é o sinal
                # de "começou a treinar". A letra fica de fora para não pagar
                # uma consulta na rota mais quente do app.
                analytics.evento(request, "treino.iniciado", {})
            if primeira_do_dia or services.supera_recorde(
                request.user, exercise, peso, reps=reps, dia=dia
            ):
                novas = conquistas.avaliar(request.user, hoje=dia)
                conquistas.anunciar(request, novas)
            # Fechou a última série: a tela seguinte já é outro exercício, e
            # sem esta frase a pessoa não sabia que o anterior tinha fechado
            # (UX TR-02). Só no fechamento — uma frase por série seria ruído.
            # A contagem é a de antes da escrita mais esta, se ela nasceu.
            fechadas = feitas + (1 if criada else 0)
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

    @staticmethod
    def _avisar_se_o_programa_mudou(request) -> bool:
        """A tela foi desenhada com um programa que já não é o vigente?

        O formulário carrega o id da sessão em que a pessoa está treinando.
        Quando aquele plano deixou de ser o ativo — outra aba pediu
        "regenerar", o perfil mudou em outro aparelho —, a série é gravada
        do mesmo jeito (`ExerciseLog` é por exercício e data, e descartar o
        toque seria o pior desfecho) e a tela DIZ o que aconteceu, em vez de
        a pessoa descobrir sozinha que o próximo exercício é outro.

        UMA consulta, e só quando o formulário traz o campo.
        """
        bruto = request.POST.get("sessao") or ""
        if not bruto.isdigit():
            return False
        ativa = telas.plano_da_sessao_vigente(request.user, int(bruto))
        if ativa is False:
            messages.warning(
                request,
                "Seu programa de treino mudou enquanto você treinava. A série foi "
                "registrada e continua no seu histórico — a ficha de hoje agora é outra.",
            )
            return True
        return False

    def _garantir_escolha(self, request, dia) -> None:
        """Lê `sessao`, `opcao` e `versao` do formulário para
        `telas.garantir_escolha` (a primeira série do dia grava a opção)."""
        try:
            sessao_id = int(request.POST.get("sessao") or "")
        except (TypeError, ValueError):
            sessao_id = None
        try:
            opcao = int(request.POST.get("opcao") or "1")
        except ValueError:
            opcao = 1
        telas.garantir_escolha(
            request.user, dia, sessao_id, opcao, request.POST.get("versao") or "completo"
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
