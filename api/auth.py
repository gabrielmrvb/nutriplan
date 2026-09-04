# -*- coding: utf-8 -*-
"""Como a API sabe quem está falando — e por que ela ignora a sessão.

A regra é uma só: **a API autentica SÓ pelo cabeçalho `Authorization: Bearer`,
e nunca pelo cookie de sessão.**

Isso não é preferência. É o que torna `csrf_exempt` correto em vez de perigoso.
CSRF existe porque o navegador ANEXA o cookie sozinho em qualquer requisição
que uma página de terceiro dispare; a proteção compara um token que só a
própria página conhece. Um endpoint que não olha cookie nenhum não tem o que
ser forjado: o atacante precisaria do `Bearer`, e o navegador não o envia
sozinho.

O contrário — deixar a sessão valer "por conveniência" e marcar
`csrf_exempt` — seria abrir CSRF de verdade em todas as rotas da API. Há teste
exigindo que sessão válida NÃO autentique aqui, e sabotagem provando que ele
morde.

O web não muda. Sessão, cookie e CSRF continuam exatamente como estavam.
"""
import json
from functools import wraps

from django.http import JsonResponse

from accounts.models import TokenDeApp


def responder(dados, status=200):
    """Toda resposta da API sai por aqui.

    `json_dumps_params` com `ensure_ascii=False` porque o app é pt-BR e o
    cliente lê UTF-8: escapar acento vira ruído no aparelho.
    """
    return JsonResponse(dados, status=status, json_dumps_params={"ensure_ascii": False})


def erro(mensagem, status):
    """Um formato só para toda falha. O cliente trata `erro`, e nada mais.

    A mensagem descreve o que o CLIENTE fez, nunca o que o servidor tem
    dentro: nome de campo do model, exceção e caminho de arquivo ficam de fora.
    """
    return responder({"erro": mensagem}, status=status)


def corpo_json(request):
    """`(dados, None)` ou `(None, resposta_de_erro)`.

    O limite de tamanho é a primeira linha de defesa: uma corrida de duas horas
    a uma leitura por segundo são ~7.200 pontos, e isso cabe folgado em 1 MB.
    Acima disso não é corrida — é alguém tentando gastar memória do servidor.
    """
    LIMITE_BYTES = 1024 * 1024

    if len(request.body) > LIMITE_BYTES:
        return None, erro("corpo grande demais", 413)
    try:
        dados = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None, erro("corpo inválido: esperado JSON", 400)
    if not isinstance(dados, dict):
        return None, erro("corpo inválido: esperado um objeto", 400)
    return dados, None


def usuario_do_pedido(request):
    """A pessoa dona do `Bearer`, ou `None`. A sessão não é consultada."""
    cabecalho = request.headers.get("Authorization", "")
    if not cabecalho.startswith("Bearer "):
        return None
    return TokenDeApp.autenticar(cabecalho[len("Bearer "):].strip())


def exige_token(view):
    """Só passa quem tem token vivo.

    Põe a pessoa em `request.dono` — nome próprio de propósito, para nunca ser
    confundido com `request.user`, que é da sessão e não vale aqui.
    """

    @wraps(view)
    def protegida(request, *args, **kwargs):
        dono = usuario_do_pedido(request)
        if dono is None:
            return erro("é preciso um token válido", 401)
        request.dono = dono
        return view(request, *args, **kwargs)

    return protegida
