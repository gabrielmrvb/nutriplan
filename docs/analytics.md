# Analytics de produto — a taxonomia e como ela nasce

Analytics **de primeira parte**: nenhum terceiro, nada vendido, nada que saia
do NutriPlan. Existe para responder "como o produto está indo" — onde a pessoa
trava no onboarding, se registra a refeição, se volta depois de sumir. A base
legal é o interesse legítimo (LGPD art. 7º IX e art. 10); ver
`analytics/privacidade.py` e a página `/privacidade/`.

## As duas tabelas

- **`Event`** — o bruto, uma linha por acontecimento, com as propriedades
  inteiras. Vive **90 dias** (`ANALYTICS_RETENCAO_DIAS`, env), depois o
  `podar_analytics` apaga. O painel lê bruto para os últimos dias.
- **`DailyAggregate`** — o rolado, uma contagem por (dia, evento, propriedade,
  valor). Sem prazo, **sem PII** (não guarda usuário). O painel lê agregado
  para períodos longos. Gerado por `agregar_analytics` (idempotente), no build.

Medido em 21/09/2026: **393 bytes/evento** com índices. 90 dias cabe no Neon
free (0,5 GB) até ~1000 MAU / ~300–400 DAU; acima disso, baixe
`ANALYTICS_RETENCAO_DIAS` — o agregado guarda a série histórica, então encurtar
o bruto não apaga a tendência.

## Identidade

- **`anon_id`** — cookie de primeira parte, `HttpOnly`, sorteado no servidor.
  Liga os toques de um aparelho antes do login.
- **alias** — no login (`user_logged_in`), todo evento anônimo daquele
  `anon_id` passa a apontar para a pessoa. É o que faz o funil "landing anônima
  → criou conta → treinou" ser de UMA pessoa. `analytics/identidade.py`.
- **exclusão** — `Event.user` é `CASCADE`: apagar a conta apaga o rastro
  identificado (LGPD). Anônimos e agregados ficam.

## Regras da propriedade

Nome é `dominio.acao`. Propriedade é **rótulo curto**, nunca PII: sem e-mail,
sem nome, e **peso vira faixa** (`progresso.peso_registrado` leva `faixa`
"80-85", nunca o kg). A lista é FECHADA em `analytics/catalogo.py`, e
`analytics/test_taxonomia.py` reprova qualquer nome usado no código que não
esteja lá.

## O catálogo, e onde cada evento nasce

### Automáticos (cliente, `static/js/analytics.js`)

| evento | props | onde |
|---|---|---|
| `tela.vista` | — | toda rota, no carregamento |
| `tela.interativa` | `ms` | TTI aproximado (navigation timing) |
| `pwa.instalada` | — | evento `appinstalled` |
| `erro.js` | `mensagem`, `rota` | `window.onerror`, teto de 5/carga |

Cliques genéricos: só com `data-evento="nome"` explícito no template (o cliente
não loga clique sozinho). O nome tem de estar no catálogo.

### De negócio (servidor, `analytics/servidor.py::evento`)

No ponto que APLICA a ação — assim a fila offline, que drena no servidor, conta
igual ao online.

| evento | props | handler |
|---|---|---|
| `conta.criada` | — | `SignupView.form_valid` |
| `conta.login` | — | `AppLoginView.form_valid` (e-mail; ver nota) |
| `conta.excluida` | — | `ExcluirContaView` (anônimo, antes do delete) |
| `onboarding.iniciado` | — | `SignupView.form_valid` |
| `onboarding.etapa_concluida` | `etapa` | `OnboardingStepMixin.finish_step` |
| `onboarding.concluido` | — | idem, no "Calcular minha estimativa" (era "Criar meu plano" até 21/09/2026) |
| `dieta.refeicao_registrada` | `opcao` | `MarkMealView` (status DONE) |
| `dieta.pulou` | — | `MarkMealView` (SKIPPED) |
| `dieta.comeu_outra_coisa` | — | `MarkMealView` (OFF_PLAN) |
| `agua.registrada` | — | `LogHydrationView` (só o somar) |
| `progresso.peso_registrado` | `faixa` | `WeightLogView` |
| `treino.serie_concluida` | `exercicio`, `carga`, `reps` | `ConcluirSerieView` (só o `criada`) |
| `treino.iniciado` | `letra` (omitida) | `ConcluirSerieView` (primeira série do dia) |
| `treino.troca` | `de`, `para` | `TrocarExercicioView` |
| `corrida.registrada` | `origem` | `RegistrarCorridaView` (manual) e importação (arquivo) |
| `conquista.desbloqueada` | `nome` (slug) | `achievements.services.anunciar` |

