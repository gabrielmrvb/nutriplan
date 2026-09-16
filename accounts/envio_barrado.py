# -*- coding: utf-8 -*-
"""O marcador de "toque não salvo" no redirecionamento para o login.

A tela de entrada tem uma frase para quem perdeu um toque — "Sua sessão
venceu. O que você tocou não foi salvo — entre e refaça" (UX E01). A primeira
versão usava a PRESENÇA de `?next=` como prova disso, e `next` é escrito em
todo GET anônimo a rota protegida: a raiz digitada, o ícone do PWA deslogado
(`start_url /`), qualquer link salvo. Medido em produção em 16/09/2026
(avaliação, B1): a primeira frase que um visitante novo lia era que a sessão
dele tinha vencido.

O sinal honesto é o MÉTODO do pedido barrado. Um POST que chegou anônimo e
virou 302 para o login é um envio perdido; um GET é só "entre para
continuar". Este middleware acrescenta `envio=1` ao `Location` no primeiro
caso, e o template lê só isso.

Mora num middleware, e não em cada `LoginRequiredMixin`, pela mesma razão da
`BarreiraDeReplayMiddleware`: cobertura. Dez módulos usam o mixin do Django e
`redirect_to_login` direto; uma rota nova entra marcada sozinha, sem depender
de alguém lembrar de trocar a classe-mãe.

Duas guardas, e as duas vieram de caso concreto:

- quem ANÔNIMO é medido ANTES da view. Depois de `logout()` o `request.user`
  já é anônimo, e o "Sair" redireciona para o login — marcar ali diria
  "sessão venceu" a quem acabou de sair de propósito;
- só quando o destino é a tela de login E carrega `next`. O login com senha
  errada devolve 200; o cadastro autentica e vai para o onboarding; a
  recuperação de senha vai para "enviado". Nenhum desses é toque perdido, e
  nenhum passa pelas duas condições.
"""
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from django.urls import reverse

#: O parâmetro que o template de login lê. Valor fixo: é um sinal, não um dado.
PARAMETRO = "envio"
REDIRECIONAMENTOS = {301, 302, 303, 307, 308}


def marcar_envio_barrado(location):
    """Devolve `location` com `envio=1` acrescentado — sem duplicar."""
    partes = urlsplit(location)
    consulta = parse_qs(partes.query, keep_blank_values=True)
    consulta[PARAMETRO] = ["1"]
    return urlunsplit(partes._replace(query=urlencode(consulta, doseq=True, safe="/:")))


def e_redirecionamento_para_o_login(location):
    partes = urlsplit(location)
    return partes.path == reverse("accounts:login") and "next" in parse_qs(partes.query)


class EnvioBarradoMiddleware:
    """Precisa vir DEPOIS de `AuthenticationMiddleware` (lê `request.user`)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        anonimo_antes = request.method == "POST" and not request.user.is_authenticated
        resposta = self.get_response(request)
        if (
            anonimo_antes
            and resposta.status_code in REDIRECIONAMENTOS
            and resposta.has_header("Location")
            and e_redirecionamento_para_o_login(resposta["Location"])
        ):
            resposta["Location"] = marcar_envio_barrado(resposta["Location"])
        return resposta
