# Missão: sequência por presença — "qual treino é hoje"

**Decisão do dono, 24/09/2026.** "Qual treino é hoje" passou a sair da
SEQUÊNCIA REALIZADA — a letra seguinte à ÚLTIMA FEITA (série registrada) —, não
da posição no calendário. A pessoa escolhe outra letra, e faltar um dia não
avança nada. Substitui a doutrina de 17/09 ("a letra sai da POSIÇÃO; pulado
conta").

Branch `treino/sequencia-por-presenca`. Base `origin/main` (mesclado até
`b4258fe`). Publicação: PR → fila.

## O que a pessoa vê
- **"Treino de hoje" é o próximo do que ela fez.** Pulou a quarta? Na quinta o
  app abre com o treino de quarta, não com o seguinte — como na academia.
- **Vem marcado "recomendado"** (é sugestão), e some quando ela escolhe.
- **"Fazer outro treino"**: um toque para fazer outra letra. Trocar depois de
  já ter registrado série hoje pede confirmação e não apaga nada.
- **Aviso, nunca bloqueio**: escolher uma letra cujo grupo caiu <48h mostra uma
  linha, e ela faz assim mesmo.
- **A tira da semana é uma projeção**: feito · pulado · hoje · futuro.

## Como está feito (engine)
- `services.sequencia_do_treino` — a leitura única (UMA consulta) da sequência
  feita: `SequenciaDoTreino.recomendada()`/`.contagem(letra)`.
- `usa_presenca(plan)` = `not is_customized`: plano com rotação E plano de antes
  da rotação entram; só o customizado à mão fica preso ao dia da semana.
- `letra_do_dia`/`sessao_do_dia` — escolha do dia → recomendada; `variacao_do_dia`
  — a opção (1/2) por presença (contagem da letra). `sessoes_da_semana` — a
  projeção. `posicao_no_ciclo`/`inicio_do_ciclo` saem da decisão da letra
  (ficam no banco como histórico).
- `registrar_escolha_de_letra` + `EscolherLetraView` (`POST /treino/letra/`);
  `aviso_de_treino_repetido`.
- `WorkoutView` separa ESTRUTURA (programa, volume, total, "Dias de treino") da
  PROJEÇÃO (a tira) e do RECOMENDADO (hoje) — a projeção reordena as letras e
  não pode contar o total da semana.

## O que NÃO mudou (com teste provando)
- Gerador, dourado (`test_ficha_de_verdade`), médias do `TREINO.md`, teto por
  letra, gate-por-letra — intactos. `test_rotacao.OVolumeMedioEmTresSemanasTests`
  mede a média sobre a SEQUÊNCIA IDEAL (a pessoa fazendo o recomendado em ordem),
  que é a mesma distribuição de antes (cada letra 5× em 3 semanas).
- Nenhuma ficha existente é remontada: a presença é LEITURA
  (`test_sequencia.ApresencaNaoRemontaAFichaTests`, retrato das linhas
  antes/depois).
- Ofensiva e "dia mensurável": inalterados.

## Decisões que tomei sozinha (DECIDA E REGISTRE)
- **usa_presenca = not is_customized** — plano antigo entra na regra nova sem
  remontar; o customizado à mão fica preso ao dia (a pessoa arranjou os dias).
- **A opção (1/2) também por presença** (contagem da letra) — coincide com o
  calendário quando nada é pulado, por isso o dourado fica intacto.
- **Sem coluna nova** em `EscolhaDeTreino`: a letra escolhida mora em
  `escolha.session.label`.
- **Orçamento da leitura do exercício 11 → 12** (a leitura da sequência, UMA
  consulta constante).
- **`tornar_hoje` põe a letra em hoje pela ESCOLHA do dia** (`EscolhaDeTreino`
  sem série), NÃO fabricando um treino feito — correção do dono antes do PR:
  registrar a letra anterior como feita inventaria um treino que a pessoa não
  fez e sujaria histórico, recordes e a sequência. A opção pinada é `opcoes[0]`,
  = a variação de uma letra sem histórico. Teste próprio prova: nenhum
  `ExerciseLog` novo, letra do dia = a pedida.
- **Achados do revisor aplicados**: (1) orçamento do painel — `aviso` e
  `preparar_dia` recebem `sessoes`/`seq`/`escolha` já carregados (uma leitura
  da escolha, uma da sequência); (2) `eh_hoje` em plano customizado com letra
  repetida passa a ser por DIA, não por letra; (3) `registrar_escolha` limpa
  `encerrado_em` ao trocar de letra (o "Encerrar" de A não herda para B);
  (5) chave de contexto `outras`, morta, removida. (4) o ramo "hoje" do aviso
  é inalcançável (`date__lt=dia`) — o aviso olha ONTEM (<48h), não o
  mesmo-dia-mais-cedo; aceito.
- **agora.html (seletor na execução) DEFERIDO**: a sessão `execucao` está
  reescrevendo o sticky de agora.html AGORA; o painel já deixa escolher e a
  execução já ABRE o recomendado pelo engine. O seletor da execução fica para
  um follow-up (colisão evitada).

## Provas
- [EXECUTADA] **Suíte de `workouts` COMPLETA verde: 1397 testes OK** (3 skip, 1
  expectedFailure nomeado — o peso do corpo do dourado), local nesta máquina.
  Testes dirigidos: `test_sequencia` (novo), `test_ficha_unica` e `test_rotacao`
  reescritos à presença, `test_escolher_letra` e `test_aviso_repetido` novos,
  os 6 arquivos que usam `tornar_hoje`, `test_exercicio_leitura` /
  `test_divisao_transparente` / `test_treino_texto_verdadeiro` ajustados. Cada
  peça de engine nasceu por TDD (RED antes do GREEN).
- [EXECUTADA] **Sabotagem 2/2 vermelha.** (1) `recomendada()` devolvendo sempre
  a 1ª letra → `test_apos_a_e_b_feitas_recomenda_c` e
  `test_pular_um_dia_nao_avanca_a_letra` FALHAM. (2) `total_sets` somando a
  PROJEÇÃO em vez da estrutura → `test_o_numero_exibido_e_mesmo_a_soma_da_semana`
  FALHA. Reverti as duas; nenhuma entrou em commit.
- [OBSERVADA] Browser QA (navegador embutido, `/demo/treino/`, 390 escuro e
  1280 claro): painel com "TREINO DE HOJE · RECOMENDADO", "Fazer outro treino"
  (formulários letra B/C, ação `/treino/letra/`, 59 px de alvo), a tira com os
  dias pulados em "·" e o de hoje destacado (DOM=A com contorno), o cartão de A
  marcado "HOJE", "99/73 séries por semana" (o total da ESTRUTURA), "PRÓXIMO
  TREINO A" no dia de descanso, e a EXECUÇÃO abrindo o recomendado (Treino A).
  Sem rolagem horizontal. O selo "RECOMENDADO" e as ações confirmadas por
  `javascript` no DOM (duas `<form>` para `/demo/treino/letra/`).
- [LIMITAÇÃO] Não provei em PRODUÇÃO com conta descartável: as regras de
  operação desta sessão proíbem criar conta e digitar senha. O caminho logado
  (painel do dia com o card de treino) foi visto no `/demo/treino/` dando ao
  Carlos um dia de treino hoje (dado fictício, revertido pelo `seed_demo`); o
  caminho de gente será provado pelo E2E do lote no staging, e o QA de produção
  fica no que o `/demo/` mostra.

## O que preciso de você
nada.
