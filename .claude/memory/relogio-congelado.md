---
name: relogio-congelado
description: a suíte vive numa quarta congelada (16/09/2026, 12:00); teste não lê date.today/datetime.now/utcnow/time.time
metadata:
  type: reference
---
Desde 21/09/2026 a suíte congela DATA e HORA: quarta 16/09/2026 às 12:00
mais o decorrido (`config/relogio.py`). `date.today()`, `datetime.now()`,
`datetime.utcnow()` e `time.time()` são proibidos em teste, e
`config/test_relogio.py` varre a árvore. Use `timezone.now()`/`localdate()`
(já congelados) ou, para contar por janela, `relogio.congelado_em(...)`.
Por quê: o minuto da máquina derrubou o gate duas vezes. Só a
`noturna.yml` roda com o relógio real.

Fonte: CLAUDE.md:2928-2950; config/relogio.py:167
