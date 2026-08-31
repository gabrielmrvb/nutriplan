"""Detectar e gravar conquistas.

QUANDO ISTO RODA. No caminho de ESCRITA — registrar série, marcar refeição,
somar água —, e nunca num agendador, porque o projeto não tem um: cron no Render
é recurso pago, e foi por isso que os lembretes de refeição ficaram desligados.
Rodar na escrita também é o que mantém a conquista honesta no tempo: ela nasce
no instante em que a pessoa fez a coisa.

As três escritas estão na lista porque as três podem FECHAR o dia da ofensiva.
Só o registro de série seria suficiente para as conquistas de treino, e deixaria
"7 dias de ofensiva" desbloqueando com um dia de atraso para quem termina o dia
bebendo água.

POR QUE NÃO RODA NA LEITURA. Um GET que grava é um GET que grava — e o painel é
a tela mais aberta do app. `avaliar` é idempotente e sobreviveria a isso, mas o
custo apareceria em toda visita para um ganho que a escrita já entrega.
"""
from dataclasses import replace
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, Min
from django.utils import timezone

from accounts.models import TrainingDay
from plans import streaks
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

    dados = Dados(
        hoje=hoje,
        dias_treinados=len(datas),
        previstos=previstos,
        # `hoje` viaja junto: sem isso a ofensiva leria o calendário real
        # enquanto o resto do cálculo usa a data recebida, e o teste que
        # controla a data mediria duas coisas diferentes ao mesmo tempo.
        ofensiva=streaks.calcular(user, hoje=hoje).dias,
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
    de_hoje = list(
        ExerciseLog.objects.filter(user=user, date=hoje, weight_kg__isnull=False)
        .values("exercise_id", "exercise__name")
        .annotate(maior=Max("weight_kg"))
    )
    if de_hoje:
        anteriores = {
            linha["exercise_id"]: linha["maior"]
            for linha in ExerciseLog.objects.filter(
                user=user,
                date__lt=hoje,
                weight_kg__isnull=False,
                exercise_id__in=[l["exercise_id"] for l in de_hoje],
            )
            .values("exercise_id")
            .annotate(maior=Max("weight_kg"))
        }
        # `anteriores.get(...)` sem valor significa estreia, e estreia não é
        # recorde — ver o contrato em `regras._recorde`.
        dados = replace(
            dados,
            recordes_hoje=tuple(
                (linha["exercise_id"], linha["exercise__name"])
                for linha in de_hoje
                if linha["exercise_id"] in anteriores
                and linha["maior"] > anteriores[linha["exercise_id"]]
            ),
        )

    return dados


def avaliar(user, hoje=None) -> list:
    """Roda o catálogo e grava o que for novo. Devolve só o que nasceu agora.

    Idempotente por construção: a unicidade `(user, slug, chave)` está no
    banco, então repetir a mesma ação não cria linha nova nem em corrida entre
    dois pedidos. O `IntegrityError` é capturado porque `get_or_create` pode
    perder a corrida entre o SELECT e o INSERT — e perder essa corrida é o
    comportamento CORRETO: significa que outro pedido já gravou.
    """
    dados = reunir(user, hoje)
    novas = []
    for regra in CATALOGO:
        for chave, contexto in regra.detectar(dados):
            try:
                with transaction.atomic():
                    conquista, criada = UserAchievement.objects.get_or_create(
                        user=user,
                        slug=regra.slug,
                        chave=chave,
                        defaults={"contexto": contexto},
                    )
            except IntegrityError:
                continue
            if criada:
                novas.append(conquista)
    return novas


def anunciar(request, novas) -> list:
    """Guarda na sessao o que acabou de nascer, para a proxima tela mostrar.

    Devolve os ids porque o caminho `fetch` de registrar serie nao recarrega a
    pagina: ali quem monta o aviso e o JavaScript, com o que vier na resposta.
    """
    from .context_processors import CHAVE

    ids = [c.pk for c in novas]
    if ids:
        request.session[CHAVE] = ids
        request.session.modified = True
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
