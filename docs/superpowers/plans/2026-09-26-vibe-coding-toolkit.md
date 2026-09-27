# Setup do Vibe Coding Toolkit no NutriPlan — plano de implementação

> **Para quem executa:** SUB-SKILL OBRIGATÓRIA — use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para implementar tarefa a tarefa.
> Os passos usam caixa (`- [ ]`) para acompanhamento.

**Objetivo:** ligar o método do Vibe Coding Toolkit neste repositório sem criar uma
segunda fonte de verdade ao lado do protocolo que o projeto já tem (missão, fila de
merge, ledger, staging→promoção).

**Arquitetura:** o toolkit é um conjunto de convenções (CLAUDE.md, memória em duas
camadas, hooks, gates de qualidade, prompts de revisão). Este projeto já implementa
QUATRO das seis frentes com outro vocabulário. O plano, então, é de INTEGRAÇÃO —
mede o que já existe, acrescenta só o que falta, e nomeia em voz alta cada ponto em
que o toolkit e a doutrina do repositório discordam.

**Stack:** Django 5.2 · PostgreSQL (Neon) · PWA em JavaScript vanilla · Render (free)
· CI no GitHub Actions · sem framework de CSS, sem build step de frontend.

**Spec:** o pedido do dono de 26/09/2026 (seis frentes), reproduzido em "O pedido,
item a item" no fim deste arquivo.

## Restrições globais

Copiadas do `CLAUDE.md`, valem para toda tarefa:

- **o gate é o CI**: branch → PR → `scripts/github.py enfileirar` → fila local →
  staging → `promover`. Ninguém mergeia à mão, ninguém empurra em `main`.
- **ledger antes de tocar arquivo em comum**: `C:\Users\biel-\nutriplan-ledger.md`,
  uma linha por aviso.
- **segredo nunca no repositório nem no relatório**; o cofre é `~/.nutriplan-secrets`
  e o `pre-commit` roda gitleaks.
- **a suíte é `manage.py test`** (~31 min serial; o CI a fatia em 5). **Não existe
  pytest neste repositório.**
- **medir antes de afirmar**; toda catraca só sobe com a medição escrita ao lado.
- **decisão de produto ou arquitetura PARA e pergunta** — é a regra do próprio
  pedido, e ela vence a autonomia padrão do `CLAUDE.md` nesta missão.

---

## O que JÁ EXISTE (medido em 26/09/2026, não suposto)

Esta seção é o motivo de o plano ser de integração e não de instalação.

| frente do pedido | estado real neste repositório |
|---|---|
| superpowers | **instalado** (`claude-plugins-official/superpowers`, `b36e0829c6d0`) |
| Ponytail + Caveman | **feito por outra sessão** — branch `chore/ponytail-e-caveman`, commit `30c0c17`, seção nova no `CLAUDE.md` com instalação e como desligar. **Fora do meu escopo.** |
| agent-browser | **instalado e é o padrão de QA** (Chrome 153 próprio); `scripts/qa/nav.py` é o fallback por CDP |
| CLAUDE.md | **existe, ~1.900 linhas**, com stack, comandos, deploy, runbook e ~120 decisões fechadas |
| memória em duas camadas | **existe**: `MEMORY.md` índice + ~45 arquivos de tópico com o frontmatter que o toolkit prescreve |
| hooks | **existem**: `scripts/hooks/pre-commit` (makemigrations --check + 6 classes de estilo + gitleaks) e `pre-push` (atalho em worktree descartável) |
| ruff | **não existe** — nenhum `pyproject.toml`, `ruff.toml` ou menção em `requirements.txt` |
| pytest | **não existe** |
| `.claude/settings.json` | **não existe** (só `launch.json` e `skills/`) |
| `.claude/prompts/` | **não existe** |
| MCPs | **nenhum configurado** (`mcpServers` vazio, global e por projeto) |

### A linha de base de qualidade, já medida

Números reais de `origin/main` em `b4258fe` — o item 5 do pedido pede o relatório,
e metade dele já está aqui:

- **597 arquivos `.py` versionados, 88 acima de 350 linhas.** Os maiores são de
  teste: `accounts/tests.py` 7.142, `workouts/tests.py` 5.729, `plans/tests.py`
  5.056. Fora de teste: `workouts/services.py` 4.278, `plans/views.py` 2.061,
  `workouts/views.py` 1.784, `accounts/views.py` 1.720.
- **10 arquivos `.js`, 4 acima de 350**: `static/js/pwa.js` 2.254,
  `templates/pwa/sw.js` 724, `static/js/fila.js` 688, `static/js/corrida.js` 590.
