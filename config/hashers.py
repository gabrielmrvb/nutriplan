# -*- coding: utf-8 -*-
"""PROTÓTIPO (auditoria 20/09/2026, upgrade 5): a senha custa 3 s no login.

Medido em produção naquele dia: login CERTO 3,0–3,2 s de TTFB, senha errada
4,4–5,6 s (dois backends, dois hashes), cadastro 3,7 s. A causa é o padrão do
Django 5.2 — PBKDF2-SHA256 com 1 000 000 iterações — na CPU do Render free:
0,56 s nesta máquina, ≈ 3 s lá.

Duas saídas, nesta ordem de preferência:

1. **Argon2id**, o que o Django recomenda: ≈ 0,05 s e resistente a GPU. Pede
   `argon2-cffi` (extensão nativa: instala no Render; nesta máquina o Smart
   App Control pode bloquear o `.pyd`, e por isso `settings.py` só o lista
   quando o `import argon2` funciona — o teste local nunca depende dele).
2. **PBKDF2 com 600 000 iterações** — o mínimo que a OWASP recomenda para
   SHA-256 (2023) e 40 % mais barato que 1 000 000. Mesmo `algorithm`, então
   toda senha gravada continua conferindo, e o Django a regrava no próximo
   login (`must_update`), sem migration e sem pedir nada a ninguém.

Nenhum dos dois muda a força da senha exigida (validadores continuam).
"""
from django.contrib.auth.hashers import PBKDF2PasswordHasher


class PBKDF2SHA256Rapido(PBKDF2PasswordHasher):
    """PBKDF2-SHA256 a 600 000 iterações (OWASP 2023), no lugar do 1 000 000."""

    iterations = 600_000


def argon2_disponivel() -> bool:
    try:
        import argon2  # noqa: F401
    except Exception:  # ImportError, e o OSError do Smart App Control no .pyd
        return False
    return True
