# O NutriPlan como ele é hoje

Inventário do produto, levantado do código. Serve para uma coisa: impedir
análise de produto apoiada em feature imaginária.

Se algo aqui divergir do código, **o código ganha** — e vale dizer isso na
análise, para o inventário ser corrigido depois.

Não repete o `CLAUDE.md`. Leia os dois: lá estão as decisões e as regras de
implementação, aqui está o mapa do que existe.

---

## 1. A proposta

PWA de dieta **e** treino, em Django 5.2 + PostgreSQL. Em produção:
`https://nutriplan-xxfn.onrender.com`.

Três coisas definem o produto e restringem quase toda ideia:

- **Uma pessoa, um plano, sem conta compartilhada.** Não há coach, aluno,
  amigo, nem visualização de dado de terceiro. Um módulo que dava a uma pessoa
  acesso aos dados de saúde de outra existiu e foi removido de propósito — há
  testes que garantem que nenhuma rota dele volte a resolver.
- **Mobile é o contexto real.** Cozinha de manhã, escolha do almoço à tarde, em
  pé na academia entre séries — às vezes com a mão suada.
- **Dieta e treino são o mesmo produto.** O treino entra na conta calórica; a
  ofensiva conta os dois lados.

Idioma: pt-BR. Números com vírgula decimal.

---

## 2. Telas

Vinte templates. Estas são as telas que a pessoa vê:

| Tela | Template | O que faz |
|---|---|---|
| Painel do dia | `plans/today.html` | Meta calórica, macros, cardápio com opções, hidratação, ofensiva. É a home e o motivo de abrir o app. |
| Ficha de treino | `workouts/routine.html` | A semana, as sessões, séries, cargas e o cronômetro de descanso. |
| Histórico | `plans/history.html` | Aderência, média calórica e curva de peso. |
| Lista de compras | `plans/shopping.html` | O que comprar para a semana, agrupado por corredor. |
| Suplementos | `supplements/list.html` | Checklist do dia e o que cada um faz, com nível de evidência. |
| Perfil | `accounts/profile.html` | Os dados que alimentam o cálculo, e a porta para reeditar cada passo. |
| Onboarding | `accounts/onboarding/step.html` | Wizard de **5 passos**, uma rota só despachando para cada. |
| Entrar / Criar conta | `accounts/login.html`, `accounts/signup.html` | |
| Offline | `pwa/offline.html` | O que o service worker serve sem rede. |
| Demo | `demo/index.html`, `sobre.html`, `indisponivel.html`, `acao_desativada.html` | |

Parciais reutilizáveis: `partials/choice_cards.html`, `field.html`,
`icones.html`, `marca.html`, `plans/_peso.html`.

**Os 5 passos do onboarding**, na ordem: dados corporais → objetivo → dias de
treino → divisão de treino → comida (estilo e restrições). A ordem tem razão: a
divisão vem depois dos dias porque a resposta só faz sentido sabendo a
frequência.

---

## 3. Rotas

```
/                            painel do dia          plans:today
/historico/                                         plans:history
/lista-de-compras/                                  plans:shopping
/refeicao/<slot_id>/marcar/                         plans:mark_meal
/refeicao/<slot_id>/desfazer/                       plans:clear_meal
/recalcular/                 replaneja               plans:recalculate
/recalibrar/                 ajuste de meta          plans:recalibrate
/agua/                                              plans:log_hydration

/conta/cadastro/ entrar/ sair/ perfil/
/conta/onboarding/  e  /conta/onboarding/<step>/

/treino/                                            workouts:routine
/treino/exercicio/<id>/carga/                       workouts:record_load
/treino/exportar/saude.tcx                          workouts:health_export

/suplementos/                                       supplements:list
/push/inscrever/  /push/cancelar/
/sw.js  /manifest.webmanifest  /offline/  /saude/  /admin/
/demo/  (o app inteiro, público e somente leitura)
```

---

## 4. Modelos

| App | Modelos |
|---|---|
| `accounts` | `User`, `Profile`, `WeightEntry`, `TrainingDay`, `SyncedOperation` |
| `catalog` | `Food`, `FoodPortion`, `MealTemplate`, `MealTemplateItem`, `DietaryTag` |
| `plans` | `NutritionPlan`, `MealSlot`, `MealOption`, `MealLog`, `HydrationLog` |
| `workouts` | `Exercise`, `WorkoutTemplate`, `WorkoutTemplateItem`, `TrainingPlan`, `TrainingSession`, `SessionExercise`, `ExerciseLog` |
| `supplements` | `Supplement`, `SupplementLog` |
| `push` | `PushSubscription`, `NotificationLog` |

O que o `Profile` guarda e alimenta o cálculo: sexo, nascimento, altura, nível
de atividade, objetivo, preferência de divisão, estilo de refeição, horário de
acordar e dormir, restrições alimentares (M2M), `kcal_adjustment`,
`recalibrated_at`, e `onboarding_step`.

Peso **não** mora no perfil: é série temporal em `WeightEntry`.

---

## 5. Motores

Onde a regra de negócio mora. Ideia que mexe aqui é complexidade `alta` por
definição.

