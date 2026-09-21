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


def pode_identificar(request):
    # DNT é a única recusa que se checa SEM CONSULTA — e é a que a rota mais
    # quente do app (concluir série) pode pagar. O opt-out do perfil (bloco 4)
    # entra por um caminho sem consulta (a sessão), justamente para não
    # acrescentar uma consulta ao POST da série. Ler `user.profile` aqui
    # custava uma consulta por evento, em toda ação — dead cost enquanto o
    # campo nem existe.
    if request.META.get("HTTP_DNT") == "1":
        return False
    return True
