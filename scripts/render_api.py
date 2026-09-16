# -*- coding: utf-8 -*-
"""O Render pela API, de ponta a ponta, sem imprimir segredo nenhum.

Nasceu no B7 da avaliação de 16/09/2026 (lembretes de refeição). Uso:

    .venv/Scripts/python.exe scripts/render_api.py inspect
    .venv/Scripts/python.exe scripts/render_api.py cron      # cria o cron (precisa de cartão na conta)
    .venv/Scripts/python.exe scripts/render_api.py trigger   # dispara uma rodada agora
    .venv/Scripts/python.exe scripts/render_api.py logs      # log do cron

Subcomandos:
  inspect            owner, serviço web, variáveis (só NOMES), crons existentes
  env                grava VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_ADMIN_EMAIL no web
  cron               cria o cron nutriplan-lembretes (copia o ambiente do web + VAPID)
  deploy             redeploy do web (env var nova precisa de deploy)
  trigger            dispara uma rodada do cron agora
  runs               lista as últimas rodadas do cron
  logs <serviceId>   últimas linhas de log do serviço
  status             estado dos deploys/rodadas

Lê RENDER_API_KEY do ambiente e o par VAPID do arquivo fora do repositório.
Nunca imprime valor de variável: só nome, tamanho e prefixo público.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.render.com/v1"
VAPID_FILE = Path.home() / ".nutriplan-secrets" / "vapid" / "vapid-nutriplan-2026-09-16.env"
WEB_NAME = "nutriplan"
CRON_NAME = "nutriplan-lembretes"
CRON_SCHEDULE = "*/15 8-23,0-2 * * *"  # UTC = 05h–23h59 em Brasília (ver render.yaml)
CRON_PLAN = "starter"
ESTADO = Path.home() / ".nutriplan-secrets" / "render_estado.json"

KEY = os.environ.get("RENDER_API_KEY", "")
_ARQ = Path.home() / ".nutriplan-secrets" / "render_api_key"
if not KEY and _ARQ.exists():
    # Gravada pelo clipboard do painel (16/09/2026); processos já abertos
    # não enxergam o `setx`, então o arquivo é o caminho até reiniciar.
    KEY = _ARQ.read_text(encoding="utf-8").strip()
if not KEY:
    sys.exit("RENDER_API_KEY ausente no ambiente — pare e peça ao dono.")


def _req(method, path, body=None, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + KEY, "Accept": "application/json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except ValueError:
            return e.code, {"raw": txt[:500]}


def vapid():
    pares = {}
    for linha in VAPID_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.startswith("#"):
            k, v = linha.split("=", 1)
            pares[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_ADMIN_EMAIL"):
        assert pares.get(k), "falta %s no arquivo VAPID" % k
    return pares


def estado():
    return json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}


def guardar(**kv):
    e = estado(); e.update(kv)
    ESTADO.write_text(json.dumps(e, indent=1), encoding="utf-8")


def _lista(path, params=None):
    """Paginação por cursor do Render: cada item vem como {"<tipo>": {...}, "cursor": "..."}."""
    itens = []
    params = dict(params or {}); params["limit"] = 100
    while True:
        st, body = _req("GET", path, params=params)
        if st != 200:
            sys.exit("GET %s -> %s %s" % (path, st, body))
        if not body:
            break
        itens.extend(body)
        if len(body) < 100:
            break
        params["cursor"] = body[-1]["cursor"]
    return itens


def owner():
    e = estado()
    if e.get("ownerId"):
        return e["ownerId"]
    owners = _lista("/owners")
    ids = [o["owner"]["id"] for o in owners]
    print("owners:", [(o["owner"]["id"], o["owner"]["type"], o["owner"].get("name")) for o in owners])
    guardar(ownerId=ids[0])
    return ids[0]


def servicos():
    return [s["service"] for s in _lista("/services", {"ownerId": owner()})]


def web():
    for s in servicos():
        if s["name"] == WEB_NAME and s["type"] == "web_service":
            return s
    sys.exit("serviço web '%s' não encontrado" % WEB_NAME)


def cron():
    for s in servicos():
        if s["name"] == CRON_NAME and s["type"] == "cron_job":
            return s
    return None


def env_vars(service_id):
    return [e["envVar"] for e in _lista("/services/%s/env-vars" % service_id)]


def resumo_env(lista):
    return sorted((e["key"], len(e.get("value") or "")) for e in lista)


def cmd_inspect():
    w = web()
    print("web:", w["id"], w["name"], "| repo:", w.get("repo"), "| branch:", w.get("branch"),
          "| region:", w["serviceDetails"].get("region"), "| plan:", w["serviceDetails"].get("plan"),
          "| autoDeploy:", w.get("autoDeploy"))
    print("env do web (nome, tamanho):", resumo_env(env_vars(w["id"])))
    c = cron()
    print("cron:", (c["id"], c["serviceDetails"].get("schedule"), c["serviceDetails"].get("plan")) if c else None)
    guardar(webId=w["id"], repo=w.get("repo"), branch=w.get("branch"), region=w["serviceDetails"].get("region"))


def cmd_env():
    w = web(); v = vapid()
    atuais = {e["key"]: e for e in env_vars(w["id"])}
    for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_ADMIN_EMAIL"):
        st, body = _req("PUT", "/services/%s/env-vars/%s" % (w["id"], k), {"value": v[k]})
        print("PUT", k, "->", st, "(tamanho %d%s)" % (len(v[k]), "; existia" if k in atuais else "; nova"))
        if st not in (200, 201):
            sys.exit("falhou: %s" % body)
    depois = {e["key"]: len(e.get("value") or "") for e in env_vars(w["id"])}
    print("conferido no web:", {k: depois.get(k) for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_ADMIN_EMAIL")})
    print("prefixo público:", v["VAPID_PUBLIC_KEY"][:12] + "…")


def cmd_cron():
    if cron():
        print("cron já existe:", cron()["id"]); return
    w = web(); v = vapid()
    base = [e for e in env_vars(w["id"]) if e["key"] not in ("WEB_CONCURRENCY", "PORT")]
    chaves = {e["key"] for e in base}
    envs = [{"key": e["key"], "value": e["value"]} for e in base if e.get("value") is not None]
    for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_ADMIN_EMAIL"):
        envs = [e for e in envs if e["key"] != k] + [{"key": k, "value": v[k]}]
    print("ambiente copiado do web (nomes):", sorted(chaves | {"VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_ADMIN_EMAIL"}))
    body = {
        "type": "cron_job",
        "name": CRON_NAME,
        "ownerId": owner(),
        "repo": w["repo"],
        "branch": w.get("branch") or "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "runtime": "python",
            "schedule": CRON_SCHEDULE,
            "plan": CRON_PLAN,
            "region": w["serviceDetails"].get("region", "oregon"),
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "python manage.py send_meal_reminders",
            },
        },
        "envVars": envs,
    }
    st, resp = _req("POST", "/services", body)
    if st != 201:
        print("POST /services ->", st, json.dumps(resp, ensure_ascii=False)[:800])
        sys.exit(2)
    s = resp["service"]
    print("cron criado:", s["id"], s["serviceDetails"].get("schedule"), s["serviceDetails"].get("plan"),
          "| deployId:", resp.get("deployId"))
    guardar(cronId=s["id"], cronDeployId=resp.get("deployId"))


def cmd_deploy():
    w = web()
    st, resp = _req("POST", "/services/%s/deploys" % w["id"], {"clearCache": "do_not_clear"})
    print("POST deploys ->", st, (resp or {}).get("id"), (resp or {}).get("status"))
    guardar(webDeployId=(resp or {}).get("id"))


def cmd_status():
    w = web()
    st, deps = _req("GET", "/services/%s/deploys" % w["id"], params={"limit": 3})
    for d in deps or []:
        d = d["deploy"]
        print("web deploy:", d["id"], d["status"], (d.get("commit") or {}).get("id", "")[:7], d.get("createdAt"), d.get("finishedAt"))
    c = cron()
    if c:
        st, deps = _req("GET", "/services/%s/deploys" % c["id"], params={"limit": 3})
        for d in deps or []:
            d = d["deploy"]
            print("cron deploy:", d["id"], d["status"], (d.get("commit") or {}).get("id", "")[:7], d.get("createdAt"), d.get("finishedAt"))


def cmd_trigger():
    c = cron() or sys.exit("sem cron")
    st, resp = _req("POST", "/cron-jobs/%s/runs" % c["id"])
    print("POST runs ->", st, json.dumps(resp, ensure_ascii=False)[:400])
    guardar(lastRunId=(resp or {}).get("id"))


def cmd_runs():
    c = cron() or sys.exit("sem cron")
    st, resp = _req("GET", "/cron-jobs/%s/runs" % c["id"], params={"limit": 5})
    print(st, json.dumps(resp, ensure_ascii=False)[:1500])


def cmd_logs(service_id=None, linhas=80):
    sid = service_id or (cron() or {}).get("id") or sys.exit("sem serviço")
    st, resp = _req("GET", "/logs", params={"ownerId": owner(), "resource": [sid], "limit": linhas, "direction": "backward"})
    if st != 200:
        print("GET /logs ->", st, resp); return
    for l in (resp or {}).get("logs", []):
        print(l.get("timestamp", "")[:19], "|", l.get("message", "").rstrip()[:300])


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "inspect"
    {"inspect": cmd_inspect, "env": cmd_env, "cron": cmd_cron, "deploy": cmd_deploy,
     "trigger": cmd_trigger, "runs": cmd_runs, "status": cmd_status,
     "logs": lambda: cmd_logs(args[1] if len(args) > 1 else None)}[cmd]()
