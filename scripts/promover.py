# -*- coding: utf-8 -*-
"""Promover um commit para PRODUÇÃO no Render — o único caminho de deploy de
produção desde 21/09/2026 (`autoDeploy: false` em `render.yaml`).

    .venv/Scripts/python.exe scripts/promover.py <sha> [--esperar] [--minutos 15]
    .venv/Scripts/python.exe scripts/promover.py --staging <sha>   # o commit já está no staging?

O que ele faz, na ordem, e por quê:

1. exige que o SHA esteja em `origin/main` (promover branch é deploy sem gate);
2. exige que o STAGING já responda esse commit em `/saude/` — o staging recebe
   todo merge sozinho; produção só recebe o que o staging provou. `--sem-staging`
   pula esta prova, para o dia em que o staging estiver fora do ar, e fica dito;
3. `POST /v1/services/<produção>/deploys {"commitId": <sha>}` na API do Render —
   a chave vem de `RENDER_API_KEY` (ambiente ou `~/.nutriplan-secrets/render_api_key`),
   nunca é impressa e nunca vai para argumento;
4. com `--esperar`, fica olhando `/saude/` de produção até ele dizer o commit
   (o deploy do free leva 3–6 min) e falha com código 2 se não chegar.

A mesma função roda no GitHub Actions (`promover.yml`, botão manual) e na
máquina de uma sessão (`scripts/github.py promover <sha>`).
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.render.com/v1"
PRODUCAO = "https://nutriplan-xxfn.onrender.com"
STAGING = "https://nutriplan-staging.onrender.com"
#: O id do serviço de produção. Não é segredo (aparece na URL do painel); a
#: variável existe para o fluxo poder apontar para outro serviço num teste.
SERVICO_PRODUCAO = os.environ.get("RENDER_SERVICO_PRODUCAO", "srv-da6f5kou01pc73fsfkqg")
UA = "nutriplan-promover"


def _chave():
    chave = os.environ.get("RENDER_API_KEY", "")
    arquivo = Path.home() / ".nutriplan-secrets" / "render_api_key"
    if not chave and arquivo.exists():
        chave = arquivo.read_text(encoding="utf-8").strip()
    if not chave:
        raise SystemExit("RENDER_API_KEY ausente (ambiente ou ~/.nutriplan-secrets/render_api_key).")
    return chave


def _api(metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(API + caminho, data=dados, method=metodo, headers={
        "Authorization": "Bearer " + _chave(), "Accept": "application/json",
        "Content-Type": "application/json", "User-Agent": UA,
    })
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            return resposta.status, json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read() or b"{}")
        except ValueError:
            return erro.code, {}


def saude(base, tempo=90):
    """O JSON de `/saude/` (ou `None` se a instância não respondeu)."""
    pedido = urllib.request.Request(base + "/saude/", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(pedido, timeout=tempo) as resposta:
            return json.loads(resposta.read())
    except Exception:
        return None


def esta_em_main(sha):
    subprocess.run(["git", "fetch", "-q", "origin"], check=False)
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"]).returncode == 0


def esperar_commit(base, curto, minutos, rotulo):
    fim = time.time() + minutos * 60
    while time.time() < fim:
        dados = saude(base)
        vivo = (dados or {}).get("commit", "")
        print(time.strftime("%H:%M:%S"), rotulo, "responde", vivo or "(nada)", "| espero", curto, flush=True)
        if vivo == curto:
            return dados
        time.sleep(30)
    return None


def promover(sha, esperar=False, minutos=15, sem_staging=False):
    curto = sha[:7]
    if not esta_em_main(sha):
        raise SystemExit("%s não está em origin/main — promover só o que passou pelo gate." % curto)
    if not sem_staging:
        dados = saude(STAGING)
        vivo = (dados or {}).get("commit", "")
        if vivo != curto:
            raise SystemExit("o staging responde %s, não %s — espere o deploy automático do staging (ou --sem-staging, dizendo por quê)." % (vivo or "(nada)", curto))
        print("staging provou", curto, "(ambiente=%s)" % (dados or {}).get("ambiente"), flush=True)
    codigo, resposta = _api("POST", "/services/%s/deploys" % SERVICO_PRODUCAO, {"commitId": sha})
    if codigo not in (200, 201):
        raise SystemExit("o Render recusou o deploy: HTTP %s %s" % (codigo, json.dumps(resposta)[:300]))
    print("deploy de produção pedido:", resposta.get("id"), "| commit", curto, flush=True)
    if not esperar:
        return 0
    dados = esperar_commit(PRODUCAO, curto, minutos, "produção")
    if dados is None:
        raise SystemExit(2)
    print("PRODUÇÃO PROVADA:", json.dumps({"commit": dados.get("commit"), "ambiente": dados.get("ambiente", ""), "status": dados.get("status")}), flush=True)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    if argv[0] == "--staging":
        dados = saude(STAGING)
        vivo = (dados or {}).get("commit", "")
        print("staging responde", vivo or "(nada)")
        raise SystemExit(0 if len(argv) > 1 and vivo == argv[1][:7] else 1)
    sha = argv[0]
    minutos = int(argv[argv.index("--minutos") + 1]) if "--minutos" in argv else 15
    return promover(sha, esperar="--esperar" in argv, minutos=minutos, sem_staging="--sem-staging" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
