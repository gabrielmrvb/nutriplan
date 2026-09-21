"""Quem é o dono de um evento — antes e depois do login.

- ANTES do login o evento é anônimo: só o `anon_id` (cookie) o liga aos outros
  toques do mesmo aparelho.
- NO LOGIN o `alias` costura: todo evento anônimo daquele `anon_id` passa a
  apontar para a pessoa, como o `alias` do Mixpanel. É o que faz o funil
  "abriu a landing (anônimo) → criou conta → treinou" ser de UMA pessoa.

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
    alias(request.COOKIES.get(COOKIE_ANON, ""), user)
