# NutriPlan

PWA de dieta e treino: calcula a meta calórica da pessoa, monta um plano de refeições
por horário com duas opções equivalentes em cada uma, monta a rotina de musculação da
semana a partir da frequência de treino, e acompanha a aderência.

## Stack

- **Django 5.2** — auth, admin, ORM e templates num pacote só
- **PostgreSQL 16** — banco
- **Templates do Django + CSS próprio** — sem framework de front-end, sem build step
- **Web Push (VAPID)** — notificações nos horários das refeições

## Rodando

O ambiente já está montado nesta máquina. Para trabalhar:

```bash
.\scripts\start_db.ps1
```

```bash
.venv\Scripts\python.exe manage.py runserver
```

O app fica em http://localhost:8000 e o admin em http://localhost:8000/admin/.

> O PostgreSQL foi instalado como binários portáteis em `C:\Users\biel-\pgsql`
> (sem privilégio de administrador), com o cluster em `C:\Users\biel-\pgdata\nutriplan`
> — de propósito fora do OneDrive, que corromperia os arquivos do banco ao sincronizar.
> Como não é um serviço do Windows, ele precisa ser iniciado a cada reboot pelo script acima.

Do zero, em outra máquina: criar venv, `pip install -r requirements.txt`, copiar
`.env.example` para `.env`, `migrate`, `seed_catalog`, `seed_workouts`, `createsuperuser`.

### Testes

```bash
.venv\Scripts\python.exe manage.py test
```

## Deploy

O repositório já vem com a infraestrutura declarada. No Render, conectar o
repositório é suficiente — o `render.yaml` cria o serviço web e o PostgreSQL, e
o `scripts/build.sh` prepara estáticos, banco e catálogo a cada deploy.

| Arquivo | Papel |
|---|---|
| `render.yaml` | Serviço web, banco e cron dos lembretes (Render Blueprint) |
| `railway.json` | Mesma coisa para o Railway |
| `Procfile` | Comando do gunicorn, para qualquer plataforma que leia Procfile |
| `scripts/build.sh` | `pip install` → `collectstatic` → `migrate` → seeds |
| `.env.example` | Todas as variáveis, com o porquê de cada uma |

Decisões que valem explicar:

- **O domínio entra sozinho em `ALLOWED_HOSTS`.** Render e Railway sorteiam o
  endereço no primeiro deploy e o publicam numa variável (`RENDER_EXTERNAL_HOSTNAME`
  / `RAILWAY_PUBLIC_DOMAIN`); `config/settings.py` lê. Sem isso, o primeiro
  acesso ao site novo responde 400 sem explicação — que é onde todo mundo trava.
- **`SECURE_PROXY_SSL_HEADER` é obrigatório.** A plataforma termina o TLS e
  conversa HTTP com o processo; sem o cabeçalho, o `SECURE_SSL_REDIRECT` vê
  "http", redireciona para https e entra em laço até o navegador desistir. Já
  aconteceu aqui num túnel que não enviava o cabeçalho — hoje há teste travando.
- **`collectstatic` roda antes de `migrate`, e o build aborta no primeiro erro.**
  Com `DEBUG=False` o Django usa o storage com manifesto: sem o manifesto, todo
  `{% static %}` explode em tempo de execução. Melhor o deploy falhar do que
  publicar quebrado.
- **O seed roda em todo deploy** porque é idempotente: no primeiro popula o
  catálogo, nos seguintes só reflete o que mudou no JSON.
- **Não ligamos HSTS preload.** Entrar na lista dos navegadores é quase
  irreversível e nem é possível de forma isolada num subdomínio emprestado
  (`*.onrender.com`). Fica para quando houver domínio próprio.
- **O banco gratuito do Render expira em 30 dias.** Para um site que precisa
  durar, troque o plano do banco no `render.yaml` antes de convidar gente.
- **Instalar no celular depende do deploy.** O navegador só oferece instalação em
  contexto seguro: `localhost` durante o desenvolvimento, HTTPS em qualquer outro
  lugar. Enquanto o app só existir na máquina local, o convite de instalação nunca
  vai aparecer num telefone.

### Vídeos dos exercícios

```bash
.venv\Scripts\python.exe manage.py check_exercise_videos
```

Confere no oEmbed do YouTube se cada vídeo do catálogo ainda existe e ainda permite ser
embutido. Vale rodar antes de um deploy e de tempos em tempos: vídeo de terceiro some sem
avisar. Para trocar algum, edite `workouts/data/exercises.json` e rode `seed_workouts`.

### Lembretes

Os lembretes saem de um comando, feito para rodar de 5 em 5 minutos no
Agendador de Tarefas do Windows (tarefa de usuário, não precisa de admin):

```bash
.venv\Scripts\python.exe manage.py send_meal_reminders --dry-run
```

`scripts\send_reminders.ps1` é o que a tarefa agendada chama. Rodar duas vezes no mesmo
minuto é seguro — quem decide se alguém já foi avisado é a constraint no banco.

## Organização

