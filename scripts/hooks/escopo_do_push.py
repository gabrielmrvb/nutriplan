# -*- coding: utf-8 -*-
"""O que o pre-push soma ao atalho, decidido pelo que o push toca.

    python scripts/hooks/escopo_do_push.py <caminho>...

Imprime rótulos de teste (`manage.py test <rótulos>`) numa linha: o app de
cada arquivo que o push muda em relação a `origin/main`, mais o que roda
sempre. O hook concatena isso ao atalho fixo (`config`, o teste dourado, a
doutrina, o gate por letra, os orçamentos); rótulo repetido não custa nada,
porque o runner do Django deduplica os casos ao montar a suíte.

A regra (decisão do dono, 16/09/2026; o gate passou ao CI em 17/09): a
suíte COMPLETA é do GitHub Actions, no PR. O push local paga só pelo que
tocou — uma branch que mexe em `templates/workouts/` roda `workouts`; uma
que só mexe em `static/css/` roda o atalho e a vitrine. 45 minutos por push
de backup é o preço que faz alguém empurrar com `--no-verify`, e trava que
se pula não é trava.
"""
import sys

#: O que roda em TODO push, independentemente do diff: as catracas do
#: sistema visual (`config`, que o atalho já traz) e a vitrine (`gestao`).
SEMPRE = ("config", "gestao")

#: Apps Django com testes, na ordem em que aparecem em `INSTALLED_APPS`.
APPS = ("accounts", "achievements", "api", "catalog", "demo", "gestao", "plans", "push", "supplements", "workouts")

#: Caminhos fora dos apps que têm dono de teste conhecido.
FORA_DOS_APPS = {
    "static/js": "push",        # pwa.js, fila.js: push/tests.py compara com o sw.js
    "templates/pwa": "push",
    "templates/base.html": "push",  # shell offline, tabbar, data-usuario
    "templates/partials": "config",
}


def app_do_caminho(caminho):
    """O rótulo de teste que cobre este arquivo, ou None."""
    caminho = caminho.replace("\\", "/")
    for prefixo, app in FORA_DOS_APPS.items():
        if caminho == prefixo or caminho.startswith(prefixo + "/"):
            return app
    partes = caminho.split("/")
    if partes[0] in APPS:
        return partes[0]
    if partes[0] == "templates" and len(partes) > 1 and partes[1] in APPS:
        return partes[1]
    return None


def escopo(caminhos):
    """Rótulos para `manage.py test`, ordenados: o de sempre mais o app de cada caminho."""
    rotulos = set(SEMPRE)
    for caminho in caminhos:
        app = app_do_caminho(caminho)
        if app:
            rotulos.add(app)
    return sorted(rotulos)


if __name__ == "__main__":
    print(" ".join(escopo(sys.argv[1:])))
