"""Emissão de evento do LADO DO SERVIDOR, no ponto exato da ação.

Por que servidor e não `npTrack` no clique, para os eventos de NEGÓCIO: água,
série concluída e refeição podem chegar pela FILA OFFLINE, que drena no servidor
sem passar pela tela. Um evento de clique perderia todos esses. Emitir no
handler que APLICA a ação pega o online e o offline pelo mesmo ponto.

Custo: um INSERT por ação — não bloqueia a tela mais do que a ação já custa.

Nome fora do catálogo não explode em produção (silêncio seguro); quem pega o
erro é `analytics/test_taxonomia.py`, que varre o código.
Analytics NUNCA derruba a ação do usuário: cada gravação é embrulhada, e uma
falha (banco fora, coluna cheia) vira uma linha de log, não um 500 na cara de
quem só queria marcar o almoço. Registrar o uso é secundário à ação.
"""
import logging
import os

from .catalogo import existe
from .identidade import COOKIE_ANON
from .privacidade import pode_identificar

logger = logging.getLogger("nutriplan.analytics")


def _commit():
    return os.environ.get("RENDER_GIT_COMMIT", "")[:7]


def _gravar(request, nome, props, user):
    from .models import Event

    if not existe(nome):
        return None
    try:
        return Event.objects.create(
            name=nome,
            props=props or {},
            user=user,
            anon_id=request.COOKIES.get(COOKIE_ANON, ""),
            route=request.path[:200],
            app_version=_commit(),
        )
    except Exception:
        # Uso é secundário à ação: um evento perdido é barato; um 500 no meio
        # de marcar a refeição, não.
        logger.warning("evento de analytics não gravado: %s", nome, exc_info=True)
        return None


def evento(request, nome, props=None):
    """Grava um evento atribuído à pessoa (quando logada e sem opt-out)."""
    user = None
    if request.user.is_authenticated and pode_identificar(request):
        user = request.user
    return _gravar(request, nome, props, user)


def evento_anonimo(request, nome, props=None):
    """Como `evento`, mas nunca atribui usuário.

    É o que `conta.excluida` precisa: se ela fosse identificada, o CASCADE que a
    própria exclusão dispara a apagaria junto — o evento sumiria no mesmo
    instante em que nasce. Anônima, ela sobrevive como contagem agregada de
    'quantas contas foram excluídas'.
    """
    return _gravar(request, nome, None if props is None else props, None)
