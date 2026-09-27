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

## DECISÕES DO DONO — o plano PARA aqui até cada uma ser respondida

O pedido diz: *"o que for decisão de produto ou arquitetura, listar e parar pra eu
aprovar, não decidir sozinho."* São sete, e cada uma trava pelo menos uma tarefa.

### D1 — O `pytest -x` do hook não existe aqui. O que o pre-commit deve rodar?

O pedido pede `ruff check` + `pytest -x` no pre-commit. **Não há pytest**; a suíte é
`manage.py test` e leva ~31 minutos serial. Pôr a suíte inteira no pre-commit faz
todo commit custar meia hora, e o `pre-commit` de hoje foi desenhado exatamente para
não fazer isso (ele roda 18 testes de estilo/alvo de toque em ~0,2 s, mais
`makemigrations --check` e o gitleaks).

Opções:
- **(a) acrescentar só `ruff check` ao pre-commit atual** — rápido, e o teste
  continua sendo trabalho do `pre-push` e do CI. *Recomendada.*
- **(b) acrescentar `ruff check` + um subconjunto dirigido** (ex.: os testes dos
  apps tocados pelo commit; `scripts/hooks/escopo_do_push.py` já sabe calcular
  escopo).
- (c) traduzir literalmente para `manage.py test` inteiro — inviável na prática.

### D2 — O ruff entra como dependência de quê, e com que severidade?

Não existe ruff hoje. Decisões embutidas:
- **onde declarar**: `requirements.txt` é o que o Render instala em produção; um
  linter não pertence ali. Sugiro `requirements-dev.txt` novo (ou `pyproject.toml`
  com `[dependency-groups]`).
- **severidade inicial**: com 597 arquivos e nenhum linter até hoje, a primeira
  execução vai acusar muito. Sugiro nascer com `E,F,W` e uma catraca de contagem
  (o padrão que o projeto já usa em `config/test_design_system.py`), em vez de
  reprovar tudo no dia um.
- **o ruff vira gate do CI?** Hoje o gate é a "suíte rápida". Acrescentar um check
  novo em `main` protegida é mudança no portão de merge.

### D3 — Chrome DevTools MCP duplica o agent-browser. Entra assim mesmo?

O `CLAUDE.md` declara: *"O agent-browser É O PADRÃO DE QA DE NAVEGADOR (20/09/2026),
e `scripts/qa/nav.py` (CDP) é o FALLBACK"*, os dois sobre o mesmo Chrome 153. O
Chrome DevTools MCP seria o **terceiro** driver de navegador, com console, rede,
trace e screenshot — que os dois já dão. O próprio doc do toolkit avisa que
instalação antiga conflita com a nova.

Opções: **(a) não instalar** e registrar a razão; **(b) instalar e rebaixar o
`nav.py` a fallback de terceiro**; **(c) instalar só para *performance tracing*,
que é o que nenhum dos dois faz hoje**. *Recomendo (c) ou (a).*

### D4 — Context7 exige OAuth no navegador: é clique seu

`npx ctx7 setup --claude` abre o navegador para você autorizar e gerar a chave. A
sessão não clica em autorização de terceiro nem cria conta. Sem a chave ele conecta
anônimo, com limite coletivo. **Preciso que você rode o comando e autorize**, ou que
diga para instalar em modo anônimo, ou que deixe de fora.

### D5 — "sessão principal planeja e delega" + "ondas paralelas" já tem equivalente aqui

O pedido quer essas duas regras no `CLAUDE.md`. O repositório já tem a doutrina
inteira em `nutriplan-missao` (planning → decomposição → subagentes → gates →
sabotagem → browser QA → suíte → PR → fila → staging → promoção), mais a regra de
propriedade de arquivo e o ledger para não colidir entre sessões.

Escrever a versão do toolkit ao lado cria **duas fontes de verdade sobre a mesma
coisa** — exatamente o que este repositório proíbe em vários lugares. Opções:
**(a) apontar do `CLAUDE.md` para a skill que já existe**, acrescentando só a
escada do Ponytail; **(b) reescrever `nutriplan-missao` no vocabulário do toolkit**
(trabalho grande, risco alto); **(c) duplicar** (não recomendo). *Recomendo (a).*

### D6 — A memória já existe, e mora no caminho de OUTRO projeto

