# Sequência por presença — "qual treino é hoje" Implementation Plan

> **For agentic workers:** executed INLINE nesta sessão (executing-plans), TDD por tarefa.

**Goal:** O app decide "qual treino é hoje" pela SEQUÊNCIA REALIZADA — o recomendado é a letra seguinte à ÚLTIMA FEITA (série registrada), a pessoa pode escolher outra, e faltar um dia não avança nada.

**Architecture:** `posicao_no_ciclo` (calendário) deixa de decidir a letra. Uma leitura só — a sequência de sessões FEITAS (EscolhaDeTreino com ExerciseLog) — governa: recomendada = letra após a última feita; opção da letra = nº de vezes que ela já foi feita. Quando a pessoa segue a recomendação em ordem, isso COINCIDE com o comportamento de calendário de hoje — então gerador, dourado, médias do TREINO.md e teto por letra ficam intactos. `inicio_do_ciclo` fica no banco só como histórico. Escolha do dia (`EscolhaDeTreino`) vence a recomendação; a letra escolhida mora em `escolha.session.label` (sem coluna nova).

**Tech Stack:** Django 5.2, PostgreSQL, sem framework de CSS.

**Spec:** a missão do dono de 24/09/2026 (substitui a doutrina de 17/09 "O CICLO DA DIVISÃO RODA CONTÍNUO / a letra sai da POSIÇÃO") + CLAUDE.md (seções do Treino).

## Global Constraints

- Relógio de teste CONGELADO (`config/relogio.py`): `timezone.now()`/`localdate()` já vêm congelados; `date.today()`/`datetime.now()` PROIBIDOS em teste; `relogio.congelado_em(dt)` para outro dia. NUNCA `mock.patch` de `localdate` novo — usar `relogio`.
- Gerador, dourado (`test_ficha_de_verdade.py`), tabela do TREINO.md, teto por letra e gate-por-letra (`test_catalogo.py`) INTACTOS.
- Nenhuma ficha existente remontada: teste com retrato das linhas antes/depois (como `test_gluteo`).
- Orçamentos de consulta: a leitura da sequência é UMA consulta, computada uma vez e passada adiante (como `sessoes`/`escolha`). Home 17, painel, execução — sem estourar teto; se subir, medir e escrever a razão.
- pt-BR, `tabular-nums`, vírgula decimal, alvo 44px, nada rola na horizontal.
- DECIDA E REGISTRE: decisões técnicas registradas no relatório; parar só nas 4 condições.

## Decisões registradas
- **`usa_presenca(plan) = plan and not plan.is_customized`** — recomendação por presença vale para plano com rotação E plano de antes da rotação (`inicio_do_ciclo` None, não remontado). Plano CUSTOMIZADO (`is_customized`, hand-edit do assistente extinto) fica preso ao dia da semana, como hoje — não disrupto arranjo manual.
- **Opção (1/2/3) também por presença** — `opcoes[(nº de feitas dessa letra) % len(opcoes)]`. Coincide com o calendário quando nada é pulado; coerente quando é. `variacao_do_dia` some do contrato de "posição"; `test_ficha_unica.py` é reescrito.
- **Sem coluna nova** em EscolhaDeTreino: a letra escolhida é `escolha.session.label`; a opção continua em `escolha.opcao`. (Migration só se um teste provar necessidade.)
- **`ciclo_roda(plan)`** continua existindo para o GERADOR/estrutura (ocorrências, teto, legenda "gira"→reescrita) — não para a recomendação.

---

## FASE A — engine (sem colisão com execucao/pente-fino)

### Task A1: a leitura da sequência realizada
**Files:** Modify `workouts/services.py`; Test `workouts/test_sequencia.py` (novo).
**Produces:** `sequencia_do_treino(user, plan, ate=None, sessoes=None) -> SequenciaDoTreino`; dataclass com `.letras`, `.feitas` (list[(date,label)]), `.ultima_letra()`, `.contagem(letra)`, `.recomendada()`.

- [ ] Teste: sem nenhuma série → `recomendada()` == primeira letra do ciclo; `feitas == []`.
- [ ] Teste: feitas A(seg),B(ter) via EscolhaDeTreino+ExerciseLog → `ultima_letra()=="B"`, `recomendada()=="C"`, `contagem("A")==1`.
- [ ] Teste: A feita, depois C feita (fora de ordem) → `recomendada()=="A"` (após C), não D.
- [ ] Teste: EscolhaDeTreino SEM ExerciseLog (encerrou com zero série) NÃO conta como feita.
- [ ] Teste: EscolhaDeTreino de OUTRO plano (session.plan != plan) não conta.
- [ ] Teste de custo: UMA consulta (`assertNumQueries(1)`), independente do nº de dias.
- [ ] Implementa: query `EscolhaDeTreino.filter(user, date__lt=ate, session__plan=plan).annotate(tem=Exists(ExerciseLog.filter(user, date=OuterRef('date')))).filter(tem=True).order_by('date').values_list('date','session__label')`.
- [ ] Commit.

