# Treino no estado da arte — plano de execução

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline, com checkpoints) sob o protocolo `nutriplan-missao`. Steps use
> checkbox (`- [ ]`) syntax for tracking. Subagente só em tarefa de arquivos
> disjuntos; `workouts/services.py`, `templates/workouts/agora.html` e
> `static/css/app.css` são serializados.

**Goal:** Fechar o que cerca a SÉRIE na hora em que ela acontece — demonstração
a um toque em qualquer tela, instrução de esforço, sugestão de carga que sobe
com razão escrita, recorde na hora, foco preservado — sem tocar na REGRA do
motor de prescrição, que a pesquisa de 13/09/2026 mediu como estado da arte.

**Architecture:** Django 5.2, templates servidos, `app.css` único, JS sem build
(`pwa.js`/`fila.js`). Toda mudança é apresentação sobre dado que `load_history`
já carrega numa consulta, mais UMA rota GET de leitura e UMA função pura de
progressão. Zero migration nas ondas 1 e 2; a onda 3 acrescenta chaves ao
`exercises.json` e ao seed, sem coluna nova.

**Tech Stack:** Django 5.2.17 · PostgreSQL · agent-browser 0.37.1 (QA) · Render.

**Spec:** `scratchpad/pesquisa-treino/brief-treino.md` (13/09/2026; 52 agentes,
18 lacunas, 10 vivas, 4 parciais, 4 refutadas) + quatro decisões do dono em
13/09: poster compacto no topo da execução; rota de leitura do exercício; dupla
progressão após UMA sessão completa; ferramenta de curadoria dos 35 vídeos.

## Global Constraints

- O MOTOR NÃO MUDA DE REGRA (`prescrever_semana`, tetos, camadas, descanso).
  Refutado ou adiado pelo brief: iframe no topo (L02), AB para 4 dias (L09),
  revisão semanal/retenção (L14), troca de exercício (L16), descanso 80→90
  (L11), trava por ocorrência (L12.2). Não reabrir aqui.
- Continuam verdadeiras e guardadas por teste: "nada que se use DURANTE a
  série mora na ficha" (`test_lista_de_hoje.py:100-107`), "a ficha de outro
  dia não executa" (`test_fluxo_do_treino.py:840`), UM iframe por tela
  (`test_lista_de_hoje.py:306`, `test_video_direto.py:459`), escolha estrita
  de exercício (404, sem fallback), `op_id` descartado na captura offline,
  `dia` no corpo, `fila.js`/`sw.js` comparados por teste.
- Sugestão de carga: prioridade hoje > mesma série anterior > melhor anterior
  (`test_hoje_manda_na_sugestao`); NUNCA número sem histórico; a progressão só
  age COM histórico completo.
- `services.py` não pode conter a string `equipment`
  (`test_capacidade_de_ambiente.py:622-633`).
- Mobile-first: medir y de "Concluir série" em 320×568, 360×800, 375×667,
  390×844, 430×932 ANTES e DEPOIS de cada item que soma linha acima do CTA
  (T1, T2, T9). A régua é a decisão de 30/08 (CTA na dobra a 360×800).
- Nenhum timestamp de vídeo é inventado: só entra o que o dono assistiu.
- Higiene: conta de QA local (`qa-redesign-treino@local.invalid`, pk 1176),
  dados controlados e restaurados; demo pública intocada; `git add` por
  caminho; `artifacts/` fora.
- Cadeia por onda: dirigidos → sabotagem → QA agent-browser (5 larguras) →
  `check` → `makemigrations --check` → `git diff --check` → commit por unidade
  → push pelo `pre-push` (suíte completa, ~27 min) → deploy provado por sinal
  observável → `/saude/` → smoke.

---

## Onda 1 — só código, dado existente (8 tarefas, 1 push)

### T1 (L05): a instrução de esforço volta à execução

**Files:** Modify `workouts/models.py:729-745` (`intensidade`),
`workouts/services.py` (novo `instrucao_de_esforco`), `templates/workouts/agora.html`
(sob `.series__titulo`), `static/css/app.css` (`.series__esforco`), Test:
`workouts/test_esforco.py` (novo).