| App | Responsabilidade |
|---|---|
| `accounts` | Usuário, perfil, histórico de peso, dias de treino, wizard de onboarding |
| `catalog` | Alimentos, medidas caseiras, receitas (templates de refeição) |
| `plans` | Plano calculado, horários, opções de refeição, registro diário |
| `workouts` | Exercícios, divisões de treino e a rotina semanal de cada pessoa |
| `push` | Assinaturas Web Push e log de envios |
| `demo` | Monta a aplicação inteira sob `/demo/`, somente leitura (veja abaixo) |

## Decisões da interface

- **Escuro por padrão, claro como exceção.** O app é aberto na academia, de
  madrugada, na cozinha antes do café. Grafite em camadas com acento verde-menta
  cansa menos a vista e economiza bateria em tela OLED — e o tema claro continua
  existindo para quem usa o sistema em claro.
- **Nada rola na horizontal, e isso é garantido por construção.** `overflow-x:
  hidden` na raiz, `min-width: 0` em toda coluna de grid e `overflow-wrap:
  anywhere` no texto. Nome de exercício e de alimento são compridos; sem essas
  três regras eles empurram a página inteira para o lado.
- **Mobile-first de verdade, não "responsivo depois".** A tela é projetada para o
  celular em pé, com uma mão, e o desktop é o caso derivado: a partir de 60rem o mesmo
  HTML vira duas colunas — o cardápio, que a pessoa percorre, à esquerda; os números,
  que ela consulta, numa coluna que acompanha a rolagem.
- **Navegação inferior no celular, superior no desktop.** São quatro destinos (dieta,
  treino, métricas, perfil) e no celular eles ficam a um polegar de distância, como em
  qualquer app instalado. Os mesmos links viram abas na barra de cima quando há espaço.
- **CSS próprio, um arquivo, sem build step.** São ~1.000 linhas legíveis com tokens de
  cor, raio, sombra e espaçamento no `:root` — e tema escuro por
  `prefers-color-scheme`, que num PWA aberto de madrugada não é enfeite.
- **Alvo de toque nunca abaixo de 44 px** e número sempre em `tabular-nums`: caloria que
  dança de lugar a cada atualização faz o app parecer planilha.
- **O cartão do exercício tem quatro blocos fixos:** cabeçalho (ordem, nome,
  músculo alvo, série×repetição e descanso), mídia 16:9, instrução e tabela de
  séries. Cada bloco é uma linha de grid com espaço próprio. A versão anterior
  era um flex solto em que o formulário de carga disputava largura com o nome do
  exercício, e o resultado era o nome quebrado uma palavra por linha — grid
  explícito é o que torna isso impossível de acontecer de novo.
- **A carga é registrada por SÉRIE.** Uma linha por série prescrita:
  `[1ª] [carga] [OK] [cronômetro]`. A versão anterior guardava um número por
  exercício por dia, o que apagava a diferença entre a série pesada e a leve.
  Nada obriga a preencher todas — quem só quer anotar a mais pesada preenche uma.
- **A comparação com o treino passado usa a série mais pesada de cada dia**, e
  não série a série: a ordem em que a pessoa anota varia, e o que responde
  "evoluí?" é o topo do dia.
- **A mídia do exercício é uma fachada.** Miniatura com botão de play; o player
  nasce no toque, dentro do próprio cartão. Dezenove iframes carregando de uma
  vez seriam dezenove conexões ao YouTube na abertura da tela.
- **Cada refeição é um cartão**, com o horário em destaque, o alvo do horário e as duas
  opções como cartões clicáveis que abrem os ingredientes já nas quantidades certas. O
  botão "Comi esta" só aparece dentro da opção aberta — marcar é uma decisão, não um
  clique de passagem.
- **O anel de progresso é conic-gradient puro**, sem biblioteca de gráfico: é uma
  variável CSS `--pct` preenchida pelo template.
- **CSS e JS têm a versão na URL** (`app.css?v=<hash do conteúdo>`, em `push/assets.py`).
  Sem isso, um deploy de layout chega pela metade: HTML novo com folha antiga servida do
  cache, que não é "uma versão atrás" — é o app sem estilo nenhum. Aconteceu em
  24/08/2026 e as três camadas de cache erraram juntas (service worker, cache HTTP e o
  `fetch` de dentro do service worker). Com o endereço mudando junto com o conteúdo,
  nenhuma delas tem o que servir de errado. O hash é recalculado quando data ou tamanho
  do arquivo mudam — memorizá-lo por processo recria o bug, porque o `runserver` não
  reinicia quando só o CSS muda.

## Decisões de modelagem

- **Peso é histórico, não campo.** `WeightEntry` guarda a série; o peso atual é o
  registro mais recente. Isso dá o gráfico de evolução de graça.
- **`NutritionPlan` é um snapshot.** Ao recalcular a dieta criamos um plano novo e
  desativamos o anterior. O histórico antigo continua sendo avaliado contra a meta que
  valia na época. Uma constraint parcial no banco garante no máximo um plano ativo por pessoa.
- **`MealSlot` define o alvo, `MealOption` é a receita escalada até esse alvo.** É o que
  faz as duas opções serem nutricionalmente equivalentes por construção.
