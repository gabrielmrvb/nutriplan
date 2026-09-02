"""Replay da fila offline: o que o servidor aceita, recusa e preserva.

Este módulo foi REESCRITO depois de medir o comportamento real. A primeira
versão recusava todo replay sem dono, o que quebrava a sincronização de todo
cliente já publicado — cinco testes pré-existentes reprovaram, e estavam certos.

## O que a medição mostrou

O item enfileirado carrega o `csrfmiddlewaretoken` do formulário, porque a fila
copia o `FormData` inteiro. `login()` chama `rotate_token`, e
`CsrfViewMiddleware` roda ANTES da autenticação e da view.

Medido com `enforce_csrf_checks=True`, emulando o cliente publicado:

    A -> B com token velho .... 403, view não executou, nada gravado
    A -> A com token velho .... 403, view não executou, nada gravado
    A -> anônimo .............. 403, sem redirect
    A -> A com token atual .... 200, gravou

Ou seja: NÃO está provado que uma operação de A já tenha sido gravada na conta
de B. O que existia era um caminho de replay cross-account inseguro na camada
cliente — a fila selecionava um item de A e o enviava com a sessão ativa do
navegador —, e o CSRF barrava o efeito.

O bug comprovado é outro: o `drenar()` publicado apaga o item em QUALQUER 4xx.
Os três 403 acima destroem a marcação que a pessoa fez sem rede. Inclusive no
caso em que ela apenas saiu e voltou.

## O contrato

Replay é reconhecido por `op_id` no corpo — o interceptor da fila sai cedo
quando há rede, então POST online nunca o carrega.

    sem op_id ................... POST normal da tela, segue o fluxo
    op_id sem dono .............. protocolo legado: segue o fluxo normal,
                                  protegido por CSRF e sessão como sempre foi
    op_id com dono igual ........ protocolo novo: segue o fluxo
    op_id com dono diferente .... recusa que PRESERVA
    op_id sem sessão ............ recusa que PRESERVA
    op_id com CSRF velho ........ recusa que PRESERVA (ver `config/csrf.py`)

O destino é SEMPRE `request.user`. O dono que chega no pedido é pré-condição —
"esta operação foi criada esperando a sessão de fulano" — e nunca um endereço.
Buscar o usuário pelo dono e gravar nele seria deixar o cliente escolher a
conta.

`op_id` reconhece o protocolo. Não autentica, não autoriza, não escolhe conta e
não dispensa CSRF.
"""
import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)

#: Presença = replay. Só a fila e o worker enviam.
CABECALHO_REPLAY = "X-NutriPlan-Replay"

#: Dono esperado, em texto, como o `dataset` do navegador entrega.
CABECALHO_DONO = "X-NutriPlan-Dono"

#: O marcador que a versão JÁ PUBLICADA envia. É ele que permite reconhecer um
#: replay legado, que não conhece os cabeçalhos acima.
CAMPO_DA_FILA = "op_id"

#: 503, e a escolha foi medida e não estética.
#:
#: O `drenar()` publicado remove o item em QUALQUER 4xx — "reenviar não conserta
#: conteúdo recusado". Recusar com 4xx apagaria a água que a pessoa marcou sem
#: rede, que é justamente o dado que esta barreira existe para proteger. Em 5xx
#: ele preserva e tenta depois.
#:
#: Semanticamente 409 seria mais preciso. Escolher o status certo e perder o
#: dado é escolher errado.
STATUS_PRESERVA = 503

#: Redirecionamentos que uma view de escrita devolve no fluxo normal (PRG).
REDIRECIONAMENTOS = (301, 302, 303, 307, 308)

CODIGO_PROCESSADO = "replay_processado"
CODIGO_OUTRA_SESSAO = "replay_offline_de_outra_sessao"
CODIGO_SEM_SESSAO = "replay_offline_sem_sessao"
CODIGO_CSRF_VELHO = "replay_offline_csrf_expirado"


def e_replay(request) -> bool:
    """Este POST veio da fila offline?

    Duas evidências, e a segunda é a que reconhece o cliente publicado: o
    cabeçalho novo, ou `op_id` no corpo.
    """
    if request.headers.get(CABECALHO_REPLAY):
        return True
    if request.method != "POST":
        return False
    try:
        return bool((request.POST.get(CAMPO_DA_FILA) or "").strip())
    except Exception:
        # Corpo ilegível não é replay; quem trata isso é a view.
        return False


