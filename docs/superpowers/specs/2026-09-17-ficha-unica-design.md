# Ficha única por letra, troca por exercício e equipamento no perfil — desenho

**Decisão do dono (17/09/2026, escrita):** a pessoa não escolhe entre opção 1
e 2. O motor continua gerando as duas opções equivalentes e as usa para
VARIAR sozinho entre as ocorrências da letra; a interação principal vira a
troca POR EXERCÍCIO ("outras formas", mesmo padrão, filtrado pelo
equipamento do perfil); o perfil ganha a pergunta do equipamento, que
filtra o catálogo antes de gerar; o teste dourado e o gate por letra passam a
valer por perfil de equipamento; a versão rápida sai do seletor e vira ação
discreta no painel, com evento de uso. Este arquivo é o desenho; o plano é
`docs/superpowers/plans/2026-09-17-ficha-unica.md`.

Regras que não mudam: o motor de opções (`workouts/opcoes.py`,
`prescrever_opcoes`) fica como está — equivalência, teto no pior caso,
`ocorrencias_das_letras`; o teste dourado não afrouxa; plano é retrato;
ficha ajustada não é remontada; histórico e contabilidade são por letra +
exercício (`ExerciseLog` é por exercício e data; `opcao` nunca entra numa
conta que a pessoa veja).

## 1. Ficha única por letra: a variação é do ciclo

- **`services.variacao_do_dia(plan, dia, sessao, sessoes)`** decide a opção
  do dia: no plano com rotação, `p = posicao_no_ciclo(inicio, dia, dias)`,
  `n = len(letras)`, ocorrência da letra = `p // n`, opção =
  `sessao.opcoes[(p // n) % len(sessao.opcoes)]` — semana 1 op. 1, semana 2
  op. 2, e assim por diante, seguindo a rotação contínua. No plano preso ao
  dia da semana (antigo ou ajustado): as linhas da mesma letra na semana,
  em ordem, mais as semanas desde a criação do plano — `(semanas ×
  ocorrências_da_letra + índice_da_linha) % len(opcoes)`.
- **`EscolhaDeTreino` vira registro INTERNO da variação**: a primeira
  série do dia grava a opção (o formulário da execução continua mandando
  `sessao/opcao/versao`), e o dia gravado fica pinado — a ficha não muda
  no meio do treino. Sem registro, vale `variacao_do_dia`.
  `opcao_recomendada` (a "menos usada") some: a variação não é preferência.
- **Some da UI**: `EscolherOpcaoView` e a rota `ficha/<id>/escolher/`; os
  formulários "Começar esta opção"; as pílulas "Escolhida hoje" /
  "Recomendada hoje"; "Opção N" nos títulos da ficha e do cabeçalho da
  execução ("Treino A · Peito e tríceps"); "Duas versões disponíveis" nos
  cartões e no painel; o aviso "Opção 1, a recomendada de hoje — trocar de
  opção na ficha"; o parâmetro `?trocar=`. A ficha desenha UMA lista: a da
  variação daquela data (para os outros dias da semana, a variação da data
  deles — `sessoes_da_semana` já veste a data).
- `nomear_ocorrencias` (A1/A2 só quando o conteúdo difere de verdade —
  plano ajustado à mão) e `agrupar_por_letra` ficam.
- **Contabilidade**: `volume_da_semana` continua o pior caso por
  ocorrência (é o teto do motor); painel, ficha e progresso contam por letra
  + exercício e nunca imprimem "opção".

## 2. Troca por exercício: "outras formas"

- **Modelo `TrocaDeExercicio(user, original, substituto, created_at)`**,
  única por `(user, original)`. É customização POR EXERCÍCIO da pessoa —
  vale em toda letra, toda semana, toda opção em que `original` apareça —
  e não toca em `SessionExercise` nem em `customized_at`: a ficha continua
  retrato, a rotação continua, `rotina_invalida`/`_prescricao_bate` não
  enxergam a troca.
- **Aplicação em memória** (`services.aplicar_trocas(user, itens)`): o item
  passa a apontar para o substituto (`item.exercise = substituto`,
  `item.original = original`), com a MESMA dose (séries, faixa, descanso) —
  trocar não altera séries nem volume da sessão. `ExerciseLog` grava no
  exercício feito (o substituto); a leitura do exercício mostra "no lugar
  de <original>" com o histórico do original ao lado, e "voltar ao
  original".
