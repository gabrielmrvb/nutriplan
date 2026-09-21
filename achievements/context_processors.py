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

E O AVISO É DADO POR VISTO NA TELA EM QUE APARECE (20/09/2026). A auditoria
da semana simulada viu o que acontece com quem nunca toca em "Continuar": o
aviso de "Primeiro treino" voltava em TODA página por dias, e na execução
cobria o campo Reps e o botão CONCLUIR SÉRIE — um aviso que "não interrompe"
virando obstáculo permanente. A conquista é anunciada onde nasce (a tela
seguinte ao POST que a desbloqueou) e ali mesmo é marcada como vista: o
"Continuar" e o Esc continuam fechando na hora, e a tela seguinte já não a
traz. Custa UM update na tela do anúncio — e as telas seguintes deixam de
pagar a consulta que o aviso eterno cobrava em cada uma.
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
    # Vista é vista: esta renderização É o anúncio. Marcar aqui (e não só no
    # "Continuar") é o que impede o aviso de acompanhar a pessoa página a
    # página até ela tocar num botão que pode estar atrás do teclado, do
    # convite de instalação ou da própria série.
    from .services import marcar_vistas

    if novas:
        marcar_vistas(user, [c.pk for c in novas])
    request.session.pop(CHAVE, None)
    request.session.modified = True
    return {"conquistas_novas": novas} if novas else {}