- **9 dos 11 `views.py` tocam o ORM direto**: `plans/views.py` 25 ocorrências de
  `.objects.`, `accounts/views.py` 19, `workouts/views.py` 15,
  `workouts/corrida_views.py` 11, `gestao/views.py` 6, `push/views.py` 4,
  `ajuda/views.py` 3, `analytics/views.py` 1.
- **5 módulos `services`**: `achievements`, `avisos`, `plans`, `push`, `workouts`.

Nada disso é defeito por si só, e o pedido diz **NÃO refatorar**. O relatório da
Tarefa 5 registra a régua e a data; quem quiser mexer decide depois, com o número
na mão.

---

## DECISÕES DO DONO — respondidas em 26/09/2026

| # | decisão |
|---|---|
| D1 | `pre-commit` roda **só `ruff check`**; suíte fica no `pre-push` e no CI. |
| D2 | ruff em `requirements-dev.txt`; no CI **só reporta**, com `ruff-baseline.txt` como piso — nenhum número sobe. Portão bloqueante só quando o burndown zerar. |
| D3 | **Chrome DevTools MCP fica de fora.** Ver abaixo. |
| D4 | Context7 em **modo anônimo**; o OAuth fica com o dono para depois. |
| D5 | **Sem segunda fonte de verdade.** Diff feito antes de editar; só o que faltava entrou no doc existente. Ver abaixo. |
| D6 | **Sem bootstrap.** Caminho da memória corrigido para este projeto. Ver abaixo. |
| D7 | Esperar `chore/ponytail-e-caveman` (#148) entrar em `main`, rebase, e só então o `CLAUDE.md`. **Feito:** #148 mergeado, rebase em `7ba672b`. |

### D3 — quando reabrir o Chrome DevTools MCP

Fora agora porque duplica o `agent-browser` (padrão declarado) e o
`scripts/qa/nav.py` (fallback por CDP), os dois sobre o mesmo Chrome 153.

**Reabrir quando aparecer investigação de PWA ou de performance** que os dois não
atendam — concretamente: *performance trace* com o timeline do DevTools. Hoje o
`agent-browser` dá `vitals` (números agregados) e o `nav.py` dá `rede 3g`
(emulação), mas nenhum dos dois grava o trace detalhado que se abre no DevTools
para achar em que quadro o tempo foi. No dia em que a pergunta for "por que este
toque custa 400 ms", o MCP passa a valer o terceiro driver.

Instalar, nesse dia:
`claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest`

### D5 — o diff entre o template do toolkit e `nutriplan-missao`

Levantado ANTES de editar, como o dono pediu. Regra do template → onde já mora:

| regra do `CLAUDE.md.template` | estado aqui |
|---|---|
| "Think before coding" — assumir explícito, marcar ambiguidade | **já existe**, mais forte: `nutriplan-missao` §1 separa **fato** de **hipótese** |
| "Simplicity first" | **já existe**: §11 "Qualidade acima de movimento" + a seção Ponytail do `CLAUDE.md` |
| "Surgical changes" | **já existe**: §10 Commits — "só o da missão, nada de conserto oportunista" |
| "Goal-driven execution" | **já existe**: §1 critérios de sucesso + §5 sabotagem |
| "Orchestrator, not implementer" | **já existe**: §2, e "O orquestrador não delega a responsabilidade" é mais duro que o template |
| delegação: sessão principal planeja, subagentes implementam | **já existe**: §2 + o contrato de sete itens |
| onda paralela: **sem dependência entre tarefas** | **já existe**: §1, rótulos SEQUENCIAL / PARALELIZÁVEL / BLOQUEADA / HUMANA |
| onda paralela: **sem sobreposição de arquivo** | **já existe**: §2 "Propriedade de arquivo" — *"Dois subagentes nunca editam a mesma superfície ao mesmo tempo"*, com `settings.py`, `urls.py`, `accounts/models.py` e `CLAUDE.md` nomeados como serializados |
| tabela de especialistas | **já existe**, mais leve: §2 "Papéis que costumam render aqui" |
| **comandos canônicos** (install, lint, typecheck, test, build, run) + "não invente variação" | **FALTAVA** |

**Um buraco só**, e foi o único editado: a tabela de comandos entrou em
"## Rodar" do `CLAUDE.md`. `typecheck` fica declarado como inexistente em vez de
apontar para nada.

### D6 — a memória

**Nada foi rodado do bootstrap** e nenhuma entrada foi criada ou apagada.

O caminho estava sob `C--Users-biel--OneDrive-Desktop-Nova-pasta/memory` (o
checkout principal, que fica em `OneDrive/Desktop/Nova pasta`). Sessão que roda de
`nutriplan-infra` procurava `C--Users-biel--nutriplan-infra/memory`, que não
existia. Corrigido com **junção** do segundo para o primeiro — uma fonte só, os
dois caminhos leem a mesma pasta. Copiar teria criado duas que divergem na
primeira escrita.

**São 41 entradas, e 40 são do NutriPlan.** A única de outro projeto:

- `controle-de-moldes.md` — app de moldes de gesso em HTML/CSS/JS, pasta `moldes/`.

Outras quatro têm título genérico mas nasceram aqui e valem aqui:
`classes-de-evidencia`, `teste-que-passa-pelo-motivo-errado`,
`dev-python-quer-aprender-construindo` (é sobre o dono) e
`notificacao-sonora-ao-concluir` (cita `scripts/fundo.py`, que é deste repo).
`smart-app-control-desligado` é da máquina e afeta este projeto.

Nenhuma foi movida — a junção serve as duas, e `moldes/` também mora no checkout
principal.

## O que foi feito

| arquivo | o quê |
|---|---|
| `docs/quality-baseline.md` | criado — a medição (item 5), agora com a seção do ruff |
| `.claude/prompts/revisao-multi-agente.md` | criado — os três revisores (item 6) |
| `ruff.toml` | criado — `E,F,W`, `line-length = 100`, migrações fora; `E501` ignorado desde 27/09/2026 |
| `requirements-dev.txt` | criado — `ruff==0.16.9`, fora do que o Render instala |
| `ruff-baseline.txt` | criado — o piso: **114** (era 1656 antes do burndown de 27/09/2026) |
| `scripts/hooks/pre-commit` | modificado — catraca de contagem do ruff; avisa e segue se o ruff não estiver instalado |
| `.github/workflows/suite-rapida.yml` | modificado — job `ruff (relatório)`, que **não** é o check obrigatório |
| `CLAUDE.md` | modificado — tabela de comandos canônicos em "## Rodar" (o único buraco do diff D5) |
| `.mcp.json` | criado — Context7 anônimo, escopo de projeto |
| memória | junção `C--Users-biel--nutriplan-infra/memory` → o caminho real (fora do repositório) |

### Provas

- **catraca do ruff morde**: linha longa acrescentada a `config/relogio.py` levou
  a contagem de 1.656 para 1.658; restaurado, voltou a 1.656. (O piso hoje é 111;
  a prova foi feita antes do burndown.)
- **agent-browser 0.38.1**: `open http://127.0.0.1:8000/` abriu a landing
  ("NutriPlan — alimentação e treino num app só"), `snapshot -i` devolveu a
  árvore com refs, captura de 93 KB a 390 px. `localhost` recusou e `127.0.0.1`
  respondeu — `runserver 8000` liga em IPv4 e o Chrome tenta `::1` primeiro.
- **YAML do CI** validado com `yaml.safe_load`.

## Como desligar cada peça

| peça | como tirar |
|---|---|
| ruff inteiro | apagar `ruff.toml`, `requirements-dev.txt`, `ruff-baseline.txt`, o bloco `-> ruff` do `pre-commit` e o job `ruff` do workflow |
| só a catraca (manter o linter) | apagar o bloco `-> ruff` do `pre-commit`; o job do CI continua reportando |
| Context7 | apagar `.mcp.json` |
| prompt de revisão | apagar `.claude/prompts/revisao-multi-agente.md` |
| tabela de comandos | apagar o trecho de "## Rodar" do `CLAUDE.md` |
| junção da memória | `rmdir` (junção, não pasta) em `C--Users-biel--nutriplan-infra/memory` — o alvo fica intacto |
| Ponytail / Caveman | `/ponytail off`, `/caveman off`, ou apagar a seção do `CLAUDE.md` (não é deste PR) |

## O pedido, item a item

1. plugins e MCPs — superpowers ✅ já estava; Ponytail/Caveman ✅ PR #148 (outra
   sessão); Context7 ✅ anônimo por `.mcp.json`; Chrome DevTools ⛔ fora por
   decisão, com gatilho de reabertura escrito acima; agent-browser ✅ smoke.
2. CLAUDE.md — ✅ só a tabela de comandos; o resto já existia (diff em D5).
3. memória — ✅ caminho corrigido, sem bootstrap, 41 entradas auditadas.
4. hooks — ✅ `pre-commit` com a catraca do ruff.
5. quality gates — ✅ `docs/quality-baseline.md`, medido e sem refatorar nada.
6. revisão — ✅ `.claude/prompts/revisao-multi-agente.md`.
