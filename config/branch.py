# -*- coding: utf-8 -*-
"""O banco de teste de cada branch. Stdlib pura, sem Django.

Até 27/09/2026 o nome era `test_` + o NAME do `.env` de cada worktree — uma
disciplina manual, e ela falhou do jeito de sempre: dois worktrees dividiam
`test_nutriplan_design`, quatro caíam em `test_nutriplan`, e o `pre-push`
testava no MESMO banco da sessão que empurrava. Agora o nome vem da branch.

Sem Django porque o `pre-push` e o `scripts/fundo.py` também perguntam o slug,
e nenhum dos dois sobe o settings para isso.
"""
import hashlib
import os
import re
import subprocess


def branch_atual(raiz):
    """A branch do checkout em `raiz`, ou `None` (HEAD destacado, sem git).

    `CREATE_NO_WINDOW` porque o `scripts/fundo.py` chama isto sob `pythonw`, e
    um `git` de console lançado de lá abriria janela.
    """
    try:
        ramo = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=raiz, capture_output=True, text=True, timeout=5, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
    except Exception:
        # Sem git, fora de repositório, git travado: não saber é o nome de hoje.
        return None
    return None if ramo in ("", "HEAD") else ramo


def slug(texto, teto=38):
    """`missao-b/quem-entra-fica` → `missao_b_quem_entra_fica`.

    O teto existe porque o Postgres corta identificador em 63 bytes SEM avisar:
    `test_nutriplan_` (15) + slug (38) + `_push` (5) + clone do `--parallel`
    (`_NN`, 3) = 61 — 63 com o `_b` de `banco_de_teste`. Acima do teto, o começo legível e um hash do nome inteiro —
    duas branches longas com o mesmo começo não viram o mesmo banco.
    """
    s = re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")
    if len(s) > teto:
        s = s[: teto - 8] + "_" + hashlib.sha1(texto.encode("utf-8")).hexdigest()[:7]
    return s


def banco_de_teste(padrao, raiz):
    """O nome do banco de teste; `padrao` é o `test_` + NAME de sempre.

    `NUTRIPLAN_BANCO_DE_TESTE` vence tudo. Sem branch (CI em PR, fila, worktree
    destacado) fica o `padrao` — o CI não muda. `NUTRIPLAN_BANCO_SUFIXO` é do
    `pre-push`, que roda enquanto a sessão da mesma branch pode estar rodando.

    Nome terminado em `_<dígitos>` ganha `_b`: `fase-1-2` virava
    `..._fase_1_2`, que é a cara de um clone `--parallel` de `..._fase_1` — o
    runner da outra branch recusava ou gritava INTRUSO. Com o `_b`, 15 + 38 + 2
    + `_push` (5) + `_NN` (3) = 63, o teto do Postgres.
    """
    if os.environ.get("NUTRIPLAN_BANCO_DE_TESTE"):
        return os.environ["NUTRIPLAN_BANCO_DE_TESTE"]
    ramo = os.environ.get("NUTRIPLAN_BRANCH") or branch_atual(raiz)
    if not ramo or ramo == "HEAD":
        return padrao
    nome = "test_nutriplan_" + slug(ramo)
    if re.search(r"_[0-9]+$", nome):
        nome += "_b"
    return nome + os.environ.get("NUTRIPLAN_BANCO_SUFIXO", "")
