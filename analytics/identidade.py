"""Quem é o dono de um evento — antes e depois do login.

- ANTES do login o evento é anônimo: só o `anon_id` (cookie) o liga aos outros
  toques do mesmo aparelho.
- NO LOGIN o `alias` costura: todo evento anônimo daquele `anon_id` passa a
  apontar para a pessoa, como o `alias` do Mixpanel. É o que faz o funil
  "abriu a landing (anônimo) → criou conta → treinou" ser de UMA pessoa.
  [REVISAR I1, Lote 1, 28/09/2026] Quem já desligou o rastreio no perfil
  (ou manda `DNT: 1`) NÃO tem o alias aplicado: costurar o `anon_id` a essa
  pessoa identificaria retroativamente linhas que nasceram anônimas —
  exatamente o que `pode_registrar` existe para evitar dali para frente.
  Sem a guarda, o opt-out virava atribuição em vez de zero linha.

A EXCLUSÃO da conta não mora aqui: `Event.user` é `CASCADE`, então
`User.delete()` de qualquer caminho (tela, admin, shell) já apaga os eventos
identificados da pessoa. Os agregados, que não guardam ninguém, ficam. LGPD
resolvida pelo banco, sem um signal que poderia esquecer de rodar.

O alias é o único que precisa de signal: ele lê um cookie do request, e o banco
não tem como costurar sozinho.
"""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

COOKIE_ANON = "np_aid"


def alias(anon_id, user):
    """Liga o histórico anônimo daquele aparelho à pessoa.

    Só toca no que ainda é anônimo (`user__isnull=True`): eventos já de outra
    pessoa no mesmo aparelho ficam onde estão — o alias costura, não rouba.
    Devolve quantas linhas costurou (para teste e para o log).
    """
    if not anon_id:
        return 0
    from .models import Event

    return Event.objects.filter(anon_id=anon_id, user__isnull=True).update(user=user)


@receiver(user_logged_in)
def _costura_no_login(sender, request, user, **kwargs):
    if request is None:
        return
    # O login é um bom lugar para pagar a leitura do opt-out UMA vez — aqui
    # ela decide DUAS coisas: se o alias corre (abaixo) e o que fica na
    # sessão para `pode_identificar`/`pode_registrar` lerem de graça depois,
    # inclusive na rota da série. Sem perfil ainda (onboarding), o padrão é
    # rastrear.
    try:
        rastrear = user.profile.rastrear_uso
    except Exception:
        rastrear = True
    dnt = request.META.get("HTTP_DNT") == "1"
    # [REVISAR I1, Lote 1, 28/09/2026] quem desligou o rastreio, ou manda
    # DNT, não tem o histórico anônimo costurado a si: sem a guarda, o
    # login identificava retroativamente linhas que nasceram anônimas —
    # o oposto de "zero linha sobre a pessoa" que o opt-out promete.
    if rastrear and not dnt:
        alias(request.COOKIES.get(COOKIE_ANON, ""), user)
    # Um login de verdade sempre tem sessão; um sinal disparado à mão (teste,
    # shell) pode não ter, e o opt-out não vale o suficiente para exigir uma.
    if hasattr(request, "session"):
        from .privacidade import marcar_sessao

        marcar_sessao(request, rastrear)
