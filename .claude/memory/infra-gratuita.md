---
name: infra-gratuita
description: toda a infra é gratuita (Render free, Neon free, Actions, UptimeRobot free); qualquer gasto novo é condição de parada
metadata:
  type: business-rule
---
Staging e produção no Render free, banco no Neon free, CI e fallback de
lembretes no GitHub Actions, monitores no UptimeRobot free. Muita coisa do
código existe só para contornar o gratuito (pausa do Neon entre refeições,
`/saude/vivo/`, disparo externo). Qualquer dinheiro novo — plano Starter,
cron do Render (402 em 16/09/2026), API cobrada — é a condição de parada 1:
pergunte ao dono. O banco antigo do Render venceu em 24/09/2026 (`suspended`
na API, lido em 27/09) e NÃO é rollback: a volta é o Neon e o backup próprio.

Fonte: CLAUDE.md:76, "Limites reais deste ambiente" e "Runbook de incidente"; `GET /v1/postgres` do Render em 27/09/2026
