---
name: patch-pelo-bash
description: não escreva código por heredoc ou `python -c` no Git Bash: ele come `\b`, `\d`, crase e aspas
metadata:
  type: reference
---
Medido: `\b` num regex via heredoc gravou o BYTE 0x08 no arquivo; heredoc
também comeu `\d`/`\r\n`; crase dentro de aspas duplas vira substituição
de comando e APAGA a palavra; heredoc com apóstrofo no corpo quebra o
comando inteiro (27/09/2026). Patch vai pela ferramenta de escrita ou por
arquivo `.py`. E o Git Bash converte `origin/main:arquivo` em caminho do
Windows (`git show` falha com "ambiguous argument"): use `MSYS_NO_PATHCONV=1`.

Fonte: memórias antigas `nutriplan-card-de-refeicao`, `nutriplan-direcoes-7-9`, `nutriplan-auditoria-20260920`; medição de 27/09/2026
