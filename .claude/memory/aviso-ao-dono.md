---
name: aviso-ao-dono
description: avise o dono com som só ao fechar missão/deploy ou antes de pedir decisão, e só por `scripts/fundo.py notificar`
metadata:
  type: feedback
---
O dono deixa o trabalho rodando e quer ser chamado só quando vale olhar:
missão ou fase fechada, deploy provado, ou decisão que só ele toma (antes do
AskUserQuestion). Nada de som por teste ou comando pequeno; se há próxima
fase executável sozinho, siga sem avisar. O único caminho é
`python scripts/fundo.py notificar --titulo "NutriPlan" "<o que terminou> ·
<onde está> · <revisar?> · <próximo passo>"` — `powershell`, `.ps1`, `cmd /c`
e `start` abrem janela na tela dele (`config/test_janela_de_fundo.py`).

Fonte: memória antiga `notificacao-sonora-ao-concluir` (14 e 16/09/2026); CLAUDE.md "Nenhum processo de fundo abre janela"
