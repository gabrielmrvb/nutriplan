# -*- coding: utf-8 -*-
"""A senha custava 3 s no login (auditoria de 20/09/2026, upgrade 5).

Medido em produção naquele dia: login CERTO 3,0–3,2 s de TTFB, senha errada
4,4–5,6 s (dois backends, dois hashes), cadastro 3,7 s. A causa é o padrão do
Django 5.2 — PBKDF2-SHA256 com 1 000 000 iterações — na CPU do Render free:
0,56 s nesta máquina, ≈ 3 s lá.

Duas saídas, nesta ordem de preferência:

1. **Argon2id**, o que o Django recomenda: ≈ 0,05–0,15 s e resistente a
   GPU. `argon2-cffi` está em `requirements.txt`; `settings.py` só o lista
   quando o `import argon2` funciona (extensão nativa — numa máquina com o
   Smart App Control ligado o `.pyd` não carrega, e a suíte não pode depender
   dele), senão cai no item 2.
2. **PBKDF2 com 600 000 iterações** — o mínimo que a OWASP recomenda para
   SHA-256 (2023) e 40 % mais barato que 1 000 000. Mesmo `algorithm`, então
   toda senha gravada continua conferindo, e o Django a regrava no próximo
   login (`must_update`), sem migration e sem pedir nada a ninguém.

Nenhum dos dois muda a força da senha exigida (validadores continuam).

E os PARÂMETROS do Argon2 são desta máquina de produção, não os do Django
(21/09/2026). Provado em produção em 887520f com os padrões (m=100 MiB,
t=2, p=8): login certo 2,0–2,6 s, dos quais ~1,7 s são o hash — um GET da
mesma tela custa 0,30 s. O CPU do Render free não tem os 8 fios que o p=8
pede nem banda de memória para 100 MiB por login. `Argon2Moderado` fica em
m=32 MiB, t=2, p=1 — acima do mínimo que a OWASP aceita (m=19 MiB, t=2,
p=1), decisão do dono. Os parâmetros viajam no próprio hash, então toda
senha gravada com os padrões continua conferindo e é regravada no login
seguinte (`must_update` compara parâmetros).
"""
from django.contrib.auth.hashers import Argon2PasswordHasher, PBKDF2PasswordHasher


class Argon2Moderado(Argon2PasswordHasher):
    """Argon2id com m=32 MiB, t=2, p=1 — o custo que o Render free paga em
    tempo razoável. Mesmo `algorithm` ("argon2") do hasher do Django: é ele
    que identifica todo hash `argon2$…` e decide a regravação."""

    memory_cost = 32 * 1024  # KiB
    time_cost = 2
    parallelism = 1


class PBKDF2SHA256Rapido(PBKDF2PasswordHasher):
    """PBKDF2-SHA256 a 600 000 iterações (OWASP 2023), no lugar do 1 000 000."""

    iterations = 600_000


def argon2_disponivel() -> bool:
    try:
        import argon2  # noqa: F401
    except Exception:  # ImportError, e o OSError do Smart App Control no .pyd
        return False
    return True
