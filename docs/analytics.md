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
- **`treino.concluido`** e **`lembrete.recebido`/`lembrete.clicado`** ainda não
  são emitidos: o primeiro exigiria detectar "sessão completa" na rota quente
  (custo de consulta), e os lembretes exigem instrumentar o service worker.
  Ficam no catálogo como contrato; são o follow-up natural.

## O painel

`/gestao/analytics/`, sob a mesma permissão do resto da gerência
(`PainelDeGestaoMixin`, `accounts.ver_painel_de_gestao`). Ver o bloco 3.