`MEMORY.md` + ~45 arquivos de tópico já estão na forma que o toolkit prescreve — mas
sob `C--Users-biel--OneDrive-Desktop-Nova-pasta\memory\`, não sob
`C--Users-biel--nutriplan-infra`. Rodar o bootstrap do zero **duplicaria** a memória.

O que o toolkit tem e este projeto não: um `INSTRUCTIONS.md` explícito e o teto de
linhas com migração para a segunda camada (~130). Opções: **(a) adotar a memória
existente e só acrescentar `INSTRUCTIONS.md` + teto**; (b) criar uma memória nova,
local ao projeto, e migrar as 45 entradas; (c) deixar como está. *Recomendo (a).*

### D7 — Sequenciamento com a outra sessão no `CLAUDE.md`

A sessão `6871ef8d` tem `chore/ponytail-e-caveman` pronta e não mergeada. Toda
tarefa deste plano que toca o `CLAUDE.md` **espera aquele PR entrar**, senão os dois
brigam no merge. Confirmo que é assim que você quer, ou prefere que eu rebase em
cima da branch dela?

---

## Estrutura de arquivos

| arquivo | responsabilidade | decisão que o trava |
|---|---|---|
| `docs/quality-baseline.md` | **criar** — a linha de base medida, com data, régua e números; explicitamente "não refatorar" | nenhuma (mede sem ruff) / D2 para a parte do ruff |
| `.claude/prompts/revisao-multi-agente.md` | **criar** — os três revisores adaptados: Django/segurança, UI/PWA, testes | nenhuma |
| `requirements-dev.txt` | **criar** — ruff | D2 |
| `ruff.toml` | **criar** — regras e exclusões | D2 |
| `scripts/hooks/pre-commit` | **modificar** — acrescentar `ruff check` | D1, D2 |
| `CLAUDE.md` | **modificar** — seção do método (comandos, delegação, ondas) | D5, D7 |
| memória (`INSTRUCTIONS.md`, `MEMORY.md`) | **modificar/criar** fora do repositório | D6 |
| MCPs (`.claude.json`) | **modificar** fora do repositório | D3, D4 |

---

## Tarefas LIBERADAS (não dependem de decisão)

### Tarefa 1: Linha de base de qualidade, sem ruff

**Arquivos:** Criar `docs/quality-baseline.md`.

**Interfaces:** Produz o documento que a Tarefa 4 (ruff) vai estender com a contagem
inicial do linter, e que a catraca futura vai citar.

- [ ] **Passo 1:** rodar a medição com o script já validado nesta sessão (arquivos
      acima de 350 linhas por extensão; `.objects.` por `views.py`; módulos
      `services`), a partir de `git ls-files` para não contar `.venv` nem
      `__pycache__`.
- [ ] **Passo 2:** escrever o documento com: data, commit medido, régua de cada
      número, a tabela por arquivo, e a frase "este documento MEDE; refatorar é
      decisão separada e não foi tomada".
- [ ] **Passo 3:** conferir que nenhum número do documento contradiz o `CLAUDE.md`.
- [ ] **Passo 4:** commit — `docs: linha de base de qualidade medida em b4258fe`.

### Tarefa 2: Prompt de revisão multi-agente, adaptado

**Arquivos:** Criar `.claude/prompts/revisao-multi-agente.md`.

- [ ] **Passo 1:** buscar `docs/prompts/03-multi-agent-code-review.md` do toolkit.
- [ ] **Passo 2:** adaptar aos TRÊS revisores que o dono pediu, cada um com as
      réguas REAIS deste repositório em vez das genéricas do toolkit:
      - **Django/segurança**: CSP com nonce, `CachePrivadoMiddleware`, idempotência
        da fila offline, `op_id`, `CheckConstraint`, gitleaks, LGPD/consentimento;
      - **UI/PWA**: alvo de toque 44×44, texto nunca abaixo de 11 px, nada rola na
        horizontal, tokens NERVURA, `prefers-reduced-motion`, service worker e
        IndexedDB nos dois lados;
      - **testes**: teste que passa pelo motivo errado, controle positivo,
        sabotagem vermelha, doutrina do relógio congelado.
- [ ] **Passo 3:** commit — `docs: prompt de revisão multi-agente adaptado ao NutriPlan`.

### Tarefa 3: Smoke do agent-browser

**Arquivos:** nenhum (verificação).

- [ ] **Passo 1:** subir o servidor por `preview_start` (nunca `runserver` pelo Bash,
      regra do harness) e conferir que responde.
- [ ] **Passo 2:** `agent-browser` com sessão própria, saída em arquivo, `stdin`
      fechado — abrir a landing, `snapshot -i`, uma captura a 390 px.
- [ ] **Passo 3:** registrar o resultado no relatório final. Sem commit.

---

## Tarefas BLOQUEADAS (esperam decisão)

### Tarefa 4 — ruff (trava: D1, D2)
Criar `requirements-dev.txt` + `ruff.toml`, rodar `ruff check --statistics`,
acrescentar a contagem ao `docs/quality-baseline.md`, e só então decidir catraca.
**Não corrigir nada.**

### Tarefa 5 — pre-commit com ruff (trava: D1, D2)
Acrescentar `ruff check` ao `scripts/hooks/pre-commit` existente, falhando de forma
segura (o hook já tem o padrão: reprovar sem travar a sessão). Provar com um commit
de teste e reverter, como o pedido manda.

### Tarefa 6 — CLAUDE.md (trava: D5, D7)
Depois de `chore/ponytail-e-caveman` entrar em `main`: acrescentar a seção do método
com stack, comandos reais (`manage.py test`, `manage.py migrate`, `preview_start`,
`ruff check` se D2 aprovar) e o PONTEIRO para `nutriplan-missao` em vez de uma
segunda doutrina de delegação.

### Tarefa 7 — memória (trava: D6)
Se (a): criar `INSTRUCTIONS.md` na pasta de memória existente e declarar o teto de
linhas, sem tocar nas 45 entradas.

### Tarefa 8 — MCPs (trava: D3, D4)
Context7 e/ou Chrome DevTools, conforme a resposta, com o comando exato e a linha de
"como desligar" no relatório.

---

## O pedido, item a item

1. plugins e MCPs — superpowers ✅ já instalado; Ponytail/Caveman ✅ outra sessão;
   Context7 ⛔ D4; Chrome DevTools ⛔ D3; agent-browser ✅ Tarefa 3.
2. CLAUDE.md — ⛔ D5, D7 (Tarefa 6).
3. memória — ⛔ D6 (Tarefa 7).
4. hooks — ⛔ D1, D2 (Tarefas 4 e 5).
5. quality gates — ✅ Tarefa 1 (parte medida) + ⛔ D2 (parte ruff, Tarefa 4).
6. revisão — ✅ Tarefa 2.
