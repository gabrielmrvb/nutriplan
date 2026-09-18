# -*- coding: utf-8 -*-
"""Reparte os módulos de teste em N fatias equilibradas, para o CI rodar
cada fatia num job SERIAL e em paralelo entre jobs.

Por que fatias, e não `manage.py test --parallel` (18/09/2026): o
`--parallel` do Django roda cada processo com um clone do banco, mas a
suíte tem teste que assume ORDEM de PK (auto-increment avança diferente
entre processos) — `test_a_ficha_de_OUTRO_dia...` foi o primeiro a cair no
CI —, e quando UM teste falha em paralelo o runner tenta enviar o erro do
worker para o pai e morre com `TypeError: cannot pickle 'traceback'`,
escondendo a falha real. Medido no PR #33 (Linux): a rápida e a completa
ficaram VERMELHAS por isso. Fatiar mantém cada job SERIAL — idêntico ao
verde de sempre —, e o ganho de tempo vem de os jobs rodarem juntos.

Contrato (o teste em `config/test_ci.py` cobra):

  * `modulos()` descobre TODO módulo de teste do repositório — nada de lista
    escrita à mão que esqueceria um arquivo novo (buraco de cobertura);
  * `particionar(n)` cobre todos os módulos, sem repetir nem deixar de fora
    (união == `modulos()`, fatias disjuntas);
  * o equilíbrio é por LINHAS (proxy de tempo, com peso extra para quem
    semeia um ano); as fatias reais são medidas no CI (cada job imprime o
    tempo e `--durations`), e o peso pode ser ajustado depois.

Uso no CI: `python ci/shard.py <i> <n>` imprime os labels da fatia i (de n),
separados por espaço, para `manage.py test $(python ci/shard.py 0 4) ...`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Módulos que SEMEIAM um ano sintético (seed_stress) custam muito mais por
#: linha; sem o peso extra caem todos numa fatia só e a desequilibram.
PESADOS_POR_SEMENTE = ("plans.test_stress", "workouts.test_instrumento")
PESO_DA_SEMENTE = 4


def _peso(label: str, linhas: int) -> int:
    return linhas * (PESO_DA_SEMENTE if label in PESADOS_POR_SEMENTE else 1)


def modulos() -> list[str]:
    """Todo módulo de teste versionado, como label do Django (`app.modulo`).

    Descobre por `git ls-files` (o que sobe é o que testa), fora de
    `scripts/` e das migrations. `tests.py` e `test_*.py` de cada app.
    """
    saida = subprocess.run(
        ["git", "ls-files", "*.py"], capture_output=True, text=True, cwd=RAIZ, check=True
    ).stdout.split()
    labels = []
    for caminho in saida:
        base = caminho.rsplit("/", 1)[-1]
        if not (base == "tests.py" or base.startswith("test")):
            continue
        if caminho.startswith("scripts/") or "/migrations/" in caminho or "/" not in caminho:
            continue
        labels.append(caminho[:-3].replace("/", "."))
    return sorted(set(labels))


def _linhas(label: str) -> int:
    caminho = RAIZ / (label.replace(".", "/") + ".py")
    try:
        return sum(1 for _ in caminho.open(encoding="utf-8", errors="replace"))
    except OSError:
        return 1


def particionar(n: int) -> list[list[str]]:
    """N fatias equilibradas por peso (LPT: o maior vai para a fatia mais
    vazia). Determinístico: mesma entrada, mesma saída."""
    if n < 1:
        raise ValueError("n >= 1")
    itens = sorted(((_peso(m, _linhas(m)), m) for m in modulos()), reverse=True)
    fatias: list[list[str]] = [[] for _ in range(n)]
    carga = [0] * n
    for peso, label in itens:
        i = carga.index(min(carga))
        fatias[i].append(label)
        carga[i] += peso
    return [sorted(f) for f in fatias]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("uso: shard.py <i> <n>\n")
        return 2
    i, n = int(argv[0]), int(argv[1])
    print(" ".join(particionar(n)[i]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
