"""Leva as conquistas recem-desbloqueadas para a proxima tela renderizada.

CUSTA ZERO CONSULTA no caso comum, e isso e o requisito e nao um detalhe: este
processador roda em TODO request autenticado do NutriPlan, e uma consulta a
mais por request para descobrir que nao ha nada novo seria um imposto cobrado
o dia inteiro para um evento que acontece algumas vezes por semana.

Por isso o gatilho e a SESSAO. Quem desbloqueia escreve os ids em
`request.session`; aqui so se toca no banco quando ha id para buscar. Sessao e
tambem o que faz o aviso sobreviver ao redirecionamento do POST de registrar
serie — e o que o impede de voltar no refresh, porque `marcar_vistas` limpa a
chave junto.
"""
CHAVE = "conquistas_novas"


def conquistas_pendentes(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    # O modo demo troca `request.user` por um usuario ficticio e nao aceita
    # POST: comemorar ali seria comemorar dado inventado.
    if getattr(request, "demo", False):
        return {}

    ids = (request.session or {}).get(CHAVE) or []
    if not ids:
        return {}

    # Import tardio: este modulo e carregado na montagem dos templates.
    from .models import UserAchievement

    novas = list(
        UserAchievement.objects.filter(user=user, pk__in=ids[:5]).order_by(
            "unlocked_at", "pk"
        )
    )
    return {"conquistas_novas": novas} if novas else {}