### Notas e pendências

- **`conta.login`** é do login por e-mail; o Google entra pelo allauth e não
  passa por `AppLoginView`. O **alias** costura a identidade dos dois; só o
  EVENTO fica de fora do caminho Google.
- **`treino.iniciado`** omite `letra` de propósito: a rota da série é a mais
  quente do app, e buscar a letra custaria uma consulta. Está no catálogo com a
  prop para quando valer o custo.
- **`onboarding.abandonado`** não é emitido: é DERIVADO do funil (quem fez
  `etapa_concluida{N}` e não `concluido`). Está no catálogo como documentação
  do que o painel calcula.
- **`lembrete.recebido`/`lembrete.clicado`** ainda não são emitidos: exigem
  instrumentar o service worker. Ficam no catálogo como contrato.
- **`treino.serie_concluida` e `treino.concluido` PASSARAM A SER EMITIDOS**
  (24/09/2026). Estavam na taxonomia desde o começo e nunca eram disparados —
  o último degrau do funil de entrada não existia, e o "uso por área"
  enxergava tudo menos o treino. A série é registrada só quando a linha NASCE
  (`criada=True`): o reenvio da fila offline é a mesma série chegando duas
  vezes, e contá-la de novo inflaria o número que decide investimento. A
  duração do `treino.concluido` é a MEDIDA (`EstadoDoTreino.minutos_do_treino`,
  da primeira série ao "Encerrar treino") — o mesmo número que o placar
  mostra, para a gestão e a tela não discordarem.

## O painel

`/gestao/analytics/`, sob a mesma permissão do resto da gerência
(`PainelDeGestaoMixin`, `accounts.ver_painel_de_gestao`). Ver o bloco 3.

## As três perguntas de produto (24/09/2026)

O painel tinha as FERRAMENTAS — explorar um evento, montar um funil qualquer,
ver a coorte semanal. Faltavam as PERGUNTAS, com os passos nomeados e o
recorte que se olha todo dia. Elas moram em `analytics/consultas.py` e têm
tela própria; a régua de sempre vale para as três (abaixo de 15 consultas,
custo que não cresce com o volume — `analytics/test_painel.py`).

### 1. Onde a pessoa desiste — `/gestao/analytics/entrada/`

`funil_de_entrada(dias, por="dia"|"semana")` sobre `PASSOS_DE_ENTRADA`:

| # | passo | evento | filtro |
|---|---|---|---|
| 1 | Abriu a landing | `site.landing_vista` | — |
| 2 | Começou o cadastro | `onboarding.iniciado` | — |
| 3 | Etapa 1 · sobre você | `onboarding.etapa_concluida` | `etapa=1` |
| 4 | Etapa 2 · objetivo e rotina | `onboarding.etapa_concluida` | `etapa=2` |
| 5 | Etapa 3 · personalização | `onboarding.etapa_concluida` | `etapa=3` |
| 6 | 1ª refeição registrada | `dieta.refeicao_registrada` | — |
| 7 | 1ª série registrada | `treino.serie_concluida` | — |

Quatro decisões que custaram pensamento:

