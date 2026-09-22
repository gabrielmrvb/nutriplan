"""Detectar e gravar conquistas.

QUANDO ISTO RODA. No caminho de ESCRITA — registrar série, nas DUAS rotas
que gravam série (`ConcluirSerieView`, a da execução, e `RecordLoadView`) —,
e nunca num agendador, porque o projeto não tem um: cron no Render é recurso
pago, e foi por isso que os lembretes de refeição ficaram desligados. Rodar na
escrita também é o que mantém a conquista honesta no tempo: ela nasce no
instante em que a pessoa fez a coisa.

Esta docstring já afirmou que refeição e água também avaliavam. Não
avaliavam, e `ConcluirSerieView` — a rota que a execução usa — tampouco: só a
rota do cartão antigo chamava `avaliar`, e como a chave do recorde é
`exercício:data`, o recorde de hoje só nascia se a pessoa abrisse
/conquistas/ no mesmo dia. Corrigido em 13/09/2026. Refeição e água
continuam FORA: "7 dias de ofensiva" desbloqueia na próxima série ou na
próxima visita a /conquistas/, e isso está dito aqui para ninguém confiar no
contrário.

POR QUE NÃO RODA NA LEITURA. Um GET que grava é um GET que grava — e o painel é
a tela mais aberta do app. `avaliar` é idempotente e sobreviveria a isso, mas o
custo apareceria em toda visita para um ganho que a escrita já entrega.
"""
from dataclasses import replace
from datetime import timedelta

from django.db.models import DecimalField, ExpressionWrapper, F, Max, Min, Q
from django.utils import timezone

from accounts.models import TrainingDay
from plans import services as plan_services
from plans import streaks, weight_trend
from workouts.models import ExerciseLog, TrainingPlan

from .models import UserAchievement
from .regras import CATALOGO, Dados

#: Até quantas semanas para trás procurar semana completa.
#:
#: Duas, e não o histórico inteiro. Uma semana fecha no domingo e pode ser
#: avaliada só na segunda, então uma janela de uma semana perderia isso; e
#: varrer um ano a cada série registrada custaria caro para desbloquear em lote
#: um punhado de conquistas retroativas que ninguém viu acontecer.
SEMANAS_OLHADAS = 2


def _segunda(dia):
    return dia - timedelta(days=dia.weekday())


