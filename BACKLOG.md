# Backlog do NutriPlan

O que ficou decidido mas não feito, e o que depende de gente. Cada item diz
**por que** está aqui — item sem motivo vira lista que ninguém lê.

## Bloqueado por decisão ou ação humana

### ⛔ Backup independente de produção
O plano gratuito do Neon dá **um** slot de snapshot manual, sem agendamento, e
PITR de 6 horas. Não existe mecanismo seguro para eu extrair uma cópia sem
manipular a `DATABASE_URL`, o que está fora do que posso fazer. Enquanto isso,
o snapshot pós-0017 precisa ser preservado.

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
Vale para Render e Neon. É a data que decide se o produto precisa de plano pago
ou de migração antes disso.

## Segurança futura

### 2FA no Admin
Hoje a entrada administrativa é Google-only, o que já é um segundo fator na
prática — mas por delegação, não por política nossa.

### Domínio próprio para o e-mail transacional
A recuperação de senha sai por remetente de terceiro. Domínio próprio muda
entregabilidade e reduz a chance de a mensagem virar spam.

## Medido e vale guardar

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

### PREMIUM POLISH — B1, B2 E B3 FEITOS; B4 É O PRÓXIMO

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

**B4 — PROGRESSO V2 ⏳ PRÓXIMO**

Escopo em [`docs/premium-polish-b1-b11.md`](docs/premium-polish-b1-b11.md).

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
