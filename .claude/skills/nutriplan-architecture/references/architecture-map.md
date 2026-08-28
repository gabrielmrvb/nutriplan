# A arquitetura real do NutriPlan

Levantado do código. Responde: **como este produto está construído hoje?**

Duas marcações, e elas nunca se misturam:

- **FATO DO CÓDIGO** — verificável abrindo o arquivo. Se divergir do repositório,
  o repositório ganha e a divergência vira achado.
- **GUARDA ARQUITETURAL** — o que se conclui do fato, e o que se recomenda por
  causa dele. É argumento, não observação.

---

## 1. Apps e responsabilidades

**FATO DO CÓDIGO** — sete apps no `INSTALLED_APPS`:

| App | Guarda |
|---|---|
| `accounts` | `User`, `Profile`, `WeightEntry`, `TrainingDay`, `SyncedOperation` |
| `catalog` | `Food`, `FoodPortion`, `MealTemplate`, `MealTemplateItem`, `DietaryTag` |
| `plans` | `NutritionPlan`, `MealSlot`, `MealOption`, `MealLog`, `HydrationLog` |
| `workouts` | `Exercise`, `WorkoutTemplate`, `TrainingPlan`, `TrainingSession`, `SessionExercise`, `ExerciseLog` |
| `supplements` | `Supplement`, `SupplementLog` |
| `push` | `PushSubscription`, `NotificationLog` |
| `demo` | Nenhum model — só middleware, views e o comando de seed |

**FATO DO CÓDIGO** — peso não mora no `Profile`: é série temporal em
`WeightEntry`. Dias de treino também não: são linhas em `TrainingDay`.

**GUARDA** — `catalog` é o dono do que existe no mundo (alimento, receita,
exercício); `plans` e `workouts` são donos do que foi prescrito para uma pessoa;
`accounts` é dono de quem a pessoa é e do que ela declarou. Um campo que descreve
alimento não vai para `plans`; um campo que descreve a pessoa não vai para
`workouts`.

---

## 2. Onde a regra de negócio mora

**FATO DO CÓDIGO** — módulos de serviço, um assunto cada:

| Módulo | Responsabilidade |
|---|---|
| `plans/calculations.py` | TMB, fator de atividade, meta calórica, macros |
| `plans/meal_planner.py` | Monta o cardápio a partir do catálogo e das restrições |
| `plans/services.py` | Cria e sincroniza o plano ativo |
| `plans/tracking.py` | Consolida o consumido no dia; `log_meal` |
| `plans/shopping.py` | Agrega o cardápio em lista por corredor |
| `plans/streaks.py` | Ofensiva |
| `plans/weight_trend.py` | Média móvel de peso, detecção de estagnação |
| `workouts/services.py` | Gera a ficha; grava carga |
| `workouts/health_export.py` | Resumo da sessão e TCX |

**FATO DO CÓDIGO** — models guardam dado e propriedades curtas
(`Profile.age`, `Profile.onboarding_complete`, `TrainingPlan.is_customized`).
Views orquestram: buscam, chamam serviço, devolvem.

**GUARDA** — a camada de serviço já existe e é o lugar da regra. Não há motivo
para introduzir repository, use case ou service layer por cima: seria um segundo
nome para o que já está lá. Regra nova entra num módulo existente, ou num módulo
novo com um assunto próprio e claro.

---

## 3. Plano-retrato

**FATO DO CÓDIGO** — `plans/services.py:167`, `plan_is_current(plan, inputs)`
devolve `False` quando:

- o plano não tem `slots`;
- alguma `MealOption` aponta para `MealTemplate` com `is_active=False`;
- qualquer campo de **entrada** diverge do perfil de hoje;
- qualquer campo de **saída** diverge do que `calculate(inputs)` produz agora.

O comentário no código explica o porquê de comparar os dois: *"trocar a duração
do treino mantém `training_days_per_week` igual, mas move o TDEE"*.

**FATO DO CÓDIGO** — `sync_active_plan(user)` devolve `(plano, mudou)` e roda na
entrada da tela. Criar plano novo desativa o anterior
(`filter(is_active=True).update(is_active=False)`), sob `@transaction.atomic`
(`plans/services.py:76`). O mesmo padrão em `workouts/services.py:188` e `:205`.

**GUARDA** — quatro conceitos que parecem um só, e confundi-los é o erro mais
caro desta área:

1. **configuração atual** — `Profile`, `WeightEntry`, `TrainingDay`;
2. **plano gerado** — o ativo, coerente com a configuração de hoje;
3. **retrato histórico** — os planos inativos, com os números do dia em que
   nasceram;
