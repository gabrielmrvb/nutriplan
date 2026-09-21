# -*- coding: utf-8 -*-
"""O runbook de incidente, em comandos — cada cenário do CLAUDE.md ("Runbook
de incidente", 21/09/2026) tem o verbo exato aqui, e cada verbo foi ENSAIADO
no staging antes de o runbook afirmar que funciona.

    .venv/Scripts/python.exe scripts/incidente.py diagnostico [--staging]
    .venv/Scripts/python.exe scripts/incidente.py banco [--staging]
    .venv/Scripts/python.exe scripts/incidente.py banco --trocar <arquivo-com-a-url> (--staging|--producao)
    .venv/Scripts/python.exe scripts/incidente.py deploy [--staging]
    .venv/Scripts/python.exe scripts/incidente.py deploy --voltar <sha> (--staging|--producao)
    .venv/Scripts/python.exe scripts/incidente.py rotacionar <NOME> (--staging|--producao) [--de-arquivo <arquivo>]
    .venv/Scripts/python.exe scripts/incidente.py rotacionar --encerrar DJANGO_SECRET_KEY (--staging|--producao)
    .venv/Scripts/python.exe scripts/incidente.py actions
    .venv/Scripts/python.exe scripts/incidente.py lembretes [--staging]

Três regras que valem para todo verbo:

* **quem LÊ escolhe produção por padrão; quem ESCREVE exige `--staging` ou
  `--producao`, escrito.** Um `--trocar` que caísse em produção por omissão é
  o incidente seguinte;
* **valor de segredo nunca passa por argumento nem por stdout.** Entra por
  ARQUIVO (`--de-arquivo`, `--trocar`) ou é gerado aqui, e o que sai na tela
  é o nome e o tamanho. O valor novo fica em `~/.nutriplan-secrets/rotacao/`
  para o dia em que alguém precisar dele (o painel do Render não o mostra
  de volta);
* **produção só muda por um comando que diz `--producao`**, e o `deploy
  --voltar` é a MESMA promoção de sempre (`scripts/promover.py`), sem a
  prova do staging — o staging está à frente, e voltar é ir para trás.

A rede é `promover._api` (Render), `github._api` (GitHub) e `promover.saude`
(as instâncias); os testes trocam as três por fakes.
"""
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from scripts import promover  # noqa: E402

SEGREDOS = Path.home() / ".nutriplan-secrets"
ROTACAO = SEGREDOS / "rotacao"
#: Os serviços por ambiente: id fixo de produção (`promover`) e o do staging
#: gravado por `artifacts/criar_staging.py` em `render_estado.json`.
AMBIENTES = {
    "producao": {"base": promover.PRODUCAO, "rotulo": "PRODUÇÃO", "flag": "--producao"},
    "staging": {"base": promover.STAGING, "rotulo": "staging", "flag": "--staging"},
}
#: Segredos que este script GERA sozinho (64 caracteres de `token_urlsafe`).
#: Os outros vêm de fora — Brevo, Google, Neon, Render — e entram por arquivo.
GERADOS = {"DJANGO_SECRET_KEY", "NUTRIPLAN_TAREFAS_TOKEN", "NUTRIPLAN_DISPARO_TOKEN"}
#: Tudo o que o app usa como segredo, e onde mais cada um mora além do Render.
ONDE_MAIS = {
    "DJANGO_SECRET_KEY": "só no Render (a antiga vai para DJANGO_SECRET_KEY_FALLBACKS por 14 dias — a idade da sessão)",
    "NUTRIPLAN_TAREFAS_TOKEN": "segredo do repositório (Actions) — este script regrava com scripts/github.py segredo",
    "NUTRIPLAN_DISPARO_TOKEN": "URL do monitor 'NutriPlan lembretes' no UptimeRobot — trocar à mão no painel",
    "DATABASE_URL": "senha do role no Neon (Roles → reset password) — use `banco --trocar <arquivo>`",
    "EMAIL_HOST_PASSWORD": "chave SMTP na Brevo (SMTP & API → gerar nova, apagar a antiga)",
    "GOOGLE_CLIENT_SECRET": "Google Cloud → APIs → Credenciais → o cliente OAuth → novo segredo, apagar o antigo",
    "VAPID_PRIVATE_KEY": "par em ~/.nutriplan-secrets/vapid/; trocar invalida TODA assinatura push (as pessoas reassinam)",
    "RENDER_API_KEY": "não é do app: Render → Account Settings → API Keys; depois ~/.nutriplan-secrets/render_api_key e scripts/github.py segredo RENDER_API_KEY",
}
FLUXOS = ("suite-rapida.yml", "suite.yml", "lembretes.yml", "promover.yml")
UA = "nutriplan-incidente"


