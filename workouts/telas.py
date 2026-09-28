"""O que as telas de treino pedem ao banco: a ficha, a leitura de um
exercício, a carga anotada e a série concluída.

As views (`FichaDaSessaoView`, `ExercicioView`, `RecordLoadView`,
`ConcluirSerieView`) leem o pedido, chamam uma função daqui e montam a
resposta. Nenhuma função recebe `request`: recebem pessoa, ids e valores, e
por isso se testam sem cliente HTTP (`test_servicos_das_telas.py`).

A IDEMPOTÊNCIA NÃO MORA AQUI, e isso é de propósito. A carga grava por
`services.record_load` (`update_or_create` na chave pessoa · exercício · dia ·
série) e a série por `services.append_set` (`op_id` na mesma transação da
escrita). Estas funções só passam por elas — quem trocar a passagem por um
`create` quebra a fila offline em silêncio, e o teste daqui fica vermelho.
"""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from . import services
from .models import Exercise, ExerciseLog, SessionExercise, TrainingSession


def ficha_da_pessoa(user, sessao_id) -> tuple:
    """`(sessao, linhas, historico)` da ficha pedida, ou 404.

    A SESSÃO DE UM PROGRAMA ANTERIOR ABRE COMO HISTÓRICO (22/09/2026). O
    filtro era `plan__is_active=True`, e a ficha EM USO respondia "Esta
    página não existe" no instante em que o programa era remontado — o dono
    viu isso com quatro séries anotadas. O fechamento de IDOR que importa é
    `plan__user=user`, e ele fica; o que sai é o `is_active`, que nunca
    protegeu ninguém.

    A sessão pedida e as linhas do plano voltam como objetos distintos (duas
    consultas); a view aplica as trocas nos dois depois.
    """
    sessao = get_object_or_404(
        TrainingSession.objects.select_related("plan"), pk=sessao_id, plan__user=user
    )
    historico = not sessao.plan.is_active
    # `prefetch` aqui e não no `get_object_or_404`: o filtro precisa bater
    # no banco antes de valer a pena trazer os exercícios.
    sessao = (
        TrainingSession.objects.filter(pk=sessao.pk)
        .prefetch_related("exercises__exercise")
        .first()
    )
    return sessao, services.linhas_do_plano(sessao.plan), historico


def series_anotadas_hoje(user, exercise_ids) -> int:
    """Quantas séries de HOJE a pessoa anotou nestes exercícios. UMA consulta."""
    return ExerciseLog.objects.filter(
        user=user, exercise_id__in=exercise_ids, date=timezone.localdate()
    ).count()


def exercicio_legivel(user, plano, exercise_id):
    """O exercício que a pessoa pode LER, ou 404.

    Duas portas: o da ficha ativa — ou o SUBSTITUTO que ela pôs no lugar de
    um deles ("outras formas") —, e um em que ela já registrou série. A
    segunda não afrouxa o IDOR: é uma condição sobre `logs__user`, a própria
    pessoa, e não exige `is_active` (exercício aposentado nunca é apagado).
    """
    do_historico = Q(logs__user=user)
    if plano is not None:
        da_ficha = (
            Q(sessions__session__plan=plano, is_active=True)
            | Q(
                trocas_como_substituto__user=user,
                trocas_como_substituto__original__sessions__session__plan=plano,
                is_active=True,
            )
        )
    else:
        da_ficha = Q(pk__in=())
    return get_object_or_404(
        Exercise.objects.filter(da_ficha | do_historico).distinct(), pk=exercise_id
    )


def semana_do_plano(user, plano, escolha=services._NAO_INFORMADO) -> list:
    """As sessões da semana de HOJE, vestidas com as trocas da pessoa, na
    ordem dos dias; `[]` sem plano.

    `exercises` sem `__exercise`: a leitura só precisa dos ids das linhas;
    `aplicar_trocas` busca o exercício só das linhas trocadas.

    A projeção é a DA PESSOA (`user=`, BA4, 28/09/2026) — a mesma da tira do
    Treino. Sem ela era a de quem nunca treinou: hoje seria sempre a primeira
    letra, e "Quando" dizia outro dia que a tira. `escolha` é a do dia, que a
    view já leu — sem ela a projeção a consultaria de novo."""
    if plano is None:
        return []
    linhas = list(plano.sessions.prefetch_related("exercises"))
    services.aplicar_trocas(user, linhas)
    letra = escolha
    if escolha is not services._NAO_INFORMADO:
        letra = escolha.session.label if escolha is not None and escolha.session.plan_id == plano.pk else None
    return sorted(
        services.sessoes_da_semana(plano, timezone.localdate(), linhas, user=user, escolha_hoje=letra),
        key=lambda s: s.weekday,
    )