### Task A2: `letra_do_dia`/`sessao_do_dia` por presença
**Files:** Modify `workouts/services.py`; Test `workouts/test_sequencia.py`.
**Consumes:** A1. **Produces:** `usa_presenca(plan)`; `letra_do_dia(plan, dia, sessoes=None, seq=None)`, `sessao_do_dia(plan, dia, sessoes=None, seq=None)` (assinatura com `seq` opcional; se None, calcula).
- Regra: se há `escolha_do_dia(user, dia)` cuja `session.plan==plan` → letra = `escolha.session.label` (só HOJE/passado, ver A5). Para HOJE sem escolha → `seq.recomendada()`. Para dia FUTURO → projeção (A4). Para dia passado FEITO → a letra feita.
- [ ] Teste: HOJE sem histórico → `letra_do_dia` == primeira letra; `sessao_do_dia().label` idem, vestindo o molde de hoje.
- [ ] Teste: com A,B feitas antes de hoje → hoje recomenda C; `sessao_do_dia` veste C no molde de hoje (pk da linha C, weekday/duração do dia de hoje).
- [ ] Teste: `usa_presenca` False para plano customizado → cai no caminho weekday-tied de hoje.
- [ ] Teste (o CASO do dono): A seg, B ter, NADA qua → qui recomenda C.
- [ ] Implementa; `sessao_do_dia` mantém `_no_dia(da_letra, molde, dia)`.
- [ ] Commit.

### Task A3: opção por presença (`variacao_do_dia`)
**Files:** Modify `workouts/services.py`; Test `workouts/test_ficha_unica.py` (reescrito).
**Consumes:** A1. **Produces:** `variacao_do_dia(plan, dia, sessao, sessoes=None, seq=None)` — opção = `opcoes[(nº feitas da letra antes de `dia`) % len(opcoes)]`.
- [ ] Reescreve `AVariacaoEDoCicloTests`: monta presença (feitas em ordem) e prova A→[1,2] etc.
- [ ] Teste: escolha gravada do dia vence a variação (mantém).
- [ ] Teste: 1 opção só → ela.
- [ ] Implementa (usa `seq.contagem(letra)` + projeção para dias futuros/ficha de outro dia).
- [ ] Commit.

### Task A4: `sessoes_da_semana` vira PROJEÇÃO
**Files:** Modify `workouts/services.py`; Test `workouts/test_rotacao.py` (reescrito), `workouts/test_sequencia.py`.
**Consumes:** A1–A3. **Produces:** `sessoes_da_semana(plan, hoje, sessoes=None, seq=None)` — passado feito→letra feita; hoje→recomendada/escolhida; futuro→sequência a partir de hoje.
- [ ] Teste: plano fresco (nada feito), semana 1 → `["A","B","C","A","B"]` (inalterado).
- [ ] Teste: plano fresco, semana 2 (nada feito) → AINDA `["A","B","C","A","B"]` (não "C..."; o calendário não avança).
- [ ] Teste (o caso do dono): A seg feito, B ter feito, qua não feito, HOJE=qui → tira mostra seg=A(feito) ter=B(feito) qua=(pulado) qui=C(hoje) sex=A(futuro).
- [ ] Implementa: helper `projecao_da_semana` que anda os dias de treino da semana-de-interesse em ordem de data.
- [ ] Commit.

### Task A5: escolher letra do dia + confirmação
**Files:** Modify `workouts/services.py`, `workouts/views.py`, `workouts/urls.py`; Test `workouts/test_escolher_letra.py` (novo).
**Produces:** `EscolherLetraView` (`POST /treino/letra/`, nome `workouts:escolher_letra`), `registrar_escolha_de_letra(user, plan, letra, dia=None, confirmar=False)` retornando `(escolha|None, precisa_confirmar:bool)`.
- Regra: grava `EscolhaDeTreino` com a session canônica da letra + opção por presença. Se já há série hoje e a letra difere da resolvida e não `confirmar` → devolve `precisa_confirmar=True`, não grava.
- [ ] Teste: POST letra=B sem série hoje → escolha gravada (session=linha B), redirect ao painel; sessao_do_dia==B.
- [ ] Teste: com série hoje em A, POST letra=B sem confirmar → não grava, contexto pede confirmação.
- [ ] Teste: com série hoje, POST letra=B confirmar=1 → grava, nada apagado (ExerciseLog de A intacto).
- [ ] Teste: letra inexistente → 404/ignora.
- [ ] Implementa (AcaoDeTela, DESTINOS fechado, sem op_id — estado absoluto por dia).
- [ ] Commit.