**Interfaces:** Produces `services.instrucao_de_esforco(item, serie, experiencia) -> str`;
`estado_do_treino` grava `item.esforco` para a `proxima_serie`.

- [ ] **Step 1: teste que falha** — `workouts/test_esforco.py`:
  (a) composto + intermediário → contém "1 a 2 repetições na reserva";
  (b) composto + iniciante → contém "2 repetições" e NÃO contém "falha";
  (c) isolador, série 1 de 3 → "última série" e "reserva"; série 3 de 3 →
  "até a falha"; (d) `measure == seconds` → "técnica" e nem "falha" nem
  "reserva"; (e) `experiencia == ""` → mesmo texto do intermediário;
  (f) a página `/treino/agora/?exercicio=<id>` da conta de teste contém
  `class="series__esforco"` com o texto de (a) — ancorado na classe com aspas.
- [ ] **Step 2: rodar** → vermelho (`instrucao_de_esforco` não existe).
- [ ] **Step 3: implementar** — função pura em `services.py` ao lado de
  `_sugestao_de_carga`; `intensidade` do modelo passa a delegar para ela com
  `serie=None, experiencia=""` (texto neutro, sem série); `estado_do_treino`
  lê `perfil.experiencia` UMA vez (já lê para o teto — reaproveitar) e grava
  `item.esforco`. Template: `<p class="series__esforco">{{ atual.esforco }}</p>`
  logo abaixo de `.series__titulo`, `--texto-xs`/`--text-dim`, sem `<b>`.
- [ ] **Step 4: verde**; sabotagem: trocar "reserva" por "" em (a) → vermelho.
- [ ] **Step 5: medir y do CTA** nas 5 larguras (antes/depois) com o `ab.sh`; anotar.
- [ ] **Step 6: commit** `Execução: a instrução de esforço volta, por série e por nível`.

### T2 (L06): pastilha com kg × reps e "antes", uma frase de sugestão só

**Files:** Modify `workouts/services.py:2236-2251` (set_rows ganha
`anterior`/`anterior_reps`; vira `linhas_de_serie(item, load)` e
`views.set_rows` passa a chamá-la — uma cópia só), `workouts/views.py:82-104`,
`templates/workouts/agora.html` (pastilha e `.agora__anterior`), CSS
`.series__reps`, `.series__antes`. Test: `workouts/test_pastilha.py` (novo).

- [ ] **Step 1: teste que falha** — com log de ontem (60 kg × 10 na série 2)
  e de hoje (62,5 × 9 na série 1): a página contém, na pastilha 1,
  "62,5 kg × 9"; na pastilha 2, "antes 60 × 10"; a frase de sugestão cita o
  MESMO número do campo `weight_kg` (ler `value="..."` e procurar
  `Sugestão: <b class="num">` com o mesmo valor); bodyweight → pastilha sem
  "kg"; `reps=None` no log → só "62,5 kg".
- [ ] **Step 2: vermelho.** **Step 3:** implementar; remover
  `previous`/`previous_reps` (mortos). **Step 4: verde**; sabotagem: apagar
  `anterior` da linha → vermelho. **Step 5:** medir a fileira a 320 px (sem
  quebra de pastilha, sem overflow). **Step 6: commit.**

### T3 (L07): concluir e desfazer devolvem ao exercício em foco

**Files:** Modify `workouts/views.py:682-733` (`ConcluirSerieView.post`),
`templates/workouts/agora.html` (hidden `exercicio` no form de série E no de
desfazer com `atual.exercise_id`; `.agora__proximo` vira `<a>`; "← Ficha" no
`.agora__head`). Test: `workouts/test_foco_na_execucao.py` (novo).