- **`MealTemplateItem.scalable`** separa o que cresce com a meta (arroz, frango) do que
  é fixo (1 ovo, 1 fatia, tempero) — sem isso o gerador produziria "1,3 ovo".
- **Macros da receita ficam em campos `_cache`,** recalculados por sinal quando um
  ingrediente ou alimento muda. Permite filtrar por caloria direto no SQL.
- **`MealLog` congela os macros no momento da marcação.** Editar uma receita hoje não
  pode reescrever o histórico de três meses atrás.
- **`NotificationLog` tem unique (usuário, refeição, dia)** — é isso que impede
  notificação duplicada se o job rodar duas vezes.

## Decisões do onboarding

- **Wizard de quatro passos**, não formulário único: dados corporais → objetivo →
  treinos → restrições.
- **Cada passo grava no banco na hora**, em vez de acumular na sessão (que é o que o
  `SessionWizardView` do django-formtools faz). Num PWA a pessoa fecha o app no meio do
  fluxo o tempo todo; com o progresso persistido em `Profile.onboarding_step`, ela
  retoma exatamente de onde parou, inclusive em outro dispositivo.
- **Guarda de navegação:** o passo N só abre se o progresso salvo já chegou nele. Não é
  segurança — é impedir que o banco fique com um perfil pela metade que o cálculo de
  dieta não consegue ler.
- **`advance_onboarding()` nunca retrocede** (`max()` do passo atual). Sem isso,
  reeditar o passo 1 depois de terminar o wizard jogaria a pessoa de volta ao começo.
- **O cadastro pede só nome, e-mail e senha.** Todo o resto é do wizard: pedir 12
  campos na tela de cadastro é a forma mais eficiente de perder o usuário na porta.
- **Passo 3 usa um horário único para todos os dias de treino.** Cobre a rotina da
  maioria e reduz o passo de 21 campos para 3; horários por dia se ajustam depois.

## Dados do seed

`catalog/data/foods.json` traz 102 alimentos, dos quais **62 ativos**: o catálogo é de
compra de mercado de bairro — arroz, feijão, ovo, frango, carne moída, batata, pão,
leite, queijo, tapioca, aveia, banana, maçã e os legumes de sempre. Suplemento (whey,
albumina), corte nobre (alcatra, salmão, camarão), castanha cara, semente fitness (chia,
linhaça), quinoa, granola, iogurte grego, tofu e fruta cara ou fora de época estão com
`"active": false` — aposentados, não apagados, para o histórico de quem já comeu aquilo
continuar legível e para voltar atrás ser questão de um campo.

Óleo de soja, margarina, requeijão, farinha de mandioca e presunto entraram porque é o
que existe na cozinha de verdade: o azeite ficou só para o que vai cru (salada, recheio
de sanduíche) e o que vai ao fogo passou a ser refogado em óleo, como se faz em casa.

`meal_templates.json` traz 54 receitas de rotina brasileira: arroz com feijão e ovo,
arroz com feijão e frango, cuscuz com carne moída, macarrão com carne moída, purê de
batata com frango, tapioca com ovo e queijo, pão francês com ovo, sanduíche de presunto e
queijo, mingau de aveia, iogurte com banana. **52 das 54 saem em 25 minutos ou menos**, e
as duas que precisam de forno estão marcadas com `everyday=False`.

Um teste percorre cada restrição do catálogo e exige receita inédita suficiente para
fechar o dia inteiro (2 no café, 4 nos lanches, 4 nas principais) — é o que impede uma
restrição de virar cardápio pela metade sem ninguém perceber.

`workouts/data/exercises.json` traz 32 exercícios de academia de bairro — barra, halter,
polia e as máquinas que existem em qualquer lugar — cada um com a dica de execução que
corrige o erro mais comum e o link de um vídeo demonstrando o movimento. `splits.json` traz as quatro divisões (corpo inteiro, AB, ABC
e ABCD) com séries, faixa de repetição e descanso por exercício.

Os valores nutricionais são aproximações de tabelas públicas — revise antes de usar com
pessoas reais. O `clean()` de `Food` avisa quando as calorias não batem com os macros
(tolerância de 20%), e há teste rodando esse `clean()` em todo alimento ativo do seed.

## Decisões do cálculo

- **`plans/calculations.py` é puro** — recebe um `PlanInputs`, devolve um `PlanResult`,
  não importa nada de banco. Toda a matemática é testável com números conferidos na mão,
  sem criar usuário. Quem lê o perfil e persiste o plano é o `plans/services.py`.
- **Mifflin-St Jeor para a TMB.** É a fórmula preditiva mais precisa entre as que só
  precisam de peso, altura, idade e sexo. Katch-McArdle acerta mais, mas exige percentual
  de gordura corporal — dado que o onboarding não pede porque quase ninguém sabe o seu.
- **Treino somado à parte, não embutido no fator de atividade.** Os fatores clássicos
  (1,2–1,9) já contam exercício e inflam a conta de quem treina. Aqui `activity_level` é
  só a rotina fora da academia, e o gasto do treino vem do MET × minutos reais.
- **Desconta 1 MET do treino.** A pessoa gastaria 1 MET só existindo naqueles minutos, e
  isso já está dentro da TMB. Sem a subtração, a mesma energia é contada duas vezes.
