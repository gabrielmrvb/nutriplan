# NutriPlan — Missão Mestre de Implementação · plano de execução

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline, com checkpoints) — subagentes só onde houver tarefas de arquivos
> disjuntos, e nunca dois no mesmo arquivo (regra de propriedade do
> `nutriplan-missao`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar o NutriPlan ao nível definido nas auditorias — mobile-first,
identidade clara e premium, navegação e Áreas como estrutura intencional —
sem recomeçar nada, com deploy por fase e prova em produção.

**Architecture:** Django 5.2 monolito com templates servidos; um `app.css` lido
de ponta a ponta; `pwa.js`/`fila.js`/`corrida.js`/`card.js`; PostgreSQL. Cada
fase termina em software funcionando, testado, publicado e provado com smoke.
O motor de treino, o motor nutricional, a fila offline e os contratos de
migration NÃO mudam de regra; muda a superfície e o que a superfície esconde.

**Tech Stack:** Django 5.2.17 · PostgreSQL 16+ · CSS sem framework · JS sem
build · agent-browser 0.37.1 (QA) · Render (deploy) · Neon (banco).

**Spec:** "NUTRIPLAN — MISSÃO MESTRE DE IMPLEMENTAÇÃO", 81 seções, recebida
inteira em 12/09/2026. O código, o banco, as migrations e os testes são a
evidência (§81); a spec é o contrato. Abaixo, cada seção está mapeada para uma
fase de §72 com o estado REAL medido — ✅ já satisfeito e guardado por teste,
🔧 a fazer, ⛔ depende de fator externo.

## Global Constraints

- Mobile-first (§3): 320×568, 375×667, 390×844, 430; tablet; desktop só
  fallback. Zero rolagem horizontal; alvo 44×44; texto ≥ 11px; CTA acessível
  com teclado aberto; barra de baixo nunca cobre conteúdo.
- Identidade (§4): `#f4f6f5` / `#0c6b40` / folha `≈#43A11B` (medido:
  `#3f9718`, 3:1 como objeto gráfico); premium, limpo, humano; sem cara de
  painel admin; sem cards iguais em série; sem excesso de bordas.
- Navegação (§5): Alimentação · Treino · Progresso · Áreas. Perfil em Áreas.
- Não recomeçar (§2). Dados existentes são sagrados (§66). Compatibilidade
  por camada (§67). Não ressuscitar ideias descartadas (§63).
- Motor de treino e motor nutricional intocados em REGRA; auditados em
  RESULTADO (§16–19) com cinco perfis (§17).
- Gates por fase (§73): dirigidos → sabotagem → QA agent-browser nas quatro
  larguras → suíte completa com `EXIT_REAL` (§75) → `check` →
  `makemigrations --check` → `git diff --check` → commit por unidade coerente
  (§56) → push pelo `pre-push` → deploy provado (§57) → `/saude/` (§58) →
  smoke (§59).
- Higiene (§54–55): conta demo pública nunca tocada por QA; contas de QA
  locais, isoladas, sem fixture no commit; nunca `git add -A`; `artifacts/` e
  `stash@{0}` fora.
- 43 sabotagens continuam 43/43 (§49); se o número mudar, o motivo fica
  escrito aqui. **Mudou, para cima: 43 → 59.** As 43 originais (18 do motor,
  9 do fluxo de treino, 16 da fila/replay) continuam e continuam vermelhas;
  cada guarda nova desta missão trouxe a sua — tema claro (3), faixa de falha
  da fila (1), G17–G20 do Hoje/Progresso/Áreas (4), portão de migration (1),
  primeira passagem em branco (1), coluna única dos cartões (1), lista de
  compras (3: leitura só do dia, rota ignorando o avulso, `name` trocado no
  template), acento na corrida (1), `VERSIONED` (1). Nenhuma entrou em commit;
  todas restauraram byte a byte.

---

## Mapa da spec → fases → estado real (medido em 12/09/2026)

| fase (§72) | seções | estado | evidência / tarefa |
|---|---|---|---|
| **0 Baseline** | §81 | ✅ | reconhecimento feito; `128aa1b` no ar; suítes 1/2/3 e `pre-push` com `EXIT_REAL`; 43/43 sabotagens |
| **1 Contratos e dados** | §13 horário, §14 duração, §15 migrations, §32, §74 | ✅ | `0029` (rede, só vazio) + `0030` (`-- (no-op)`); rotas A/B por execução e em `accounts/test_duracao_portao.py`; `start_time=None` e POST forjado guardados |
| **2 Treino** | §10 tela principal, §11 ficha, §12 execução, §21 drawer | ✅ | três telas; 0/0/1 iframe; seleção estrita → 404; estado preservado (`OFluxoResisteAoUsoRealTests`); sem caixa preta (`agora__sem-media`) |
| | §16 séries/reps, §18 cobertura | ✅ | 5 camadas + devolução de série; 4/4/3/3; zero órfão ≥45 min (`CLAUDE.md`, `sabotagem.py` 18/18); resultado auditado em **T2.1** (`78fd530`) — só órfão em "até 30 min", e nomeado |
| | §17 cinco perfis | ✅ | `workouts/test_perfis_de_qa.py` (`78fd530`) |
| | §19 catálogo, §20 vídeos, §53 100% dos vídeos | ✅ | mapeamento por nome; 35/35 alcançáveis por HTTP (`videos_alcance.py`, 12/09) |
| **3 Navegação e shell** | §5 barra, §33 Perfil em Áreas | ✅ | `accounts/tests.py:657`, `test_areas.py` |
| | §6 Áreas como hub (Conquistas, valor antes do clique, composição assimétrica) | ✅ | **T3.1** (`7f5c018`, `d8df108`): fatos de hidratação/corrida/conquistas/perfil, Perfil largo, orçamento de 8 consultas |
| **4 Alimentação e hidratação** | §9 zerar com confirmação | ✅ | `_agua.html` `<details class="acao-perigosa">`; `test_o_zerar_esta_atras_de_uma_confirmacao` |
| | §7 Hoje: ação atual primeiro, estados | ✅ | **T4.1** (`a007f2c`): só a refeição da vez aberta, futuras atrás de "Ver opções", só A é verde; offline com faixa de falha (`push/test_offline.py`) |
| | §8 alimentação: módulo inteiro | ✅ | **T4.2** no navegador (12/09): registrar A → ✓ verde + saldo 618/2467 + 1/5 → desfazer → 0; histórico; lista. Achados corrigidos: vazio do Progresso (`ae33c0d`), lista (`e8cca30`) |
| **5 Progresso e secundários** | §22 Progresso, §35 conquistas, §36 compras, §39 vazios, §33 blocos do Perfil | ✅ | **T5.1** vazios convidam (`a375544`, `ae33c0d`); §35 vazio diz como ganhar a primeira (auditado, sem alteração); **T5.3** compras: adicionar/remover/marcar/persistir sete dias (`e8cca30`); §33 Perfil já em 11 blocos, do dado corporal à exclusão por último (auditado, zero linhas) |
| **6 Onboarding/auth** | §29 login estrutural, §30 cadastro, §31 onboarding, §32 duração | ✅ | **T6.1** (`8fa213c`); **T6.2** (`39e67b0`): seis passos percorridos a 390px com conta descartável (apagada depois); primeira passagem sem resposta marcada; "Emagrecer" inteiro; §32: duração fora do wizard, `padrao` por omissão (`0030`) |
| **7 Corrida** | §23–27 | ✅ web · ⛔ nativo | **T7.1** (12/09): sem histórico a tela diz a função e a limitação de segundo plano; sem permissão o estado explica (`74dbd52`: frases com acento, `corrida.js` na versão do cache). Nativo continua bloqueado (BACKLOG 421) |
| **8 Segurança/PWA** | §44–45 cache, logout, SW | ✅ | **T8.1** no navegador (12/09): A → sair → B, nada de A; `VERSIONED` cobre todo `asset()` (`74dbd52`) |
| **9 Freemium** | §37 | ✅ | **T9.1** (`3c604a5`): `accounts/gates.py`, `Profile.plano` (`0031`), context processor preguiçoso, 403 por GET e POST; `RECURSOS_PRO` vazio de propósito |
| **10 Polimento** | §64 telas-mãe, §65 microcopy, §41, §42 | ✅ | §64 auditado tela a tela (12/09); §65 corrida (`74dbd52`); §41/§42 guardados por `config/tests.py` (contraste medido, alvos, `prefers-reduced-motion`) |
| **11 QA final** | §47–53, §76 adversarial | ✅ | suíte completa 2.806 verde no `pre-push` (EXIT 0); 59 sabotagens; smoke 30/30 com controle positivo; quatro larguras em produção (`prod-lote3`) |
| **12 Entrega** | §57–59, §79 relatório | ✅ | `128aa1b..ae33c0d` + `74dbd52` em `main`; `/saude/` 200; sinal observável (`id="seus-itens"` no demo); relatório no `BACKLOG.md` |
| fora do alcance | §70–71 marketing/Instagram | ⛔ | não há infraestrutura de marketing neste repositório; token da Meta é bloqueio humano legítimo (§71) |
| decisão do operador | BACKLOG 610 `podar()` | ⛔ | três alternativas materialmente diferentes; recomendação: `build.sh` |

Feito nesta sessão antes deste mapa: **SP1** (`4eeacc1`, Node/agent-browser
no `CLAUDE.md`) e **SP2** (`42ab8e0`, claro-primeiro + `--folha`).

---

### Task T2.1: Cinco perfis de QA, um relatório de prescrição

**Files:**
- Create: `workouts/test_perfis_de_qa.py` (os cinco perfis como teste — não
  como fixture: nascem e morrem na suíte)
- Create (scratchpad): relatório por perfil

**Interfaces:**
- Consumes: `services.create_routine`, `prescrever_semana`, `segundos_da_sessao`.

- [ ] **Step 1: teste que falha** — cinco perfis com `subTest`: (a) mulher
  24 anos 58 kg emagrecer 3 dias iniciante rápido; (b) homem 27 anos 102 kg
  emagrecer 5 dias intermediário padrão (referência); (c) homem 45 anos 88 kg
  manter 4 dias avançado completo; (d) mulher 35 anos 70 kg ganhar massa 6
  dias intermediário padrão; (e) homem 19 anos 65 kg ganhar massa 2 dias
  iniciante livre. Para cada: split esperado (`split_for`), toda sessão com
  ≥2 exercícios, nenhum principal composto abaixo de 3 séries no padrão, teto
  respeitado (`estimated_minutes ≤ MINUTOS_POR_DURACAO[faixa]` quando há
  teto), zero grupo órfão ≥45 min, nenhum exercício repetido na mesma sessão,
  4/4/3/3 de 3 dias para cima.
- [ ] **Step 2: rodar** — o que reprovar é achado de §16/§18, e vira correção
  no motor SÓ com medição escrita (regra do `CLAUDE.md`).
- [ ] **Step 3: commit** `"Cinco perfis de QA provam a prescrição, e não um só"`.

### Task T2.2: 100% dos vídeos alcançáveis

**Files:**
- Create (scratchpad): `videos_alcance.py` — para cada ativo com `video_url`,
  `HEAD`/`GET` no `youtube-nocookie.com/embed/<id>` e no oEmbed do YouTube
  (`https://www.youtube.com/oembed?url=...`), que devolve 404 para id
  inexistente/privado; registrar título devolvido e comparar com
  `titulo_confere`.
- Test: `workouts/test_video_direto.py` já prende título e unicidade; o
  alcance HTTP fica no relatório (rede não entra na suíte).

- [ ] **Step 1: rodar** contra os 35 ativos. **Step 2:** divergência → corrigir
  conscientemente (§20), nunca por substituição automática. **Step 3:**
  registrar total ativo / com vídeo / sem vídeo / inválidos / corrigidos (§53).

### Task T3.1: Áreas vira hub com valor antes do clique

**Files:**
- Modify: `accounts/views.py:928-1010` (`AreasView`), `templates/accounts/areas.html`,
  `static/css/app.css` (`.modulo*`)
- Test: `accounts/test_areas.py`

**Interfaces:**
- Produces: contexto `areas` (Corrida com "última corrida: 5,2 km · 6'10\"/km"
  ou convite; Hidratação com "1.250 de 3.500 ml" e progresso), `ferramentas`
  (Conquistas com "3 ganhas · próxima: 7 dias seguidos"; Lista de compras com
  "12 itens, 4 marcados"; Perfil com objetivo e meta), `mostra_gestao`.
- `achievements.services.resumo(user)` já existe e custa consultas
  constantes (CLAUDE.md); a lista de compras tem `plans/compra.py`.

- [ ] **Step 1: teste que falha** — `/areas/` contém link para
  `achievements:lista` com número de conquistas; módulo de Hidratação com
  `progress`; módulo principal (`modulo--principal`) com tamanho maior na
  grade (composição assimétrica: `grid-column: span 2` só nele); nenhum link
  para os três pilares da barra (já existe); todo módulo ≥ 44px.
- [ ] **Step 2: vermelho.** **Step 3:** view + template + CSS. **Step 4:
  verde.** **Step 5: QA** 320/390 com `qa_larguras.sh`. **Step 6: commit.**

### Task T4.1: Hoje — auditoria por estado, no navegador

- [ ] Estados (§7): sem plano, plano vazio, refeição futura, atual,
  concluída, parcial, offline. Conta local de QA; cada estado produzido por
  dado controlado e restaurado. Registrar por estado: o bloco atual vem
  primeiro? feito parece feito? verde só em estado positivo? saldo afirma
  resultado sem dado? Corrigir o que reprovar, com teste de estrutura.

### Task T4.2: Alimentação — módulo inteiro

- [ ] Percorrer refeição → detalhe → registrar → concluir → histórico →
  recálculo; formulários com teclado; estados vazios. Corrigir e testar.

### Task T5.1–T5.3: Progresso, Conquistas, Compras, Perfil, estados vazios

- [ ] Progresso responde "estou evoluindo?" com o que há (peso, aderência,
  treinos, água, corrida); nada inventado (§22). Conquistas: vazio mostra
  como ganhar a primeira (§35). Compras: adicionar/remover/marcar/persistir
  (§36). Perfil em blocos (§33). Todo vazio explica área, benefício, próximo
  passo (§39).

### Task T6.1–T6.2: Login estrutural, cadastro, onboarding

- [ ] Login: marca + confiança + formulário rápido; `autocomplete`,
  `inputmode`, password manager, loading, erro, recuperação, logout e volta
  (§29). Cadastro curto (§30). Onboarding: pergunta protagonista por passo
  (§31), duração simples e `padrao` por omissão (§32).

### Task T7.1: Corrida — o que é web, o que é nativo

- [ ] Validar GPS web, estados (§26), histórico, share (§28); documentar a
  fronteira nativa (§24–25) sem prometer background em iOS.

### Task T8.1: Cache, logout, troca de usuário — no navegador

- [ ] agent-browser: logar A, navegar, sair, logar B, voltar; nada de A
  aparece; SW não serve página autenticada de outro; `no-store` respeitado.

### Task T9.1: Feature gates centralizados

**Files:**
- Create: `accounts/gates.py` (`Recurso` enum, `tem_acesso(user, recurso)`,
  `PLANO_GRATIS`/`PLANO_PRO` como conjuntos), `accounts/test_gates.py`
- Modify: `accounts/models.py` (`Profile.plano` = `"gratis"` default, sem
  cobrança), migration de campo com default no Python (no-op SQL)

- [ ] Um lugar só decide; template usa `{% if recurso_pro %}` vindo do
  contexto, nunca `if pro` solto; POST/URL de recurso Pro por usuário Free →
  403 com mensagem, testado (§76). Nada de cobrança ativa (§37).

### Task T10.x: Polimento por tela-mãe (§64), microcopy (§65), a11y (§42)

### Task T11: QA final — suíte, 43 sabotagens, perfis, browser (§50), capturas (§51), fluxo do treino (§52)

### Task T12: Entrega — commits, push, deploy provado, `/saude/`, smoke, relatório (§79)

---

## Self-review

- Cobertura: as 81 seções estão na tabela; as não numeradas em tarefa são
  restrições globais (§1–5, §47–49, §54–58, §60–63, §66–69, §73–81).
- Placeholders: tarefas de auditoria (T4, T5, T6, T10) listam o que medir e
  o critério; o código exato nasce da medição, e é por isso que cada uma
  começa por navegador e não por edição.
- Decisões revistas pela spec e registradas: Conquistas volta a Áreas (§6
  supera a nota de 08/09 no BACKLOG).