- [ ] **Step 1: teste que falha** — (a) POST série do 3º exercício com
  `exercicio=<id3>` e série pendente → 302 para `/treino/agora/?exercicio=<id3>`;
  (b) fechou a última série → 302 sem parâmetro; (c) desfazer com
  `exercicio=<id_em_foco>` e `exercise_id` de OUTRO exercício → volta ao foco;
  (d) `exercicio=abc`/ausente → 302 sem parâmetro, nunca 404; (e) a página
  tem `<a class="agora__proximo-link"` com `?exercicio=<próximo>`; (f) `<a`
  com `href` da ficha da sessão de hoje no `page-head`; (g) contrato da fila:
  o hidden viaja no corpo (teste existente de captura continua verde).
- [ ] **Step 2: vermelho. Step 3:** implementar (`_destino_em_foco(request)`:
  int válido e ainda com série pendente hoje → `?exercicio=`; senão redirect
  puro). **Step 4:** verde; sabotagem: redirect sem parâmetro → vermelho.
  **Step 5: commit.**

### T4 (L15): recorde na hora, na rota que a execução usa

**Files:** Modify `workouts/services.py:1985-2040` (`load_history` devolve
`recorde_anterior`: maior `weight_kg` em datas < hoje), `workouts/views.py:682-733`
(`avaliar(request.user, hoje=dia)` + `anunciar` só no ramo de gravação),
`templates/workouts/agora.html` (linha "recorde: X kg × Y" e a palavra
"recorde" na pastilha que supera), `views.py:498-505` e docstring de
`achievements/services.py:3-16` (texto). Test: `workouts/test_recorde_na_hora.py`.

- [ ] **Step 1: teste que falha** — (a) histórico 60/62,5/65 → página mostra
  "recorde" com "65"; (b) série de hoje a 67,5 → pastilha contém "recorde";
  (c) POST série 67,5 cria `Conquista` slug `recorde` chave `<id>:<dia>`
  (dia do corpo, não `localdate`); desfazer NÃO avalia; (d)
  `assertNumQueries` da execução: medir ANTES (escrever o número no teste) e
  garantir que depois é o mesmo.
- [ ] **Step 2–4:** vermelho → implementar → verde; sabotagem: remover a
  chamada de `avaliar` → (c) vermelho. **Step 5: commit.**

### T5 (L17a): o Progresso não arredonda 2,5 kg para um número que não existe

**Files:** Modify `templates/plans/_progresso_treino.html:63-67`
(`floatformat:'-2'`). Test: `plans/test_progresso.py`.

- [ ] **Step 1:** teste: cargas 60 → 62,5 renderizam "60 → 62,5 kg" e "+2,5".
- [ ] **Step 2–4:** vermelho → uma linha → verde. **Step 5: commit** (junto de T6, T7, T8).

### T6 (L18): peso do corpo sem carga obrigatória; Prancha em segundos

**Files:** Modify `templates/workouts/agora.html:245-270` (`required` e
placeholder condicionais a `atual.exercise.equipment != 'bodyweight'`; rótulo
"Segundos" e `aria-label` quando `atual.measure == 'seconds'`; linha 157
deixa de concatenar " reps"), `workouts/views.py:727-731` (vazio → `0` SÓ
quando `exercise.equipment == 'bodyweight'`). Test: `workouts/test_peso_do_corpo.py`.

- [ ] **Step 1:** testes: POST `weight_kg=""` em Flexão → grava 0; em Supino →
  erro "Carga inválida" e nada gravado; página da Prancha contém
  `>Segundos<` e não contém "reps" na faixa; página do Supino mantém `required`.
- [ ] **Step 2–4:** vermelho → implementar → verde. **Step 5: commit.**

### T7 (L10): três frases de divisão que afirmavam fisiologia sem fonte

**Files:** Modify `workouts/services.py:92-94` (`SPLIT_NOTE[ABC]`,
`[ABCDE]`), `workouts/models.py:552` (label `Split.ABCDE`). Test:
`workouts/test_treino_texto_verdadeiro.py` (adicionar caso).