- **Uma meta só para a semana toda**, com o gasto do treino diluído em 7 dias. Meta de
  treino e meta de descanso seriam mais fiéis à fisiologia, mas dobrariam o plano de
  refeições — e o balanço energético não fecha à meia-noite.
- **Fator de atividade conservador, com o treino já dentro.** Três perfis, cada um uma
  faixa: sentado o dia todo (1,25–1,35), rotina com caminhada e tarefas (1,40–1,45),
  trabalho braçal ou cardio pesado (1,50–1,60). A posição dentro da faixa vem da
  frequência de treino — sem treino é o piso, cinco vezes por semana é o teto. Até
  24/08/2026 o nível descrevia só a rotina e o treino era somado por MET; isso inflava a
  meta de quem treina, porque a fórmula do MET trata uma hora de musculação como uma hora
  de esforço contínuo quando metade dela é descanso entre séries. **Efeito colateral
  aceito:** a duração da sessão deixou de mexer na dieta (só a frequência mexe) — ela
  continua descrevendo a ficha de treino.
- **Déficit de emagrecimento preso entre 300 e 500 kcal.** O percentual (-20%) decide
  onde dentro da faixa a pessoa cai; a faixa corta os extremos: 20% de 3.200 seriam 640
  kcal, déficit que quase ninguém sustenta sem perder massa magra. Ganhar massa e
  recompor seguem percentuais — recomposição depende de um déficit pequeno de propósito.
- **Teto de 2.800 kcal para emagrecer ou manter.** Meta acima disso quase sempre nasce de
  nível de atividade otimista, e o resultado é uma dieta que ninguém emagrece seguindo.
  A meta é limitada e o motivo vai para a tela. **Exceção:** acima de 120 kg o teto não
  se aplica — gente grande gasta mais mesmo — mas a meta sai explicada.
- **Quem quer as duas coisas tem objetivo próprio.** `Goal.RECOMP` (emagrecer e ganhar
  massa ao mesmo tempo) não é um "emagrecer" com etiqueta: a prescrição é outra — déficit
  de 5% em vez de 20%, porque o corte agressivo impede o ganho de massa, e proteína a
  2,0 g/kg em vez de 1,8, porque sem energia sobrando é ela que decide se o corpo mantém
  ou consome o músculo. O plano sai com um aviso de que a balança vai andar devagar, sem
  o qual a pessoa desiste em três semanas achando que a dieta não funcionou.
- **O déficit/superávit é mostrado como número, não deduzido.** A tela abre com
  "Déficit diário recomendado: −513 kcal" e a conta inteira ao lado
  (`gasto − déficit = meta`), mais o ritmo estimado em kg por semana pela convenção de
  7.700 kcal por quilo. Sem esse número a pessoa teria que subtrair de cabeça a meta do
  gasto para saber de que lado da linha ela está.
- **Pisos de segurança:** a meta nunca fica abaixo da TMB nem de 1.500/1.200 kcal, e a
  gordura nunca abaixo de 0,6 g/kg. Quando um piso entra em ação, o motivo é gravado em
  `NutritionPlan.notes` e explicado na tela — a pessoa não fica sem entender por que a
  meta não bateu com a conta.
- **Ordem dos macros:** proteína primeiro (1,8 g/kg, 2,0 na recomposição — alvo
  absoluto), gordura por percentual (25%), carboidrato com o que sobrou. Carboidrato é o
  macro flexível.
- **Recálculo é reconciliação, não evento.** `sync_active_plan()` roda na entrada da tela
  e compara entradas *e* saídas do plano ativo com os dados de hoje. Isso pega mudança
  vinda do wizard, do admin ou de um peso novo, sem espalhar chamadas de recálculo pelo
  código — e as saídas denunciam o que as entradas não pegam (mudar a duração do treino
  mantém `training_days_per_week`, mas move o TDEE).

## Decisões do cardápio

- **Cinco refeições fixas** (25/10/30/10/25% da meta), espalhadas entre acordar e dormir.
  Quantidade fixa em vez de variável com a janela mantém a tabela de percentuais legível
  e o plano previsível.
- **A refeição mais próxima do fim do treino vira o pós-treino**, 45 min depois. Escolher
  a mais próxima, em vez de fixar "o lanche da tarde", faz a regra servir tanto para quem
  treina 6h (o café vira o pós-treino) quanto para quem treina 19h (o jantar vira). Quem
  treina colado na hora de dormir come no fim do treino: comer tarde incomoda menos que
  comer no meio do próprio treino, que era o que acontecia sem essa amarra.
- **Distribuição por maior resto.** A meta é dividida em inteiros de forma que a soma das
  refeições bate exatamente com a meta do dia — arredondar cada parte isoladamente deixa
  uma diferença de poucas kcal que faz o app parecer que não sabe somar.
- **A escala isola os itens fixos.** `alvo = fixo + escalável × fator` é exato; usar
  `alvo / total` erraria proporcionalmente ao peso do que não escala. O fator fica preso
  entre 0,5x e 2,5x — fora disso a porção deixa de ser comida de verdade.
