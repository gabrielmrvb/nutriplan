# -*- coding: utf-8 -*-
"""Imprime um `sessionid` para o `nav.py cookie` — login de QA sem senha.

    .venv/Scripts/python.exe scripts/qa/sessao.py joao@demo.local

Cria uma sessão do Django para a pessoa e escreve a chave. A sessão vale o
`SESSION_COOKIE_AGE` do settings; nada mais é gravado. Só para uso local:
o servidor de QA é o `runserver` desta máquina.
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402


def sessao_para(email):
    usuario = get_user_model().objects.get(email=email)
    sessao = SessionStore()
    sessao[SESSION_KEY] = str(usuario.pk)
    sessao[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    sessao[HASH_SESSION_KEY] = usuario.get_session_auth_hash()
    sessao.create()
    return sessao.session_key


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(sessao_para(sys.argv[1]))