- **Alternativas**: mesmo `padrao`, ativo, `equipment` dentro do
  equipamento do perfil, fora do próprio e dos que já estão na sessão; com
  foto (`frames.0`) e nome. Na ficha, cada linha ganha "outras formas"
  (porta para a leitura do exercício, onde a lista mora — a ficha continua
  lista, não painel). `POST /treino/trocar/` com `original`+`substituto`
  cria/atualiza; com `desfazer=1` apaga. Idempotente (estado absoluto).
- Testes: trocar mantém séries/volume da sessão (diferença 0, dentro do
  ±1); a troca persiste entre sessões (outra letra com o mesmo exercício,
  semana seguinte); desfazer volta ao original; o histórico do original
  continua visível na leitura; alternativa fora do equipamento do perfil
  não é oferecida e é recusada no POST; a troca não remonta a ficha.

## 3. Equipamento no perfil

- **`Profile.equipamento`** (`Equipamento`: `completa` · `basica` ·
  `casa_halteres` · `peso_corporal`; default `completa`; migration com
  default constante — contas existentes ficam em "completa" e NÃO remontam,
  porque `TrainingPlan.equipamento` nasce com o mesmo default).
- **Mapa em `TREINO.md`** ("Mapa de equipamento", tabela lida por
  `doutrina.equipamentos_de(perfil)`): completa = barra, halteres, máquina,
  polia, peso do corpo · básica = halteres, máquina, polia, peso do corpo
  (sem barra livre) · casa com halteres = halteres, peso do corpo · só peso
  do corpo = peso do corpo.
- **O motor filtra ANTES de prescrever** (`prescrever_opcoes(...,
  permitidos=...)`, chamado igual em `create_routine` e em
  `_prescricao_confere`): item do modelo com equipamento fora do perfil é
  SUBSTITUÍDO por exercício ativo do mesmo `padrao` e mesmo grupo dentro do
  perfil que ainda não esteja no modelo (mesma dose); sem substituto, sai.
  `TrainingPlan.equipamento` é retrato; mudar no perfil torna a ficha
  inválida (`rotina_invalida`) e remonta, como nível e duração.
- Pergunta no onboarding (etapa 2, ao lado da experiência) e no Perfil.
- Os três testes que congelavam "o produto não promete ambiente" viram o
  contrato novo: o motor LÊ equipamento, o perfil TEM a pergunta, e a
  capacidade por ambiente passa a ser medida pelos quatro perfis.

## 4. Teste dourado e gate por perfil de equipamento

- `workouts/test_ficha_de_verdade.py` roda por perfil: **completa** e
  **básica** têm de fechar como hoje (A com ≥ 6 exercícios, ≥ 4 peito, ≥ 2
  tríceps, 21–28 séries, 55–65 min). **Casa com halteres** e **só peso do
  corpo** são MEDIDOS: onde o catálogo não fecha, o teste lista os
  exercícios a ativar (mosaico para o dono) e fica como `expectedFailure`
  nomeado, nunca afrouxado. O gate por letra (`LETRAS_COM_OPCOES_EM_PRODUCAO`)
  continua no perfil completo; por perfil restrito, uma opção só é
  aceitável (é o caso já documentado do "Superior").
- Catálogo: com mídia curada (foto conferida na free-exercise-db, vídeo por
  título, anatomia), ativam-se os que fecharem as lacunas; os demais entram
  na lista com o motivo.

## 5. Versão rápida

- Some o `<nav class="versoes">` da ficha e o `?versao=`. No painel, no
  cartão de hoje, uma ação discreta "Menos tempo hoje?" (`POST
  /treino/hoje/rapida/`) pina a versão rápida no registro do dia (e o
  contrário, "Treino completo"). Cada uso grava `EventoDeProduto(user,
  "versao_rapida", dia)` — único por pessoa e dia — e `medir_progressao`
  conta os usos dos últimos 30 dias, que é o dado da decisão.

## 6. Prova em produção

Duas contas descartáveis pelo signup público — uma em academia básica, uma
em completa: ficha de A com ≥ 6 exercícios (7 no perfil de referência),
troca de um exercício por alternativa do mesmo padrão sem máquina,
histórico contínuo (série no substituto, histórico do original visível),
conta apagada pela tela, demo intacto; capturas antes/depois da ficha.