- **A escolha pontua desvio de caloria e de proteína, com a proteína pesando o dobro.**
  Só por caloria, o algoritmo bate o alvo com macarrão puro e ignora a meta de proteína.
- **Receita não repete no mesmo dia** — o gerador carrega o que já usou, porque almoço e
  jantar olham para a mesma categoria e o mesmo alvo. Repetição só é liberada quando não
  há candidata inédita, para o horário não ficar vazio.
- **Exatamente duas opções por refeição, A e B.** O número não é uma constante escrita à
  mão: `OPTIONS_PER_SLOT` é a quantidade de rótulos em `OptionLabel`, então o cardápio só
  cresce se alguém acrescentar um rótulo de propósito. Duas é decisão de produto — a
  pessoa abre o app com fome e precisa escolher, não comparar; com três ou mais a decisão
  custa mais que cozinhar e a refeição acaba pulada.
- **Catálogo curto não derruba o plano.** O horário sai com uma opção, ou nenhuma, e o
  motivo vai para `NutritionPlan.notes` e aparece na tela. Plano parcial e honesto é mais
  útil que uma tela de erro.
- **O cardápio fecha na meta, e a tela mostra a soma.** Os alvos por horário somam a
  meta exatamente (método do maior resto) e cada receita é escalada até o alvo do seu
  horário; seguindo a Opção A do dia inteiro, o total cai dentro de 3% da meta em todos
  os objetivos — e a tela imprime esse total em vez de pedir confiança. Quando a
  diferença passa de 40 kcal, ela é mostrada com o motivo: em algum horário a porção
  chegaria ao limite do que ainda é comida de verdade.
- **O plano avisa quando o catálogo não alcança a proteína.** Se somar a opção mais
  proteica de cada horário ainda ficar abaixo de 85% da meta do dia — o caso real é a
  dieta vegana barata — a nota diz a quantos gramas o cardápio chega de fato. Prescrever
  120 g e entregar 87 g em silêncio é pior que a lacuna em si.
- **`plan_is_current()` exige que o plano tenha refeições.** Sem isso, planos criados
  antes desta etapa continuariam ativos e a tela apareceria sem cardápio.
- **Praticidade entra na nota, não como filtro.** Receita marcada como não-cotidiana leva
  penalidade equivalente a errar 35% da caloria, e cada minuto de preparo acima de 20
  custa um pouco mais (com teto). Dieta que a pessoa não consegue executar não é dieta —
  mas como é só uma parcela da nota, a elaborada ainda entra quando é a única que atende
  às restrições.
- **Passar da proteína custa 35% do que custa ficar abaixo.** A meta de proteína é piso
  funcional, não teto: 80 g num almoço de 55 g não faz mal, 30 g deixa o dia devendo. Com
  o desvio simétrico o gerador fugia de frango e carne — que estouram o alvo — e enchia o
  almoço de tofu e carne de soja para quem nunca pediu isso. A caloria continua penalizada
  igual nos dois sentidos: é ela que decide se a pessoa emagrece ou engorda.
- **Plano com receita aposentada é refeito sozinho.** `plan_is_current()` também olha se
  o cardápio aponta para template inativo: mudar o catálogo propaga para quem já tem
  plano, na próxima visita, sem migração de dados nem botão.
- **Ingrediente aposentado derruba a receita inteira.** `candidates_for` exclui qualquer
  template com alimento inativo, então desativar um alimento no admin tira do ar todas as
  receitas que dependem dele — sem caçar receita por receita.

## Decisões do treino

- **A divisão vem da frequência, não do gosto.** 1 dia → corpo inteiro; 2 → AB (superior
  e inferior); 3 → ABC (empurrar, puxar, pernas); 4 → ABCD. Dividir o corpo em quatro
  dias para quem treina duas vezes por semana significa treinar cada músculo a cada duas
  semanas — a pior forma de organizar treino que existe.
- **De cinco dias em diante a divisão repete, não cresce.** Quem treina cinco ou seis
  vezes roda o ABC de novo (A, B, C, A, B). Inventar um quinto dia de "braço" preenche a
  semana sem adicionar estímulo; repetir o ciclo dá a cada grupo duas sessões na semana,
  que é o que rende mais.
- **Multiarticular primeiro, e com descanso maior.** Agachamento e supino abrem a ficha
  porque exigem o sistema inteiro descansado, e descansam 90-120 s entre séries — cortar
  esse tempo derruba a carga da série seguinte, que é justamente o que se quer aumentar.
  Isolados fecham o treino com 45-60 s. Há teste garantindo as duas coisas em todas as
  divisões do seed.
- **Repetição é faixa, não número.** A ficha manda 4×6-10: começa no 6, sobe semana a
  semana com a mesma carga e, ao fechar 10 em todas as séries, aumenta a carga e volta
  ao 6. É a progressão que faz o músculo crescer, não a variedade de exercícios.
- **Prancha é medida em segundos.** O campo `measure` existe para a ficha não dizer
  "3 × 12 de prancha", que não quer dizer nada para quem treina.