4. **customização** — o que a pessoa mudou à mão.

Mudar uma fórmula em `calculations.py` **reinterpreta o passado**: planos antigos
passam a ser julgados por uma régua que não existia. Mudança em cálculo é sempre
**A3**, e a saída precisa dizer o que acontece com o histórico.

---

## 4. `customized_at`

**FATO DO CÓDIGO** — verificado por grep em todo o projeto (excluindo migrations
e testes):

- **Definido**: `workouts/models.py:532` — `DateTimeField(null=True, blank=True)`.
- **Propriedade**: `workouts/models.py:535-536` — `is_customized` devolve
  `customized_at is not None`.
- **Lido**: `workouts/services.py:275` e `:278`, dentro da função que decide se a
  ficha ativa ainda serve. Ficha customizada é poupada da comparação com o
  catálogo e **retorna cedo como válida**.
- **Escrito**: **em lugar nenhum.** Nenhuma atribuição fora de migration.
- **Testado**: `config/tests.py:897` afirma apenas que o campo existe.

**GUARDA** — a trava está ligada e nada a arma. É uma porta preparada: o
mecanismo de proteção funciona, e o fluxo que o acionaria não existe. Consequência
para quem for construir em cima: a primeira feature que escrever `customized_at`
**liga um caminho de código que nunca rodou em produção** — aquele `return True`
antecipado passa a valer pela primeira vez. Tratar como A3 e validar os dois
ramos, não só o novo.

---

## 5. Fila offline e idempotência

**FATO DO CÓDIGO** — o cliente, em `static/js/fila.js`:

- identificador gerado com `crypto.randomUUID()` (linha 49), com alternativa
  quando a API não existe;
- IndexedDB com `keyPath: "op_id"` (linha 61) — o próprio identificador é a
  chave, então guardar duas vezes é sobrescrever;
- `op_id` é anexado aos dados do formulário e enfileirado (linhas 149-151);
- no reenvio, o item sai da fila quando a resposta é `ok` **ou** `4xx`
  (linha 127).

**FATO DO CÓDIGO** — o servidor, em `accounts/models.py:326`,
`SyncedOperation.ja_aplicada(user, op_id)`: normaliza, recusa vazio ou maior que
64 caracteres, e usa `get_or_create(user=..., op_id=...)` para devolver se aquilo
já tinha sido visto. Constraint `UniqueConstraint(("user", "op_id"))`.

**FATO DO CÓDIGO** — exatamente **duas** views consultam `ja_aplicada`:
`plans/views.py:540` (hidratação) e `supplements/views.py:70` (suplemento).

**FATO DO CÓDIGO** — as outras duas escritas da fila são idempotentes por
natureza: `plans/tracking.py:44` (`log_meal`) e `workouts/services.py:321`
(`ExerciseLog`) usam `update_or_create`.

**FATO DO CÓDIGO** — o comentário de topo do `fila.js` registra o que ela **não**
cobre por decisão: assistente de treino, recalibragem e geração de plano — as três
leem estado do servidor para decidir, e enfileirá-las produziria decisão sobre
dado velho. E registra que Background Sync não existe no Safari do iPhone: o
mecanismo principal é o evento `online` mais drenagem na abertura da página.

**GUARDA** — o contrato tem duas metades, e a categoria de cada operação é uma
decisão arquitetural, não um detalhe:

- operação que **acumula ou alterna** (água SOMA, suplemento ALTERNA) precisa de
  `op_id`, porque repetir muda o resultado;
- operação que **estabelece um estado** (marcação de refeição, carga da série)
  é idempotente por `update_or_create` e dispensa `op_id`.

Trocar uma categoria pela outra quebra sem erro visível. Escrita nova que entre
na fila precisa declarar em qual metade cai. O `4xx` que remove da fila também é
contrato: o servidor recusar de forma definitiva significa "não tente de novo".

---

## 6. Demo

**FATO DO CÓDIGO** — `demo/middleware.py` monta a aplicação inteira sob `/demo/`:
tira o prefixo de `path_info`, chama `set_script_prefix("/demo/")` para os
`reverse()` voltarem com prefixo, e troca `request.user`. Sem telas duplicadas.

**FATO DO CÓDIGO** — métodos fora de `GET/HEAD/OPTIONS` são recusados **antes da
view**, com `demo/acao_desativada.html`. Duas personas escolhidas por caminho:
rota sob `/conta/onboarding/` responde como a persona do onboarding, o resto como
a persona principal. Apelidos: `/demo/hoje/` e `/demo/comecar/`.

