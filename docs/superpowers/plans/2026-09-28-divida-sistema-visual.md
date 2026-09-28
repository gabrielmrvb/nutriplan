# Dívida de sistema visual — o sistema vira a lei no código

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) — os seis lotes tocam `static/css/app.css`, então subagente em paralelo está fora (decisão do dono: `subagent-driven-development` só em lote sem arquivo em comum). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tokens, escala e componentes canônicos viram lei verificada por teste fora de `templates/workouts/`, em seis lotes com um PR cada, sem nenhuma nota de tela cair.

**Architecture:** Um arquivo de CSS (`static/css/app.css`) com os tokens no `:root`; a régua em `config/test_design_system.py` (catracas de folga zero + a lei do legado); cada lote migra uma família para o canônico da tela Mais (nota 3,00) e prova com captura antes/depois a 390 e 1280 no harness da auditoria.

**Tech Stack:** Django 5.2, CSS sem build, `agent-browser` (Chromium) e o harness `scratchpad/av` + `scratchpad/av2` da auditoria.

**Spec:** `achados/auditoria-visual-20260927.md` (#181) + gate 1 do dono (28/09/2026) + `docs/briefs/design/DESIGN.md`.

## Global Constraints

- Proibido tocar `templates/workouts/` e `workouts/` (a Fase A mora lá). O que for de treino vai para o ledger.
- `h2`: **R** — canônico é o rótulo de seção da Mais (`.sobretitulo.secao-rotulo`, 11,2 px, caixa alta, .16em) nas telas do app e em gestão/analytics; prosa longa (Termos, Privacidade) usa `--texto-lg` 18,4/700. Tela que ficar só com rótulo, sem display acima, entra na lista de achados com captura — não inventar título.
- Espaço: `--e1…--e8` = 4 · 8 · 12 · 16 · 20 · 24 · 32 · 48. `--espaco-*` fica só no treino, marcado como legado no `:root` com data.
- Tintas: as 5 de `--brand` (9 · 12 · 24 · 32 · 45 %), a mesma escada nos pilares, `--terra` primeiro.
- Cada lote: TDD, sabotagem da régua nova, suíte rápida (pre-push + CI), revisão de código, captura antes/depois a 390 e 1280, nota por tela remedida (não pode cair). Um PR por lote, pela fila (`scripts/github.py enfileirar`).
- Parar em decisão nova.

## O harness de prova (vale para todos os lotes)

- Banco `nutriplan_sistema`; servidor **antes** = `origin/main` no worktree `~/nutriplan-auditoria-visual` (porta 8216, `DATABASE_URL` do banco de captura no ambiente); servidor **depois** = a branch do lote em `~/nutriplan-sistema` (porta 8217).
- Personas criadas uma vez pelo cadastro público local (`comparar.py preparar`): P1 ABC com 12 dias de histórico, P2 só corre, P3 casa/peso do corpo, e `onb` parada na etapa 3. Apagadas pela tela no fim da missão (`comparar.py apagar`).
- `comparar.py capturar 8216 loteN-antes` e `… 8217 loteN-depois`: 43 cenas × 3 vistas; `comparar.py notas loteN-antes loteN-depois` compara Ti/Es/Cc por tela e marca o que cai; pares de imagem para Co/Hi/Ev/Vo/Cs a olho.

---

### Lote 1: tokens + régua — FEITO (branch `sistema/lote-1-tokens`)

**Files:** `static/css/app.css` · `config/test_design_system.py` · `config/tests.py` · `config/test_foco.py` · `config/test_nervura.py` · `config/test_superficie_de_foco.py` · `config/test_teclado_e_flutuantes.py` · `plans/test_agua_zerar_nao_empurra.py` · `docs/briefs/design/DESIGN.md` · `CLAUDE.md` · `CHANGELOG.md` · `achados/divida-visual-medicao-20260927.md`

- [x] Régua nova vermelha (`OSistemaViraALeiTests`): oito degraus com os valores, `--pad`/`--gap` apontando para eles, legado datado, legado só em regra de treino (com controle positivo `.card` × `.card.hoje`), cinco tintas da marca, catracas de entrelinha / cor literal / `color-mix()` fora do `:root` com folga zero, `<style>` só no 500.
- [x] Migração mecânica (`scratchpad/av2/migrar_lote1.py`, 640 trocas + 18 do legado em qualquer propriedade): degrau mais perto; 40/36/52 px como soma exata; fora: treino, `h2` base (lote 4), `.app-bar` (lote 6, só o tamanho de texto), `.auth .card` (lote 3), `em`, `%`, `clamp()`, > 56 px.
- [x] Tokens no `:root`: `--e1…--e8`, quatro entrelinhas, 30 tintas e receitas com nome; legado datado.
- [x] Testes de texto exato atualizados para o token novo de mesmo valor em px.
- [x] Sabotagem 10/10 vermelha.
- [x] Captura antes/depois: 129 × 2, zero queda de Ti/Es/Cc.
- [x] Suíte rápida (pre-push), revisão de código, PR #187, fila — em produção (`d998ee4`).

### Lote 2: botão primário único (`sistema/lote-2-botao`)

**Canônico:** `.btn.btn--primary` (display 22,4, inclinado) e `.btn--primary.btn--sm` (o pequeno, Archivo, regra da NERVURA).

**Files:** `templates/plans/_peso_campo.html:45` · `templates/partials/_conquista.html:55` · `static/css/app.css` (`.pesagem__salvar` sai; o link "Buscar no YouTube" ganha 44 px) · `templates/plans/alimentacao.html` + CSS (o chip "Agora" 46 → 50 px) · `config/test_design_system.py`

- [ ] Régua vermelha: nenhum template fora de `templates/workouts/` com classe de botão que pinte `--brand` cheio sem `btn--primary` (varre o CSS: seletor com `background: var(--brand)` + `color: var(--on-brand)` cujo elemento não é `.btn--primary`); no máximo UM `btn--primary` visível por tela nas capturas (a medição do harness) — e o aviso de conquista não entra como segundo.
- [ ] `pesagem__salvar` → `btn btn--primary btn--sm`; o CSS de `.pesagem__salvar` sai.
- [ ] "Compartilhar" do aviso de conquista → `btn btn--ghost` (o primário da tela da execução é CONCLUIR SÉRIE).
- [ ] Junto: "Buscar no YouTube" com alvo de 44 px (CSS da classe; o template é de treino e não muda); o chip "Agora" com largura para o texto inteiro (≥ 50 px, medido com `scrollWidth`).
- [ ] Sabotagem, captura antes/depois (Home, Progresso, execução em leitura), notas, suíte, revisão, PR, fila.

### Lote 3: cartão único (`sistema/lote-3-cartao`)

**Canônico:** `.card` da Mais (`--pad`, régua de `--traco` em `--fio`, `--surface`) e `.card--prato` (o bloco que manda, um por tela, com a nervura).

**Files:** `static/css/app.css` · `templates/plans/_agora.html` · `templates/plans/alimentacao.html` · `templates/accounts/profile.html` · `templates/accounts/login.html` · `templates/accounts/signup.html` · `templates/accounts/onboarding/step.html` · `templates/plans/landing.html` · `config/test_design_system.py`

- [ ] Régua vermelha: fora de treino, `.card` só com os modificadores da lista fechada (`--prato`, `--prosa`, e os de CONTEÚDO que não mudam a caixa); nenhuma regra fora de treino muda `padding`/`border`/`background` de `.card` a não ser `.card--prato`; no máximo um `--prato` por tela.
- [ ] `.auth .card` (27,2/22,4) → `--pad`; `today-hero` e `agora-card` → `card--prato`; `card--metas` → `.card`; `explicacao` → `.card` com o `<summary>` como linha; `.auth--entrada .card` deixa de ser `.card`.
- [ ] Sabotagem, captura, notas, suíte, revisão, PR, fila.

### Lote 4: `h2` único (`sistema/lote-4-h2`)

**Canônico:** `h2.secao-rotulo` (rótulo da Mais); prosa (`.card--prosa`, `.legal`) com `--texto-lg` 18,4/700.

**Files:** os 99 `<h2>` fora de treino listados em `achados/divida-visual-medicao-20260927.md` (seção "O `h2` de 20,8 px") · `static/css/app.css` · `config/test_design_system.py`

- [ ] Régua vermelha: todo `<h2>` de template fora de `templates/workouts/` tem `secao-rotulo` ou mora em prosa; o `h2 { font-size: 1.3rem }` base fica só para o treino (legado datado).
- [ ] Migração dos templates; `demo-titulo` e `sobretitulo` avulso → rótulo; `agora__titulo` → display `--texto-xl` (nome herói, não seção).
- [ ] **Achado obrigatório:** toda tela que ficar só com rótulo de seção, sem display acima, entra em `achados/` com captura — sem inventar título — e vai para o dono.
- [ ] Sabotagem, captura, notas, suíte, revisão, PR, fila.

### Lote 5: controle de escolha único (`sistema/lote-5-escolha`)

**Canônico:** `templates/partials/choice_cards.html` (rádio e caixa, visto quadrado).

**Files:** `templates/partials/field.html` · `templates/partials/caixas_de_consentimento.html` · `templates/accounts/signup.html` · `templates/accounts/profile.html` · `templates/socialaccount/connections.html` · `templates/partials/choice_cards.html` · `static/css/app.css` · `config/test_design_system.py`

- [ ] Régua vermelha: nenhum `choice-list`/`segmented` em template fora de `templates/workouts/`; `input[type=radio]` visível fora de `.choice-card` = 0 nas capturas.
- [ ] Rádio em lista (experiência, equipamento) → `choice_cards` 1 coluna; caixa em lista (restrições, interesses, consentimento, Termos, análise de uso, Google) → `choice_cards` caixa; sexo → `colunas=2`; dias → modificador `--dias`, 7 colunas, mesmo visto.
- [ ] Sabotagem, captura (onboarding 1–3, Perfil, cadastro), notas, suíte, revisão, PR, fila.

### Lote 6: cromo global (`sistema/lote-6-cromo`)

**Files:** `static/css/app.css` (`.app-bar*`) · `config/test_design_system.py`

- [ ] Régua vermelha: nenhum `font-size` cru em regra `.app-bar*`.
- [ ] Marca 16,8 px → degrau; links do desktop 14 px → `--texto-md`; a barra anônima a 390 não quebra palavra ("NutriPla/n", "Entra/r" — medido).
- [ ] Sabotagem, captura (todas as telas: é cromo), notas, suíte, revisão, PR, fila.

### Fecho — FEITO (28/09/2026)

Lotes 2–6 como planejado, cada um com régua vermelha antes, sabotagem 100 % vermelha, captura antes/depois (129 × 2), revisão de código e um PR pela fila: #188 (botão), #189 (cartão), #191 (`h2`), e os PRs do lote 5 (escolha) e 6 (cromo). Nenhuma nota medida caiu em lote nenhum.

Desvios do plano, decididos e registrados: dias em fila que QUEBRA, não em 7 colunas (a 390 px seriam 42 px, abaixo do alvo); `choice-cards--lista` e `--par` (a lista antiga tinha 50 px, o cartão com ícone pede 68; o sexo sem ícone não cabe no `--duas`); caixa da lista com o quadrado vazio à vista (consentimento tem de parecer que se marca); foco do `choice-card` em anel com vão (a decisão de 16/09 para o chip de dia e o segmented); abaixo de 24rem a barra com ações mostra só o símbolo (a 320 px ela pediria 374 de 305). A lista de "só rótulo, sem display acima" (lote 4) saiu vazia.

#### Mapa de calor remedido (a função de nota da auditoria; Ti/Es/Cc medidos nas capturas finais, os observados são os da auditoria)

| tela | Ti | Es | Cc | média (auditoria) | Ti | Es | Cc | média (depois) |
|---|---|---|---|---|---|---|---|---|
| Landing | 2 | 0 | 3 | 1.95 | 3 | 3 | 3 | **2.52** |
| Cadastro | 2 | 2 | 3 | 2.57 | 3 | 3 | 3 | **2.86** |
| Entrar | 2 | 2 | 3 | 2.57 | 3 | 3 | 3 | **2.86** |
| Onboarding 1 | 1 | 1 | 3 | 2.00 | 3 | 3 | 3 | **2.52** |
| Onboarding 2 | 0 | 0 | 2 | 1.27 | 3 | 3 | 3 | **2.08** |
| Onboarding 3 | 1 | 0 | 3 | 1.43 | 3 | 3 | 3 | **2.14** |
| Home | 1 | 1 | 3 | 1.83 | 2 | 3 | 3 | **2.17** |
| Treino · dia de treino | 0 | 1 | 1 | 1.42 | 1 | 3 | 3 | **2.05** |
| Treino · descanso | 1 | 1 | 3 | 2.12 | 1 | 3 | 3 | **2.38** |
| Treino · sem musculação | 2 | 1 | 3 | 2.04 | 3 | 3 | 3 | **2.25** |
| Ficha | 3 | 2 | 3 | 2.26 | 3 | 3 | 3 | **2.29** |
| Alimentação · fechada | 1 | 2 | 2 | 1.93 | 3 | 3 | 3 | **2.39** |
| Alimentação · refeição aberta | 1 | 2 | 2 | 1.83 | 3 | 3 | 3 | **2.29** |
| Alimentação · comi outra coisa | 1 | 2 | 2 | 1.72 | 3 | 3 | 3 | **2.12** |
| Corrida | 1 | 0 | 3 | 2.13 | 3 | 3 | 3 | **2.25** |
| Progresso | 2 | 2 | 2 | 1.87 | 3 | 3 | 3 | **2.09** |
| Conquistas | 1 | 0 | 3 | 1.83 | 3 | 3 | 3 | **2.30** |
| Histórico (exercícios que já fiz) | 2 | 0 | 3 | 2.36 | 3 | 3 | 3 | **2.57** |
| Conta · Mais | 3 | 3 | 3 | 3.00 | 3 | 3 | 3 | **3.00** |
| Conta · Perfil | 2 | 2 | 3 | 1.71 | 3 | 3 | 3 | **2.00** |
| Ajuda | 0 | 0 | 3 | 1.60 | 3 | 3 | 3 | **2.33** |
| /demo/ | 1 | 0 | 3 | 1.67 | 3 | 3 | 3 | **2.29** |

Ti da Home ainda é 2 — o número do anel do cartão de Alimentação a 18,4 px em display (a display nunca desce de 20) e um `<b>` em Big Shoulders 700 — e o do treino é 1: as regras da Fase A não foram tocadas. O anel da Home fica como achado para um próximo lote (não é de treino).

#### O que ficou para `templates/workouts/` (ledger, 27/09 21:57)

- `btn--hoje` (display 16 px, routine.html) e "Compartilhar o que já fiz" (Archivo 14,4) → `btn--primary` canônico;
- 14 `h2` do treino ainda no legado de 20,8 px, mais `hoje__nome`, `agora__confirmar-titulo`, `folha-troca__titulo`;
- cartões `agora`, `agora--com-descanso`, `fim recompensa`, `opcao`, `hoje` → `.card` / `.card--prato`;
- a duração da sessão em `choice-list` (routine.html) → `choice_cards`; depois disso `choice-list` sai do CSS;
- nas regras só de treino: 22 `font-size` crus, 14 entrelinhas cruas e 129 usos de `--espaco-*` (legado datado).