- **A ficha é um snapshot, como o plano alimentar.** `TrainingPlan` → `TrainingSession` →
  `SessionExercise` copia séries, repetições e descanso no dia da montagem: mexer no
  catálogo amanhã não reescreve a ficha de quem está treinando hoje. Mudou a frequência,
  o horário ou a duração do treino, nasce uma rotina nova na próxima visita à tela.
- **Cada exercício tem vídeo de execução, e o app sabe quando ele morreu.** O campo
  `Exercise.video_url` guarda o link normal do YouTube (o que se copia da barra do
  navegador) e a tela converte para embed na hora, em `youtube-nocookie.com` — o domínio
  que não grava cookie de rastreamento antes do play, o que num app que já sabe peso e
  objetivo de quem usa é a linha que interessa preservar. O botão "Ver execução" abre um
  modal **único para a página inteira**, e o iframe só nasce no clique: dezoito players
  embutidos de uma vez seriam dezoito pedidos ao YouTube na abertura da tela, no 4G da
  academia. Fechar o modal destrói o iframe, que é o que corta o áudio.
- **Vídeo de terceiro apodrece, então existe comando para conferir:**
  `manage.py check_exercise_videos` bate no oEmbed do YouTube e falha (status 1) quando
  algum vídeo saiu do ar ou teve o embed bloqueado pelo dono — foi assim que um dos 32 do
  seed foi pego antes de chegar ao usuário. Quando um vídeo morre, o modal ainda oferece
  a busca pelo nome do exercício em vez de mostrar tela preta.
- **`SECURE_REFERRER_POLICY` precisa ser `strict-origin-when-cross-origin`.** O padrão do
  Django (`same-origin`) remove o Referer de toda requisição externa, e o player do
  YouTube usa esse cabeçalho para autorizar o embed: sem ele o modal abria com
  "Erro 153". A política escolhida entrega só a ORIGEM para fora — o YouTube sabe que
  veio do NutriPlan e não descobre de qual página.
- **O volume semanal por grupo muscular fica visível** — é o número que denuncia quinze
  séries de bíceps e três de posterior. E o texto ao lado é honesto sobre o que a
  frequência atual permite, em vez de prometer uma faixa que a rotina não entrega.

## Decisões de engajamento

- **Carga é registrada por (pessoa, exercício, dia), não por série.** Anotar seis linhas
  por exercício no meio do treino ninguém faz, e a informação que decide o próximo treino
  é uma só: quanto você levantou. Anotar de novo no mesmo dia corrige em vez de duplicar.
  O vínculo é com o exercício e não com a ficha: a rotina é remontada quando a frequência
  muda, e o histórico de carga não pode morrer junto.
- **O campo de carga é `type="text"` com `inputmode="decimal"`.** Com `type="number"` o
  navegador descarta "62,5" e envia campo vazio — brasileiro digita vírgula, e quem tem
  que se adaptar é o formulário. A normalização e a faixa são validadas no servidor.
- **O cronômetro de descanso é uma barra fixa no rodapé, não um modal.** Durante o
  descanso a pessoa continua olhando a ficha para saber o próximo exercício. Vibra no
  fim (som na academia ninguém ouve) e o tempo vem da própria prescrição do exercício.
- **A lista de compras é organizada por corredor de supermercado**, não por refeição nem
  por macro: quem está no mercado anda por corredor. As quantidades são somadas para sete
  dias e arredondadas para cima, para embalagem — ninguém compra 847 g de arroz.
- **A substituição de alimento troca pelo macro dominante, não pela caloria.** Trocar
  150 g de arroz por uma quantidade isocalórica de azeite fecha a conta e destrói a
  refeição. O alimento é classificado pelo macro que domina as calorias dele, só entram
  substitutos da mesma classe, e a quantidade é calculada para igualar esse macro — com
  o resultado descartado quando as calorias fogem mais de 35%.

## Decisões do acompanhamento

- **Uma marcação por (pessoa, dia, horário)**, com `update_or_create`. Marcar de novo é
  corriqueiro — a pessoa clica em "pulei", muda de ideia e come. O registro é o estado
  final do horário naquele dia, não um log de auditoria de cliques.
- **Só o que foi comido conforme o plano soma macros.** "Pulei" zera e "comi outra coisa"
  também: não sabemos o que foi, e chutar contaminaria o histórico com número inventado.
- **Refeição pendente não é falha.** A aderência é `feitas / marcadas`, não
  `feitas / total do dia` — senão a tela acusa a pessoa de furar a dieta às oito da manhã,
  por causa do jantar que ainda nem chegou.
- **Dia sem marcação não entra no histórico.** Linha zerada de quando a pessoa nem usava
  o app não informa nada e ainda parece cobrança.
- **O slot é buscado dentro do plano ativo do próprio usuário** (e a opção, dentro do
  slot). Sem esses dois filtros, um id chutado marcaria refeição na conta errada.
- **A view guarda o log em `slot.log`** antes de renderizar. A linguagem de template do
  Django não indexa dicionário por variável, e criar um filtro só para isso é peso morto.
- **Recalcular no meio do dia carrega as marcações de hoje para o plano novo**
  (`carry_today_logs`), casando pela posição da refeição no dia. Sem isso a tela zeraria
  o dia e, ao marcar de novo, o mesmo almoço contaria duas vezes. O filtro é "tudo de
  hoje que não está no plano novo", porque dois recálculos no mesmo dia deixariam
  registros presos num plano ainda mais antigo.
