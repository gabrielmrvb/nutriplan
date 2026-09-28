"""Pode ligar este evento à pessoa? E, desde 28/09/2026 (Lote 1 da missão
LGPD), pode gravar o evento de jeito nenhum?

Rastrear o USO agregado é legítimo por interesse legítimo (LGPD art. 7º, IX e
art. 10) — é analytics de primeira parte, sem terceiros, sem venda, para
melhorar o próprio produto. Duas perguntas diferentes, duas respostas:

- `pode_identificar`: o cabeçalho `DNT: 1` (Do-Not-Track) recusa só a
  IDENTIFICAÇÃO — o evento continua contando no agregado anônimo;
- `pode_registrar`: o opt-out do perfil (`Profile.rastrear_uso == False`,
  guardado na sessão) recusa o evento INTEIRO de quem está logado — nem
  anônimo. Antes o opt-out passava pelo mesmo caminho do DNT e a linha
  continuava gravando com `anon_id`; a decisão de 28/09 é que quem desligou
  o rastreio não quer NENHUM registro seu, nem sem nome.

O opt-out NÃO apaga o visitante anônimo: sem sessão autenticada (a landing,
por exemplo) o evento sempre conta — não há perfil para desligar."""


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


def pode_registrar(request):
    """Com o rastreio desligado no perfil, NADA é gravado — nem anônimo.
    DNT continua só anonimizando (decisão 2 do plano de 28/09/2026).

    Zero consulta: lê a sessão, nunca o perfil — a mesma régua de
    `pode_identificar`, para não pesar a rota mais quente do app."""
    user = getattr(request, "user", None)
    return not (
        user is not None
        and user.is_authenticated
        and request.session.get(CHAVE_SEM_RASTREIO)
    )


def marcar_sessao(request, rastrear_uso):
    """Escreve na sessão se a pessoa NÃO quer ser rastreada. Chamado no login e
    quando o opt-out do perfil muda — os dois pontos em que dá para pagar a
    leitura do perfil sem ser numa rota quente."""
    if rastrear_uso:
        request.session.pop(CHAVE_SEM_RASTREIO, None)
    else:
        request.session[CHAVE_SEM_RASTREIO] = True
