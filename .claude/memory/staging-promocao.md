---
name: staging-promocao
description: merge em main só chega ao staging; produção muda por promover.py, em lote provado, no máximo uma vez por hora
metadata:
  type: architecture
---
Desde 21/09/2026 o merge em `main` faz deploy SÓ do staging; produção tem
`autoDeploy: false` e muda por `scripts/promover.py --lote` (fim da fila e
cron de 30 min): o staging tem de responder a ponta de `main`, a última
promoção tem de ter mais de 60 min (senão "LOTE ADIADO"), e smoke + E2E do
staging têm de passar. E2E vermelho PARA o lote. `--forcar-janela` pula o
relógio para hotfix, NUNCA a prova. Não estranhe produção "atrasada".

Fonte: CLAUDE.md:3167-3238