- **O resumo do dia só conta o que está no plano ativo.** O que não aparece na tela não
  pode somar no total — é essa regra que impede um registro órfão de inflar o dia.
  O histórico, ao contrário, conta tudo: lá o passado é fato consumado.

## Decisões do PWA e das notificações

- **O `sw.js` é servido pela raiz por uma view**, não como arquivo estático. Um service
  worker em `/static/` teria escopo só sobre `/static/` e não controlaria o app. A view
  ainda manda `no-store`: service worker cacheado é app congelado numa versão antiga, e
  é o problema mais chato de diagnosticar em PWA.
- **Cache só de `/static/`.** Guardar HTML de usuário logado no cache do dispositivo
  serviria o dia de uma pessoa para outra no mesmo aparelho — e mostraria dieta velha
  depois de cada marcação. Navegação é network-first com a página offline como rede de
  segurança.
- **Estático com `?v=` vem do cache primeiro; sem `?v=`, vai à rede.** É de onde vem o
  carregamento instantâneo na segunda abertura. A distinção não é estilo: uma URL que
  carrega o hash do conteúdo (`app.css?v=8dd82f15`) responde sempre a mesma coisa, então
  servir do cache não pode servir algo diferente do que a página pediu. Sem o hash, a URL
  não promete nada — e foi exatamente esse caso que já entregou CSS velho junto com HTML
  novo, deixando o app sem estilo. Os dois caminhos têm teste.
- **A ativação do service worker poda o cache.** Apaga gerações antigas (`nutriplan-v4`
  quando já se está na v5) e, dentro da geração atual, os arquivos de builds anteriores.
  Sem isso o cache-first só cresce: numa máquina de desenvolvimento chegaram a nove pares
  de CSS e JS empilhados, e é o disco do usuário que paga.
- **Ícone `any` e ícone `maskable` são arquivos diferentes.** O Android recorta o maskable
  no formato que o fabricante escolher e só o círculo central sobrevive; declarar
  `"any maskable"` no mesmo arquivo — o atalho comum — faz a letra aparecer cortada em
  boa parte dos aparelhos. São dois desenhos: um preenchendo a arte, outro com margem.
- **Os ícones não levam `?v=`, ao contrário do CSS.** O endereço do ícone é a identidade
  do app instalado; mudá-lo a cada alteração de folha de estilo faria o sistema baixar
  tudo de novo à toa. Ícone que muda é ícone com nome novo.
- **iOS ignora o manifest inteiro.** Lá quem manda são as metas `apple-*` no `<head>`.
  `black-translucent` na barra de status é o que dá o visual de app nativo no tema escuro
  — e exige `viewport-fit=cover` mais `env(safe-area-inset-top)` no CSS, senão o conteúdo
  fica embaixo do relógio.
- **O convite de instalação nasce escondido.** No Android aparece quando o navegador
  dispara `beforeinstallprompt` (que é o próprio veredito dele de que o app é instalável);
  no iPhone, onde não existe evento nem API de instalação, aparece com o caminho do menu
  Compartilhar. Some para quem já instalou, e a recusa fica guardada.
- **A duplicidade de notificação é resolvida pelo banco, não por `if`.** O
  `NotificationLog` é criado ANTES do envio; se a constraint (usuário, refeição, dia)
  recusar, é porque outro ciclo do job já cuidou. É isso que torna o comando seguro de
  rodar de 5 em 5 minutos — ou duas vezes por engano.
- **Refeição já marcada não gera lembrete.** Avisar sobre o almoço que a pessoa já comeu
  é o tipo de detalhe que faz desinstalar o app.
- **Assinatura morta (404/410) é desativada, não apagada** — o histórico de qual
  dispositivo recebeu o quê continua legível. Erro de rede, ao contrário, não desativa
  nada: é temporário, e um celular com problema não pode custar o lembrete dos outros.
- **Sem chave VAPID o app funciona igual**, só não oferece notificação. É o que permite
  rodar em dev, em CI e no primeiro deploy sem ter gerado chave nenhuma.
- **Ícones gerados por código** (`scripts/make_icons.py`), sem dependência de biblioteca
  de imagem: um PNG escrito na mão com `zlib` é menos peso que arrastar Pillow para o
  projeto por causa de quatro arquivos. E, como o desenho sai das cores da marca,
  repintar tudo quando a paleta muda é um comando em vez de quatro exportações à mão.

## Modo demo

Uma versão pública e somente leitura do aplicativo, em `/demo/`. Existe para
mostrar o NutriPlan a quem não tem conta — pessoa ou ferramenta de análise —
sem expor dado de ninguém.

**Em produção:** <https://nutriplan-xxfn.onrender.com/demo/>

### Não é uma segunda aplicação

Essa foi a decisão que definiu tudo o resto. Uma cópia das telas nasce igual e
diverge na primeira semana: o demo passa a mostrar uma versão do app que não
existe mais, o que é pior do que não ter demo.

