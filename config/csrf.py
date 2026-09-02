"""O que acontece quando o CSRF recusa um replay da fila offline.

A ordem real, medida e não deduzida: `CsrfViewMiddleware` valida em
`process_view`, que só roda DEPOIS da fase de request de todos os middlewares.
Então a barreira de identidade fala primeiro, e o CSRF só decide o que ela
deixou passar — na prática, o cliente publicado, que não declara dono.

Eu tinha documentado o contrário. O teste que nomeia a camada corrigiu a
suposição: com dono alheio E token velho, quem responde é a barreira.

O problema não é a recusa: ela está certa, e continua. O problema é o STATUS.
O `drenar()` publicado apaga o item em qualquer 4xx, e o 403 padrão destrói a
água que a pessoa marcou sem rede.

Medido com a stack real: depois de qualquer login o token guardado no item fica
velho, porque `login()` chama `rotate_token`. Isso acontece também quando quem
volta é a MESMA pessoa — e ali não há vazamento nenhum envolvido, só perda.

Isto NÃO é bypass de CSRF. A view não executa, nada é mutado, e o pedido
continua recusado. Só a forma de dizer muda, para o cliente não jogar fora o
que ainda pode ser sincronizado.
"""
from django.middleware.csrf import CsrfViewMiddleware
from django.views.csrf import csrf_failure as csrf_failure_padrao

from accounts.replay import CODIGO_CSRF_VELHO, e_replay, resposta_que_preserva


def falha_de_csrf(request, reason="", template_name=None):
    """Recusa por CSRF, com resposta preservável quando é replay offline."""
    if e_replay(request):
        return resposta_que_preserva(CODIGO_CSRF_VELHO)
    # Qualquer outro POST continua vendo o 403 de sempre.
    if template_name is None:
        return csrf_failure_padrao(request, reason=reason)
    return csrf_failure_padrao(request, reason=reason, template_name=template_name)


class BarreiraDeReplayMiddleware:
    """A identidade do replay, checada antes de qualquer view.

    Mora aqui e não nas views por dois motivos.

    O primeiro é cobertura: uma rota nova que a fila passe a enfileirar entra
    protegida sozinha, sem depender de alguém lembrar de acrescentar a chamada
    — e sem um teste de completude para vigiar esse esquecimento.

    O segundo é ORDEM. O caso anônimo precisa ser respondido antes do
    `LoginRequiredMixin`: ele devolve 302 para o login, o cliente publicado
    segue o redirect, a tela de login responde 200, e a regra dele lê isso como
    sucesso e apaga a operação. Uma checagem dentro do `post()` da view chegaria
    tarde demais.

    Precisa vir DEPOIS de `AuthenticationMiddleware`, que é quem põe
    `request.user` no pedido.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Ler `request.POST` obrigaria o Django a consumir o corpo em TODO
        # pedido, inclusive nos que chegam em JSON e são lidos por
        # `request.body` na view. Então a detecção é em dois degraus:
        #
        #   1. o CABEÇALHO de replay, que não custa nada e não toca no corpo;
        #   2. só se ele não vier, e só para corpo de FORMULÁRIO, procurar
        #      `op_id` — que é como o cliente publicado se identifica.
        #
        # A primeira versão desta guarda exigia `x-www-form-urlencoded` antes
        # de qualquer coisa, e com isso nem o cabeçalho era lido: um POST
        # `multipart` com `op_id` passava direto pela barreira.
        #
        # Honestidade sobre o alcance disto, medida numa sabotagem que NAO foi
        # detectada: o Django ja nao consome o corpo de um pedido JSON quando
        # `request.POST` e lido — `_load_post_and_files` devolve um QueryDict
        # vazio sem tocar no stream. Entao esta guarda e defesa em
        # profundidade, e tira-la nao quebra o endpoint de corrida.
        #
        # O que ela CRIA, e vale saber: com `multipart` na lista, um endpoint
        # futuro que aceite multipart e leia `request.body` receberia o corpo
        # ja consumido aqui. Nenhum existe hoje. Se algum nascer, e este
        # comentario que precisa ser lido antes.
        if request.method != "POST":
            return self.get_response(request)

        from accounts.replay import CABECALHO_REPLAY, recusa_de_identidade

        tipo = request.META.get("CONTENT_TYPE", "")
        e_formulario = tipo.startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")
        )
        if request.headers.get(CABECALHO_REPLAY) or e_formulario:
            recusa = recusa_de_identidade(request)
            if recusa is not None:
                return recusa

        resposta = self.get_response(request)

        # Só o protocolo NOVO. Ver `resposta_de_sucesso`.
        if request.headers.get(CABECALHO_REPLAY):
            from accounts.replay import REDIRECIONAMENTOS, resposta_de_sucesso

            if resposta.status_code in REDIRECIONAMENTOS:
                return resposta_de_sucesso()

        return resposta