def resposta_que_preserva(codigo):
    """A recusa que nem o cliente novo nem o publicado interpretam como fim.

    Não é erro de servidor. É condição conhecida: a operação não pode ser
    aplicada agora, e a resposta diz isso de um jeito que ninguém a descarte.
    """
    resposta = JsonResponse(
        {
            "code": codigo,
            "detail": "Operacao offline preservada: nao pertence a sessao atual.",
        },
        status=STATUS_PRESERVA,
    )
    # `django.request` loga QUALQUER 5xx como ERROR "Service Unavailable". Isto
    # aqui não é erro de servidor: é uma condição esperada, e em produção cada
    # replay preservado viraria uma linha de erro. O custo não é estética — é
    # que o 5xx de VERDADE fica escondido no meio delas.
    #
    # `_has_been_logged` é o mesmo atributo que o próprio Django marca depois de
    # logar, justamente para não logar duas vezes. Marcar antes suprime a linha.
    resposta._has_been_logged = True
    # Fica o registro, no nível certo, e sem caminho: `/refeicao/<id>/marcar/`
    # carrega o id do slot, e log de rotina não precisa dele.
    logger.info("replay offline preservado: %s", codigo)
    return resposta


def resposta_de_sucesso():
    """O 302 do PRG traduzido para algo que um `fetch` consegue ler.

    Medido: `/agua/` responde 302 quando a escrita DA CERTO — é o padrão
    post/redirect/get. O cliente novo manda `redirect: "manual"`, para que um
    302 para o login não seja seguido até uma página 200 que ele leria como
    sucesso. Só que aí o 302 de SUCESSO chega como `opaqueredirect`, sem status
    e sem destino, indistinguível do outro — e o item ficava na fila para
    sempre, reenviado a cada carregamento.

    Traduzir aqui resolve os dois de uma vez: quem chegou até a view estava
    autenticado (a barreira responde antes, sem sessão), então um redirect
    daqui significa que a operação foi processada.

    Só para o protocolo NOVO. O cliente publicado segue redirect e sempre
    funcionou assim; mexer nele seria mudar o que não está quebrado.

    O código é "processado" e não "aplicado", e a diferença é honestidade: a
    view também redireciona quando RECUSA o conteúdo — `/agua/` só aceita 250,
    500 e 750, e um valor fora disso vira `messages.error` mais redirect. Sair
    da fila é a ação certa nos dois casos (reenviar não conserta um valor
    recusado), mas dizer "aplicado" quando o servidor recusou seria mentir no
    corpo da resposta.
    """
    return JsonResponse({"code": CODIGO_PROCESSADO}, status=200)


def recusa_de_identidade(request):
    """Devolve a recusa quando o replay não pode ser aplicado, ou `None`.

    Roda ANTES de qualquer mutação e antes da marcação idempotente: marcar a
    operação como aplicada e recusar depois deixaria a conta certa sem
    conseguir reenviar — o servidor lembraria de um `op_id` que nunca foi
    aplicado.
    """
    if not e_replay(request):
        return None

    if not request.user.is_authenticated:
        # Sem isto, `login_required` responde 302 e o cliente publicado segue
        # até a página de login, que devolve 200 — e a regra dele leria isso
        # como sucesso e apagaria a operação.
        return resposta_que_preserva(CODIGO_SEM_SESSAO)

    esperado = (request.headers.get(CABECALHO_DONO) or "").strip()

    if not esperado:
        # Protocolo LEGADO. Não recusar: o cliente publicado não conhece o
        # cabeçalho, e recusá-lo quebraria a sincronização de quem ainda não
        # recarregou a página. A proteção dele continua sendo a que sempre foi
        # — CSRF e sessão —, e a medição mostrou que ela funciona.
        #
        # E não inventar dono aqui: aceitar o transporte legado não é adotar a
        # propriedade do item.
        return None

    if esperado != str(request.user.pk):
        return resposta_que_preserva(CODIGO_OUTRA_SESSAO)

    return None
