# -*- coding: utf-8 -*-
"""A trava de segredo do pre-commit, em Python puro (21/09/2026).

    .venv/Scripts/python.exe scripts/segredos.py --staged [--repo <pasta>]

Lê as regras PRÓPRIAS de `.gitleaks.toml` (as `[[rules]]` com `path` e/ou
`regex`, e o `[allowlist].paths`) e as aplica ao que está no índice: nome de
arquivo do cofre `~/.nutriplan-secrets` em qualquer pasta, chave da API do
Render, URL do Neon com senha, chave SMTP da Brevo. É o que roda quando o
`gitleaks` não está instalado — e é a razão de a trava não depender de
instalar nada: um hook que só protege quem instalou a ferramenta não é hook.

Com o `gitleaks` presente, o hook roda ELE (com as mesmas regras e mais as
150+ padrão) e não este. Os dois são provados em `config/test_segredos.py`.
Sai com 1 e a lista do que achou (arquivo:linha, regra — nunca o valor
inteiro), 0 quando está limpo.
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def regras(caminho=RAIZ / ".gitleaks.toml"):
    dados = tomllib.loads(Path(caminho).read_text(encoding="utf-8"))
    saida = []
    for regra in dados.get("rules", []):
        saida.append({
            "id": regra["id"],
            "path": re.compile(regra["path"]) if regra.get("path") else None,
            "regex": re.compile(regra["regex"]) if regra.get("regex") else None,
        })
    permitidos = [re.compile(p) for p in dados.get("allowlist", {}).get("paths", [])]
    return saida, permitidos


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout


def arquivos_no_indice(repo):
    codigo, saida = _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [a for a in saida.split("\0") if a] if codigo == 0 else []


def conteudo_no_indice(repo, arquivo):
    codigo, saida = _git(repo, "show", ":" + arquivo)
    return saida if codigo == 0 else ""


def varrer(arquivos, ler, regras_e_permitidos):
    """[(arquivo, linha, id)] — `ler(arquivo)` devolve o conteúdo; puro, para o teste."""
    lista, permitidos = regras_e_permitidos
    achados = []
    for arquivo in arquivos:
        if any(p.search(arquivo) for p in permitidos):
            continue
        for regra in lista:
            if regra["path"] and regra["path"].search(arquivo) and not regra["regex"]:
                achados.append((arquivo, 0, regra["id"]))
        texto = None
        for regra in lista:
            if not regra["regex"]:
                continue
            if regra["path"] and not regra["path"].search(arquivo):
                continue
            if texto is None:
                texto = ler(arquivo)
            for numero, linha in enumerate(texto.splitlines(), 1):
                if regra["regex"].search(linha):
                    achados.append((arquivo, numero, regra["id"]))
    return achados


def main(argv):
    if "--staged" not in argv:
        raise SystemExit(__doc__)
    repo = Path(argv[argv.index("--repo") + 1]) if "--repo" in argv else RAIZ
    config = Path(argv[argv.index("--config") + 1]) if "--config" in argv else RAIZ / ".gitleaks.toml"
    achados = varrer(arquivos_no_indice(repo), lambda a: conteudo_no_indice(repo, a), regras(config))
    if not achados:
        return 0
    print("SEGREDO NO COMMIT — nada foi gravado:")
    for arquivo, linha, regra in achados:
        print("  %s%s  (%s)" % (arquivo, ":%d" % linha if linha else "", regra))
    print("Tire do índice (`git restore --staged <arquivo>`); o cofre mora em ~/.nutriplan-secrets, fora de todo repositório.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
