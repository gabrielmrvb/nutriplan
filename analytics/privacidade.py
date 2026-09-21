"""Pode ligar este evento à pessoa?

Rastrear o USO agregado é legítimo por interesse legítimo (LGPD art. 7º, IX e
art. 10) — é analytics de primeira parte, sem terceiros, sem venda, para
melhorar o próprio produto. O que a pessoa pode recusar é ser IDENTIFICADA: o
evento continua contando no agregado anônimo, mas não vira linha do tempo dela.

Duas fontes de recusa:
- o cabeçalho `DNT: 1` (Do-Not-Track), que o navegador manda;
- (bloco 4) o opt-out no perfil, `Profile.rastrear_uso == False`.

Enquanto o campo do perfil não existe, só o DNT vale — e já vale.
"""


#: O opt-out do perfil vive na SESSÃO, não numa consulta: a rota da série é a
#: mais quente do app e não pode pagar um SELECT por evento. O flag é escrito no
#: login (`analytics/identidade`) e quando o perfil é salvo (`PrivacidadeView`).
CHAVE_SEM_RASTREIO = "np_sem_rastreio"


def pode_identificar(request):
    # Duas recusas, as duas SEM CONSULTA: o cabeçalho DNT e o opt-out do perfil
    # lido da sessão. Nenhuma toca o banco — é o que mantém o POST da série no
    # orçamento.
    if request.META.get("HTTP_DNT") == "1":
        return False
    if request.session.get(CHAVE_SEM_RASTREIO):
        return False
    return True


def marcar_sessao(request, rastrear_uso):
    """Escreve na sessão se a pessoa NÃO quer ser rastreada. Chamado no login e
    quando o opt-out do perfil muda — os dois pontos em que dá para pagar a
    leitura do perfil sem ser numa rota quente."""
    if rastrear_uso:
        request.session.pop(CHAVE_SEM_RASTREIO, None)
    else:
        request.session[CHAVE_SEM_RASTREIO] = True