def reunir(user, hoje=None) -> Dados:
    """Lê o banco uma vez e monta o que os detectores consomem."""
    hoje = hoje or timezone.localdate()

    datas = set(
        ExerciseLog.objects.filter(user=user)
        .values_list("date", flat=True)
        .distinct()
    )
    previstos = frozenset(
        TrainingDay.objects.filter(user=user).values_list("weekday", flat=True)
    )

    # A MESMA META DE ÁGUA QUE A HOME (22/09/2026): sem ela a água "fechava"
    # todo dia e as Conquistas diziam "3 dias" enquanto a Home dizia 0. O
    # plano ativo é lido uma vez aqui e emprestado à ofensiva
    # (`_streak_tem_plano`), então o custo não muda.
    plano = plan_services.get_active_plan(user)
    user._streak_tem_plano = plano is not None
    meta_agua = weight_trend.hidratacao_ml(plano.weight_kg) if plano else None

    dados = Dados(
        hoje=hoje,
        dias_treinados=len(datas),
        previstos=previstos,
        # `hoje` viaja junto: sem isso a ofensiva leria o calendário real
        # enquanto o resto do cálculo usa a data recebida, e o teste que
        # controla a data mediria duas coisas diferentes ao mesmo tempo.
        ofensiva=streaks.calcular(user, hoje=hoje, meta_agua_ml=meta_agua).dias,
        tem_plano=TrainingPlan.objects.filter(user=user, is_active=True).exists(),
    )

    # ------------------------------------------------------ semana completa
    completas = []
    if previstos:
        for atras in range(SEMANAS_OLHADAS):
            segunda = _segunda(hoje) - timedelta(weeks=atras)
            dias = {segunda + timedelta(days=d) for d in previstos}
            # Dia previsto que ainda não chegou não reprova a semana atual —
            # ele simplesmente ainda não aconteceu, e por isso a semana só
            # conta quando TODOS os previstos já passaram e foram cumpridos.
            if all(d <= hoje for d in dias) and dias <= datas:
                completas.append(segunda)
    dados = replace(dados, semanas_completas=tuple(completas))

    # ------------------------------------------------------------- recordes
    #
    # As duas espécies (`_recorde` e `_melhor_serie`) saem da MESMA consulta
    # de hoje e da MESMA consulta de anteriores — o produto reps×carga é só
    # mais uma agregação ao lado de `Max("weight_kg")`, o mesmo truque de
    # `workouts.services.supera_recorde`. Zero consultas a mais.
    produto_serie = ExpressionWrapper(
        F("weight_kg") * F("reps"),
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    de_hoje = list(
        ExerciseLog.objects.filter(user=user, date=hoje, weight_kg__isnull=False)
        .values("exercise_id", "exercise__name")
        .annotate(
            maior=Max("weight_kg"),
            melhor_serie=Max(produto_serie, filter=Q(reps__isnull=False)),
        )
    )
    if de_hoje:
        anteriores_agregados = list(
            ExerciseLog.objects.filter(
                user=user,
                date__lt=hoje,
                weight_kg__isnull=False,
                exercise_id__in=[l["exercise_id"] for l in de_hoje],
            )
            .values("exercise_id")
            .annotate(
                maior=Max("weight_kg"),
                melhor_serie=Max(produto_serie, filter=Q(reps__isnull=False)),
            )
        )
        cargas_anteriores = {
            linha["exercise_id"]: linha["maior"] for linha in anteriores_agregados
        }
        series_anteriores = {
            linha["exercise_id"]: linha["melhor_serie"]
            for linha in anteriores_agregados
        }
        # `anteriores.get(...)` sem valor significa estreia, e estreia não é
        # recorde — ver o contrato em `regras._recorde` e `regras._melhor_serie`.
        dados = replace(
            dados,
            recordes_hoje=tuple(
                (linha["exercise_id"], linha["exercise__name"])
                for linha in de_hoje
                if linha["exercise_id"] in cargas_anteriores
                and linha["maior"] > cargas_anteriores[linha["exercise_id"]]
            ),
            melhores_series_hoje=tuple(
                (linha["exercise_id"], linha["exercise__name"])
                for linha in de_hoje
                if linha["melhor_serie"] is not None
                and series_anteriores.get(linha["exercise_id"]) is not None
                and linha["melhor_serie"] > series_anteriores[linha["exercise_id"]]
            ),
        )

    return dados


def avaliar(user, hoje=None) -> list:
    """Roda o catálogo e grava o que for novo. Devolve só o que nasceu agora.

    Idempotente por construção: a unicidade `(user, slug, chave)` está no
    banco, então repetir a mesma ação não cria linha nova nem em corrida entre
    dois pedidos — `ignore_conflicts` é o que aceita perder essa corrida, e
    perder é o comportamento CORRETO: significa que outro pedido já gravou.

    E grava em LOTE. Até 20/09/2026 era um `get_or_create` transacional POR
    DETECÇÃO, e o recorde detecta um par `(exercício, data)` por exercício:
    para o Carlos do demo (487 séries) `/conquistas/` fazia 252 consultas,
    159 repetidas — 75 × (BEGIN + SELECT + COMMIT) — e respondia em 1,1–1,2 s
    no Render enquanto toda outra tela ficava em 250–350 ms. O custo crescia
    com o histórico: quanto mais a pessoa treinava, mais lenta ficava a tela
    que celebra isso. Hoje são três consultas fixas para qualquer quantidade
    de detecções (`achievements/test_avaliar_em_lote.py`).
    """
    dados = reunir(user, hoje)
    detectadas = []
    for regra in CATALOGO:
        detectadas.extend((regra, chave, contexto) for chave, contexto in regra.detectar(dados))
    return _gravar_lote(user, detectadas)


def _gravar(user, regra, dados) -> list:
    """Roda UMA regra sobre dados já reunidos e grava o que for novo.

    Existe para `resumo` poder desbloquear só a regra que chegou a 100 % sem
    pagar o catálogo inteiro; é o mesmo lote de `avaliar`, com uma regra só.
    """
    return _gravar_lote(user, [(regra, chave, contexto) for chave, contexto in regra.detectar(dados)])


def _gravar_lote(user, detectadas) -> list:
    """Grava as detecções que ainda não existem, em três consultas fixas.

    1. o que a pessoa JÁ tem, entre os slugs detectados;
    2. um `INSERT` só, com `ignore_conflicts` para a corrida entre dois
       pedidos (a constraint decide, como antes);
    3. releitura do que acabou de nascer — `bulk_create` com
       `ignore_conflicts` não devolve `pk`, e `anunciar` guarda os ids na
       sessão.

    Sem detecção nova, as consultas 2 e 3 não acontecem.
    """
    if not detectadas:
        return []
    slugs = {regra.slug for regra, _, _ in detectadas}
    existentes = set(
        UserAchievement.objects.filter(user=user, slug__in=slugs).values_list("slug", "chave")
    )
    novas, vistas = [], set()
    for regra, chave, contexto in detectadas:
        par = (regra.slug, chave)
        if par in existentes or par in vistas:
            continue
        vistas.add(par)
        novas.append(UserAchievement(user=user, slug=regra.slug, chave=chave, contexto=contexto))
    if not novas:
        return []
    UserAchievement.objects.bulk_create(novas, ignore_conflicts=True)
    condicao = Q()
    for conquista in novas:
        condicao |= Q(slug=conquista.slug, chave=conquista.chave)
    nascidas = {
        (c.slug, c.chave): c
        for c in UserAchievement.objects.filter(condicao, user=user)
    }
    # Na ordem do catálogo, como o laço antigo devolvia. Uma diferença
    # escrita: se OUTRO pedido gravou o mesmo par entre a leitura e o INSERT
    # (a corrida que `ignore_conflicts` absorve), os dois pedidos anunciam a
    # mesma linha — o laço antigo calava o perdedor. A linha continua sendo
    # uma, e o aviso na sessão é o mesmo id duas vezes.
    return [nascidas[(c.slug, c.chave)] for c in novas if (c.slug, c.chave) in nascidas]


def resumo(user, hoje=None, request=None):
    """O que o bloco compacto do Progresso precisa saber.

    Devolve `(quantas, mais_recente, proxima)`:

      - `quantas` — conquistas ganhas, contando repetição;
      - `mais_recente` — o `UserAchievement` mais novo, ou `None`;
      - `proxima` — dict com `regra`, `atual`, `alvo` e `pct` da que está mais
        perto de fechar, ou `None` quando nada tem progresso mensurável.

    A REGRA NÃO É COPIADA DA VIEW: a tela de conquistas passou a chamar esta
    função. Duas cópias da mesma decisão divergem na primeira mudança, e aqui a
    decisão é delicada — "só entra em `próxima` o que dá para medir sem
    inventar", que é o que impede a parede de medalhas cinzentas.

    ESTA FUNÇÃO NÃO CHAMA `avaliar`, e isso é decisão medida.

    A primeira versão chamava, para o bloco do Progresso mostrar conquistas
    recém-fechadas. O custo apareceu no orçamento de consultas: a tela foi de
    ~12 para **50 consultas** com teto de 15, e o número CRESCIA com o
    histórico (36 contra 54). `avaliar` percorre o catálogo inteiro com
    `get_or_create` por regra, e `ScreenQueryBudgetTests` existe exatamente
    para pegar isso.

    E a decisão já estava escrita: o docstring de `ConquistasView` registra que
    "a avaliação continua FORA dos demais requests". Desbloquear é da página de
    conquistas, que a pessoa abre de vez em quando; o Progresso LÊ o que já
    está gravado.

    A consequência que essa decisão tinha, vista em produção em 16/09/2026
    (avaliação, B35): "Desbloqueadas 0" com a barra "Primeiro treino 1/1"
    CHEIA na mesma caixa. A função pintava 100 % de uma conquista que não
    existia — e "aparece depois que a pessoa abrir a página de conquistas"
    é exatamente o que ninguém que está olhando para a barra cheia faz.

    O QUE ELA FAZ EM VEZ DE `avaliar`: desbloqueia SÓ a regra que chegou a
    100 %, com os `dados` que já reuniu para medir o progresso. Custa duas
    consultas (o `get_or_create` de `_gravar`) UMA vez — na visita em que a
    condição fechou — e zero nas seguintes, porque a regra sai de
    `candidatas` assim que está em `conquistados`. O custo constante do
    Progresso continua sendo o de sempre (`plans.test_stress`); há teste
    comparando a visita seguinte com a de quem não tem nada a 100 %
    (`test_na_hora`). Com `request`, o que nasce é anunciado na mesma tela.
    """
    from .models import UserAchievement
    from .regras import CATALOGO

    ganhas = list(UserAchievement.objects.filter(user=user))
    conquistados = {c.slug for c in ganhas}

    dados = reunir(user, hoje=hoje)
    candidatas = a_caminho(dados, conquistados)
    novas = []
    while candidatas and candidatas[0]["pct"] >= 100:
        regra = candidatas[0]["regra"]
        nascidas = _gravar(user, regra, dados)
        if not nascidas:
            # `progresso` diz 100 % e `detectar` discorda (ou outro pedido
            # gravou antes): não insiste — e não pinta de novo em laço.
            break
        novas.extend(nascidas)
        ganhas.extend(nascidas)
        conquistados.add(regra.slug)
        candidatas = a_caminho(dados, conquistados)
    if request is not None and novas:
        anunciar(request, novas)

    mais_recente = max(ganhas, key=lambda c: c.pk) if ganhas else None
    return len(ganhas), mais_recente, (candidatas[0] if candidatas else None)


def a_caminho(dados, conquistados) -> list:
    """As conquistas que faltam e que DÁ para medir, da mais perto para a longe.

    A regra fica aqui, num lugar só, porque ela é a decisão delicada do
    sistema: **só entra o que tem progresso real**. Sem ela, a tela vira a
    parede de medalhas cinzentas — cem coisas que a pessoa não fez —, que é o
    oposto do que a ofensiva do NutriPlan faz, cujo texto inteiro foi escrito
    para não cobrar.

    A tela de conquistas mostra as quatro primeiras; o bloco do Progresso mostra
    uma. As duas leem esta lista, e não uma cópia da regra: duas cópias
    divergem na primeira mudança.
    """
    from .regras import CATALOGO

    candidatas = []
    for regra in CATALOGO:
        if regra.slug in conquistados:
            continue
        if not (regra.alvo and regra.progresso):
            continue
        atual = regra.progresso(dados)
        candidatas.append(
            {
                "regra": regra,
                "atual": atual,
                "alvo": regra.alvo,
                "pct": min(100, round(atual * 100 / regra.alvo)),
            }
        )
    # A mais perto primeiro: é a que a pessoa consegue fechar hoje.
    candidatas.sort(key=lambda item: -item["pct"])
    return candidatas


def anunciar(request, novas) -> list:
    """Guarda na sessao o que acabou de nascer, para a proxima tela mostrar.

    Devolve os ids porque o caminho `fetch` de registrar serie nao recarrega a
    pagina: ali quem monta o aviso e o JavaScript, com o que vier na resposta.
    """
    from .context_processors import CHAVE
    from analytics import servidor as analytics

    ids = [c.pk for c in novas]
    if ids:
        request.session[CHAVE] = ids
        request.session.modified = True
        # Ponto central de desbloqueio: todo caminho que ANUNCIA passa por
        # aqui (série, carga, Progresso). `slug` e não `titulo` — identidade
        # estável e de baixa cardinalidade para o painel agrupar.
        for c in novas:
            analytics.evento(request, "conquista.desbloqueada", {"nome": c.slug})
    return ids


def esquecer(request) -> None:
    from .context_processors import CHAVE

    if request.session.pop(CHAVE, None) is not None:
        request.session.modified = True


def nao_vistas(user):
    """As que ainda não foram mostradas — é o que abre a sobreposição."""
    return list(
        UserAchievement.objects.filter(user=user, seen_at__isnull=True).order_by(
            "unlocked_at", "id"
        )
    )


def marcar_vistas(user, ids):
    """Fecha o aviso. Recebe ids para não marcar como vista uma conquista que
    chegou entre a renderização e o toque da pessoa."""
    return UserAchievement.objects.filter(
        user=user, pk__in=list(ids), seen_at__isnull=True
    ).update(seen_at=timezone.now())


def duracao_observada(user, dia=None):
    """Minutos entre a PRIMEIRA e a ULTIMA serie registradas no dia, ou None.

    Existe porque `health_export.resumo_da_sessao` devolve duracao ESTIMADA —
    ela calcula a partir do numero de series e do descanso prescrito, que e o
    certo para exportar um TCX, e e errado para estampar num card como se
    fosse cronometro.

    Aqui a fonte e `ExerciseLog.created_at`, que e quando a pessoa de fato
    anotou. Com menos de duas anotacoes nao ha intervalo nenhum para medir, e
    entao o numero simplesmente NAO APARECE — um card sem duracao e melhor que
    um card com duracao inventada.

    Tambem devolve None quando o intervalo e absurdo (mais de seis horas):
    isso nao e um treino, e alguem que anotou a primeira serie de manha e a
    ultima a noite.
    """
    from workouts.models import ExerciseLog

    dia = dia or timezone.localdate()
    extremos = ExerciseLog.objects.filter(user=user, date=dia).aggregate(
        primeiro=Min("created_at"), ultimo=Max("created_at")
    )
    inicio, fim = extremos["primeiro"], extremos["ultimo"]
    if not inicio or not fim or inicio == fim:
        return None

    minutos = round((fim - inicio).total_seconds() / 60)
    if minutos < 1 or minutos > 360:
        return None
    return minutos