**GUARDA** — o demo prova que as telas não podem assumir um único caminho de
entrada. Arquitetura que dependa de sessão, de `request.user` vindo do login, ou
de URL absoluta escrita à mão quebra o isolamento. Mudança em middleware, em
autenticação ou em como uma view descobre o usuário alcança `/demo/` inteiro —
sempre A3.

---

## 7. Autenticação e ownership

**FATO DO CÓDIGO** — `accounts/views.py:250`,
`OnboardingRequiredMixin(LoginRequiredMixin)`: sem onboarding completo, redireciona
para o wizard.

**FATO DO CÓDIGO** — ownership é aplicado **na consulta**, não numa camada de
permissão. Exemplo em `plans/views.py:274`:

```
get_object_or_404(MealSlot, pk=slot_id, plan__user=request.user, plan__is_active=True)
```

**FATO DO CÓDIGO** — `config/tests.py`, `SingleUserAppTests` guarda a remoção do
módulo que dava a uma pessoa acesso aos dados de outra: rotas mortas, nomes de URL
que não resolvem, campos removidos do `Profile`.

**GUARDA** — o produto é de uma pessoa só, e o isolamento existe porque toda
consulta filtra por usuário. É simples e depende de disciplina: consulta nova sem
o filtro abre um buraco que nenhuma camada intercepta. Não construa auth paralela;
siga o padrão do `get_object_or_404` filtrado.

---

## 8. Transações

**FATO DO CÓDIGO** — `@transaction.atomic` em `plans/services.py:76` (criação de
plano), `workouts/services.py:188` (criação de ficha), `push/services.py:144`, e
nos comandos de seed. Não há `select_for_update` no projeto.

**GUARDA** — a transação está onde vários registros nascem juntos e um plano pela
metade seria pior que nenhum. Escrita simples de uma linha não precisa. Ausência
de `select_for_update` é coerente com o produto ser de uma pessoa: não há duas
sessões disputando a mesma linha em condição normal. Feature que introduza
concorrência real precisa dizer isso explicitamente — seria um contrato novo.

---

## 9. Contratos entre frontend e backend

**FATO DO CÓDIGO**:

- `record_load` (`workouts/views.py`) responde **JSON** quando o cabeçalho
  `X-Requested-With: fetch` está presente, e **redireciona para
  `#exercicio-<pk>`** quando não está. Os dois caminhos existem e são usados.
- A fila envia POST de formulário com `op_id` embutido nos dados.
- `push/assets.py` versiona `app.css`, `pwa.js` e `fila.js` por hash de conteúdo,
  recalculado por requisição quando o arquivo muda.
- O service worker (`templates/pwa/sw.js`) é servido pelo Django, não é estático.

**GUARDA** — quem mexer numa view que tem os dois caminhos precisa manter os
dois. O caminho sem JavaScript não é legado: é o que funciona quando a fila
reenvia e quando o navegador falha. E mudar o nome de um arquivo versionado toca
o cache do service worker — contrato, não detalhe.

---

## 10. Áreas sensíveis, em ordem

**GUARDA** — onde um erro custa mais caro ou aparece mais tarde:

1. `plans/calculations.py` — reinterpreta histórico.
2. Fila offline (`fila.js` + `SyncedOperation`) — quebra em silêncio.
3. `demo/middleware.py` — alcança todas as telas.
4. `plan_is_current` / `sync_active_plan` — decide quando um plano morre.
5. Ownership nas consultas — sem rede de proteção acima.
6. `workouts/services.py` (geração de ficha) — remonta a semana.
7. `customized_at` — caminho preparado e nunca exercitado.

---

## 11. Anti-padrões para este projeto

**GUARDA** — coisas que já têm resposta aqui, e reintroduzi-las é regressão:

- **Camada sobre a camada de serviço.** Já existe; um segundo nome não melhora.
- **App novo para agrupar.** Sete apps com dono claro; o oitavo precisa de um
  conceito que não pertença a nenhum dos sete.
- **Guardar o que dá para derivar**, sem número que justifique — dado guardado
  diverge da fonte.
- **Editar plano ativo** em vez de gerar um novo. O produto trata plano como
  retrato; editar apaga história.
- **Escrita nova fora do contrato da fila**, quando a ação acontece no meio de
  outra atividade.
- **Auth paralela** — o filtro por usuário na consulta é o mecanismo.
- **`:has()` para estrutura**, framework de CSS, build step, dependência de Node
  — registrados no `CLAUDE.md`, e Node não existe neste ambiente.
- **Cache sem medição.**
