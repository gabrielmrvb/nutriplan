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

### PREMIUM POLISH — B1 A B10 FEITOS; B11 É O PRÓXIMO

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

**B11 — TESTES / PUBLICAÇÃO ⏳ PRÓXIMO**

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
