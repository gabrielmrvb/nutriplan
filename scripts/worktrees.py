# -*- coding: utf-8 -*-
"""Poda de worktrees e de bancos de teste órfãos (21/09/2026).

    .venv/Scripts/python.exe scripts/worktrees.py --podar              # dry-run: o relatório, nada apagado
    .venv/Scripts/python.exe scripts/worktrees.py --podar --executar   # apaga o que o relatório marcou
    .venv/Scripts/python.exe scripts/worktrees.py --podar --json       # o mesmo relatório em JSON

Esta máquina acumula worktrees (uma por sessão, mais os descartáveis do
pre-push e da fila) e bancos `test_nutriplan_*` (um por suíte interrompida).
A poda é SEMANAL (CLAUDE.md, "Rodar") e tem quatro regras, todas
conservadoras — em dúvida, fica:

* **apaga** o worktree cuja branch está MERGEADA em `origin/main`, ou cuja
  branch NÃO EXISTE mais no origin, ou que está DESTACADO (os descartáveis
  `nutriplan-push-*`/`nutriplan-fila-*`), desde que a árvore esteja LIMPA
  (`git status --porcelain` vazio) — trabalho não commitado nunca é apagado;
* **preserva** o checkout principal, o worktree de onde o script roda, todo
  worktree TRANCADO (`git worktree lock`) e todo worktree citado no ledger
  compartilhado nas últimas `--ledger-horas` (12) horas — é o que "sessão
  ativa" quer dizer aqui: quem escreveu no ledger hoje está trabalhando;
* **apaga** o banco `test_nutriplan_*` sem NENHUMA conexão em
  `pg_stat_activity` (uma suíte viva está conectada; um órfão não) — o
  Django recria o banco na próxima suíte, e `--keepdb` só perde segundos;
* nunca toca no `nutriplan` (o banco de desenvolvimento) nem em nada fora
  do prefixo `test_nutriplan`;
* **nunca atravessa junção nem symlink**: quase todo worktree tem `.venv`
  como junção para o venv compartilhado do checkout principal, e `os.walk`
  segue junção (contava 0,18 GB por worktree de 0,02). `tamanho` não entra
  nelas e `desligar_links` remove SÓ a entrada, antes de qualquer remoção
  recursiva — o alvo fica (`config/test_worktrees.py`, com junção real).

Depois de apagar diretórios, `git worktree prune` limpa os registros. O
relatório diz antes/depois em quantidade e bytes; `--json` é para o CI ou
para quem quiser guardar o histórico.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LEDGER = Path(os.environ.get("NUTRIPLAN_LEDGER", "C:/Users/biel-/nutriplan-ledger.md"))
PSQL_PADRAO = "C:/Users/biel-/pgsql/bin/psql.exe"
PREFIXO_DB = "test_nutriplan"


def _git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=str(cwd or RAIZ), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout.strip()


def _norm(caminho):
    return str(Path(caminho)).replace("\\", "/").rstrip("/").lower()


def e_link(caminho):
    """Symlink OU junção do Windows. `os.path.islink` diz não para junção, e
    `os.walk`/`shutil.rmtree` seguiriam por ela: quase todo worktree desta
    máquina tem `.venv` como junção para o venv compartilhado."""
    caminho = str(caminho)
    return os.path.islink(caminho) or (os.name == "nt" and os.path.isjunction(caminho))


def tamanho(caminho):
    """Bytes da árvore SEM atravessar link nem junção — o `.venv` de 200 MB
    apontado por junção não é do worktree e não vai ser liberado."""
    total = 0
    for pasta, subpastas, arquivos in os.walk(caminho):
        subpastas[:] = [s for s in subpastas if not e_link(os.path.join(pasta, s))]
        for a in arquivos:
            try:
                total += os.lstat(os.path.join(pasta, a)).st_size
            except OSError:
                pass
    return total


def worktrees():
    """[{caminho, head, branch, destacado, trancado, principal}] do `git worktree list --porcelain`."""
    codigo, saida = _git("worktree", "list", "--porcelain")
    lista, atual = [], None
    for linha in saida.splitlines() + [""]:
        if linha.startswith("worktree "):
            atual = {"caminho": linha[9:], "head": "", "branch": "", "destacado": False, "trancado": False, "principal": False}
        elif linha.startswith("HEAD ") and atual:
            atual["head"] = linha[5:]
        elif linha.startswith("branch ") and atual:
            atual["branch"] = linha[7:].replace("refs/heads/", "")
        elif linha == "detached" and atual:
            atual["destacado"] = True
        elif linha.startswith("locked") and atual:
            atual["trancado"] = True
        elif linha == "bare" and atual:
            atual["principal"] = True
        elif linha == "" and atual:
            lista.append(atual)
            atual = None
    if lista:
        lista[0]["principal"] = True
    return lista


def citados_no_ledger(horas):
    """Nomes de pasta (wt-x, nutriplan-x) citados no ledger nas últimas N horas."""
    if not LEDGER.exists():
        return set()
    limite = time.time() - horas * 3600
    nomes = set()
    for linha in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d)", linha) or re.match(r"(\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d)", linha)
        if not m:
            continue
        g = m.groups()
        ano, mes, dia = (g[0], g[1], g[2]) if len(g[0]) == 4 else (g[2], g[1], g[0])
        try:
            quando = time.mktime((int(ano), int(mes), int(dia), int(g[3]), int(g[4]), 0, 0, 0, -1))
        except ValueError:
            continue
        if quando >= limite:
            nomes.update(re.findall(r"\b(wt-[a-z0-9-]+|nutriplan-[a-z0-9-]+)\b", linha))
    return nomes


def classificar(wt, origem_branches, citados, aqui):
    """(veredito, motivo). Veredito: 'preservar' ou 'apagar'."""
    caminho = _norm(wt["caminho"])
    nome = Path(wt["caminho"]).name
    if wt["principal"]:
        return "preservar", "checkout principal"
    if caminho == aqui:
        return "preservar", "é daqui que o script roda"
    if wt["trancado"]:
        return "preservar", "trancado (git worktree lock)"
    if nome in citados:
        return "preservar", "citado no ledger (sessão ativa)"
    if not Path(wt["caminho"]).exists():
        return "apagar", "diretório já não existe (só o registro; prune)"
    codigo, sujo = _git("status", "--porcelain", cwd=wt["caminho"])
    if codigo != 0:
        return "preservar", "git status falhou: %s" % sujo[-80:]
    if sujo.strip():
        return "preservar", "árvore com mudanças não commitadas"
    if wt["destacado"]:
        return "apagar", "destacado (descartável de hook/fila) e limpo"
    if wt["branch"] not in origem_branches:
        return "apagar", "branch %s não existe mais no origin" % wt["branch"]
    codigo, _ = _git("merge-base", "--is-ancestor", wt["head"], "origin/main")
    if codigo == 0:
        return "apagar", "branch %s mergeada em origin/main" % wt["branch"]
    return "preservar", "branch %s com trabalho ainda não mergeado" % wt["branch"]


def bancos(psql):
    """[{nome, bytes, conexoes}] dos bancos test_nutriplan_*."""
    consulta = ("select datname, pg_database_size(datname), (select count(*) from pg_stat_activity a where a.datname = d.datname) "
                "from pg_database d where datname like '%s%%' order by 1" % PREFIXO_DB)
    r = subprocess.run([psql, "-U", "postgres", "-d", "postgres", "-tAc", consulta], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    saida = []
    for linha in r.stdout.splitlines():
        if not linha.strip():
            continue
        nome, tam, con = linha.split("|")
        saida.append({"nome": nome, "bytes": int(tam), "conexoes": int(con)})
    return saida


def apagar_banco(psql, nome):
    assert nome.startswith(PREFIXO_DB)
    r = subprocess.run([psql, "-U", "postgres", "-d", "postgres", "-c", 'DROP DATABASE IF EXISTS "%s"' % nome],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stderr or r.stdout).strip()[-120:]


def desligar_links(caminho):
    """Remove a ENTRADA de todo symlink/junção da árvore, sem entrar neles.
    Devolve os caminhos removidos. Roda ANTES de qualquer remoção recursiva
    (`git worktree remove`, `rmtree`): o que está do outro lado do link —
    o `.venv` compartilhado — não é deste worktree e fica intacto."""
    removidos = []
    for pasta, subpastas, arquivos in os.walk(caminho):
        for nome in list(subpastas):
            alvo = os.path.join(pasta, nome)
            if e_link(alvo):
                os.rmdir(alvo)          # junção/symlink de diretório: só a entrada
                removidos.append(alvo)
                subpastas.remove(nome)
        for nome in arquivos:
            alvo = os.path.join(pasta, nome)
            if os.path.islink(alvo):
                os.unlink(alvo)
                removidos.append(alvo)
    return removidos


def _apagar_arvore(caminho):
    def forcar(func, alvo, _exc):
        os.chmod(alvo, stat.S_IWRITE)
        func(alvo)
    desligar_links(caminho)
    shutil.rmtree(caminho, onexc=forcar) if sys.version_info >= (3, 12) else shutil.rmtree(caminho, onerror=forcar)


def apagar_worktree(caminho):
    """Links fora primeiro; depois o git (que também desregistra); se ele
    recusar, a árvore sai à mão. Devolve (sumiu, erro): um diretório que
    algum processo segura como cwd (`WinError 32`, visto na primeira
    execução) fica vazio e é reportado — a poda segue para o próximo, e o
    `prune` do fim desregistra o que ficou sem `.git`."""
    erro = ""
    if Path(caminho).exists():
        try:
            desligar_links(caminho)
            codigo, _ = _git("worktree", "remove", "--force", caminho)
            if codigo != 0 and Path(caminho).exists():
                _apagar_arvore(caminho)
        except OSError as e:
            erro = str(e)[-120:]
    return not Path(caminho).exists(), erro


def podar(executar=False, ledger_horas=12, psql=PSQL_PADRAO):
    _git("fetch", "-q", "--prune", "origin")
    _, refs = _git("ls-remote", "--heads", "origin")
    origem_branches = {linha.split("refs/heads/", 1)[1] for linha in refs.splitlines() if "refs/heads/" in linha}
    citados = citados_no_ledger(ledger_horas)
    aqui = _norm(RAIZ)
    relatorio = {"worktrees": [], "bancos": [], "executado": executar, "disco_livre_antes": shutil.disk_usage(RAIZ.anchor).free}
    for wt in worktrees():
        veredito, motivo = classificar(wt, origem_branches, citados, aqui)
        existe = Path(wt["caminho"]).exists()
        item = {"caminho": wt["caminho"], "branch": wt["branch"] or ("(destacado %s)" % wt["head"][:7]), "veredito": veredito,
                "motivo": motivo, "bytes": tamanho(wt["caminho"]) if existe and not wt["principal"] else 0, "feito": False}
        if executar and veredito == "apagar":
            item["feito"], item["erro"] = apagar_worktree(wt["caminho"])
        relatorio["worktrees"].append(item)
    if executar:
        _git("worktree", "prune")
    lista = bancos(psql)
    if lista is None:
        relatorio["bancos_erro"] = "psql não respondeu (%s) — o PostgreSQL está de pé?" % psql
    else:
        for b in lista:
            item = dict(b, veredito="apagar" if b["conexoes"] == 0 else "preservar",
                        motivo="sem conexão: órfão" if b["conexoes"] == 0 else "%d conexão(ões): suíte viva" % b["conexoes"], feito=False)
            if executar and item["veredito"] == "apagar":
                item["feito"], item["erro"] = apagar_banco(psql, b["nome"])
            relatorio["bancos"].append(item)
    relatorio["disco_livre_depois"] = shutil.disk_usage(RAIZ.anchor).free
    return relatorio


def resumo(relatorio):
    wts = relatorio["worktrees"]
    dbs = relatorio["bancos"]
    apagar_wt = [w for w in wts if w["veredito"] == "apagar"]
    apagar_db = [d for d in dbs if d["veredito"] == "apagar"]
    feitos_wt = [w for w in apagar_wt if w["feito"]]
    feitos_db = [d for d in apagar_db if d["feito"]]
    return {
        "worktrees_antes": len(wts), "worktrees_a_apagar": len(apagar_wt), "worktrees_apagados": len(feitos_wt),
        "worktrees_depois": len(wts) - len(feitos_wt),
        "bytes_worktrees_a_liberar": sum(w["bytes"] for w in apagar_wt), "bytes_worktrees_liberados": sum(w["bytes"] for w in feitos_wt),
        "bancos_antes": len(dbs), "bancos_a_apagar": len(apagar_db), "bancos_apagados": len(feitos_db), "bancos_depois": len(dbs) - len(feitos_db),
        "bytes_bancos_a_liberar": sum(d["bytes"] for d in apagar_db), "bytes_bancos_liberados": sum(d["bytes"] for d in feitos_db),
        "disco_livre_antes": relatorio.get("disco_livre_antes", 0), "disco_livre_depois": relatorio.get("disco_livre_depois", 0),
    }


def gb(n):
    return "%.2f GB" % (n / 1e9)


def imprimir(relatorio):
    print("WORKTREES")
    for w in relatorio["worktrees"]:
        marca = "APAGAR " if w["veredito"] == "apagar" else "fica   "
        print("  %s %-9s %-45s %s%s%s" % (marca, gb(w["bytes"]), w["branch"][:45], w["motivo"], "  ✓" if w["feito"] else "",
                                          "  ✗ %s" % w["erro"] if w.get("erro") else ""))
    print("BANCOS DE TESTE")
    if "bancos_erro" in relatorio:
        print("  ", relatorio["bancos_erro"])
    for d in relatorio["bancos"]:
        marca = "APAGAR " if d["veredito"] == "apagar" else "fica   "
        print("  %s %-9s %-40s %s%s" % (marca, gb(d["bytes"]), d["nome"], d["motivo"], "  ✓" if d["feito"] else ""))
    r = resumo(relatorio)
    verbo = "liberados" if relatorio["executado"] else "a liberar"
    print("RESUMO %s" % ("(EXECUTADO)" if relatorio["executado"] else "(dry-run — nada apagado; --executar para apagar)"))
    print("  worktrees: %d → %d (%d %s, %s)" % (r["worktrees_antes"], r["worktrees_depois"], r["worktrees_apagados"] if relatorio["executado"] else r["worktrees_a_apagar"], verbo.split()[0] if relatorio["executado"] else "a apagar",
                                               gb(r["bytes_worktrees_liberados"] if relatorio["executado"] else r["bytes_worktrees_a_liberar"])))
    print("  bancos de teste: %d → %d (%s)" % (r["bancos_antes"], r["bancos_depois"], gb(r["bytes_bancos_liberados"] if relatorio["executado"] else r["bytes_bancos_a_liberar"])))
    print("  total %s: %s" % (verbo, gb((r["bytes_worktrees_liberados"] + r["bytes_bancos_liberados"]) if relatorio["executado"] else (r["bytes_worktrees_a_liberar"] + r["bytes_bancos_a_liberar"]))))
    if relatorio["executado"]:
        print("  disco livre: %s → %s (+%s, medido no disco)" % (gb(r["disco_livre_antes"]), gb(r["disco_livre_depois"]), gb(r["disco_livre_depois"] - r["disco_livre_antes"])))


def main(argv=None):
    parser = argparse.ArgumentParser(description="poda de worktrees e bancos de teste órfãos")
    parser.add_argument("--podar", action="store_true", help="calcula o que apagar (dry-run por padrão)")
    parser.add_argument("--executar", action="store_true", help="apaga de verdade")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ledger-horas", type=int, default=12)
    parser.add_argument("--psql", default=PSQL_PADRAO)
    args = parser.parse_args(argv)
    if not args.podar:
        parser.print_help()
        return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace", **({"encoding": "utf-8"} if args.json else {}))  # JSON redirecionado para arquivo sai em UTF-8
    relatorio = podar(executar=args.executar, ledger_horas=args.ledger_horas, psql=args.psql)
    if args.json:
        print(json.dumps({"resumo": resumo(relatorio), **relatorio}, ensure_ascii=False, indent=1))
    else:
        imprimir(relatorio)
    return 0


if __name__ == "__main__":
    sys.exit(main())
