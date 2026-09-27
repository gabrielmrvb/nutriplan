---
name: log-fora-do-namespace
description: logger fora de `nutriplan.*` fica MUDO em produção; `assertLogs` esconde isso
metadata:
  type: reference
---
`config/observabilidade.py` põe só o logger `nutriplan` em INFO; o `root` é
WARNING. `logger.info` num `getLogger(__name__)` qualquer some em produção.
Log que precisa sair usa `getLogger("nutriplan.<algo>")`, e o teste aplica
`configuracao(debug=False)` e captura no handler — não `assertLogs`, que
força o nível e passa com o log mudo. Achado provando o disparo externo em
produção (18/09/2026).

Fonte: config/observabilidade.py; memória antiga `nutriplan-disparo-pontual`