- [ ] **Step 1:** teste: `SPLIT_NOTE[Split.ABC]` não contém "metade" nem
  "cansa"; `SPLIT_NOTE[Split.ABCDE]` não contém "quatro"; label ABCDE não
  contém "pontos fracos". **Step 2–4:** reescrever por ORGANIZAÇÃO
  ("empurrar num dia, puxar no outro, pernas no terceiro"; "peito, costas,
  pernas, ombros e braços, um por dia"). **Step 5: commit.**

### T8 (L12.1): a nota diz a causa quando o iniciante tem 4+ dias

**Files:** Modify `workouts/services.py` (`nota_da_divisao` ou onde a nota da
ficha nasce; quando `teto_semanal == 12` e dias > 3, acrescenta "Com o volume
de quem está começando, três dias já entregam a semana inteira — os outros
ficam mais curtos de propósito."). Test: `workouts/test_perfis_de_qa.py`
(caso iniciante 5 dias contém a frase; intermediário 5 dias não contém).

- [ ] **Step 1–4:** teste → vermelho → implementar → verde. **Step 5: commit.**

### Fechamento da onda 1
- [ ] Sabotagens registradas (uma por tarefa, acima) todas vermelhas e restauradas.
- [ ] QA agent-browser: execução nas 5 larguras com dado controlado (conta
  1176: 1 série registrada e desfeita ao fim; zero `ExerciseLog` ao terminar).
- [ ] `check`, `makemigrations --check`, `git diff --check`, B9, fetch, push
  pelo `pre-push`, deploy provado (`class="series__esforco"` no HTML de
  `/demo/treino/agora/` num dia de treino do demo, ou o CSS servido contendo
  `.series__esforco`), `/saude/`, smoke.

---

## Onda 2 — as decisões do dono (4 tarefas, 1 push)

### T9 (L02 corrigida): poster compacto acima das pastilhas

**Files:** Modify `templates/workouts/agora.html` (novo `<div class="agora__poster"
data-poster data-tipo=... data-src=... data-quadros=...>` entre `.agora__topo`
e `.series`; `.agora__media` de baixo do botão SAI; `.agora__cue` sobe para
logo abaixo do poster), `static/css/app.css:5857-5890` (`.agora__poster`
4:3, `max-height: 9rem`, botão "toque para ver o vídeo" 44 px), JS no fim de
`agora.html` (toque monta `<iframe>`/`<video>` no lugar, com o mesmo padrão
da anatomia: cria no toque, destrói ao fechar; nunca `class toggle`).
Tests: `workouts/test_poster.py` (novo) + ajustar `test_lista_de_hoje.py:306`,
`test_video_direto.py:459` (UM iframe continua valendo: zero no HTML servido,
um depois do toque — o teste de servidor mede zero `<iframe` e a presença de
`data-src` com o id do vídeo).

- [ ] **Step 1: medir ANTES** — y de "Concluir série" e y da mídia nas 5
  larguras, salvar em `scratchpad/poster-antes.txt`.
- [ ] **Step 2: teste que falha** — página tem `class="agora__poster"` ANTES de
  `class="series"` (índice), `data-src` contém o id do vídeo, zero `<iframe`
  no HTML, `<img` com `frames.0` e `alt`, botão com texto "vídeo"; o `cue`
  vem antes do formulário.
- [ ] **Step 3: implementar. Step 4: verde.** Sabotagem: mover o poster para
  depois do form → vermelho.
- [ ] **Step 5: medir DEPOIS** — CTA na dobra a 360×800 e 390×844; poster
  ≤ 150 px; anotar as 5 larguras. Se o CTA sair da dobra a 360×800, reduzir o
  poster (`max-height`) antes de qualquer outra coisa.
- [ ] **Step 6: QA no navegador** — toque monta o iframe (contar 1), fechar
  destrói (0); reduced-motion respeitado nas fotos alternadas.
- [ ] **Step 7: commit** com as medições na mensagem; atualizar o comentário
  de `app.css` da decisão de 30/08 ("mídia abaixo do botão") com a medição nova.

### T10 (L01): a rota de leitura do exercício, e o nome como porta

**Files:** Create `templates/workouts/exercicio.html`; Modify
`workouts/urls.py` (`path("exercicio/<int:exercise_id>/", ExercicioView, name="exercicio")`),
`workouts/views.py` (`ExercicioView(OnboardingRequiredMixin, TemplateView)`:
`get_object_or_404(Exercise, pk=..., is_active=True, sessions__session__plan__user=user, sessions__session__plan__is_active=True)` — confirmar o
related_name real de `SessionExercise`), `templates/workouts/_item_da_ficha.html`
(nome vira `<a class="ficha-item__nome" href="{% url 'workouts:exercicio' item.exercise_id %}">` em QUALQUER dia; na linha de hoje o "Fazer" continua `<a>` para a execução — dois alvos de 44 px, medidos a 320), `templates/workouts/agora.html` (`<h1>` ganha o link), CSS.
Tests: `workouts/test_exercicio_leitura.py` (novo); ajustar
`test_fluxo_do_treino.py:840` (continua sem `?exercicio=` fora do dia; ganha
`href="/treino/exercicio/<id>/"`).

- [ ] **Step 1: teste que falha** — (a) GET da rota para exercício do plano
  ativo → 200, contém o id do vídeo, o `cue`, "também trabalha"; (b) zero
  `<form`, zero `name="weight_kg"`, zero `data-descanso`; (c) exercício de
  OUTRA conta → 404; exercício ativo fora do plano da pessoa → 404;
  (d) ficha de OUTRO dia contém `href="/treino/exercicio/<id>/"` para cada
  item e NÃO contém `?exercicio=`; (e) ficha de hoje contém os dois links;
  (f) execução: `<h1` contém o link; (g) uma consulta por exercício, medida.
- [ ] **Step 2–4:** vermelho → implementar (o poster de T9 vira parcial
  `_demonstracao.html` usado nas duas telas: uma cópia) → verde. Sabotagem:
  tirar o filtro de dono → (c) vermelho.
- [ ] **Step 5:** QA: ficha de sexta numa terça → tocar no nome → vídeo; alvos.
- [ ] **Step 6: commit.**

### T11 (L04): dupla progressão com razão escrita

**Files:** Modify `workouts/services.py` (nova `proxima_carga(item) ->
Sugestao(valor, estado, razao)` pura; `estado_do_treino` grava
`item.progressao`), `templates/workouts/agora.html` (a frase "Sugestão" passa
a ler `atual.progressao` — SUBIR: "Fechou 3×10 na última vez — sugestão
62,5 kg"; MANTER: "Faltam 2 reps na série 3 para subir"), campo `weight_kg`
pré-preenchido com o valor SUGERIDO só na série 1 do exercício hoje (nas
seguintes vale hoje > anterior, sem mudança). Tests: reescrever
`ACargaAnteriorNaoViraRecomendacaoTests` para "só sobe com razão escrita e
nunca sem reps completos" mantendo os cinco casos; novo
`workouts/test_dupla_progressao.py`.

Regra (decisão do dono, 13/09): SUBIR quando TODAS as séries prescritas
(`>= item.sets`) da ÚLTIMA data anterior têm `reps >= rep_max`
(`measure == reps`, `equipment != bodyweight`, e reps anotadas — não
prefill: prefill é copiado por `_sugestao_de_reps`, então a regra exige que
`reps` tenha vindo do POST; hoje o modelo não distingue → tratar como
condição: `reps == rep_max` em TODAS as séries E carga igual em todas —
documentar o limite e medir uso antes de refinar); degrau +2,5 kg absoluto
para grupo superior (peito, costas, ombro, braços) e +5 kg para inferior
(quadríceps, posterior, glúteo, panturrilha), arredondado a múltiplo de 2,5;
MANTER caso contrário, com a razão ("faltam N reps na série K"); sem
histórico completo (menos séries anotadas que prescritas) → sem frase.

- [ ] **Step 1: teste que falha** — casos: 3×10/10/10 rep_max 10 a 60 kg →
  SUBIR 62,5; perna 3×12 a 80 → 85; 10/10/9 → MANTER "faltam 1 rep na série 3";
  só 2 de 3 séries anotadas → sem sugestão; bodyweight → sem sugestão; dia
  atual já com série → não muda o comportamento hoje > anterior.
- [ ] **Step 2–4:** vermelho → implementar → verde. Sabotagem: `>=` vira `>`
  → vermelho. **Step 5: commit.**

### T12 (L17b): histórico do exercício na rota de leitura

**Files:** Modify `workouts/views.py` (`ExercicioView` ganha as últimas 8
datas: `ExerciseLog.objects.filter(user, exercise).order_by("-date","set_number")`,
limitado no Python a 8 datas — UMA consulta), `templates/workouts/exercicio.html`
(`<dl class="data-list">`: "03/09 · 60 × 10, 10, 9"; recorde = maior carga).
Test: em `test_exercicio_leitura.py` (`assertNumQueries` medido; 9ª data não
aparece).

- [ ] **Step 1–4:** teste → vermelho → implementar → verde. **Step 5: commit.**

### Fechamento da onda 2
- [ ] Sabotagens, QA nas 5 larguras (execução com poster, ficha de outro dia →
  leitura, execução → leitura pelo título), `check`, `makemigrations --check`,
  `git diff --check`, push, deploy provado (`/demo/treino/exercicio/<id>/`
  responde 200 com o id do vídeo), `/saude/`, smoke; conta 1176 com zero
  `ExerciseLog` ao fim.

---

## Onda 3 — ferramenta de curadoria dos vídeos (1 tarefa + trabalho humano)

### T13 (L03): início/fim do vídeo entram pelo catálogo, e o teste vira catraca

**Files:** Modify `workouts/data/exercises.json` (chaves opcionais
`video_start`, `video_end`, ausentes hoje), `workouts/management/commands/seed_workouts.py:106-125`
(`defaults` ganham `video_start_seconds`/`video_end_seconds` quando as
chaves existem — e SÓ então, para não apagar valor gravado pelo admin),
`workouts/test_treino_v4.py:323-330` (`test_nenhum_timestamp_foi_inventado`
vira `test_os_recortes_conferidos_nao_diminuem`: a contagem de exercícios com
`video_start` no JSON é `>= CONFERIDOS`, constante que sobe a cada rodada de
curadoria — hoje 0 — e todo valor no JSON precisa de `video_conferido_em`
com data ao lado; sem a data, vermelho: é a guarda contra chute).
Create `scratchpad/curadoria-videos.md` (fora do repositório): tabela com os
35 nomes, o link do Short, colunas `início (s)`, `fim (s)`, `tem vinheta?`,
`observação` — para o dono preencher; e `scripts/curar_videos.py` (no
repositório, documentado) que lê um CSV preenchido e escreve as chaves no
JSON com a data, sem tocar em mais nada.

- [ ] **Step 1: teste que falha** — JSON com `video_start` sem
  `video_conferido_em` → vermelho; seed com as chaves grava os dois campos;
  seed sem as chaves NÃO sobrescreve valor existente no banco.
- [ ] **Step 2–4:** vermelho → implementar → verde. **Step 5:** entregar a
  tabela ao dono; nada entra no JSON até ele preencher. **Step 6: commit + push.**

Decisão do loop (registrar no BACKLOG, não implementar agora): aceitar que o
recorte vale só na primeira volta do `loop=1`; `iframe_api` e MP4 próprios
ficam como alternativas escritas, com o custo de cada.

---

## Self-review

- Cobertura da spec: L01→T10, L04→T11, L05→T1, L06→T2, L07→T3, L10→T7,
  L12.1→T8, L15→T4, L17a→T5, L17b→T12, L18→T6, L02corrigida→T9, L03→T13.
  L08 (fetch sem recarga), L11, L12.2, L13, L16: fora, com motivo no brief.
- Placeholders: nenhum "TBD"; onde o nome de um related_name é incerto (T10),
  o passo manda confirmar no modelo antes de escrever o filtro.
- Consistência: `instrucao_de_esforco` (T1) e `proxima_carga` (T11) são
  funções puras em `services.py`; `linhas_de_serie` (T2) substitui as duas
  cópias de `set_rows`; `_demonstracao.html` (T9/T10) é a única cópia do poster.
