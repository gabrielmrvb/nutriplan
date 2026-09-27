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

O GET NÃO MARCA MAIS COMO VISTA (decisão do dono, 27/09/2026, revisão do PR
#162). A renderização LÊ: mostra as conquistas da sessão que ainda estão sem
`seen_at`, e não toca nem no banco nem na sessão. Quem marca é um POST — o
mesmo `achievements:marcar_vistas` do "Continuar" —, que `conquista.js` manda
quando o aviso está VISÍVEL de verdade (`visibilityState` e não
`document.prerendering`). A razão: um prefetch, uma pré-renderização ou um
"abrir em nova aba" RENDERIZA a página sem a pessoa ver, e quando o "visto"
morava aqui ele consumia o anúncio — ela nunca via "Conquista desbloqueada"
na aba em que estava. `config/test_get_nao_grava.py` é a régua.

O que a decisão de 20/09, abaixo, resolvia continua resolvido pelo POST: o
aviso é dado por visto na tela em que aparece, só que por quem a VIU.

A DECISÃO DE 20/09/2026 (o aviso dado por visto na tela em que aparece). A auditoria
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

    # SÓ LEITURA. As que ainda não foram vistas: depois do POST de "visto"
    # (o `fetch` de `conquista.js`, ou o "Continuar"), elas saem daqui mesmo
    # que a sessão ainda as liste — e a sessão é limpa pelo próprio POST
    # (`services.esquecer`). Nada nesta função escreve.
    novas = list(
        UserAchievement.objects.filter(
            user=user, pk__in=ids[:5], seen_at__isnull=True
        ).order_by("unlocked_at", "pk")
    )
    return {"conquistas_novas": novas} if novas else {}
