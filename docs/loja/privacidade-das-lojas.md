# App Privacy (Apple) e Data Safety (Google) — o que marcar, item a item

Escrito em 22/09/2026 (Fase 3 da missão Capacitor). **Cada linha aqui foi
conferida contra o código**, e é isso que faz o formulário bater com o app —
a divergência entre o que o formulário diz e o que o app faz é motivo
frequente de rejeição e de remoção depois de publicado.

Onde cada dado vive está em `templates/legal/privacidade.html`; a seção de
saúde do aparelho é `#saude-do-aparelho`.

---

## Apple — App Privacy ("nutrition labels")

Para cada tipo: **coletado?** · **ligado à identidade?** · **usado para
rastreamento?** · **finalidades**.

O NutriPlan **não rastreia** (nenhum SDK de publicidade, nenhum
identificador compartilhado com terceiros): em "Tracking", responda
**No** em tudo. Nada é usado para publicidade nem para marketing de
terceiros.

| Tipo de dado | Coletado | Ligado à identidade | Rastreamento | Finalidade | Onde no código |
|---|---|---|---|---|---|
| Contact Info › Email Address | Sim | Sim | Não | App Functionality (login, recuperação de senha, avisos) | `accounts.User.email` |
| Contact Info › Name | Sim | Sim | Não | App Functionality (a tela diz "Olá, Fulano") | `accounts.User.first_name` |
| Health & Fitness › Health | Sim | Sim | Não | App Functionality (peso do HealthKit vira a sua pesagem) | `accounts.saude_do_aparelho`, `accounts.WeightEntry` |
| Health & Fitness › Fitness | Sim | Sim | Não | App Functionality (treinos de corrida do HealthKit viram corridas; séries e cargas) | `workouts.corrida_views.CorridasDoAparelhoView`, `workouts.ExerciseLog` |
| User Content › Other User Content | Sim | Sim | Não | App Functionality (refeições marcadas, água, sensação da corrida) | `plans.MealLog`, `plans.HydrationLog` |
| Identifiers › User ID | Sim | Sim | Não | App Functionality, Analytics (o identificador da conta; no analytics ele é ANÔNIMO — `blake2b` com a `SECRET_KEY`) | `analytics/`, `config/observabilidade.py` |
| Usage Data › Product Interaction | Sim | Sim | Não | Analytics (de primeira parte, só para melhorar o app) | `analytics/servidor.py` |
| Diagnostics › Crash/Performance | **Não** | — | — | — | não há SDK de crash |
| Location | **Não** | — | — | — | o app não lê GPS (a corrida por GPS saiu em 20/09/2026) |
| Purchases, Financial Info | **Não** | — | — | — | não há compra |
| Contacts, Photos, Audio, Browsing History, Search History, Sensitive Info | **Não** | — | — | — | — |

**Perguntas que a Apple faz sobre HealthKit** (no envio e na revisão):

- *Você usa dados do HealthKit para publicidade ou marketing?* **Não.**
- *Você compartilha dados do HealthKit com terceiros?* **Não.**
- *Para que usa?* Ler peso (para a pesagem do Progresso) e treinos de
  corrida (para o histórico de corridas), **só quando a pessoa toca em
  "Importar do aparelho"**. O app **não escreve** no HealthKit.
- A `NSHealthShareUsageDescription` do `Info.plist` diz isso com as mesmas
  palavras (`config/test_politica_de_saude.py` cobra).

## Google — Data Safety

Para cada tipo: **coletado** · **compartilhado** · **obrigatório ou
opcional** · **finalidade** · **criptografado em trânsito** · **dá para
pedir exclusão**.

Respostas gerais: **tudo trafega criptografado** (HTTPS/TLS, HSTS ligado);
**a pessoa pode pedir a exclusão** e também apagar tudo sozinha
(Perfil › Excluir minha conta, `accounts.ExcluirContaView`); **nada é
compartilhado com terceiros** (os provedores de infraestrutura — Neon,
Render, Brevo — são operadores, não "compartilhamento" no sentido do
formulário); **não há publicidade**.

| Tipo | Coletado | Compartilhado | Obrigatório | Finalidade |
|---|---|---|---|---|
| Informações pessoais › Nome | Sim | Não | Opcional | Funcionalidade do app |
| Informações pessoais › E-mail | Sim | Não | Obrigatório | Funcionalidade do app, gerenciamento da conta |
| Saúde e fitness › Informações de saúde | Sim | Não | Opcional | Funcionalidade do app (peso, do Health Connect ou digitado) |
| Saúde e fitness › Informações de atividade física | Sim | Não | Opcional | Funcionalidade do app (corridas, séries, treinos) |
| Atividade no app › Interações | Sim | Não | Opcional | Análise (própria) |
| Atividade no app › Outras ações | Sim | Não | Opcional | Funcionalidade do app (refeições, água) |
| IDs do dispositivo ou outros | Sim | Não | Obrigatório | Funcionalidade do app (token do FCM, para os lembretes) |
| Local, Fotos, Contatos, Arquivos, Financeiro, Mensagens | Não | — | — | — |

**Declaração de permissões de saúde (Health Connect)** — o Play exige
justificativa POR PERMISSÃO, e o app declara só três:

| Permissão | Por que |
|---|---|
| `READ_WEIGHT` | Importar a pesagem para o Progresso sem digitar |
| `READ_EXERCISE` | Importar treinos de corrida (data e duração) |
| `READ_DISTANCE` | A distância desses treinos |

As outras nove que o plugin traz são **removidas** no manifesto
(`tools:node="remove"`) — o Health Connect mostra toda permissão declarada
na folha de consentimento, e pedir o que não se usa é pedir demais.
`config/test_politica_de_saude.py` prende essa lista.

**Política de privacidade dentro do app**: a folha de permissões do Health
Connect abre `…/privacidade/#saude-do-aparelho` num WebView
(`privacy_policy_url` em `strings.xml`).

## O que muda se algo for acrescentado depois

Qualquer campo novo que grave dado de pessoa, qualquer SDK de terceiro e
qualquer leitura nova do HealthKit/Health Connect exigem **atualizar estes
dois formulários ANTES do envio**. É por isso que este arquivo existe: a
próxima pessoa não precisa reconstruir a lista, só conferir a linha que
mudou.