| Módulo | Responsabilidade |
|---|---|
| `plans/calculations.py` | TMB, fator de atividade, meta calórica, macros |
| `plans/meal_planner.py` | Monta o cardápio a partir do catálogo e das restrições |
| `plans/services.py` | Cria e sincroniza o plano ativo |
| `plans/shopping.py` | Agrega o cardápio em lista por corredor |
| `plans/streaks.py` | A ofensiva |
| `plans/tracking.py` | Consolida o que foi consumido no dia |
| `plans/weight_trend.py` | Média móvel de peso e detecção de estagnação |
| `workouts/services.py` | Gera a ficha a partir da divisão e dos dias |
| `workouts/health_export.py` | Resumo da sessão e geração do TCX |

---

## 6. Funcionalidades que existem

- **Cardápio do dia com opções** por refeição, e substituição de alimento.
- **Marcar refeição** como feita, pulada ou "comi outra coisa" — e desfazer.
- **Hidratação** com botões de volume e meta diária.
- **Ofensiva (streak)** contando dieta e treino juntos.
- **Lista de compras** da semana, por corredor.
- **Histórico** de 14 dias: aderência, média calórica, curva de peso.
- **Recalibração**: quando a média de peso empaca, o app oferece ajustar a meta.
  O ajuste mora em `Profile.kcal_adjustment`; `recalibrated_at` evita repetir o
  aviso para quem já respondeu.
- **Ficha de treino** gerada da divisão e dos dias declarados.
- **Registro de carga por série**, com histórico e progressão visível.
- **Cronômetro de descanso.**
- **Exportação TCX** da sessão do dia, para importar em app de saúde.
- **Checklist de suplementos**, com nível de evidência de cada um.
- **Fila offline idempotente**: as escritas feitas sem rede são guardadas no
  navegador e reenviadas quando ela volta (`static/js/fila.js` +
  `SyncedOperation`). Cobre água, suplemento, marcação de refeição e carga.
- **Notificações push** de refeição chegando.
- **Modo demo público** em `/demo/`: o app inteiro montado por middleware sobre
  dados fictícios, somente leitura — sem telas duplicadas.

Cobertura de teste: cerca de **825 testes**, incluindo travas de contraste
WCAG, alvo de toque e regras de estilo.

---

## 7. O que o produto NÃO tem

A parte mais útil deste documento. Não presuma que exista:

- **Entrada por voz.** Existiu e **foi removida** — há comentários no código
  registrando isso. Repropor exige argumentar contra a remoção.
- **Assistente de ajuste de treino com interface.** O campo
  `TrainingPlan.customized_at` existe como trava (ficha ajustada não é
  remontada), mas **nada no código o escreve hoje**. É uma porta preparada, não
  uma feature entregue.
- **Fotos de refeição** — nenhum campo de imagem, nenhum upload.
- **Qualquer coisa social**: feed, amigos, compartilhamento, comparação.
- **Escrita direta no Apple Saúde ou Health Connect** — não existe API web para
  isso. O TCX é o caminho, e ele é manual.
- **Múltiplos usuários, coach, nutricionista** — removido de propósito.
- **Registro de tempo real de treino** (início/fim, duração medida). Existe
  `duration_min`, que é a duração **prevista** da sessão, não a executada.
- **Contagem de passos, integração com wearable, batimentos.**
- **Chat, IA conversacional dentro do app.**

---

## 8. Limites que restringem o desenho

- **Node/npm não estão instalados.** Nada que dependa de build step, Tailwind,
  Playwright ou Lighthouse.
- **Sem framework de CSS**: um arquivo, `static/css/app.css`, com seções
  numeradas e tokens no topo.
- **Sem Background Sync no Safari do iPhone** — a fila offline depende do evento
  `online`.
- **O banco gratuito do Render é apagado por volta de 23/09/2026.** Ideia cujo
  valor só aparece depois de meses de dado acumulado precisa considerar isso.
- **Plano é retrato, não referência**: os números de um plano ativo nunca são
  editados. Mudou a entrada, nasce plano novo. Qualquer ideia de "ajustar a meta
  do plano atual" colide com isso — o caminho existente é a recalibração.
- **Idempotência é requisito da fila offline**: água SOMA e suplemento ALTERNA,
  e as duas dependem de `op_id`. Feature nova que escreva offline precisa entrar
  nesse contrato.

---

## 9. Como o dia acontece

A jornada real, para situar "momento da jornada" na análise:

1. **Estreia** — cadastro, 5 passos de onboarding, e o app calcula o primeiro
   plano. Ponto de maior abandono do produto.
2. **Manhã** — abre o painel, vê a meta, escolhe e marca o café.
3. **Ao longo do dia** — marca refeições, registra água, consulta substituição
   quando o cardápio não bate com a geladeira.
4. **Academia** — abre a ficha, anota carga por série, usa o cronômetro.
5. **Semana** — lista de compras, histórico, curva de peso.
6. **Estagnação** — o peso empaca, o app oferece recalibrar. É o momento em que
   a pessoa decide se o app entende o corpo dela ou não.
