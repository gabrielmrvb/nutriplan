"""A sessão de quem usa o app não vence no meio do uso (22/09/2026).

O `SESSION_COOKIE_AGE` (14 dias) conta do LOGIN: quem entra todo dia era
deslogado a cada duas semanas, do nada — no meio da etapa 2 ou do registro
de uma corrida, e o formulário voltava vazio ("queda de sessão sem aviso",
item 2 da missão de UX). `SESSION_SAVE_EVERY_REQUEST` resolveria gravando a
sessão em TODA resposta: uma escrita a mais por tela, contra o orçamento
de consultas. Aqui a renovação acontece só quando a sessão passou da
METADE da vida — uma escrita por semana para quem usa; quem some por 14
dias continua saindo, como antes.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def marcar_vencimento_no_login(sender, request, user, **kwargs):
    """No login a data já entra na sessão — a mesma escrita que o login já
    faz, sem uma segunda na primeira tela. Ligado em `config.apps`."""
    sessao = getattr(request, "session", None)
    if sessao is not None and not sessao.get_expire_at_browser_close():
        sessao.set_expiry(timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE))


class RenovarSessaoMiddleware:
    """Depois de `SessionMiddleware`: lê quanto falta para a sessão vencer e,
    passada a metade da vida, marca a expiração de novo — `modified` faz o
    `SessionMiddleware` gravar e reemitir o cookie na resposta.

    A sessão só sabe quanto falta quando a expiração é uma DATA guardada
    nela (`set_expiry(datetime)`): sem isso `get_expiry_age()` devolve a
    idade cheia, sempre — a data real mora só na linha do banco, e lê-la
    seria uma consulta a mais por pedido. Então a primeira passagem de cada
    sessão grava a data (uma escrita), e as seguintes só comparam."""

    CHAVE = "_session_expiry"  # o mesmo que `set_expiry` grava

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        sessao = getattr(request, "session", None)
        if sessao is not None and sessao.session_key and not sessao.get_expire_at_browser_close():
            idade = settings.SESSION_COOKIE_AGE
            if sessao.get(self.CHAVE) is None:
                sessao.set_expiry(timezone.now() + timedelta(seconds=idade))
            else:
                try:
                    restante = sessao.get_expiry_age()
                except Exception:
                    restante = idade
                if restante < idade / 2:
                    sessao.set_expiry(timezone.now() + timedelta(seconds=idade))
        return self.get_response(request)
