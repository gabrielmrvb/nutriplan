# Operação confiável e qualidade contínua — plano (21/09/2026)

Missão do dono, um PR por item, tudo free. Sessão `ops` (worktree
`nutriplan-design`, branches `ops/*`). O que cada item entrega e como se prova.

| # | item | branch | entrega | prova |
|---|---|---|---|---|
| 1 | Staging + promoção | `ops/staging` | serviço `nutriplan-staging` (Render free, `autoDeploy: true`, branch `staging` do Neon *schema only*), produção `autoDeploy: false`, `scripts/promover.py`, `promover.yml`, `enfileirar` prova o staging, `config/ambiente.py` | um PR entra em `main` → `/saude/` do staging responde o SHA → produção continua no anterior → `promover` → produção responde |
| 2 | Runbook de incidente | `ops/runbook` | seção "Runbook" no `CLAUDE.md`: banco caiu, deploy quebrou (rollback pelo Render), segredo vazou (rotação), Actions fora — comando exato por cenário; `scripts/incidente.py` | cada comando executado uma vez contra o staging (rollback real, rotação de token de staging) |
| 3 | Restauração mensal | `ops/restaurar-mensal` | `restaurar-mensal.yml` (cron mensal + manual): dump de produção com papel só-leitura → restaura no Postgres do job → `scripts/restaurar.sh` (órfãos, contagens) → issue se falhar | um run manual verde; sabotagem (dump truncado) vermelha |
| 4 | Logs JSON + alerta 5xx | `ops/logs-json` | formatter JSON em `config/observabilidade.py` (request id, rota, usuário anônimo, duração, status), contador de 5xx em cache com e-mail ao passar de N em 5 min | teste do formatter; alerta disparado num teste com 5xx simulados; log de produção lido em JSON |
| 5 | E2E noturno | `ops/e2e-noturno` | `e2e-noturno.yml`: agent-browser no runner contra o STAGING: signup descartável → onboarding → série → refeição → água, dois temas, capturas como artefato, conta apagada; falha abre issue | um run verde com artefatos; run vermelho provocado |
| 6 | Carga | `ops/carga` | `carga.yml` (manual): k6 com 50 VUs contra o staging, p95 por rota, relatório como artefato; nunca produção | um run com relatório e o teto encontrado |
| 7 | Movimento + i18n | `ops/movimento-i18n` | teste "toda animação respeita `prefers-reduced-motion`"; `gettext` nos templates novos, `LANGUAGE_CODE`/`LOCALE_PATHS`, `makemessages` sem traduzir | testes; `manage.py makemessages` gera o `.po` |

Regras: ledger antes de tocar arquivo comum; `git merge origin/main` antes de
cada `enfileirar`; nada de segredo em argumento, log ou relatório; conta de
QA descartável só no staging.