Então o demo **monta a mesma aplicação sob outro prefixo**. Quem faz isso é
`demo/middleware.py`, em três passos:

1. tira o `/demo` de `request.path_info` — o resolvedor de URL do Django
   encontra a rota real, e `/demo/treino/` cai em `workouts:routine`;
2. chama `set_script_prefix("/demo/")` — e aí todo `reverse()` da renderização
   devolve o prefixo de volta, então a barra de abas, os formulários e os links
   do template **real** apontam para dentro do demo sozinhos;
3. troca `request.user` pelo usuário fictício.

O passo 2 é o que faz a coisa funcionar. Sem ele, a navegação de dentro do demo
mandaria a pessoa para `/treino/`, que exige login — exatamente o beco sem
saída que o demo existe para não ter. Nenhum template foi duplicado.

### Rotas

| Rota | O que é |
|---|---|
| `/demo/` | Capa: quem é o personagem e a lista das telas |
| `/demo/sobre/` | O que é o demo, o que não funciona e por quê |
| `/demo/hoje/` | Painel do dia — apelido, veja abaixo |
| `/demo/treino/` | Ficha da semana |
| `/demo/suplementos/` | Checklist e o que cada suplemento faz |
| `/demo/historico/` | Aderência, média de calorias, curva de peso |
| `/demo/lista-de-compras/` | Compras da semana por corredor |
| `/demo/conta/perfil/` | Dados que alimentam o cálculo |

Qualquer rota do app funciona sob `/demo/` sem ser listada aqui — a tabela é o
que a capa oferece, não o que o middleware aceita.

`/demo/hoje/` é o **único apelido** do demo, e existe por colisão: o painel do
dia mora na raiz da aplicação (`/`), e a raiz do demo é a capa. Ele está em
`APELIDOS`, no middleware. Cada apelido novo é uma rota que existe no demo e
não existe no app — é assim que um demo começa a divergir do produto, então a
regra é não criar o segundo sem um motivo tão concreto quanto este.

### Como os dados reais ficam protegidos

Três camadas, e a primeira é a que não depende de memória:

1. **Nenhum método que escreve chega na view.** O middleware recusa tudo que
   não é `GET`, `HEAD` ou `OPTIONS`, e responde com uma página explicando.
   Proteger botão por botão dependeria de eu lembrar de todos — hoje e no
   próximo recurso.
2. **O demo não alcança outro usuário.** As telas leem sempre `request.user`,
   e sob `/demo/` ele é sempre o Carlos. Não existe caminho que receba id de
   pessoa por parâmetro.
3. **A conta do demo tem senha inutilizável.** Ela existe para o middleware
   ler, e não para alguém entrar nela pela tela de login.

Fora de `/demo/`, nada muda: `/`, `/treino/` e o resto continuam pedindo login.
Há teste para cada uma dessas quatro afirmações em `demo/tests.py`.

### Os dados fictícios

Carlos Silva, 28 anos, 78 kg, 1,78 m, hipertrofia, três treinos por semana à
noite. Mora em `demo/management/commands/seed_demo.py`.

O que **não** está escrito à mão: a meta calórica, os macros, o cardápio e a
ficha de treino. Todos saem das mesmas funções que atendem qualquer pessoa —
`plans.services.sync_active_plan` e `workouts.services.create_routine`. É isso
que faz o demo continuar parecido com o produto quando o produto muda.

O que está escrito à mão é só a entrada: idade, peso, altura, objetivo, dias de
treino, e uma curva de doze semanas de peso subindo devagar.

O dia chega **meio vivido**: as primeiras refeições marcadas e 1,6 L de água. É
deliberado — dia em branco esconde a barra de progresso e o cartão de refeição
concluída; dia cheio esconde o botão de marcar. Metade mostra os dois estados.

Para mudar o personagem, edite as constantes no topo do comando e rode:

```bash
python manage.py seed_demo --refazer
```

O comando é idempotente: sem `--refazer` ele atualiza o que existe.

### Para acrescentar uma tela ao demo

Na maioria dos casos, nada — qualquer rota nova do app já funciona sob
`/demo/`. O que costuma faltar é ela aparecer na capa: acrescente uma linha em
`AREAS`, em `demo/views.py`, com o nome da rota, o título e uma frase do que a
tela faz.

Se a tela nova precisar de dado que o Carlos não tem, o lugar é o `seed_demo` —
e prefira montar esse dado com a função de serviço que o app usa, em vez de
escrever o resultado.

### O que não funciona no demo

Tudo que escreve: marcar refeição, registrar carga, anotar água, salvar perfil,
refazer o onboarding. A pessoa recebe uma página dizendo que o modo é somente
leitura, e não uma tela de login nem um erro.

Login, cadastro e recuperação de senha também ficam de fora — o demo não tem
conta para entrar.

## Roadmap

- [x] Etapa 1 — modelagem do banco
- [x] Etapa 2 — cadastro, autenticação e onboarding
- [x] Etapa 3 — cálculo de meta calórica e macros
- [x] Etapa 4 — geração do plano de refeições
- [x] Etapa 5 — tela de acompanhamento diário e histórico
- [x] Etapa 6 — PWA e notificações push