# ---------------------------------------------------------------- utilidades

def _alvo(args, escrita):
    """`producao` ou `staging`. Quem escreve precisa dizer qual, por extenso."""
    if "--staging" in args and "--producao" in args:
        raise SystemExit("--staging OU --producao, não os dois.")
    if "--staging" in args:
        return "staging"
    if "--producao" in args:
        return "producao"
    if escrita:
        raise SystemExit("este verbo ESCREVE: diga --staging ou --producao.")
    return "producao"


def _servico(alvo):
    if alvo == "producao":
        return promover.SERVICO_PRODUCAO
    estado = SEGREDOS / "render_estado.json"
    if estado.exists():
        sid = json.loads(estado.read_text(encoding="utf-8")).get("stagingId")
        if sid:
            return sid
    codigo, lista = promover._api("GET", "/services?name=nutriplan-staging&limit=5")
    for item in lista or []:
        if item.get("service", {}).get("name") == "nutriplan-staging":
            return item["service"]["id"]
    raise SystemExit("serviço de staging não encontrado no Render")


def _get_json(url, tempo=60):
    pedido = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=tempo) as resposta:
            return resposta.status, json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as erro:
        return erro.code, {}
    except Exception as erro:  # rede, DNS, timeout
        return 0, {"erro": type(erro).__name__}


