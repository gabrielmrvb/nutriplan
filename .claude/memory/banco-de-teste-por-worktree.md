---
name: banco-de-teste-por-worktree
description: cada worktree testa no próprio banco: `.env` com `nutriplan_<x>` vira `test_nutriplan_<x>`
metadata:
  type: reference
---
O `RunnerUnico` recusa rodar quando outra suíte usa o mesmo `test_nutriplan`
(comum: várias sessões e o pre-push). No `.env` do worktree, troque o nome do
banco em `DATABASE_URL` para `nutriplan_<x>`; o Django testa em
`test_nutriplan_<x>` (medido em 27/09: o pre-commit só passou assim). O
`.venv` do worktree é JUNÇÃO para o do checkout principal — nunca `rmtree`
nele. `manage.py test` sempre com `--noinput`: banco órfão faz o Django
perguntar, e o hook morre em `EOFError`.

Fonte: config/runner.py:39-44; memórias antigas `nutriplan-retencao-descoberta`, `processo-de-fundo-sem-janela`
