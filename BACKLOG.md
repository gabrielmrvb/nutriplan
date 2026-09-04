# Backlog do NutriPlan

O que ficou decidido mas não feito, e o que depende de gente. Cada item diz
**por que** está aqui — item sem motivo vira lista que ninguém lê.

## Bloqueado por decisão ou ação humana

### ⛔ Validação de GPS em aparelho físico — CORRIDA V1
O software da Corrida V1 está pronto, publicado e provado em navegador com
geolocalização SIMULADA. Simulação não é aparelho na rua, e as duas não podem
ser confundidas.

O roteiro é [`docs/prova-corrida-aparelho.md`](docs/prova-corrida-aparelho.md),
11 itens, 10 a 15 minutos, com uma caminhada curta. O **item 11 é o novo**, e é
o que a V1 acrescentou: encerrar a corrida com o modo avião LIGADO e conferir
que ela sobe sozinha depois — e uma vez só, o que prova a idempotência na rua.

Enquanto isso não acontecer, a Corrida fica em
**CORRIDA V1 — SOFTWARE ✅ / VALIDAÇÃO GPS FÍSICO ⏳**, e não vira quinta aba.

### ⛔ Backup independente de produção — UM CLIQUE SEU
Revalidado em 04/09/2026, e o registro anterior estava desatualizado: a máquina
de backup existe inteira e foi endurecida na INFRA SAFETY P0. O que falta é
humano e é pequeno.

O que está pronto e provado: `scripts/backup.sh` despeja e confere,
`scripts/guardar.sh` criptografa em AES-256 e **prova que decifra** antes de
apagar o original, `scripts/restaurar.sh` aceita o `.gpg` direto e restaura num
banco descartável varrendo integridade referencial. A cadeia inteira foi
executada de ponta a ponta contra o banco local em 04/09/2026.

O que falta, e só você pode fazer — **uma das duas**:

1. **Rota da máquina** (menor superfície): rodar as duas linhas de
   [`docs/infra-recuperacao.md`](docs/infra-recuperacao.md) com a
   `DATABASE_URL` do painel e uma senha do seu gerenciador. Nenhum segredo sai
   daqui.
2. **Rota do GitHub**: cadastrar os segredos `DATABASE_URL` e
   `BACKUP_PASSPHRASE` em Settings → Secrets → Actions e apertar "Run workflow"
   em `.github/workflows/backup.yml`. Medido pela API pública em 04/09/2026:
   `total_count: 0` — **o fluxo nunca rodou nem uma vez**.

Enquanto nenhuma das duas acontecer, a cópia mais nova é de 01/09/2026 16:09,
está só nesta máquina e está **em claro**.

### ⛔ Classificar as 52 contas de produção
O campo `classificacao` existe e o painel mostra quantas estão sem
classificação. Nenhuma foi classificada — de propósito: o banco não sabe o que
elas são, e adivinhar inventaria o número. É decisão de gente, uma a uma, no
Django Admin.

### ⛔ OAuth do Admin de ponta a ponta
O seletor de contas do Google exige clique humano: evento sintético não dispara
os manipuladores dele. O que está provado sem isso, em produção: anônimo vai ao
login, `next` é preservado, destino externo é descartado, staff autenticado
entra direto, e o provedor continua ligado.

### ⛔ Usuário comum → 403 em `/admin/`
Provado em ambiente controlado. Em produção exigiria a sessão de uma conta
real, e o demo não serve: o middleware troca `request.user` por requisição e só
sob `/demo/`, sem criar sessão.

### ⛔ `LEGAL_RESPONSAVEL` e `LEGAL_CONTATO`
Faltam os dados para as páginas legais.

## Decisões a revisar antes de crescer

### `/conta/social/` não tem porta no app
A tela de contas conectadas foi vestida com a identidade do produto em
`57a9f6a`, e a capability é real: ver e desvincular o Google só existe ali — o
perfil não oferece nada disso. Mas **nada linka para ela**. Quem quiser
desvincular precisa digitar a URL.

Ficou de fora de propósito: acrescentar uma entrada no perfil é decisão de
produto, não conserto de defeito. A pergunta é se desvincular o Google é coisa
que alguém faz — se for, o lugar é o perfil, perto de "Trocar minha senha".

É a mesma pergunta que `TodaTelaTemPortaTests` faz para decidir quem entra na
tabela dele: "alguém precisa poder ir até lá por vontade própria?". Se a
resposta for sim, o destino entra em `DESTINOS` e o teste passa a cobrar o
link — hoje ele falharia, porque link nenhum existe. Por isso a decisão vem
antes do teste, e não o contrário.

### Retenção do log administrativo, antes de operação multi-staff
`RegistroAdministrativo` usa CASCADE: apagar a conta apaga a trilha dela,
inclusive o marcador de primeiro administrador. É o contrato atual do projeto —
toda FK para User é CASCADE para que excluir a conta apague o dado pessoal. Com
mais de uma pessoa operando, a pergunta "quem fez o quê" passa a competir com
essa regra, e a hora de decidir é antes.

### `change_user` permite editar o e-mail
Trocar o e-mail de alguém e pedir recuperação de senha é tomada de conta em dois
passos — a mesma família do que foi fechado em `<pk>/password/`. O contrato
atual mantém `change_user`; vale decidir se o campo `email` fica somente
leitura, e qual é o caso de suporte que o exige.

### Duas superfícies registradas que ninguém alcança
`plans.mealslot` e `workouts.trainingsession` estão registradas no Admin e
nenhum papel tem `view`. Ficam na matriz de capability documentadas como
fechadas. Decidir se desregistra — hoje a proteção depende só da ausência de
permissão.

### `plans.meallog` visível ao Administrador
É o registro alimentar de todas as pessoas. A mesma pergunta que levou a tirar a
página avulsa de pesagens: qual é o caso operacional que a tela da própria conta
não resolve?

### `PushSubscription` sem `has_delete_permission` negado
As outras superfícies imutáveis negam os três métodos. Esta nega `add` e
`change` e deixa `delete` só pela ausência de permissão.

## Perdido de propósito, para recuperar em outro lugar

### Diagnóstico agregado de registro de peso
A página avulsa de pesagens saiu porque navegar a série de todas as contas não
responde atendimento nenhum. O que ela permitia e ninguém mais permite é
perguntar "o registro de peso parou para todo mundo depois do dia X?". É
pergunta legítima e é de painel agregado — cabe em `/gestao/`.

## Prazo

### Banco gratuito apagado por volta de 23/09/2026
O prazo é do banco do **Render**, lido no painel em 31/08/2026. Produção NÃO
está mais nele desde 01/09 — provado em 04/09 pelo cabeçalho do dump daquele
dia, que declara servidor 16.9, enquanto o Render rodava 18.4 e um cliente 16.9
não consegue despejar um servidor 18.4. O bloco `databases:` do `render.yaml`
mantém o banco antigo de propósito: ele é o rollback, e expira sozinho.

**NÃO verificado por mim:** se o plano gratuito do Neon tem prazo próprio. É
uma olhada no painel do Neon, e é sua. Até lá, o risco de expiração do banco em
uso é desconhecido, não descartado.

## Segurança futura

### 2FA no Admin
Hoje a entrada administrativa é Google-only, o que já é um segundo fator na
prática — mas por delegação, não por política nossa.

### Domínio próprio para o e-mail transacional
A recuperação de senha sai por remetente de terceiro. Domínio próprio muda
entregabilidade e reduz a chance de a mensagem virar spam.

