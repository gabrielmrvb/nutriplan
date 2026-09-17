# -*- coding: utf-8 -*-
"""O GitHub sem `gh`: abrir PR, esperar o check, fazer merge, proteger `main`.

Desde 17/09/2026 ninguém empurra em `main` — o gate é o CI
(`.github/workflows/suite.yml`) e a branch tem proteção. Toda sessão
precisa, então, de quatro gestos que o `gh` faria e que esta máquina não
tem: abrir o PR, saber se o check ficou verde, fazer o merge e (uma vez)
ligar a proteção. Este arquivo é só isso, com `urllib`, sem dependência.

O token vem do Git Credential Manager (`git credential fill`), o mesmo que
o `git push` usa — escopos `repo` e `workflow`. Ele NUNCA é impresso, nunca
vai para argumento de linha de comando (iria para o histórico do shell e
para o relatório) e nunca é gravado em arquivo.

Uso (sempre com o python do .venv, na raiz do repositório):

  scripts/github.py pr <branch> "<título>" [--corpo <arquivo.md>]
  scripts/github.py status <número>
  scripts/github.py esperar <número> [--minutos 45]      exit 0 verde / 1 vermelho
  scripts/github.py merge <número>                        merge commit; imprime o SHA
  scripts/github.py fechar <número>                       fecha SEM merge
  scripts/github.py enfileirar <número> [--esperar]       põe o PR na FILA DE MERGE
                                                          (o caminho normal desde 17/09)
  scripts/github.py fila                                  mostra a fila de main
  scripts/github.py fila-ativar                           cria/atualiza o ruleset da
                                                          fila e tira a proteção antiga
  scripts/github.py proteger                              (antigo) proteção clássica
  scripts/github.py protecao                              mostra proteção e rulesets
  scripts/github.py segredo <NOME> <arquivo>              grava um segredo de Actions
                                                          (valor lido do arquivo; nunca
                                                          por argumento nem impresso)
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"

#: O nome do job em `.github/workflows/suite.yml` — é o "context" que a
#: proteção exige, por TEXTO. `config/test_ci.py` confere que os dois batem.
CHECK = "suíte completa"

#: Merge commit, e não squash nem rebase: os SHAs testados no PR continuam
#: existindo em `main`, e o merge commit é o que `/saude/` mostra.
METODO_DE_MERGE = "merge"

COMANDOS = ("pr", "status", "esperar", "merge", "fechar", "proteger", "protecao", "segredo", "enfileirar", "fila", "fila-ativar")

#: O nome do ruleset de `main` — é por ele que `fila-ativar` acha o que já existe.
RULESET = "main: fila de merge"


def corpo_da_fila() -> dict:
    """O ruleset de `main` (Settings → Rules), que substitui a proteção
    clássica desde 17/09/2026: PR obrigatório para todo mundo (`bypass_actors`
    vazio — admin inclusive), o check "suíte completa" SEM `strict` (com
    quatro sessões mergeando, `strict` deixava o PR verde "behind" no meio do
    check; agora é a FILA que atualiza e serializa), fila por merge commit em
    lotes de no máximo dois, sem apagar nem forçar a branch."""
    return {
        "name": RULESET,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": False,
                "allowed_merge_methods": ["merge"],
            }},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": False,
                "do_not_enforce_on_create": False,
                "required_status_checks": [{"context": CHECK}],
            }},
            {"type": "merge_queue", "parameters": {
                "merge_method": "MERGE",
                "grouping_strategy": "ALLGREEN",
                "max_entries_to_build": 2,
                "min_entries_to_merge": 1,
                "max_entries_to_merge": 2,
                "min_entries_to_merge_wait_minutes": 1,
                "check_response_timeout_minutes": 60,
            }},
        ],
    }


def corpo_da_protecao() -> dict:
    """A proteção de `main`, inteira: check verde, branch atualizada
    (`strict`), vale para admin, sem push direto, sem force, sem apagar. Sem
    revisor obrigatório: quem abre o PR é quem faz o merge quando o check
    fica verde — o revisor é a suíte."""
    return {
        "required_status_checks": {"strict": True, "contexts": [CHECK]},
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_linear_history": False,
        "required_conversation_resolution": False,
    }


def _token() -> str:
    saida = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    for linha in saida.splitlines():
        if linha.startswith("password="):
            return linha[len("password="):]
    raise SystemExit("sem credencial do GitHub no credential manager (faça um git push interativo uma vez)")


def _repo() -> str:
    url = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()
    caminho = url.split("github.com", 1)[1].lstrip(":/")
    return caminho[:-4] if caminho.endswith(".git") else caminho


def _api(metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    pedido = urllib.request.Request(
        API + caminho, data=dados, method=metodo,
        headers={
            "Authorization": "Bearer " + _token(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "nutriplan-scripts-github",
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            texto = resposta.read().decode("utf-8")
            return resposta.status, (json.loads(texto) if texto else {})
    except urllib.error.HTTPError as erro:
        texto = erro.read().decode("utf-8", errors="replace")
        try:
            return erro.code, json.loads(texto)
        except ValueError:
            return erro.code, {"message": texto}


def _graphql(query, variaveis):
    """A fila de merge só existe no GraphQL (`enqueuePullRequest`,
    `mergeQueue`); o REST não a expõe."""
    codigo, dados = _api("POST", "/graphql", {"query": query, "variables": variaveis})
    if codigo != 200 or dados.get("errors"):
        raise SystemExit("GraphQL: HTTP %d %s" % (codigo, dados.get("errors") or dados.get("message")))
    return dados["data"]


def _pr(repo, numero):
    codigo, pr = _api("GET", "/repos/%s/pulls/%d" % (repo, numero))
    if codigo != 200:
        raise SystemExit("PR #%d: HTTP %d %s" % (numero, codigo, pr.get("message")))
    return pr


def _check(repo, sha):
    """(status, conclusion) do check `CHECK` no commit, ou (None, None)."""
    codigo, dados = _api("GET", "/repos/%s/commits/%s/check-runs?per_page=50" % (repo, sha))
    if codigo != 200:
        return None, None
    for run in dados.get("check_runs", []):
        if run.get("name") == CHECK:
            return run.get("status"), run.get("conclusion")
    return None, None


def cmd_pr(args):
    branch, titulo = args[0], args[1]
    corpo = ""
    if "--corpo" in args:
        corpo = open(args[args.index("--corpo") + 1], encoding="utf-8").read()
    repo = _repo()
    codigo, pr = _api("POST", "/repos/%s/pulls" % repo, {"title": titulo, "head": branch, "base": "main", "body": corpo})
    if codigo != 201:
        raise SystemExit("não abriu o PR: HTTP %d %s %s" % (codigo, pr.get("message"), pr.get("errors", "")))
    print("PR #%d %s" % (pr["number"], pr["html_url"]))


def cmd_status(args):
    repo = _repo()
    pr = _pr(repo, int(args[0]))
    status, conclusao = _check(repo, pr["head"]["sha"])
    print(json.dumps({
        "numero": pr["number"], "estado": pr["state"], "head": pr["head"]["sha"][:7],
        "mergeable_state": pr.get("mergeable_state"), "check": CHECK,
        "status": status, "conclusion": conclusao, "merged": pr.get("merged"),
    }, ensure_ascii=False))


def cmd_esperar(args):
    """Espera o check terminar. exit 0 verde, 1 vermelho/cancelado, 2 tempo."""
    numero = int(args[0])
    minutos = int(args[args.index("--minutos") + 1]) if "--minutos" in args else 45
    repo = _repo()
    sha = _pr(repo, numero)["head"]["sha"]
    fim = time.time() + minutos * 60
    while time.time() < fim:
        status, conclusao = _check(repo, sha)
        print(time.strftime("%H:%M:%S"), sha[:7], status, conclusao, flush=True)
        if status == "completed":
            raise SystemExit(0 if conclusao == "success" else 1)
        time.sleep(60)
    raise SystemExit(2)


def cmd_merge(args):
    numero = int(args[0])
    repo = _repo()
    pr = _pr(repo, numero)
    codigo, resposta = _api("PUT", "/repos/%s/pulls/%d/merge" % (repo, numero), {
        "merge_method": METODO_DE_MERGE, "sha": pr["head"]["sha"],
        "commit_title": "Merge PR #%d: %s" % (numero, pr["title"]),
    })
    if codigo != 200:
        raise SystemExit("merge recusado: HTTP %d %s — com a fila ativa o caminho é `enfileirar`" % (codigo, resposta.get("message")))
    print("merge %s %s" % (resposta.get("sha", "")[:7], resposta.get("message", "")))


def cmd_fechar(args):
    repo = _repo()
    codigo, pr = _api("PATCH", "/repos/%s/pulls/%d" % (repo, int(args[0])), {"state": "closed"})
    if codigo != 200:
        raise SystemExit("não fechou: HTTP %d %s" % (codigo, pr.get("message")))
    print("PR #%d fechado sem merge (merged=%s)" % (pr["number"], pr.get("merged")))


def cmd_enfileirar(args):
    """Põe o PR na fila de merge de `main`. Com `--esperar`, acompanha até o
    merge (exit 0), a saída da fila (exit 1) ou o tempo (exit 2)."""
    numero = int(args[0])
    repo = _repo()
    pr = _pr(repo, numero)
    if pr.get("merged"):
        print("PR #%d já mergeado" % numero)
        return
    dados = _graphql(
        "mutation($id: ID!) { enqueuePullRequest(input: {pullRequestId: $id}) {"
        " mergeQueueEntry { position state estimatedTimeToMerge } } }",
        {"id": pr["node_id"]},
    )
    entrada = dados["enqueuePullRequest"]["mergeQueueEntry"]
    print("PR #%d na fila: posição %s, estado %s" % (numero, entrada.get("position"), entrada.get("state")))
    if "--esperar" not in args:
        return
    minutos = int(args[args.index("--minutos") + 1]) if "--minutos" in args else 120
    fim = time.time() + minutos * 60
    while time.time() < fim:
        time.sleep(60)
        pr = _pr(repo, numero)
        na_fila = _entrada_na_fila(repo, numero)
        print(time.strftime("%H:%M:%S"), "merged=%s" % pr.get("merged"), "fila=%s" % (na_fila or "-"), flush=True)
        if pr.get("merged"):
            print("MERGEADO %s" % (pr.get("merge_commit_sha") or "")[:7])
            raise SystemExit(0)
        if na_fila is None and pr.get("state") == "open":
            raise SystemExit("PR #%d saiu da fila sem merge (check vermelho ou conflito)" % numero)
    raise SystemExit(2)


def _entrada_na_fila(repo, numero):
    dono, nome = repo.split("/", 1)
    dados = _graphql(
        "query($dono: String!, $nome: String!) { repository(owner: $dono, name: $nome) {"
        " mergeQueue(branch: \"main\") { entries(first: 50) { nodes { position state"
        " pullRequest { number } } } } } }",
        {"dono": dono, "nome": nome},
    )
    fila = (dados["repository"].get("mergeQueue") or {}).get("entries", {}).get("nodes", [])
    for e in fila:
        if e["pullRequest"]["number"] == numero:
            return "%s@%s" % (e["state"], e["position"])
    return None


def cmd_fila(args):
    repo = _repo()
    dono, nome = repo.split("/", 1)
    dados = _graphql(
        "query($dono: String!, $nome: String!) { repository(owner: $dono, name: $nome) {"
        " mergeQueue(branch: \"main\") { entries(first: 50) { nodes { position state"
        " estimatedTimeToMerge pullRequest { number title } } } } } }",
        {"dono": dono, "nome": nome},
    )
    fila = dados["repository"].get("mergeQueue")
    if not fila:
        print("main não tem fila de merge (rode fila-ativar)")
        return
    entradas = fila["entries"]["nodes"]
    if not entradas:
        print("fila vazia")
    for e in entradas:
        print("%s. PR #%d %s — %s" % (e["position"], e["pullRequest"]["number"], e["state"], e["pullRequest"]["title"][:60]))


def cmd_fila_ativar(args):
    """Cria (ou atualiza) o ruleset da fila e tira a proteção clássica —
    as duas juntas fariam o `strict` da antiga travar a fila."""
    repo = _repo()
    codigo, existentes = _api("GET", "/repos/%s/rulesets" % repo)
    if codigo != 200:
        raise SystemExit("rulesets: HTTP %d %s" % (codigo, existentes))
    atual = next((r for r in existentes if r.get("name") == RULESET), None)
    if atual:
        codigo, resposta = _api("PUT", "/repos/%s/rulesets/%d" % (repo, atual["id"]), corpo_da_fila())
    else:
        codigo, resposta = _api("POST", "/repos/%s/rulesets" % repo, corpo_da_fila())
    if codigo not in (200, 201):
        raise SystemExit("ruleset recusado: HTTP %d %s %s" % (codigo, resposta.get("message"), resposta.get("errors", "")))
    print("ruleset %s: %s (id %s)" % (RULESET, "atualizado" if atual else "criado", resposta.get("id")))
    codigo, _ = _api("DELETE", "/repos/%s/branches/main/protection" % repo)
    print("proteção clássica: %s" % ("removida" if codigo == 204 else "não havia (HTTP %d)" % codigo))
    cmd_protecao(args)


def cmd_proteger(args):
    """(Antigo) A proteção clássica de 16/09 — substituída pelo ruleset da
    fila (`fila-ativar`); fica para o dia em que a fila precisar ser
    desligada às pressas."""
    repo = _repo()
    codigo, resposta = _api("PUT", "/repos/%s/branches/main/protection" % repo, corpo_da_protecao())
    if codigo != 200:
        raise SystemExit("proteção recusada: HTTP %d %s" % (codigo, resposta.get("message")))
    print("proteção de main aplicada")
    cmd_protecao(args)


def cmd_protecao(args):
    repo = _repo()
    codigo, p = _api("GET", "/repos/%s/branches/main/protection" % repo)
    if codigo != 200:
        print(json.dumps({"protegida": False, "http": codigo, "mensagem": p.get("message")}, ensure_ascii=False))
        return
    checks = p.get("required_status_checks") or {}
    print(json.dumps({
        "protegida": True,
        "contexts": checks.get("contexts"),
        "strict": checks.get("strict"),
        "enforce_admins": (p.get("enforce_admins") or {}).get("enabled"),
        "force_push": (p.get("allow_force_pushes") or {}).get("enabled"),
        "deletions": (p.get("allow_deletions") or {}).get("enabled"),
        "reviews": bool(p.get("required_pull_request_reviews")),
    }, ensure_ascii=False))
    codigo, rulesets = _api("GET", "/repos/%s/rulesets" % repo)
    if codigo == 200:
        for r in rulesets:
            codigo, detalhe = _api("GET", "/repos/%s/rulesets/%d" % (repo, r["id"]))
            tipos = [x["type"] for x in detalhe.get("rules", [])] if codigo == 200 else []
            print(json.dumps({"ruleset": r.get("name"), "enforcement": r.get("enforcement"), "regras": tipos}, ensure_ascii=False))


def cmd_segredo(args):
    """`segredo NOME arquivo`: grava (ou troca) um segredo de Actions do repositório.

    O GitHub exige o valor cifrado com a chave pública do repositório
    (sealed box, libsodium) — é a única dependência fora da biblioteca padrão
    deste arquivo, e só deste comando: `pip install pynacl` no .venv, fora do
    `requirements.txt` (produção não precisa). O valor vem de um ARQUIVO fora
    do repositório e não passa por argumento nem por stdout.
    """
    if len(args) != 2:
        raise SystemExit("uso: segredo <NOME> <arquivo-com-o-valor>")
    nome, caminho = args
    from base64 import b64decode, b64encode
    from pathlib import Path

    try:
        from nacl import encoding, public
    except ImportError:
        raise SystemExit("pip install pynacl (só para este comando)")
    valor = Path(caminho).read_text(encoding="utf-8").strip()
    if not valor:
        raise SystemExit("arquivo vazio")
    repo = _repo()
    st, chave = _api("GET", "/repos/%s/actions/secrets/public-key" % repo)
    if st != 200:
        raise SystemExit("chave pública: %s %s" % (st, chave))
    caixa = public.SealedBox(public.PublicKey(chave["key"].encode(), encoding.Base64Encoder()))
    cifrado = b64encode(caixa.encrypt(valor.encode("utf-8"))).decode()
    st, resp = _api("PUT", "/repos/%s/actions/secrets/%s" % (repo, nome),
                    {"encrypted_value": cifrado, "key_id": chave["key_id"]})
    if st not in (201, 204):
        raise SystemExit("segredo: %s %s" % (st, resp))
    print("segredo %s %s (tamanho %d)" % (nome, "criado" if st == 201 else "atualizado", len(valor)))


def main(argv):
    if not argv or argv[0] not in COMANDOS:
        raise SystemExit(__doc__)
    globals()["cmd_" + argv[0].replace("-", "_")](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
