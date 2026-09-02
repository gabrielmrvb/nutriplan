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
