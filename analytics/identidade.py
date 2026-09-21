"""Quem é o dono de um evento — antes e depois do login, e no fim.

Três momentos:

- ANTES do login o evento é anônimo: só o `anon_id` (cookie) o liga aos outros
  toques do mesmo aparelho.
- NO LOGIN o `alias` costura: todo evento anônimo daquele `anon_id` passa a
  apontar para a pessoa, como o `alias` do Mixpanel. É o que faz o funil
  "abriu a landing (anônimo) → criou conta → treinou" ser de UMA pessoa.
- NA EXCLUSÃO da conta o `esquecer` apaga o rastro bruto da pessoa. Os
  agregados, que não guardam ninguém, ficam — a série histórica sobrevive sem
  PII. É a LGPD sem reescrever o passado inteiro.

Tudo por signal, para não depender de a exclusão/login passarem por uma view
específica: `User.delete()` de qualquer caminho (tela, admin, shell) dispara o
esquecimento.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import pre_delete
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


def esquecer(user):
    """Apaga o rastro bruto da pessoa. Devolve quantas linhas apagou."""
    from .models import Event

    apagadas, _ = Event.objects.filter(user=user).delete()
    return apagadas


@receiver(user_logged_in)
def _costura_no_login(sender, request, user, **kwargs):
    if request is None:
        return
    alias(request.COOKIES.get(COOKIE_ANON, ""), user)


@receiver(pre_delete, sender=get_user_model())
def _esquece_na_exclusao(sender, instance, **kwargs):
    esquecer(instance)
