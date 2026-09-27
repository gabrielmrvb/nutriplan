---
name: fila-local-armadilhas
description: fila de merge local: leia o ledger pelo tema antes de começar, e a posse pode ficar órfã
metadata:
  type: reference
---
- Antes de começar uma missão, procure no ledger pelo TEMA se outra sessão
  já a pegou, não só nas últimas linhas: em 27/09/2026 duas sessões fizeram o
  mesmo setup (#150 e #153) e a segunda teve de ser recortada.
- `enfileirar` em segundo plano pode sair sem imprimir e deixar a POSSE com o
  PR; confira com `scripts/github.py fila` e `status <n>` antes de relançar.
- Quem é a única mão na fila pode serializar à mão: worktree descartável,
  `git merge origin/main`, push, esperar "suíte rápida" no HEAD QUE SUBIU,
  merge pela API.
- Log de job do Actions: o 302 aponta para blob; refaça o GET no `Location`
  SEM o cabeçalho de autorização (com ele, 401).

Fonte: memórias antigas `nutriplan-fila-do-dono`, `nutriplan-sequencia-por-presenca`; ledger de 27/09/2026
