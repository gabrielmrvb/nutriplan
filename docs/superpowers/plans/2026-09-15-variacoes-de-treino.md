# Variações intercambiáveis de treino — plano (Onda 2 · T2.1)

> Um agente. O motor ganha UMA camada (opções por letra) sem perder as
> regras que já tem; a tela passa a mostrar letras, e a pessoa escolhe a
> versão do dia.

**Baseline (15/09/2026, intermediário · 5 dias · 2 grupos):** A1 4 ex/13
séries/36 min e A2 4/13/29 — mesma letra, conteúdos diferentes, dias
"obrigatórios"; B1 19/42, B2 16/40; C 24/60. A ficha explica "uma delas
pode vir mais curta". Capturas em `scratchpad/shots-var/baseline/`.

**Diagnóstico.** `repartir_ocorrencia` reparte o modelo entre as
ocorrências da letra: cada passagem recebe METADE dos exercícios por grupo,
com a dose cheia. O volume semanal fecha, mas cada sessão fica curta e a
nomenclatura A1/A2 diz "dois treinos diferentes". A repartição já é, na
prática, DUAS VERSÕES da mesma letra — o que falta é tratá-las como
intercambiáveis, dar a cada uma o tamanho de uma sessão, e deixar a pessoa
escolher.

## Global Constraints

- Letras no calendário (A · B · C · A · B); nenhum "A1/A2" como dia obrigatório.
- Cada letra oferece até DUAS opções completas e equivalentes: mesmos grupos
  principais, volume por grupo com diferença ≤ 1 série, duração estimada
  com diferença ≤ 5 min, ≥ 50 % dos exercícios distintos, cada grupo
  principal presente nas duas. Sem catálogo para isso, UMA opção — e a
  limitação registrada com números.
- Volume semanal: uma opção por ocorrência da letra; a repetição da mesma
  opção em todas as ocorrências fica ≤ `teto_semanal_de(user)` (pior caso
  por grupo: Σ ocorrências × max(opções)). Nunca somar as duas opções.
- Sessão completa: alvo de 15–18 séries e o tempo perto de 60 min dentro do
  teto da pessoa; versão rápida derivada da opção escolhida por
  `escolher_para_o_tempo` (≤ 40 min), preservando principais e ordem.
- Complementares continuam separados e nomeados.
- Regras intocadas: teto semanal, três travas do aparo, 4/4/3/3, cinco
  camadas do tempo, frequência, nível, zero dias, sem horário, validação de
  séries/reps, `ExerciseLog` por exercício e data (histórico intacto).
- Migração aditiva: `SessionExercise.opcao` (default 1) e
  `EscolhaDeTreino`; nada é apagado; plano antigo ativo é remontado pela
  conferência de prescrição (como toda mudança de motor), plano ajustado
  (`customized_at`) fica como está e continua legível.
- Conta demo intocada em produção; QA com conta descartável criada pela
  interface e removida pela tela.

## Arquitetura

- `workouts/opcoes.py` (puro): `montar_opcoes(itens, principais)`,
  `preencher_ate_a_faixa`, `aparar_opcoes`, `equivalentes`, `versao_rapida`.
- `services.prescrever_opcoes(sessoes, modelos, teto, teto_semanal)` →
  `{(sessao.pk, opcao, exercise_id): (series, item)}`; `prescrever_semana`
  vira a projeção da opção 1 (compatibilidade); `create_routine` grava
  `opcao`; `_prescricao_confere` compara com `opcao`.
- `EscolhaDeTreino(user, date, session, opcao, versao)` — a opção executada
  em cada dia; `opcao_recomendada(user, session)` = a menos usada
  recentemente; `estado_do_treino` lê a escolha do dia (ou a recomendada) e
  monta `itens` da opção (rápida quando pedida).
- Telas: painel com um cartão por LETRA; ficha com as duas opções lado a
  lado, "Recomendada hoje", Completo/Rápido, "Começar esta opção" (POST);
  execução com "Treino A · Opção 2"; troca depois da primeira série pede
  confirmação e não apaga nada.

## Tarefas

1. Modelo + migration (`opcao`, `EscolhaDeTreino`, propriedades da sessão).
2. `opcoes.py` + `prescrever_opcoes` + `create_routine`/conferência + testes
   dos cinco perfis (`workouts/test_opcoes.py`).
3. Estado do treino por opção; escolha/recomendação; versão rápida; série
   grava a escolha; troca com confirmação.
4. Painel, ficha, execução, compartilhamento (`resumo_da_sessao`) — templates.
5. Adaptar testes que assumiam A1/A2 (agente auxiliar, contrato escrito).
6. Sabotagens, revisão adversarial, QA local, suíte, push, deploy, QA prod.

## Executado — 15/09/2026

Tarefas 1–5 feitas. Decisões que a medição forçou, com o motivo:

- **tantas opções quantas ocorrências (mínimo duas)**: com a letra 3× na
  semana, duas opções de meio modelo davam 1,5 modelo no pior caso e o teto
  esvaziava as duas; três opções de um terço fecham no modelo;
- **a régua de equivalência é o volume DIRETO** (o secundário da flexão
  desequilibrava ombro e core sem ser exercício de ombro);
- **equilibrar dá antes de tirar** (tirar primeiro deixava o tríceps em duas
  séries nas duas opções), e o teto é conferido de novo depois;
- **a repartição começa pela outra opção a cada grupo** e **a concessão num
  exercício compartilhado é espelhada** — sem isso, três compostos numa opção
  e um na outra (12 min), e o crucifixo saindo de uma opção só;
- **faixa de séries por nível** (12–15 / 15–18 / 16–20), lida do teto semanal;
- **`prescrever_opcoes(teto=None)` é sem relógio**; a faixa "livre" vira 65
  min em `teto_completo_de` antes de chegar ao motor;
- a letra que não fecha as réguas volta ao modelo INTEIRO (não à metade);
- **limitação medida**: a 7 dias em ABC o peito fica com 3 exercícios
  distintos na semana (o quarto, compartilhado pelas três opções, não cabe no
  teto); o contrato 4/4/3/3 vale de 3 a 6 dias. Sessões de "peito e
  tríceps" têm 4 exercícios por opção porque o catálogo tem 4 peitos e 3
  tríceps (BACKLOG diz o que falta).

Números (intermediário, 60 min): 3 dias A 13/13 séries ~32 min, B 19/19,
C 22/24 ~50–54 min; 5 dias A 13/14, B 17/18, C 22/24; 4 dias em ABC A 16/16
~40 min, B 20/19, C 20/20; 6 dias A 12/13, B 17/18, C 22/23; 7 dias A três
opções de 7 séries ~20 min, B 17/18, C 21/23; 2 dias A uma opção (25 séries
~59 min), B 15/13. Testes adaptados por agente auxiliar (contrato em
`scratchpad/var_contrato_testes.md`): 236 falhas → 0, nenhum apagado; três
achados do auxiliar viraram as regras acima.

