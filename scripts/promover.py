# -*- coding: utf-8 -*-
"""Promover um commit para PRODUÇÃO no Render — o único caminho de deploy de
produção desde 21/09/2026 (`autoDeploy: false` em `render.yaml`).

    .venv/Scripts/python.exe scripts/promover.py --lote [--forcar-janela] [--sem-e2e]   # A REGRA (21/09/2026)
    .venv/Scripts/python.exe scripts/promover.py <sha> [--esperar] [--minutos 15]        # a exceção, à mão
    .venv/Scripts/python.exe scripts/promover.py --staging <sha>   # o commit já está no staging?

A REGRA DA PROMOÇÃO (decisão do dono, 21/09/2026): produção só muda no fim de
um LOTE PROVADO, e no máximo uma vez por hora. `--lote` é o que a fila roda
depois de cada merge e o que `promover-lote.yml` roda de meia em meia hora:

1. o lote é a ponta de `origin/main`, e o staging tem de estar respondendo
   esse commit (senão espera; não prova, não promove);
2. produção já nesse commit → nada a fazer;
3. a JANELA: a última promoção (o deploy mais novo de produção, pela API do
   Render) tem de ter mais de `JANELA_MIN` (60) minutos — senão o lote é
   ADIADO, produção não muda, e o próximo `--lote` (o merge seguinte ou o
   cron) o leva, junto com o que entrou no meio. É assim que dois merges
   seguidos viram UMA promoção;
4. a PROVA: smoke nas rotas públicas do staging (200) e o E2E
   (`scripts/qa/e2e_staging.py`: cadastro → onboarding → água → refeição →
   série → temas → exclusão) verde. Reprovou, o lote NÃO sobe e o código de
   saída é 1;
5. só então a promoção de sempre (`promover()`), com a prova do staging.

`--forcar-janela` ignora o relógio (hotfix), NUNCA a prova; `--sem-e2e`
existe para o runner sem navegador e fica dito no log. Promover um SHA à mão
(`promover.py <sha>`) continua sendo a exceção — o runbook a usa para
voltar.

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


#: A janela mínima entre duas promoções, em minutos (decisão do dono, 21/09/2026).
JANELA_MIN = 60
#: O smoke do lote: as rotas públicas do staging que precisam responder 200.
ROTAS_DO_SMOKE = ("/", "/conta/entrar/", "/saude/", "/demo/", "/robots.txt")


def _ponta_de_main():
    subprocess.run(["git", "fetch", "-q", "origin"], check=False)
    return subprocess.run(["git", "rev-parse", "origin/main"], capture_output=True, text=True, check=True).stdout.strip()


def minutos_desde_a_ultima_promocao():
    """Idade, em minutos, do deploy mais novo de produção — qualquer gatilho
    conta (promoção, rollback, redeploy de rotação): é o relógio da janela."""
    codigo, deploys = _api("GET", "/services/%s/deploys?limit=1" % SERVICO_PRODUCAO)
    if codigo != 200 or not deploys:
        return None
    quando = (deploys[0].get("deploy") or {}).get("createdAt", "")
    if not quando:
        return None
    from datetime import datetime, timezone
    inicio = datetime.fromisoformat(quando.replace("Z", "+00:00"))
    return int((datetime.now(timezone.utc) - inicio).total_seconds() // 60)


def smoke(base):
    """[(rota, status)] das rotas públicas; tudo 200 é o mínimo para um lote subir."""
    saida = []
    for rota in ROTAS_DO_SMOKE:
        pedido = urllib.request.Request(base + rota, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(pedido, timeout=90) as resposta:
                saida.append((rota, resposta.status))
        except urllib.error.HTTPError as erro:
            saida.append((rota, erro.code))
        except Exception:
            saida.append((rota, 0))
    return saida


def e2e(base):
    """Roda o roteiro de gente no staging; True se os 12 passos passaram."""
    raiz = Path(__file__).resolve().parents[1]
    capturas = Path(os.environ.get("RUNNER_TEMP") or os.environ.get("TEMP") or ".") / "capturas-lote"
    r = subprocess.run([sys.executable, str(raiz / "scripts" / "qa" / "e2e_staging.py"), "--base", base,
                        "--capturas", str(capturas), "--run", "lote%s" % time.strftime("%H%M%S")])
    return r.returncode == 0


def promover_lote(forcar_janela=False, sem_e2e=False, minutos_staging=12):
    sha = _ponta_de_main()
    curto = sha[:7]
    prod = (saude(PRODUCAO) or {}).get("commit", "")
    if prod == curto:
        print("LOTE: produção já está em %s — nada a promover." % curto, flush=True)
        return 0
    if esperar_commit(STAGING, curto, minutos_staging, "staging") is None:
        print("LOTE NÃO PROVADO: o staging não respondeu %s em %d min — nada sobe." % (curto, minutos_staging), flush=True)
        return 2
    idade = minutos_desde_a_ultima_promocao()
    if not forcar_janela and idade is not None and idade < JANELA_MIN:
        print("LOTE ADIADO: última promoção há %d min (janela de %d); produção fica em %s e o lote %s espera o próximo --lote."
              % (idade, JANELA_MIN, prod or "?", curto), flush=True)
        return 0
    if forcar_janela and idade is not None and idade < JANELA_MIN:
        print("JANELA FORÇADA (--forcar-janela): última promoção há %d min." % idade, flush=True)
    resultado = smoke(STAGING)
    print("smoke no staging:", " ".join("%s=%s" % (rota, status) for rota, status in resultado), flush=True)
    if any(status != 200 for _, status in resultado):
        print("LOTE REPROVADO no smoke — nada sobe.", flush=True)
        return 1
    if sem_e2e:
        print("E2E PULADO (--sem-e2e) — o lote sobe só com o smoke; fica dito.", flush=True)
    elif not e2e(STAGING):
        print("LOTE REPROVADO no E2E — nada sobe.", flush=True)
        return 1
    else:
        print("E2E verde no staging.", flush=True)
    print("LOTE PROVADO: promovendo %s (produção estava em %s)." % (curto, prod or "?"), flush=True)
    return promover(sha, esperar=True, minutos=15)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    if argv[0] == "--lote":
        return promover_lote(forcar_janela="--forcar-janela" in argv, sem_e2e="--sem-e2e" in argv)
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