### Task A6: aviso "treino repetido" (nunca bloqueia)
**Files:** Modify `workouts/services.py`; Test `workouts/test_aviso_repetido.py` (novo).
**Produces:** `aviso_de_treino_repetido(user, plan, letra_escolhida, dia=None, seq=None) -> str|None`.
- Regra: só quando `letra_escolhida != recomendada` e um `main_group` da letra escolhida foi treinado <48h (sessão feita com esse grupo anunciado). Frase: "{Nome do treino} treina {grupo} de novo; o recomendado hoje é {Nome recomendado}." `None` caso contrário.
- [ ] Teste: escolheu a recomendada → None.
- [ ] Teste: escolheu letra cujo grupo caiu ontem → frase com o nome do treino recomendado.
- [ ] Teste: escolheu outra letra sem grupo recente → None.
- [ ] Commit.

### Task A7: `tornar_hoje` reescrito + os 9 arquivos de teste que o usam
**Files:** Modify `workouts/test_fluxo_do_treino.py` (`tornar_hoje`); os callers só se o contrato mudar (não deve).
**Consumes:** A1–A2.
- `tornar_hoje(user, letra)`: registra a letra ANTERIOR como FEITA ONTEM (EscolhaDeTreino + ExerciseLog em dia anterior) para que a presença recomende `letra` hoje; devolve `sessao_do_dia(plano, hoje)`. NÃO mexe em `weekday` nem `inicio_do_ciclo`.
- [ ] Reescreve `tornar_hoje`; roda os 9 arquivos; devolve a sessão da letra vestida hoje.
- [ ] `sessao_de_hoje(user)` helper: continua `sessao_do_dia(plano, localdate())`.
- [ ] Commit.

### Task A8: reescrever test_rotacao.py à doutrina nova
**Files:** `workouts/test_rotacao.py`.
- Substitui os testes de posição-por-calendário pelos de presença: cycle dá DIREÇÃO; recomendado = após última feita; pular não avança; plano antigo entra na regra nova sem remontar; `OVolumeMedioEmTresSemanasTests.media_por_grupo` passa a medir a SEQUÊNCIA IDEAL (`letras_do_ciclo[k%n]` sobre os dias), preservando as médias do TREINO.md.
- [ ] Reescreve, roda, prova médias iguais às do TREINO.md.
- [ ] Commit.

### Task A9: não remonta ficha + `estado_do_treino`/`proximo_treino` coerentes
**Files:** `workouts/services.py`; Test `workouts/test_sequencia.py`.
- [ ] Teste (retrato das linhas antes/depois, como test_gluteo): abrir painel/execução por presença NÃO altera `SessionExercise` nem `customized_at`; `rotina_invalida`/`_prescricao_bate` inalterados.
- [ ] `proximo_treino` (dia de descanso) usa a projeção por presença.
- [ ] `estado_do_treino` já resolve via `sessao_do_dia` — passa `seq` para não reconsultar.
- [ ] Suíte de workouts verde (dirigida). Commit.

---

## FASE B — contexto das telas (workouts/views.py, sem tocar template)
### Task B1: contexto do painel e da execução
**Files:** `workouts/views.py` (WorkoutView, ModoTreinoView/estado), Test `workouts/test_dia_por_presenca.py` (novo, via `context`).
- [ ] `context`: `recomendada` (bool: hoje é recomendação, não escolha), `outras_letras` (lista {letra,nome,url}), `aviso_treino` (str|None), e a tira já projetada em `week`/`sessions`.
- [ ] Testes de contexto (sem asserção de HTML ainda): recomendado marcado; outras letras presentes; aviso quando aplicável.
- [ ] Commit.

---

## FASE C — templates + CSS + docs (SERIALIZADO com execucao + pente-fino)
### Task C1: routine.html (tira-projeção + "recomendado" + "Fazer outro treino" + aviso)  — após pente-fino pousar
### Task C2: agora.html (recomendado + seletor + aviso) — após execucao pousar
### Task C3: app.css seção nova (estados `--feito`, seletor, aviso) — após os dois
### Task C4: CLAUDE.md (risca "O CICLO DA DIVISÃO RODA CONTÍNUO", escreve a nova) + TREINO.md + CHANGELOG
- Cada um: sabotagem, browser QA (390/1280, 2 temas), depois PR.

---

## Self-review
- Cobertura da spec: 6 partes → A2/A5 (1,2), A6 (3), A4/C1 (4), A2/A9 (5), A9 + "dia mensurável" intacto (6). ✓
- Sem placeholder de código: os testes-chave estão nomeados por comportamento; implementação TDD.
- Consistência de tipos: `seq` (SequenciaDoTreino) atravessa A1→A9; `sessao_do_dia(...,seq=)` e `variacao_do_dia(...,seq=)` mesma assinatura.