## Medido e vale guardar

### Ativar o service worker apaga o cache de páginas inteiro
Medido em navegador real em 04/09/2026, no local e em produção:
`nutriplan-v6-paginas` tinha 2 entradas antes; depois de uma ativação de worker
de verdade, o cache **não existe mais**. Como toda publicação instala um worker
novo, **todo deploy zera o cache de páginas**.

Quem faz isso é `limpar()`, na primeira das duas limpezas:
`keys.filter((k) => k !== CACHE)`. `CACHE_PAGINAS` é `"nutriplan-v6-paginas"`,
que é `!== "nutriplan-v6"` — então ele entra no filtro. O comentário ao lado só
promete apagar "gerações antigas" (`nutriplan-v4` quando já estamos na v5), e
o cache de páginas da geração ATUAL não é isso.

**Não corrigir sem defeito comprovado.** O comportamento é defensável: uma
página guardada aponta para estáticos do build anterior, e servir esse shell
velho depois de um deploy seria pior que perder o offline por uma navegação. O
que está errado é a documentação, não o efeito — está certo por acidente de
nomenclatura, e é isso que fica registrado aqui.

Isto é diferente da limpeza que `f301dc6` acrescentou: aquela é por RECADO, na
tela de entrar, e existe para a sessão que acaba. Esta é no `activate`, e
acontece por publicação.

### O peso sozinho responde por 17 contas
Medido em produção em 02/09/2026: 17 contas registraram peso e **nenhuma** outra
ação voluntária. Se o peso contasse como engajamento, "registraram algo por
conta própria" saltaria de 27 para 44 — exatamente o número de quem terminou o
onboarding, porque o peso é obrigatório no passo 1. É a prova concreta de por
que ele fica de fora.

## Corrida

### ⛔ Medir o GPS num aparelho de verdade
Cinco medições de poucos minutos, listadas em `docs/running-analise.md`: quanto
tempo `watchPosition` entrega com Wake Lock; quantos segundos até parar ao
bloquear a tela; se retoma sozinho ao voltar; quantas leituras se perdem ao
trocar de app por 30 s; e qual a `accuracy` típica na rua onde a pessoa corre.

A última decide o limite do filtro, que hoje é palpite informado — e chutar o
limite é chutar a distância.

### Corrida vira aba de topo depois da medição
A visão aprovada é Dieta / Treino / Corrida / Progresso / Perfil. Hoje a porta
está na tela de treino, e não na barra de baixo, porque promover a destino de
topo é dizer "isto funciona" — e ninguém verificou que funciona com a tela de
um celular de verdade.

### Mapa e traçado
O traçado NÃO é guardado hoje, e é decisão. Quando o mapa for desenhado, a
decisão que vem junto é o corte das pontas da rota: uma imagem compartilhada
que começa e termina na porta de casa publica o endereço.

### "Recorde" precisa de definição
Melhor pace de 1 km, melhor pace médio de uma corrida de 1 km, e melhor 1 km
dentro de uma corrida longa são três coisas. Sem escolher, a tela mostra as
três com o mesmo nome.

## Fila offline local

### Recuperação/expiração de fila offline legada
Operações enfileiradas antes da separação por dono ficam em quarentena: não são
enviadas por ninguém e não são apagadas. Não há tela para elas, e criar um botão
"recuperar" que peça à pessoa para adivinhar de quem eram os dados trocaria um
problema por outro. Decidir: mostrar, expirar, ou deixar como está.

### Retenção da fila local
A fila pode conter alimentação, água e carga — dado pessoal, guardado no
aparelho por tempo indefinido se a pessoa nunca voltar. Falta política de idade
máxima, tamanho máximo, limpeza de órfãos e uma tela de "ações aguardando
sincronização". Nada disso pede criptografia no cliente: a chave teria que ficar
no mesmo aparelho, e isso é enfeite, não proteção.

### Limpeza/expiração de filas órfãs
Se o navegador fechar entre a exclusão da conta e a tela seguinte, o sinal morre
com a sessão e a fila daquela conta fica órfã no aparelho. Não é vazamento — ela
nunca drena, nunca conta para ninguém e nunca é atribuída. É dado pessoal
ocupando espaço sem prazo. Mesma família do item de retenção acima.

### Notificação entre abas no logout
Não existe `BroadcastChannel` nem ouvinte de `storage`. Sair numa aba não avisa
as outras, que seguem mostrando o HTML já renderizado. Não abre acesso — toda
navegação cai em 302 e o cache de páginas já foi apagado —, mas é risco
conhecido de navegador com várias abas.

## Achados da varredura de navegador (02/09/2026) — PUBLICADOS

Fechados e no ar em `aac20b8`. Ficam registrados porque a origem de cada um
ensina mais que a correção:

- **P0 — loop de redirecionamento** entre `/` e `/conta/onboarding/`. Duas
  réguas de "onboarding completo": o contador de passos e o que o motor exige
  (que também pede peso). Perfil no passo final sem pesagem ficava preso, com a
  tela em branco e sem mensagem.
- **P0 privacidade — shell offline guardava sessão.** `cache.addAll(SHELL)`
  leva cookie, então `/offline/` era pré-cacheado AUTENTICADO no cache de
  estáticos, que sobrevive ao logout. No ar isso congelava
  `data-autenticado="1"` e as mensagens da sessão que instalou o app; nesta
  branch teria congelado também `data-usuario`, a chave que a fila lê.
- **P0 — service worker publicado quebrava a drenagem.** `const db` preso ao
  `try` fazia `removerDaFila` lançar `ReferenceError`; o `catch` executava
  `break` e a fila abortava no primeiro item, com o `waitUntil` rejeitando e o
  Background Sync reagendando. Introduzido em `9bc541f`.
- **P2 — link quebrado na política de privacidade**, apontando para uma rota
  que só aceita POST de propósito.

### PREMIUM POLISH — B1 A B11 ✅ COMPLETO

**B1 — LOGIN / CADASTRO ✅** Auditado em navegador real em 375, 430, 768 e
desktop. A tela já estava boa: zero rolagem horizontal, zero alvo abaixo de
44×44, zero texto abaixo de 11px, contraste AA em todos os textos medidos,
`autocomplete` correto em todos os campos, foco de teclado visível por
`:focus-visible`, e o estado de carregamento do botão já implementado com
`aria-busy`, pulso lento e `prefers-reduced-motion`.

Dois defeitos reais, os dois medidos e não supostos:

1. o `autofocus` do cadastro caía no SEGUNDO campo — `UserCreationForm` o marca
   no `USERNAME_FIELD`, que aqui é o e-mail, enquanto a tela pergunta o nome
   primeiro. Quem começava a digitar escrevia o nome dentro do e-mail;
2. a mensagem de credencial inválida afirmava que "ambos os campos diferenciam
   maiúsculas e minúsculas". Medido: o e-mail entra em caixa alta sem problema,
   porque o backend do allauth acha a conta sem diferenciar caixa. A frase
   mandava conferir a capitalização do e-mail quando o defeito estava na senha.

**B2 — HOJE ✅** Auditada em navegador real em 375, 430, 768 e desktop. A tela
já respondia "o que preciso fazer agora?" na primeira dobra: o cartão AGORA em
y=93 com a ação e o CTA em y=202, o resumo de uma linha em y=283, e a primeira
refeição pendente com seus botões ainda dentro da dobra. Réguas limpas nas
quatro larguras.

