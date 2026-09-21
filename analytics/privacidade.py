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
    if request.META.get("HTTP_DNT") == "1":
        return False
    user = getattr(request, "user", None)
    perfil = _perfil(user)
    if perfil is not None and getattr(perfil, "rastrear_uso", True) is False:
        return False
    return True


def _perfil(user):
    """O perfil pode não existir ainda (durante o onboarding). O acesso reverso
    a um OneToOne ausente LEVANTA (não devolve None), então isolamos aqui."""
    if user is None:
        return None
    try:
        return user.profile
    except Exception:
        return None