- **`site.landing_vista` nasce no CLIENTE**, e é o único degrau assim. A
  primeira versão o disparava em `LandingView.get()` e quebrou uma garantia
  medida: `/` anônima é a página mais barata do app, com ZERO consulta
  (`plans/test_landing.py`), porque é ela que o visitante novo vê com o
  Render dormindo e o Neon à parte — um INSERT ali custaria o banco em toda
  visita, inclusive as de robô. O marcador é `data-evento-ao-abrir` no
  template (`analytics.js`, "EVENTO AO ABRIR"), e a ingestão é o mesmo
  `sendBeacon` de sempre, com o mesmo consentimento. E não é `tela.vista`
  com filtro de rota: `/` é a landing para quem não entrou e o app para quem
  entrou, e o mesmo caminho contaria os dois — além de um degrau preso ao
  TEXTO de uma rota quebrar em silêncio no dia em que a rota muda de nome.

  **O que o cliente muda na leitura do número:** o degrau conta só quem
  EXECUTA JavaScript. Robô que só busca o HTML não entra (a versão do
  servidor contaria todos eles); robô que renderiza, como o do buscador,
  entra. O topo do funil é um TETO — "aberturas de navegador", não
  "pessoas" —, e os degraus seguintes exigem POST, que nenhum robô alcança.
  É por isso que a taxa do passo 1 para o 2 é a que menos se deve ler
  sozinha.

- **A COORTE é do PRIMEIRO passo da pessoa**, não do dia do evento. Quem
  abriu a landing na segunda e treinou na quarta pertence à segunda —
  contar a série de quarta como conversão de quarta faria a taxa de um dia
  depender do movimento do dia anterior.
- **A ORDEM NO TEMPO manda**: um passo só conta se aconteceu DEPOIS do
  anterior. É a mesma régua de `funil()`, e ela é o que separa conversão de
  coincidência no mesmo aparelho.
- **Quem entrou direto pelo cadastro não some**: ela entra na coorte pelo
  passo em que apareceu, e os passos acima ficam zerados naquela coorte —
  que é a verdade, e não um buraco.

Custo: UMA consulta por passo (sete, fixas), matriz em Python.

### 2. A pessoa volta? — `/gestao/analytics/retencao/`

`retencao_por_coorte(semanas)`: coortes por SEMANA DE CADASTRO × **D1, D7 e
D30**. Fica acima da matriz semanal que já existia, porque é a régua de
produto; a matriz é a curva de longo prazo.

- **"Voltou" é ter REGISTRADO alguma coisa** (`EVENTOS_DE_REGISTRO`), e não
  ter aberto o app: abrir sem registrar é curiosidade.
- **Janela que não fechou vem VAZIA, não zero.** O D30 de quem se cadastrou
  ontem é `None`; zero seria a tela afirmando que ninguém voltou de um prazo
  que ainda não chegou.

### 3. O que a base usa de fato — `/gestao/analytics/uso/`

`uso_por_area(semanas)`: registros **e pessoas** por pilar, semana a semana.
Os dois números juntos de propósito — 400 registros podem ser quarenta
pessoas ou uma obsessiva, e a decisão de onde investir muda com a resposta.

| chave (`Pilar`) | nome de tela (`Pilar.label`) | eventos |
|---|---|---|
| `dieta` | Alimentação | `dieta.refeicao_registrada`, `dieta.pulou`, `dieta.comeu_outra_coisa` |
| `treino` | Treino | `treino.serie_concluida` |
| `hidratacao` | Hidratação | `agua.registrada` |
| `progresso` | Progresso | `progresso.peso_registrado` |
| `corrida` | Corrida | `corrida.registrada` |

A chave é o `value` de `accounts.models.Pilar` e o nome vem de
`Pilar.label` — o único lugar do projeto onde ele é escrito (`CLAUDE.md`,
"Uma área, um nome"). A primeira versão da tabela tinha slug próprio
("alimentacao") e a tela escrevia `capfirst` em cima, o que dava
"Alimentacao" e "Hidratacao": um terceiro vocabulário para as mesmas cinco
áreas.

`EVENTOS_DE_REGISTRO` é essa tabela achatada, e é a MESMA lista de onde a
retenção tira o "voltou": duas definições de "usou o app" é como duas telas
passam a discordar. Área sem registro aparece zerada — sumir da tabela faria
ninguém reparar que a corrida não é usada.

### Consentimento

Nada disso muda a privacidade: os três leem `Event`, que já nasce pelo
`analytics.servidor.evento` respeitando o opt-out do Perfil — quem desligou a
atribuição conta só de forma anônima, e a exclusão da conta apaga os eventos
identificados por `CASCADE`.