def _idade(iso):
    """Minutos desde um instante ISO-8601 do GitHub/Render (`2026-09-21T05:00:00Z`)."""
    if not iso:
        return None
    quando = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int((datetime.now(timezone.utc) - quando).total_seconds() // 60)


def _env_var(alvo, nome, valor):
    """PUT de UMA variável no serviço. O Render redeploya sozinho em seguida."""
    codigo, resposta = promover._api("PUT", "/services/%s/env-vars/%s" % (_servico(alvo), nome), {"value": valor})
    if codigo not in (200, 201):
        raise SystemExit("PUT %s no %s: HTTP %s %s" % (nome, alvo, codigo, json.dumps(resposta)[:200]))
    print("PUT", nome, "no", AMBIENTES[alvo]["rotulo"], "-> HTTP", codigo, "(tamanho %d)" % len(valor), flush=True)


def _env_apagar(alvo, nome):
    codigo, resposta = promover._api("DELETE", "/services/%s/env-vars/%s" % (_servico(alvo), nome))
    if codigo not in (200, 204):
        raise SystemExit("DELETE %s no %s: HTTP %s %s" % (nome, alvo, codigo, json.dumps(resposta)[:200]))
    print("DELETE", nome, "no", AMBIENTES[alvo]["rotulo"], "-> HTTP", codigo, flush=True)


def _env_atual(alvo):
    """{nome: valor} das variáveis do serviço. Só para LER a chave antiga na rotação — nunca impresso."""
    codigo, lista = promover._api("GET", "/services/%s/env-vars?limit=100" % _servico(alvo))
    if codigo != 200:
        raise SystemExit("GET env-vars do %s: HTTP %s" % (alvo, codigo))
    return {item["envVar"]["key"]: item["envVar"].get("value", "") for item in lista or []}


#: Onde a máquina guarda o valor CORRENTE de cada segredo que ela mesma usa
#: (`lembretes`, o disparo externo, os scripts de QA). A rotação regrava aqui,
#: senão o comando seguinte manda o token que acabou de morrer.
CANONICO = {
    ("producao", "NUTRIPLAN_TAREFAS_TOKEN"): SEGREDOS / "tarefas_token",
    ("producao", "NUTRIPLAN_DISPARO_TOKEN"): SEGREDOS / "disparo_token",
}
STAGING_ENV = SEGREDOS / "staging_env.json"


def _guardar(alvo, nome, valor):
    """O valor novo, num arquivo fora do repositório, com a data — o painel não devolve segredo."""
    ROTACAO.mkdir(parents=True, exist_ok=True)
    arquivo = ROTACAO / ("%s-%s-%s" % (alvo, nome, datetime.now().strftime("%Y%m%d-%H%M%S")))
    arquivo.write_text(valor, encoding="utf-8")
    try:
        os.chmod(arquivo, 0o600)
    except OSError:
        pass
    canonico = CANONICO.get((alvo, nome))
    if canonico is not None:
        canonico.write_text(valor, encoding="utf-8")
    elif alvo == "staging" and nome in GERADOS and STAGING_ENV.exists():
        dados = json.loads(STAGING_ENV.read_text(encoding="utf-8"))
        dados[nome] = valor
        STAGING_ENV.write_text(json.dumps(dados, indent=1), encoding="utf-8")
    print("guardado em", arquivo, flush=True)
    return arquivo


def _ler_arquivo(caminho):
    valor = Path(caminho).read_text(encoding="utf-8").strip()
    if not valor:
        raise SystemExit("%s está vazio" % caminho)
    return valor


def _commit_vivo(alvo):
    """O SHA do deploy `live` do serviço — o que um redeploy tem de repetir."""
    codigo, deploys = promover._api("GET", "/services/%s/deploys?limit=10" % _servico(alvo))
    for item in (deploys or []) if codigo == 200 else []:
        if item["deploy"].get("status") == "live":
            return (item["deploy"].get("commit") or {}).get("id", "")
    raise SystemExit("o %s não tem deploy live — nada para repetir." % alvo)


def _ponta_de_main():
    subprocess.run(["git", "fetch", "-q", "origin"], check=False)
    return subprocess.run(["git", "rev-parse", "origin/main"], capture_output=True, text=True, check=True).stdout.strip()


def _aplicar(alvo, esperar=True, minutos=12):
    """Redeploy do MESMO commit que está no ar, para a variável nova valer.

    MEDIDO em 21/09/2026 no staging: o `PUT /env-vars/<nome>` pela API NÃO
    redeploya (o painel redeploya; a API não) — o token novo respondia 403
    até alguém pedir o deploy. E o deploy é pedido com `commitId` de
    propósito: sem ele o Render sobe a ponta de `main`, que em produção
    (autoDeploy desligado) seria uma PROMOÇÃO escondida dentro de uma
    rotação de segredo.
    """
    # Produção repete o commit LIVE; o staging segue `main` (é o que o
    # autoDeploy faria — MEDIDO: repetir o live ali devolvia o staging a um
    # commit anterior quando um merge novo estava no meio do deploy).
    sha = _commit_vivo(alvo) if alvo == "producao" else _ponta_de_main()
    codigo, resposta = promover._api("POST", "/services/%s/deploys" % _servico(alvo), {"commitId": sha, "clearCache": "do_not_clear"})
    if codigo not in (200, 201, 202):
        raise SystemExit("o Render recusou o redeploy: HTTP %s %s" % (codigo, json.dumps(resposta)[:200]))
    deploy_id = (resposta or {}).get("id") or _deploy_na_fila(alvo, sha)
    # 202 (MEDIDO em 21/09/2026): outro deploy estava no meio, o pedido entrou
    # na fila do Render e a resposta veio sem corpo — o id sai da lista.
    print("redeploy do", AMBIENTES[alvo]["rotulo"], "pedido:", deploy_id, "| commit", sha[:7], "| HTTP", codigo, flush=True)
    if not esperar:
        return deploy_id
    if _esperar_deploy(alvo, deploy_id, minutos) is None:
        raise SystemExit(2)
    return deploy_id


def _deploy_na_fila(alvo, sha):
    codigo, deploys = promover._api("GET", "/services/%s/deploys?limit=5" % _servico(alvo))
    for item in (deploys or []) if codigo == 200 else []:
        d = item["deploy"]
        if (d.get("commit") or {}).get("id", "").startswith(sha[:7]) and d.get("status") in ("queued", "created", "build_in_progress"):
            return d["id"]
    raise SystemExit("o Render aceitou o redeploy mas ele não aparece na lista — olhe o painel.")


def _esperar_deploy(alvo, deploy_id, minutos=12):
    """Espera ESSE deploy ficar `live` (o free leva 3–6 min); falha se ele morrer."""
    fim = time.time() + minutos * 60
    while time.time() < fim:
        codigo, dados = promover._api("GET", "/services/%s/deploys/%s" % (_servico(alvo), deploy_id))
        estado = (dados or {}).get("status") if codigo == 200 else "HTTP %s" % codigo
        print(time.strftime("%H:%M:%S"), AMBIENTES[alvo]["rotulo"], deploy_id, "->", estado, flush=True)
        if estado == "live":
            saude = promover.saude(AMBIENTES[alvo]["base"])
            print("/saude/ ->", json.dumps({"status": (saude or {}).get("status"), "commit": (saude or {}).get("commit")}), flush=True)
            return dados
        if estado in ("build_failed", "update_failed", "canceled", "deactivated", "pre_deploy_failed"):
            print("o deploy morreu em", estado, "— o anterior continua no ar", flush=True)
            return None
        time.sleep(30)
    return None


# ---------------------------------------------------------------- diagnóstico

def diagnostico(alvo):
    """O que está de pé, na ordem em que se descobre onde dói."""
    base = AMBIENTES[alvo]["base"]
    linhas = {}
    vivo, _ = _get_json(base + "/saude/vivo/", tempo=70)
    linhas["web"] = "de pé (/saude/vivo/ %s)" % vivo if vivo == 200 else "FORA (/saude/vivo/ -> %s; cold start leva ~50 s, repita)" % vivo
    codigo, saude = _get_json(base + "/saude/", tempo=90)
    if codigo == 200 and saude.get("status") == "ok":
        linhas["banco"] = "ok (commit %s, ambiente %r)" % (saude.get("commit"), saude.get("ambiente", ""))
    else:
        linhas["banco"] = "FORA (/saude/ -> %s %s) — é o cenário 'banco caiu'" % (codigo, json.dumps(saude)[:120])
    codigo, deploys = promover._api("GET", "/services/%s/deploys?limit=3" % _servico(alvo))
    if codigo == 200 and deploys:
        ultimo = deploys[0]["deploy"]
        linhas["deploy"] = "%s %s (%s, há %s min)" % (ultimo.get("status"), (ultimo.get("commit") or {}).get("id", "")[:7], ultimo.get("id"), _idade(ultimo.get("finishedAt") or ultimo.get("createdAt")))
        vivos = [d["deploy"] for d in deploys if d["deploy"].get("status") == "live"]
        if vivos:
            linhas["ultimo_live"] = (vivos[0].get("commit") or {}).get("id", "")[:7]
    else:
        linhas["deploy"] = "Render API -> HTTP %s" % codigo
    linhas["actions"] = actions(imprimir=False)
    for chave, texto in linhas.items():
        print("%-12s %s" % (chave, texto))
    return linhas


# ---------------------------------------------------------------- banco caiu

def banco(alvo, trocar=None, esperar=True):
    if trocar is None:
        print("BANCO — %s" % AMBIENTES[alvo]["rotulo"])
        diagnostico(alvo)
        print("""
Se `web` está de pé e `banco` FORA, o Neon não responde. Na ordem:
 1. https://neonstatus.com (AWS us-west-2) — incidente deles: espere; o app volta sozinho.
 2. Neon console → projeto → Branches → a branch em uso → compute: se está
    'suspended' e não acorda, 'Restart compute'.
 3. Dado corrompido ou apagado: Neon → Branches → Restore → escolha o instante
    (até 6 h atrás no free) → o Neon cria uma branch nova → copie a URL de
    conexão para um ARQUIVO fora do repositório e:
      scripts/incidente.py banco --trocar <arquivo> --producao
    (redeploya com a URL nova e espera /saude/ dizer ok).
 4. Backup próprio (mais velho que 6 h): scripts/restaurar.sh num Postgres
    local, depois pg_dump | pg_restore para uma branch nova do Neon, e o
    mesmo `banco --trocar`. Ver docs/infra-recuperacao.md.
""")
        return
    url = _ler_arquivo(trocar)
    if not url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("%s não contém uma URL postgres:// — nada foi trocado." % trocar)
    _env_var(alvo, "DATABASE_URL", url)
    _guardar(alvo, "DATABASE_URL", url)
    _aplicar(alvo, esperar)
    if esperar:
        print("BANCO TROCADO e provado no", AMBIENTES[alvo]["rotulo"])


# ---------------------------------------------------------------- deploy quebrou

def deploy(alvo, voltar=None, esperar=True):
    sid = _servico(alvo)
    codigo, deploys = promover._api("GET", "/services/%s/deploys?limit=10" % sid)
    if codigo != 200:
        raise SystemExit("Render API -> HTTP %s" % codigo)
    deploys = [item["deploy"] for item in deploys or []]
    print("DEPLOYS — %s" % AMBIENTES[alvo]["rotulo"])
    for d in deploys:
        print("  %-16s %-8s %s  %s" % (d.get("status"), (d.get("commit") or {}).get("id", "")[:7], d.get("finishedAt") or d.get("createdAt"), d.get("id")))
    if voltar is None:
        print("""
Build reprovou (status build_failed / update_failed): o deploy anterior continua
no ar — nada a desfazer; conserte em main, o staging prova, promova.
Subiu e quebrou (live, mas a tela erra): volte ao último commit bom da lista:
  scripts/incidente.py deploy --voltar <sha> --producao
Sem a prova do staging (o staging está à frente), e sem build quando o Render
ainda tem a imagem daquele deploy (rollback, ~1 min; MEDIDO no free).
""")
        return
    if not promover.esta_em_main(voltar):
        raise SystemExit("%s não está em origin/main — só se volta para o que já foi produção." % voltar[:7])
    # O deploy ANTERIOR desse commit, se o Render ainda o tem: rollback reaproveita
    # a imagem (sem build, ~1 min). Sem ele, deploy novo do commit (3–6 min).
    anterior = next((d for d in deploys if (d.get("commit") or {}).get("id", "").startswith(voltar[:7])
                     and d.get("status") in ("deactivated", "live")), None)
    if anterior:
        codigo, resposta = promover._api("POST", "/services/%s/rollback" % sid, {"deployId": anterior["id"]})
        modo = "rollback de %s" % anterior["id"]
    else:
        codigo, resposta = promover._api("POST", "/services/%s/deploys" % sid, {"commitId": voltar})
        modo = "deploy novo"
    if codigo not in (200, 201, 202):
        raise SystemExit("o Render recusou (%s): HTTP %s %s" % (modo, codigo, json.dumps(resposta)[:200]))
    print("VOLTAR no", AMBIENTES[alvo]["rotulo"], "->", modo, "|", (resposta or {}).get("id"), "| commit", voltar[:7], flush=True)
    if esperar and promover.esperar_commit(AMBIENTES[alvo]["base"], voltar[:7], 15, AMBIENTES[alvo]["rotulo"]) is None:
        raise SystemExit(2)
    return 0


# ---------------------------------------------------------------- segredo vazou

def gerar():
    return secrets.token_urlsafe(48)  # 64 caracteres — o Django pede 50+


def rotacionar(alvo, nome, de_arquivo=None, encerrar=False, esperar=True):
    if encerrar:
        if nome != "DJANGO_SECRET_KEY":
            raise SystemExit("--encerrar só faz sentido para DJANGO_SECRET_KEY (tira a antiga dos FALLBACKS).")
        _env_apagar(alvo, "DJANGO_SECRET_KEY_FALLBACKS")
        _aplicar(alvo, esperar)
        print("a chave antiga deixou de valer no", AMBIENTES[alvo]["rotulo"])
        return
    if nome not in ONDE_MAIS:
        raise SystemExit("%s não é segredo do app. Conheço: %s" % (nome, ", ".join(sorted(ONDE_MAIS))))
    if nome == "RENDER_API_KEY" or nome == "DATABASE_URL":
        raise SystemExit("%s: %s" % (nome, ONDE_MAIS[nome]))
    if de_arquivo:
        valor = _ler_arquivo(de_arquivo)
    elif nome in GERADOS:
        valor = gerar()
    else:
        raise SystemExit("%s vem de fora — %s — e entra com --de-arquivo <arquivo>." % (nome, ONDE_MAIS[nome]))
    if nome == "DJANGO_SECRET_KEY":
        antiga = _env_atual(alvo).get("DJANGO_SECRET_KEY", "")
        if antiga:
            _env_var(alvo, "DJANGO_SECRET_KEY_FALLBACKS", antiga)
    _env_var(alvo, nome, valor)
    arquivo = _guardar(alvo, nome, valor)
    if nome == "NUTRIPLAN_TAREFAS_TOKEN" and alvo == "producao":
        subprocess.run([sys.executable, str(RAIZ / "scripts" / "github.py"), "segredo", nome, str(arquivo)], check=True)
    print("onde mais:", ONDE_MAIS[nome])
    _aplicar(alvo, esperar)
    return arquivo


# ---------------------------------------------------------------- Actions fora

def actions(imprimir=True):
    """Idade do último run de cada fluxo, e o que o GitHub diz de si mesmo."""
    from scripts import github
    repo = github._repo()
    partes = []
    for fluxo in FLUXOS:
        codigo, dados = github._api("GET", "/repos/%s/actions/workflows/%s/runs?per_page=1" % (repo, fluxo))
        runs = (dados or {}).get("workflow_runs") or []
        if codigo != 200 or not runs:
            partes.append("%s: sem run (HTTP %s)" % (fluxo, codigo))
            continue
        run = runs[0]
        partes.append("%s: %s/%s há %s min" % (fluxo, run.get("status"), run.get("conclusion"), _idade(run.get("updated_at"))))
    codigo, status = _get_json("https://www.githubstatus.com/api/v2/components.json", tempo=20)
    componente = next((c for c in (status or {}).get("components", []) if c.get("name") == "Actions"), None)
    partes.append("githubstatus Actions: %s" % (componente or {}).get("status", "(sem resposta %s)" % codigo))
    texto = " | ".join(partes)
    if imprimir:
        print("ACTIONS —", texto)
        print("""
Actions fora NÃO derruba produção: ela só muda por promoção, e promover e voltar
rodam da máquina (scripts/promover.py, scripts/incidente.py deploy --voltar).
O que para, e o que fazer:
 - o gate dos PRs ("suíte rápida") não roda → main não recebe merge. Espere;
   a proteção de main não se desliga para passar um hotfix — rollback é
   `deploy --voltar`, e hotfix espera o gate voltar.
 - lembretes: quem dispara é o UptimeRobot (externo, pontual); o schedule do
   Actions é só o fallback. Para uma rodada agora, da máquina:
     scripts/incidente.py lembretes
 - a fila local (scripts/github.py enfileirar) fica esperando o check; ela
   solta a posse sozinha em 90 min. Nada a fazer.
 - schedule parado há mais de 60 dias sem commit: um commit qualquer religa.
""")
    return texto


# ---------------------------------------------------------------- lembretes à mão

def lembretes(alvo):
    """`POST /tarefas/lembretes/` com o token da máquina — a rodada que o Actions faria."""
    if alvo == "producao":
        token = _ler_arquivo(SEGREDOS / "tarefas_token")
    else:
        token = json.loads((SEGREDOS / "staging_env.json").read_text(encoding="utf-8"))["NUTRIPLAN_TAREFAS_TOKEN"]
    pedido = urllib.request.Request(AMBIENTES[alvo]["base"] + "/tarefas/lembretes/", method="POST", data=b"",
                                    headers={"Authorization": "Bearer " + token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(pedido, timeout=90) as resposta:
            corpo = resposta.read().decode()[:300]
            print("lembretes no", AMBIENTES[alvo]["rotulo"], "-> HTTP", resposta.status, corpo)
            return resposta.status
    except urllib.error.HTTPError as erro:
        print("lembretes no", AMBIENTES[alvo]["rotulo"], "-> HTTP", erro.code, erro.read().decode()[:200])
        return erro.code


# ---------------------------------------------------------------- entrada

def _opcao(args, nome):
    return args[args.index(nome) + 1] if nome in args and args.index(nome) + 1 < len(args) else None


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        raise SystemExit(__doc__)
    verbo, args = argv[0], argv[1:]
    if verbo == "diagnostico":
        return diagnostico(_alvo(args, escrita=False)) and 0
    if verbo == "banco":
        trocar = _opcao(args, "--trocar")
        return banco(_alvo(args, escrita=trocar is not None), trocar, esperar="--sem-esperar" not in args) or 0
    if verbo == "deploy":
        voltar = _opcao(args, "--voltar")
        return deploy(_alvo(args, escrita=voltar is not None), voltar, esperar="--sem-esperar" not in args) or 0
    if verbo == "rotacionar":
        encerrar = "--encerrar" in args
        nomes = [a for a in args if not a.startswith("--") and a != _opcao(args, "--de-arquivo")]
        if not nomes:
            raise SystemExit("rotacionar <NOME> — conheço: %s" % ", ".join(sorted(ONDE_MAIS)))
        rotacionar(_alvo(args, escrita=True), nomes[0], _opcao(args, "--de-arquivo"), encerrar, esperar="--sem-esperar" not in args)
        return 0
    if verbo == "actions":
        actions()
        return 0
    if verbo == "lembretes":
        return 0 if lembretes(_alvo(args, escrita=False)) == 200 else 1
    raise SystemExit("verbo desconhecido: %s\n%s" % (verbo, __doc__))


COMANDOS = ("diagnostico", "banco", "deploy", "rotacionar", "actions", "lembretes")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
