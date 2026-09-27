---
name: conta-qa-descartavel
description: QA em produção usa conta descartável do AGENTE, criada pelo signup público e apagada pela tela; nunca a conta do dono
metadata:
  type: feedback
---
Decisão do dono de 18/09/2026: a sessão cria a conta pelo signup público
com e-mail `qa-<sessão>-<data>@nutriplan.invalid`, senha só para ela e
nunca no relatório; ao terminar, APAGA pela tela e prova que sumiu (login
recusado). Nunca a conta pessoal do dono. Se o ambiente proibir criar conta
ou digitar senha, diga isso no relatório e prove o que der pelo `/demo/`.

Fonte: CLAUDE.md:92-99