def anotar_carga(user, exercise, peso, serie, reps=None, feitas=None) -> bool:
    """Anota a carga pela ficha e diz se esta é a PRIMEIRA série do dia.

    Com `feitas`, grava de 1 até N com a mesma carga e APAGA o que passar de
    N. Apagar é o que torna o contador honesto: baixar de 4 para 3 significa
    que a quarta não aconteceu, e deixá-la no banco faria o volume do dia
    mentir para sempre. O formato do histórico não muda — uma linha por
    série, que é o que o cálculo de volume lê.
    """
    if feitas is not None:
        for numero in range(1, feitas + 1):
            services.record_load(user, exercise, peso, set_number=numero, reps=reps)
        ExerciseLog.objects.filter(
            user=user,
            exercise=exercise,
            date=timezone.localdate(),
            set_number__gt=feitas,
        ).delete()
    else:
        services.record_load(user, exercise, peso, set_number=serie, reps=reps)
    return not (
        ExerciseLog.objects.filter(user=user, date=timezone.localdate())
        .exclude(exercise=exercise, set_number=serie)
        .exists()
    )


def descanso_de(user, exercise) -> int:
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


def concluir_serie(
    user, exercise, peso, dia, reps=None, op_id="", nota="", falhou=False, evento=None,
) -> tuple:
    """Grava UMA série no dia do toque: `(criada, primeira_do_dia)`.

    `criada=False` é reenvio reconhecido pelo `op_id` (a fila offline), e aí
    não é dia novo — uma consulta só decide a primeira quando a linha NASCE.
    `ValueError` (vinte séries no dia) sobe para a tela dizer o limite.

    `evento(nome, props)` (a view passa `analytics.evento` com o request)
    emite `treino.serie_concluida` UMA vez, e só quando a linha NASCE: o
    reenvio da fila é a mesma série chegando de novo, e contá-la inflaria a
    gestão. Sem `evento` (quem grava fora do HTTP), nada é emitido. Sai
    depois do commit — `append_set` fecha o próprio `atomic` antes de voltar
    e o projeto não liga `ATOMIC_REQUESTS`. Até 27/09/2026 a view emitia
    duas vezes; `props` é a união dos dois payloads, e nada nele é PII.
    """
    log, criada = services.append_set(
        user, exercise, peso, reps=reps, op_id=op_id, day=dia, nota=nota, falhou=falhou,
    )
    if criada and evento is not None:
        evento("treino.serie_concluida", {
            "exercicio": exercise.pk, "exercicio_nome": exercise.name,
            "carga": float(peso or 0), "reps": reps if reps is not None else 0,
        })
    primeira_do_dia = criada and not (
        ExerciseLog.objects.filter(user=user, date=dia).exclude(pk=log.pk).exists()
    )
    return criada, primeira_do_dia


def plano_da_sessao_vigente(user, sessao_id):
    """`True`/`False` se a sessão é da pessoa e o plano dela é (ou não) o
    ativo; `None` se a sessão não é dela. UMA consulta."""
    return (
        TrainingSession.objects.filter(pk=sessao_id, plan__user=user)
        .values_list("plan__is_active", flat=True)
        .first()
    )


def garantir_escolha(user, dia, sessao_id, opcao, versao) -> None:
    """A primeira série do dia grava qual opção está sendo feita.

    O formulário da execução traz `sessao`, `opcao` e `versao` (escritos
    pelo servidor); item antigo da fila offline não traz, e aí a escolha
    cai na opção 1 da sessão do dia. Idempotente: uma escolha por dia.
    """
    if services.escolha_do_dia(user, dia) is not None:
        return
    sessao = None
    if sessao_id:
        sessao = TrainingSession.objects.filter(
            pk=sessao_id, plan__user=user, plan__is_active=True
        ).prefetch_related("exercises").first()
    if sessao is None:
        # `escolha=None`: a primeira linha desta função já viu que não há.
        sessao = services.sessao_do_dia(services.get_active_routine(user), dia, user=user, escolha=None)
    if sessao is None:
        return
    services.registrar_escolha(user, sessao, opcao, versao=versao, dia=dia)