Um defeito real, medido: **toda escrita da tela devolvia a pessoa ao TOPO** de
uma página de 4 a 5 dobras. O cartão de água começa em y=2491, então cada
"+250" era rolar 2500px, tocar e ser jogado de volta — doze idas para fechar
três litros. O mesmo em marcar refeição e desfazer. As âncoras já existiam no
template (`#hidratacao`, `#slot-<pk>`, esta já usada pelo cartão AGORA); o
conserto foi usá-las no redirect. Os ramos de ERRO continuam no topo, onde a
mensagem é renderizada.

Não mexido, por decisão declarada no código: a água só vira cartão AGORA quando
não há refeição nem treino pendente ("sobra a água — e ela só aparece quando
falta mesmo").

**B3 — TREINO ✅** Auditado em navegador real em 375, 430, 768 e desktop, nos
quatro estados da tela: sem rotina, dia de descanso, em treino e concluído.
Réguas limpas em todos — zero rolagem horizontal, zero alvo abaixo de 44×44,
zero texto abaixo de 11px. A conclusão foi percorrida no navegador até o fim:
última série → tela "Treino concluído" com 9 exercícios e 29 séries contadas
(não estimadas). O `<dialog>` do vídeo abre, nomeia o exercício, prende o foco,
devolve o foco ao gatilho ao fechar, destrói a mídia e não perde a rolagem.

Cinco defeitos reais, os cinco medidos:

1. **o relógio do descanso falava uma vez por segundo.** Ele vivia dentro de um
   `role="status" aria-live="polite"` e trocava de texto a cada tique — medido
   com `MutationObserver`, cinco mutações em 5,2 s, nas DUAS telas de treino.
   Cada mutação faz o leitor de tela reler a região inteira: são ~80 anúncios
   por descanso e ~2.200 num treino de 29 séries, e nada mais da tela consegue
   ser ouvido nesse meio-tempo. O relógio continua na tela e continua legível;
   quem fala agora é um aviso `.vis-oculto` à parte, duas vezes — quando o
   descanso começa e quando acaba;
2. **"desfazer última série" sumia quando o exercício fechava.** A última série
   da puxada é justamente a que passa a vez para a remada, e aí `atual.feitas`
   é zero e o botão não existe mais — nove vezes por treino, sempre logo depois
   da série mais provável de ter sido anotada por engano. Agora ele segue
   `estado.ultimo_log`, e nomeia o exercício quando não é o da tela;
3. **a única porta para a Corrida era o último bloco do documento** — medido a
   375px, o cabeçalho "Corrida" em y=5476 de uma página de 5755, abaixo de três
   blocos que não são ação nenhuma. Subiu para o começo da coluna lateral, e o
   cabeçalho passou para y=3155 numa página de 5787. O link em si ficou em
   y=3250 em 375, 3117 em 430, 2865 em 768 e 3311 em 1280 — e a coluna é única
   em toda largura, por decisão já registrada no CSS, então a ordem do
   documento é a ordem da tela nas quatro.

E mais dois, achados na própria correção:

4. **o empate de carimbo escolhia ao acaso.** `ultimo_log` saía de um `max` por
   `created_at`, e `auto_now_add` chama `timezone.now()` no Python — cujo
   relógio no Windows tem granularidade de milissegundos. Duas séries gravadas
   na mesma janela ficam com o carimbo idêntico, e `max` devolvia a primeira da
   iteração, que era a do exercício ANTERIOR. Enquanto isso só alimentava o
   cronômetro custava segundos de descanso; com o desfazer pendurado nisso,
   apagaria a série errada. Desempate agora é `(created_at, pk)`;
5. o `<title>` dizia "Treinando" nos três estados, inclusive na tela que diz
   que o treino acabou e na que diz que hoje é descanso.

Publicado em `50668fb` e verificado em produção, em navegador real sobre
`/demo/treino/` (leitura, nenhuma conta tocada): a barra do cronômetro já não
tem ancestral com `aria-live`, o aviso escondido existe, e num descanso inteiro
a barra mudou 7 vezes enquanto a região viva falou DUAS — "Descanso de 5
segundos." e "Descanso terminado, pode ir.". A porta da Corrida ficou em y=3513
(375), 3217 (430), 3129 (768) e 3460 (1280), em páginas de 6051 a 5240, sempre
uma só. Zero rolagem horizontal, zero alvo abaixo de 44×44 e zero texto abaixo
de 11px nas quatro. Zero 5xx em 16 rotas.

O que NÃO foi provado em produção: o redirect do desfazer e a conclusão do
treino, porque exigiriam ESCREVER numa conta real. Os dois estão provados no
navegador contra a stack local, com conta QA descartável.

A primeira versão da mudança da Corrida movia o cartão para dentro da coluna
lateral e apagava a porta de quem ainda não cadastrou dias de treino —
`ACorridaTemPortaTests`, que já existia, pegou. O cartão virou
`_corrida.html` e é incluído nos dois estados.

Não mexido, por decisão: o motor de volume e duração; a fonte e o timestamp dos
vídeos; e o recarregamento de página a cada série — ele é consequência de todo
o estado sair de `ExerciseLog`, e não custa posição porque o cartão inteiro
cabe na primeira dobra (medido: `scrollY` volta a 0 e o botão fica em y≈600).

Achado durante o B3 e NÃO corrigido nele, porque não é polimento: a fila
offline cobre `/treino/exercicio/<id>/carga/` — a gravação pela LISTA — e não
cobre `/treino/agora/serie/`, que é a tela usada de pé na academia, onde o sinal
é pior. Não é uma linha de código: `record_load` é idempotente por
`update_or_create`, então enfileirar a GRAVAÇÃO seria seguro, mas a mesma rota
também recebe `acao=desfazer`, que apaga o maior `set_number` e reenviado duas
vezes apaga duas séries. Entrar na fila exige separar as duas ações, ou dar
`op_id` ao desfazer — decisão de arquitetura, não de tela.

Pendência declarada: "pular" o descanso é só do cliente. Recarregar a página
traz o descanso de volta, porque ele é derivado de `created_at` — que é
exatamente o que o faz sobreviver a trocar de aba e bloquear a tela. Lembrar a
recusa exigiria estado novo para um elemento que é informação, não porteiro.

**B4 — PROGRESSO V2 ✅** Auditada em navegador real em 375, 430, 768 e desktop,
nos dois estados: sem nada registrado e com oito semanas de peso, treino, água
e refeições. Réguas limpas nos oito cruzamentos — zero rolagem horizontal, zero
alvo abaixo de 44×44, zero texto abaixo de 11px. Contraste medido nos 16 textos
da tela, compondo os fundos tingidos antes de contar: de 5,68 a 18,18, todos
acima de AA. A ordem do contrato — Resumo → Peso → Treino → Água → Dia a dia —
está no documento e, como `.split` é coluna única em toda largura, é também a
ordem da tela nas quatro.

Quatro defeitos, os quatro medidos:

1. **o convite a recalibrar a dieta não sumia depois de respondido, e o botão
   não tinha teto.** `Profile.recalibrated_at` era gravado pelas duas respostas
   e não era lido por ninguém — `grep` não achava uma leitura sequer, e
   `sugerir_recalibragem` saía só do peso, que não se mexe em dois minutos.
   Medido no navegador: dois toques em "Cortar 150 kcal" no mesmo minuto
   levaram `kcal_adjustment` a −300 e a meta a 1773 kcal, com o cartão ainda na
   tela oferecendo o terceiro. A docstring da própria view já dizia que o app
   registra a escolha "para não repetir a pergunta na semana seguinte" — dizia,
   e não fazia. Agora espera duas semanas, que é o prazo que os dois textos de
   resposta já prometiam por escrito, e a view recusa o reenvio de uma aba
   velha explicando por quê;
2. **as barras de Treino e Água não eram comparáveis.** As duas desenham a
   mesma escala de 0 a 7, uma embaixo da outra, e os trilhos tinham larguras
   diferentes porque a barra é `1fr` e a coluna de valor da água reserva mais
   espaço. Medido a 375px: 192px no treino e 129px na água — cinco dias de água
   (91px) desenhavam quase igual a três dias de treino (83px), que é exatamente
   a comparação que unificar as duas listas existia para permitir. Agora a
   coluna de valor reserva a mesma largura nos dois: trilhos de 129/184/234/234
   px nas quatro larguras, e a mesma semana com 1 dia desenha 18px nos dois
   cartões;
3. **os vãos entre cartões saíam 16, 32, 32, 16.** A tela partia cinco cartões
   em três containers de um `.split` que é coluna única em toda largura — não
   produzia coluna nenhuma, produzia espaçamento desigual, e o agrupamento saía
   invertido: Peso, Treino e Água, que são a mesma gramática, mais afastados
   entre si do que da fronteira com os blocos que não são deles. Um container
   só, e os cinco ficam com 32px;
4. **a mesma tela mudava de ritmo entre os estados.** Solto no `.container`, o
   estado vazio espaçava por `.card + .card` (16px); o cheio, dentro do
   `split__main`, por `gap` mais margem (32px). Estado vazio não é outra tela.

E um acerto de texto: o `<title>` dizia "Histórico" numa tela cuja aba e cujo
`<h1>` dizem "Métricas". A rota continua `/historico/` — rótulo se troca,
endereço publicado não.

Não mexido, por decisão: os cálculos e o motor; a régua da meta por dia
(snapshot da época), a contagem de dias de treino, a guarda do peso corporal e
as semanas zeradas — as quatro continuam como estavam, e os testes que já as
protegiam passaram junto.

Falso positivo descartado: suspeitei que salvar o peso em Métricas custasse a
posição, como acontecia em Hoje antes do B2. Medido: não custa. A pessoa volta
ao topo, onde está a mensagem "Peso registrado.", e o cartão de Peso já começa
em y=507 com a primeira semana em y=606 — dentro da dobra, com a média nova
(81,3 → 81,1 kg) visível sem rolar.

**Observação registrada e NÃO corrigida:** `.stack > * + *` aplica margem em
containers que já distribuem por `gap` do flex, e as duas somam. Vale em 11 dos
12 usos de `.stack` no app — Hoje, Treino, Perfil e Lista de compras inclusive —
e o efeito é um vão de 32px onde o token diz 16. Não é defeito visível dentro de
uma tela (lá tudo fica uniforme em 32); só aparece quando um `.split` tem mais
de um filho com cartões, que era o caso de Métricas e foi corrigido movendo os
cartões, sem tocar no mecanismo. Unificar de verdade mudaria o ritmo vertical
de cinco telas de uma vez, o que é decisão de design e não polimento de uma.

**B5 — /GESTAO/ ✅** Auditado em navegador real em 375, 430, 768 e desktop, nas
três telas e nas duas sessões que o contrato distingue: com a permissão e sem
ela. Réguas limpas nos doze cruzamentos — zero rolagem horizontal DA PÁGINA,
zero alvo abaixo de 44×44, zero texto abaixo de 11px. Contraste medido em 40
elementos: pior caso 6,42.

Cinco achados. Três deles têm a mesma forma — um nome errado num template do
Django não levanta erro, vira string vazia, e a tela mente sem quebrar:

1. **a coluna "Onboarding" dizia "não" para todo mundo.** O template pedia
   `pessoa.profile.onboarding_completo`; a propriedade chama-se
   `onboarding_complete`. Medido: um valor distinto nas 41 linhas, enquanto o
   Painel dizia "Terminaram o onboarding — 36" sobre os mesmos dados. Depois:
   36 "sim" e 5 "não", e as duas telas concordam;
2. **"Com acesso administrativo" estava dentro de uma soma que não é a dele.**
   As quatro classificações somam o total (35+3+1+2=41); a linha de staff, no
   meio delas e acima do "Total", fazia a coluna dar 44. Saiu da soma, ganhou
   separação e a palavra "Destas";
3. **as notas eram maiores que os números que explicam.** `class="nota"` não
   tem uma única regra no CSS: renderizava a 16px em cor cheia, contra 14,4px
   cinza dos rótulos. A classe de rodapé do app é `.hint` (12,8px), e existe;
4. **dia sem ninguém sumia da tela de Atividade.** A tabela só listava os dias
   que o banco devolvia. É o oposto do que Métricas já decidira para as semanas
   ("buraco na série é informação"), e num painel operacional o dia morto é o
   que se quer ver. Junto veio um ajuste de um dia: a janela pegava 31 dias com
   a frase dizendo 30 — medido, 31 linhas antes e 30 depois. E o estado vazio
   precisou de `tem_atividade`, senão viraria código morto e a tela
   responderia com trinta linhas de zero.

Contrato de acesso preservado e medido nos dois sentidos: anônimo → login com
`next`; staff SEM a permissão → **403** nas três rotas; permissão SEM staff →
200. `Cache-Control: no-cache, no-store, must-revalidate, private` com
`Vary: Cookie` nas três. A porta para `/gestao/` continua invisível no perfil
de quem não pode entrar. Nada de pagamento, assinatura, cupom ou exportação
entrou, nenhuma capability foi ampliada, e o painel continua sem editar
usuário.

5. **a 1280px o operador via três das sete colunas.** O container ficava em
   `--max` (480px) e a tabela de Pessoas, que precisa de 788, rolava dentro de
   uma janela de 440 — na máquina em que um painel de fato é lido. As telas de
   TABELA passaram a pedir `container.gestao-tabela`, com `max-width: 60rem`,
   pelo gancho `{% templatetag openblock %} block container_class {% templatetag closeblock %}` que o `base.html` já
   oferecia às telas de `auth`. Medido depois, por largura (janela da tabela →
   colunas visíveis de 7): 375 → 334px/1 coluna, **igual a antes**; 430 →
   389px/2, **igual a antes**; 768 → 711px/**6** (era 438px/3); 1280 →
   918px/**7**, sem rolagem interna nenhuma (era 440px/3). Nenhuma media query:
   um `max-width` maior que a tela não faz nada, e é essa a garantia estrutural
   de que o celular não mudou. O Painel fica em `--max` de propósito: os
   cartões dele são pares rótulo/número em `space-between`, e a 920px o número
   ficaria a 900px do rótulo.

Janela de Atividade provada no navegador, exatamente como o contrato exige:
**30 datas**, a primeira é hoje, a última é hoje−29, todas consecutivas — nem
29 nem 31 — e a frase da tela diz 30.

**Observação registrada e NÃO corrigida:** a ordem dos cartões do Painel deixa o
pulso ("registraram algo nos últimos 7 dias") por último, a 1253px — a ordem
atual tem lógica narrativa (quem existe, quem chegou, quem avançou, quem está
ativo) e não há dano medido além da rolagem.

**B6 — NAVEGAÇÃO ✅** Auditado em navegador real em 375, 430, 768 e desktop,
com o mapa de portas de onze telas. Réguas limpas — zero rolagem horizontal,
alvos ≥44×44, todas as abas alcançáveis por hit-test. A aba ativa está correta
em todas: Hoje→Dieta, Treino/agora/corridas→Treino, histórico→Progresso,
perfil/conquistas→Perfil, lista de compras→Dieta.

Uma divergência de contrato e dois defeitos:

0. **o rótulo da terceira aba contrariava o contrato.** O documento escreve
   `Progresso` duas vezes — na barra de hoje e na barra futura, depois da
   medição do GPS — e não escreve `Métricas` uma única vez. A barra nasceu com
   "Métricas" no primeiro commit (`git log -S`) e nunca houve decisão
   registrada; `Progresso` não aparecia em nenhum template. O
   `[manter a estrutura real atualmente publicada]` do contrato fala de
   ESTRUTURA — quatro abas, esta ordem, Corrida sob Treino —, não de
   nomenclatura, e eu tinha estendido o colchete para cobrir o rótulo. Quatro
   strings trocadas: as duas navegações, o `<h1>` e o `<title>`. A rota
   continua `/historico/`;
1. **o passo "Dias de treino" era beco de mão única.** De `/treino/`, o link
   leva ao passo 3 do cadastro, que não tem barra de abas — e isso é decisão
   certa, porque os destinos da barra devolveriam quem está no meio do wizard.
   O problema era a saída: "Voltar" apontava para o passo 2 (a tela de meta) e
   "Salvar" ia para o Perfil. Nenhum dos dois voltava para o treino, cuja ficha
   acabara de ser remontada com os dias alterados; só o botão do NAVEGADOR
   voltava. Corrigido com lista fechada de origens, o mesmo padrão de
   `LogWeightView` — origem vem do endereço, e endereço é do cliente;
2. **a aba da vez não era anunciada.** `aria-current` voltava `null` nas quatro
   abas, em todas as telas, nas DUAS navegações. A barra do painel de gestão já
   usava o atributo; a que todo mundo usa, não.

Falso positivo descartado: o convite de instalação cobrindo a navegação. Forcei
o banner visível a 375 e medi — banner em 588–730, tabbar em 744–812, 14px de
folga, z-index 28 contra 30, `pointer-events: none` no cartão, e as quatro abas
seguem alcançáveis.

Corrida continua alcançável pelo Treino, não virou aba, e a aba ativa em
`/treino/corridas/` é Treino nas quatro larguras. `TodaTelaTemPortaTests`
preservado.

**B7 — PWA / SERVICE WORKER ✅** O contrato manda preservar `/admin/` e
`/gestao/` fora do cache, auditar se existe OUTRA rota autenticada com PII
entrando em `CACHE_PAGINAS` e, se existir, corrigir "com regra estrutural, não
lista frágil de páginas uma por uma".

O buraco estava na FORMA, não numa rota: nada no worker consultava a resposta
antes de guardá-la. A única proteção era `ehTelaOperacional`, uma lista de dois
prefixos que quem escrever a próxima view precisa lembrar. Agora `podeGuardar`
obedece o `Cache-Control: no-store` que o servidor já emite — toda view marcada
com `never_cache` fica protegida sem editar o `sw.js`, que é a diferença entre
regra e lista. A lista continua, porque faz mais do que impedir cache: ela faz
o pedido não passar pelo worker.

A superfície que a auditoria encontrou: **a tela de entrar**. O `LoginView` do
Django vem com `never_cache`, então ela responde `no-store` desde sempre — e o
worker vinha guardando, porque a lista não a incluía. Medido rota a rota e não
generalizado: `/conta/cadastro/` e `/conta/senha/` não declaram nada.

`private` NÃO entra na condição, e é decisão: ele proíbe cache COMPARTILHADO, e
o cache do worker é do perfil daquele navegador — é ele que faz a dieta abrir
no metrô.

**Falso positivo descartado:** a exportação de dados manda `no-store` e carrega
dado de saúde, mas é `http_method_names = ["post"]` e o worker ignora tudo que
não é GET. Nunca chegou perto do cache.

**Defeito meu, pego pelo navegador e não pelos testes:** a primeira versão da
regra usava expressão regular com limite de palavra, e o escape virou
CARACTERE DE CONTROLE no arquivo — a expressão passou a procurar
`0x08 no-store 0x08` e nunca casou. Os testes que liam o TEXTO do worker
continuaram verdes, porque a string estava lá. Quem pegou foi executar a função
do `sw.js` servido contra respostas HTTP reais no navegador. A regra passou a
comparar TOKEN separado por vírgula, sem escape nenhum, e entrou um teste que
proíbe caractere de controle no arquivo inteiro — com sabotagem que o
reintroduz.

**B8 — VISUAL QA REAL ✅** Varredura de navegador em 375, 430, 768 e desktop,
nas quatro larguras para cada tela: 24 telas do app mais as 4 de erro. Réguas
limpas — zero rolagem horizontal da página, zero texto abaixo de 11px, zero
falha de contraste, e nenhum alvo abaixo de 44px fora do caso corrigido abaixo.

O achado principal não estava em nenhuma das telas que a varredura veio medir:
**o app não tinha página de erro nenhuma**. Medido em produção antes da
correção, `GET /rota-que-nao-existe/` devolvia 179 bytes da página embutida do
Django — em inglês, sem marca, sem estilo e sem um link. Num app cuja regra é
`TodaTelaTemPortaTests`, a única tela sem saída era a de quem chegou no lugar
errado. As três são alcançáveis: 404 por link velho ou rota renomeada, 403 por
quem é da equipe sem `ver_painel_de_gestao` (cenário que o B5 já testa), e 500
quando o resto falhou.

A porta fica DENTRO do cartão, e isso é o desenho: um 404 é alcançável
deslogado, e nesse estado o `base.html` não desenha barra de abas — medido,
`<body class="">` sem `tem-tabbar`. Herdar a porta da navegação deixaria sem
saída exatamente quem mais precisa dela.

O 500 é autocontido porque tem regra diferente: `server_error` faz
`template.render()` sem request e sem context processors — "Context: None" na
docstring do Django. Herdar do `base.html` renderizaria `app_css_url` vazio, e
variável desconhecida vira string vazia sem erro nenhum: sairia uma tela sem
estilo, e o defeito só apareceria no dia em que o servidor já estivesse
quebrado. Há teste estrutural proibindo a herança.

Um alvo corrigido: `.legal__volta a`, o link de volta da privacidade e dos
termos, media 102x22 e 157x22. Ele não é link no meio de frase — é o parágrafo
inteiro, e serve de navegação —, então a exceção de alvo inline da WCAG (2.5.5
e 2.5.8) não o cobre. Agora mede 44x131 e 44x186, e entrou em
`TouchTargetTests`. Os links de "Perfil" e "Excluir minha conta" no meio das
definições continuam com 22px de propósito: esses SÃO texto corrido.

Dois falsos positivos, e os dois eram cegueira da régua, não defeito do app:
26 caixas de 22x22 na lista de compras que moram num `<label>` de 242x44 (o
alvo efetivo), e contraste 1,15 nas pastilhas marcadas do cadastro — o fundo é
pintado por um IRMÃO absoluto com `pointer-events: none`, invisível tanto para
a subida na árvore quanto para `elementsFromPoint`. Medida a camada real: 6,58
e 6,35, ambos passando AA. A régua passou a resolver os dois casos.

`/agua/`, `/conta/peso/` e companhia devolvem 405 com corpo vazio: são
endpoints de POST, não telas, e não entram na conta de "tela sem porta".

Registrado e NÃO feito aqui, porque é fora do escopo do B8: falta
`403_csrf.html`. Uma página cacheada pelo worker com token vencido cai na
página embutida do Django na hora de enviar o formulário. Pertence ao B10.

**B9 — DISCIPLINA DE TESTES ✅** Os quatro guardrails do contrato —
`RotasExtrasDoAdminTests`, `TodaTelaTemPortaTests`,
`ComentarioDeTemplateNaoVazaTests` e `MatrizDeCapabilityTests` — foram lidos um
a um e estão íntegros. O B8 só ACRESCENTOU referências de `{% url %}`: o
`TodaTelaTemPortaTests` ficou mais forte.

Mas "preservar" precisava de mecanismo, porque apagar um guardrail não deixa
nada vermelho — o guardrail ERA o vermelho. Os quatro passaram a ser nomeados
num teste que falha se a classe sumir ou virar casca sem método dentro.

A regra do runner único era só escrita, e falhou DUAS vezes nesta sessão: uma
suíte dirigida disparada durante a completa, e uma conexão órfã derrubando o
hook de push com uma mensagem sobre banco quando o problema era de processo.
`config/runner.py` agora verifica `pg_stat_activity` antes de criar o banco — a
ordem é o teste, porque perguntar depois de criar já é tarde. Verifica e não
mata: derrubar a conexão de uma suíte legítima trocaria um erro claro por um
resultado errado.

A prova não dá para encenar: com o push do B8 rodando a suíte completa de
verdade, uma suíte dirigida foi recusada com o pid na tela e saída 1.

A escotilha `NUTRIPLAN_IGNORAR_RUNNER_UNICO` existe porque guardrail sem saída,
num projeto de uma pessoa, é um jeito de ficar sem poder publicar. O preço dela
está escrito ao lado, e há teste exigindo que continue escrito.

Sabotagem: 8 execuções, 8 cenários, 8 detectados. Três apareceram como "NÃO
APLICADA" na primeira rodada porque `config/runner.py` está em CRLF e o roteiro
lê em bytes — a verificação de âncora em modo texto normaliza sozinha e me
disse que estava tudo bem. O roteiro passou a normalizar para casar e a
restaurar pelos bytes originais.

**B10 — SEGURANÇA ✅** As nove capacidades do contrato foram auditadas uma a
uma, com o teste que fecha cada uma nomeado: `change_profile` em
`PedirNovaEscolhaDeDivisaoTests`; `add_user` na matriz, 403 nos dois papéis;
senha de terceiros em `SenhaNaoAtravessaOAdminTests`, cinco testes incluindo o
POST na rota `<pk>/password/`; `SocialToken`, `SocialApp`, `SocialAccount`,
`EmailAddress` e `WeightEntry` avulso na matriz, 404; permissões amplas em
`EscaladaDePrivilegioNoUserAdminTests`, sete testes. Nada foi reaberto por
B1–B9 — nenhum daqueles blocos tocou permissão, papel ou registro de Admin.

Reverificado em 04/09/2026 por um ângulo diferente: em vez de conferir que
a trava existe, cada uma das nove foi REABERTA na origem — tirando o model
de `SEM_TELA`, registrando `WeightEntry` como `ModelAdmin`, trocando
`EDICAO` por `ESCRITA`, devolvendo a rota de senha ao Django, pondo
`delete` em `LEITURA`. Nove cenários, nove detectados; nada mudou no
código, e a conclusão do bloco continua a mesma.

O que essa rodada acrescentou é uma nuance: `WeightEntry` fica em 404
porque só existe como *inline*, nunca registrado avulso. A proteção é a
AUSÊNCIA de registro, e não uma negação explícita — mais frágil que as
outras oito, e a única das nove que um `@admin.register` distraído
reabriria sem tocar em permissão nenhuma.

O buraco não estava numa capacidade, e sim na FORMA da trava. Cinco das nove
são protegidas por uma tabela só, a `ALCANCE`, onde a proteção e o valor
esperado moram no mesmo lugar: quem reabrir `SocialToken` no código e trocar o
404 por 200 na linha correspondente tem a suíte verde de novo.

Medido, e o primeiro resultado desmentiu a suposição: reabrindo SÓ o Admin, a
própria matriz pega — a tela responde 403 onde a tabela diz 404. O que ela não
pega é a reabertura COM o ajuste na linha dela. Medido: matriz verde, trava do
B10 vermelha. É a sabotagem S138, e é o único cenário que justifica o bloco.

Os nove nomes passaram a vir do CONTRATO, num arquivo separado, com as
respostas exigidas asseridas de novo. Reabrir uma delas exige agora mexer em
dois arquivos que discordam entre si. E há teste exigindo que os nove nomes
continuem escritos no contrato: apagar uma linha de lá deixaria o teste verde
por ter menos o que provar.

A regra "mudança visual não pode ressuscitar capability" foi aplicada à
superfície mais nova: a tela de 403 do B8 aparece também dentro do `/admin/`, e
uma tela de erro que diz qual permissão falta entrega o nome interno de graça.
Há teste proibindo `ver_painel_de_gestao` no corpo, e teste exigindo que a
saída leve para o dia de hoje — um botão de volta para `/gestao/` seria um
laço, e um para `/admin/` seria a tela de erro sugerindo o caminho.

Sabotagem: 8 execuções, 8 cenários, 8 detectados.

NÃO PROVADO EM PRODUÇÃO: o 403 de equipe-sem-permissão exige sessão
autenticada, e não abro sessão em conta real. O que está provado lá é o
anônimo — `/gestao/` responde 302 com `no-store` e `Vary: Cookie`.

REGISTRADO E NÃO FEITO: `/saude/` não informa qual commit está no ar. Expor
`RENDER_GIT_COMMIT` ali provaria "o commit testado é o commit publicado" em um
pedido, mas o endpoint é público, e acrescentar identificação de versão logo
depois de um bloco que fechou vazamentos merece decisão explícita, não carona.
A alternativa sem custo é a que está em uso: cada bloco prova a identidade do
commit por um artefato observável próprio — o `podeGuardar` no `sw.js` do B7, a
tela de 404 do B8. Blocos que não criam superfície de produção (B9, B10) não
têm esse artefato, e isso fica dito em vez de contornado.

Falta também `403_csrf.html`, herdado do B8: uma página cacheada pelo worker
com token vencido cai na página embutida do Django ao enviar o formulário.

**B11 — TESTES / PUBLICAÇÃO ✅** Dez blocos, onze commits, todos publicados em
`origin/main` com a suíte completa verde no hook antes de cada push. O B3 é o
único com dois commits, e por um motivo: o segundo registra a prova de produção
no BACKLOG, que só existiu depois do deploy do primeiro. Nenhum commit
cosmético, nenhum lote publicado sem gate.

O achado do bloco é que o `/demo/` é uma superfície de PROVA. Durante os blocos
anteriores várias verificações ficaram como "não provável sem sessão" — barra
de navegação, título da tela de progresso, porta para corridas —, porque todas
moram atrás de login e não se abre sessão em conta real. O demo responde 200
para anônimo e renderiza as mesmas telas com o mesmo `base.html`: não vale para
nada que dependa de escrita, mas para estrutura, rótulo e porta é prova de
produção obtida sem tocar em conta nenhuma.

Destravado e medido em produção: B1 (o primeiro campo da tela de entrar tem
`autofocus` E é o `activeElement` — o atributo sozinho não prova o foco); B3
("Abrir corridas" leva a `/demo/treino/corridas/` com a aba Treino ativa); B4
(`<h1>` "Progresso" igual ao `<title>`, um único `main.container`, `--largo`
extinto do HTML servido); B6 (quatro abas nas duas navegações, uma só com
`aria-current`, zero "Métricas").

Do B2 dá para provar em produção a metade que o próprio commit dele diz ser a
que costuma faltar: as âncoras EXISTIREM. Medido: `id="hidratacao"` presente e
cinco `id="slot-N"`, um por refeição. O POST devolvendo para a âncora exige
sessão e fica como prova local.

Smoke final: 24 rotas públicas, zero 5xx.

NENHUM TESTE NOVO. `demo/tests.py` já exige que o demo abra sem sessão, que
toda área responda, que a navegação nunca aponte para fora dele e que nenhum
POST altere nada; `config/test_b6_navegacao.py` já trava os rótulos no
`base.html`, que é o mesmo que o demo usa. Um teste a mais aqui seria trabalho
sem função.

NÃO PROVADO EM PRODUÇÃO: B9 e B10 não criam superfície de produção — um é o
runner de teste, o outro é uma trava de teste. Sobem no deploy e ficam inertes.
O que se verifica deles lá é que o build passou (`scripts/build.sh` roda com
`errexit`, então deploy verde prova migração e seeds) e que o app seguiu
saudável. Chamar isso de "validado em produção" seria esticar a palavra.

### Registrado e NÃO feito, com o custo ao lado

- **`403_csrf.html`.** Herdado do B8. Uma página cacheada pelo worker com token
  vencido cai na página embutida do Django ao enviar o formulário. É a mesma
  família das três telas de erro criadas, e ficou de fora porque não estava no
  escopo do B8 e porque o cenário depende do worker — merece ser reproduzido
  antes de ser corrigido.
- **Identificação de versão em `/saude/`.** Expor `RENDER_GIT_COMMIT` provaria
  "o commit testado é o commit publicado" num pedido só. O endpoint é público, e
  acrescentar isso logo depois do bloco que fechou vazamentos merece decisão
  explícita, não carona. A alternativa em uso é cada bloco provar a identidade
  do commit por um artefato observável próprio.

### Escopo B1–B11 recuperado

O escopo original está em [`docs/premium-polish-b1-b11.md`](docs/premium-polish-b1-b11.md),
recuperado do transcript da sessão (linha 29190, mensagem do usuário de
02/09/2026) e copiado literalmente — não reconstruído de memória. A emenda
posterior a B7, de doze minutos depois, está registrada no mesmo arquivo.

Cuidado ao ler: a missão de 01/09 "NUTRIPLAN PREMIUM UI/UX POLISH V1" é OUTRA,
anterior, e não usa rótulos B. Não misturar as duas.

Estado técnico para retomar, quando o escopo voltar:

- base: `aac20b8` em `main`, publicado e verificado em produção;
- suíte: 1649 testes verdes, ~17 min; o `pre-push` roda a suíte inteira;
- identidade visual atual é para MANTER — sem redesenho de produto;
- réguas travadas em teste que o polimento não pode violar: alvo de toque
  44×44, texto de interface >= 11px, zero rolagem horizontal, contraste WCAG
  recalculado a partir dos tokens, catálogo anti-padrão em
  `ImpeccableStyleTests`;
- auditoria de navegador desta rodada não achou violação dessas réguas em
  375/390/430/768/1265 nas telas medidas — o polimento parte de uma base limpa;
- `:has()` continua proibido para estrutura, e não há build step de CSS.

### ALIMENTO FORA DO CATÁLOGO GRAVA ZERO SEM AVISAR

Em "Comi outra coisa", o nome do alimento é texto livre com um `<datalist>` de
62 sugestões. Quem digita um nome que não bate com o catálogo tem a linha
descartada **em silêncio** — a refeição fica registrada pela descrição, com
0 kcal.

O descarte silencioso é decisão declarada em `_itens_descritos`: recusar a
refeição inteira por causa de uma linha mal digitada é o caminho mais curto
para a pessoa parar de registrar. O `<datalist>` reduz o risco, mas não força
escolha.

O que falta é FEEDBACK, não validação: a tela poderia dizer "2 de 3 itens
entraram na conta" depois de salvar. Medido no navegador: "Arroz 150 g" +
"Frango 120 g" → `kcal=0.00`, sem nenhuma indicação.

Não mexi porque a mudança é de produto (o que dizer, e onde), não de correção.

### `navigator.onLine` NÃO COBRE SERVIDOR FORA DO AR

A fila offline só intercepta o POST quando `navigator.onLine` é falso. Com rede
viva e servidor inacessível — testado derrubando o servidor local — o POST sai,
falha, e a marcação se perde; a pessoa cai na tela "Sem conexão" sem que nada
tenha sido enfileirado.

O gatilho por `navigator.onLine` é o que está documentado e funciona para o caso
principal (celular sem sinal). Cobrir servidor fora do ar exigiria enfileirar no
ERRO do `fetch`, e isso muda o contrato da fila — decisão de produto.

## Achados da varredura geral (04/09/2026) — PUBLICADOS

Fechados e no ar em `f301dc6` e `57a9f6a`. Ficam registrados porque a origem de
cada um ensina mais que a correção — e as três primeiras têm a MESMA origem:
nenhuma fumaça olhava para o caminho, porque ninguém NAVEGA até ele.

- **ALTO privacidade — o dia guardado sobrevivia à sessão.** `CACHE_PAGINAS`
  guardava cópia de cada tela e nada a apagava. Medido no navegador: a cópia de
  `/hoje/` tinha 55.831 bytes, com `data-usuario`, `data-autenticado="1"` e as
  cinco refeições. O `sw.js` já nomeava esta ameaça para `/admin/` e `/gestao/`
  e nunca a aplicou às telas da própria pessoa. O gatilho é a TELA DE ENTRAR e
  não o botão de sair: sessão que EXPIRA não passa por logout nenhum.
- **ALTO — endpoint de ação devolvia 405 com zero byte.** Sessão expira, a
  pessoa toca em "+250 ml", `login_required` manda para
  `/conta/entrar/?next=/agua/`, ela acerta a senha, e o Django devolve o `next`
  com um GET. Página completamente em branco depois de um login bem-sucedido.
  `TodaTelaTemPortaTests` não pegava: ele cuida de destinos que alguém alcança
  de propósito, e este caminho quem monta é o Django.
- **ALTO — desistir do consentimento do Google terminava em 500.** O allauth
  traduz `access_denied` em `AuthError.CANCELLED` e redireciona para
  `socialaccount_login_cancelled`, cuja view reverte `account_login` — nome que
  mora em `allauth.account.urls`, deixado de fora de propósito. Não eram três
  rotas: 25 lugares da biblioteca revertem esse nome, com o `AccountMiddleware`
  instalado entre eles. Em produção, `signup/`, `login/cancelled/` e
  `login/error/` respondiam 500.
- **A interface que ainda era da biblioteca.** Três telas do allauth chegavam a
  uma pessoa de verdade. `/conta/social/` respondia 200 com 2.517 bytes para
  quem está logado — sem `app.css`, sem navegação, sem marca. Ela NÃO foi
  escondida: ver e desvincular o Google só existe ali. Só o template mudou; a
  view continua sendo a do allauth, com o `DisconnectForm` e a trava de
  `validate_disconnect`.

### O que estes achados ensinaram sobre os testes
Seis sabotagens passaram verdes na primeira rodada e viraram conserto de teste.
Duas merecem ficar escritas:

- `assertIn('href="/conta/entrar/"', html)` casava com o "Entrar" do cabeçalho,
  e não com o botão do cartão. É a armadilha que o `CLAUDE.md` descreve, na
  terceira aparição — agora ancorada no texto do próprio botão.
- `self.client.post(url, {"account": pk})` provava que a VIEW funciona, e ela
  era do allauth e já funcionava. Com o nome do campo trocado no template ou o
  `csrf_token` removido, o teste seguia verde e a tela ficava bonita e
  quebrada. **Teste de formulário precisa enviar o formulário RENDERIZADO**,
  com `enforce_csrf_checks=True` — o cliente padrão do Django não confere o
  token.

### ⏳ QA visual real das telas novas
`authentication_error.html` e `connections.html` foram provados por HTTP e por
teste. A de erro também foi vista no navegador a 375px (botão 297×47px, sem
rolagem horizontal). A de contas conectadas **não** foi vista no navegador com
usuário autenticado: não há conta de teste em produção, e usar a conta real
para isso seria fabricar evidência.

## QA visual real (04/09/2026) — B8

Matriz completa: 16 telas × 375, 430, 768 e desktop, medidas no navegador com
conta de QA local (VAZIO, CHEIO e staff), mais login, cadastro, erro social e
demo em produção. **Nenhum defeito visual real.** Rolagem horizontal zero,
nenhum alvo abaixo de 44px, nenhum texto abaixo de 11px, nenhum controle
encoberto, nada preso atrás da barra fixa.

Provado também: foco visível com anel de 6,06:1 sobre o fundo composto
(alphas somados árvore acima, e não lidos do pai direto); `inputmode="decimal"`
na carga e `numeric` nas reps; drawer 375x747 dentro da tela com fechar 44x44 e
foco indo para ele; overlay de montagem do plano com `role="status"`. O modal
prende o foco de verdade — dos 180 controles fora dele, zero recebem foco
enquanto está aberto —, e não há `tabindex` positivo nem controle tirado da
ordem natural em nenhuma tela.

### O que a régua errou, e por quê
Três achados foram **falsos positivos da medição**, não do produto. Ficam
escritos porque a próxima varredura visual vai encontrar os mesmos três:

1. **Rádio de 19x19 dentro de `.choice-list`.** Quem recebe o dedo é o RÓTULO,
   de 294x50 — provado clicando a 8px da borda direita, longe do rádio. Medir o
   `<input>` cru acusa um alvo que ninguém precisa acertar.
2. **Tabela de `/gestao/` "estourando" a 375px.** Ela mora em
   `div.tabela-rolavel` com `overflow-x: auto` — 334 visíveis de 756 roláveis —
   e a PÁGINA não rola. É o padrão documentado para conteúdo largo.
3. **Botões "Comi esta" cobertos.** Estão dentro de `<details>` FECHADO, que o
   navegador torna inerte: `focus()` não move o foco e `elementFromPoint`
   devolve o `<summary>`. Cobrir conteúdo fechado é o que "fechado" significa.

4. **Contraste de 3,21:1 no botão de desvincular.** O `btn--perigo` tem fundo
   `color(srgb 0.70 0.15 0.12 / 0.12)`, e os componentes de `color(srgb ...)`
   vêm em 0–1, não em 0–255. Lidos como 0–255 o número sai inventado. Com o
   parser certo, e compondo o alpha sobre o cartão, a razão é **5,37:1** —
   passa. Todo cálculo de contraste passou a ter controle positivo: preto sobre
   branco tem de dar 21.

Uma quinta armadilha, de ambiente: a primeira medição de produção mediu a
página **"Render - Application loading"** durante um cold start. Toda medição
remota passou a conferir o `<title>` antes de valer.

### Espaçamento entre alvos — OBSERVAÇÃO, não defeito
Os três botões de água ficam a 6,4px um do outro, e as abas a 3,2px. Medidos,
cada botão de água tem **82x54** e cada aba passa dos 44. O espaçamento do
WCAG 2.5.8 só é exigido quando o alvo tem MENOS de 24px, então proximidade
entre alvos grandes não é violação — e um toque errado na água é desfeito pelo
"zerar", que mede 44x44.

### A rede que faltava
`TouchTargetTests` trava as REGRAS de CSS, não o uso delas. Sabotando antes de
escrever qualquer coisa: trocar `class="btn btn--perigo btn--block"` por uma
classe sem altura no botão de desvincular deixou os 13 testes das telas novas
**verdes**. `config/test_alvos_das_telas_do_b7.py` fecha isso para as duas
telas que o B7 criou.

### ⏳ Ainda NÃO PROVADO em produção
`/conta/social/` renderizada com usuário autenticado. Não há conta de teste em
produção, e usar a conta real seria fabricar evidência. Provada local/QA, nos
quatro viewports, nos estados vazio e cheio.

## Disciplina de testes (04/09/2026) — B9

O contrato do B9 pede duas coisas: preservar quatro guardrails sistêmicos e
preservar a regra de nunca rodar suíte dirigida enquanto a completa usa o mesmo
`test_nutriplan`. As duas já tinham mecanismo — `config/test_b9_disciplina.py` e
`config/runner.py`. A auditoria desta rodada perguntou se o mecanismo PROTEGE,
e achou um buraco.

### O guardrail podia virar no-op sem ninguém notar
`OsQuatroGuardrailsContinuamDePeTests` cobrava que a classe existisse e tivesse
um método `test_*`. Isso pega quem APAGA um guardrail — e ninguém apaga uma
classe para fazer a suíte passar. O atalho de sempre é esvaziar a asserção.

Medido: com `return` no topo de
`test_nenhum_comentario_de_cerquilha_atravessa_linhas`, o guardrail passou a
proteger **nada** e a suíte respondeu `Ran 15 tests ... OK`.

Inspeção de código-fonte não resolveria, e é por isso que a correção não é
essa: o `return` fica ANTES da asserção, então o texto `assertEqual` continua no
arquivo e qualquer busca por "assert" passaria verde. **Só executar resolve.**

`CadaGuardrailFicaVermelhoQuandoOMundoQuebraTests` roda cada um dos quatro pela
máquina do `unittest` contra um mundo quebrado de propósito — pasta de
templates com `{#` de três linhas, pasta sem template nenhum, tabela de decisões
do Admin esvaziada, `ALCANCE` declarando 404 onde o HTTP responde 200 — e exige
vermelho. Cada mutação vem com o controle sem mutação: sem ele, um guardrail
quebrado por acidente ficaria vermelho sempre e a asserção passaria pelo motivo
errado.

A checagem antiga ficou: ela pega o caso que a nova não pega, porque a nova
precisa que a classe exista para poder rodá-la. As duas têm trabalho próprio, e
a sabotagem S216 é a prova disso.

Sabotagem: 6 cenários, 6 detectados — os quatro guardrails esvaziados por
dentro, mais os dois contra-controles.
