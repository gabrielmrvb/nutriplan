---
name: comentario-template
description: "{# #} do Django é comentário de UMA linha; multilinha vaza para a página — use {% comment %}"
metadata:
  type: reference
---
Achado pelo CI no PR #147 (27/09/2026): um `{# ... #}` de cinco linhas
vazou como texto na tela, e a suíte local não alcançou. Pegaram
`config.tests.ComentarioDeTemplateNaoVazaTests` e
`workouts.tests.LoadInputFormatTests`, em fatias diferentes. Comentário de
mais de uma linha em template é `{% comment %}...{% endcomment %}`.

Fonte: workouts/tests.py:1159-1185; config/test_b9_disciplina.py:109-132; config/tests.py:2507; C:\Users\biel-\nutriplan-ledger.md:512 (fora do repositório)
