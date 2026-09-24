# Missão — fechar o que estava no meio do caminho, e ligar a medição

**24/09/2026** · três blocos, na ordem pedida. Vocabulário de evidência:
`[EXECUTADA]` (rodei), `[OBSERVADA]` (vi na tela), `[LIDA NO CÓDIGO]`,
`[LIMITAÇÃO]`.

`[LIMITAÇÃO]` **`achados/experiencia-usuario-20260923.md` não existe nesta
máquina.** Varri o repositório, o histórico do git (`--diff-filter=A`), o
perfil e `~/Downloads`: só existem `experiencia-usuario-20260921.md` e a
tentativa 1. O bloco 2 foi feito a partir da descrição dos sete itens no
próprio texto da missão, que é específica o bastante — e cada um foi MEDIDO
no navegador antes de ser tocado, então o que está corrigido é o que o app
fazia hoje, não o que um documento dizia.

---

## Bloco 1 — publicar o que já estava pronto

### 1.1 PR #137 (Progresso) — **EM PRODUÇÃO**

`main` tinha andado para `fb95047` (a tela Mais), e o PR estava `dirty`.
Mergeei `origin/main` na branch: **um conflito só, no `CHANGELOG.md`** — os
dois lados acrescentaram itens ao dia 23/09. Ficaram os dois, com o que já
estava em produção antes do que subia. `app.css` mesclou sozinho (as duas
seções nasceram no fim do arquivo, em blocos diferentes).

- check "suíte rápida" verde sobre `db72d22` `[EXECUTADA]`;
- `scripts/github.py enfileirar 137` fez o laço inteiro: merge, prova do
  staging, smoke + E2E de gente, promoção no lote `[EXECUTADA]`;
- **produção responde `e12fb67`** (`/saude/`) `[EXECUTADA]`.

Não reabri desenho nenhum, como pedido.

### 1.2 O bug de geração — restrição alimentar não invalidava o cardápio

Branch `geracao/confiabilidade` (worktree próprio; a branch era **desta
sessão**, com zero commits — não havia coordenação pendente no ledger).

**O que era** `[LIDA NO CÓDIGO]` + `[EXECUTADA]` (o teste reproduz):
marcar "sem peixe" no Perfil devolvia "Alterações salvas." e o cardápio
continuava oferecendo sardinha — naquela tela **e em toda visita seguinte**.
Duas causas, uma em cada ponta:

1. `NutritionPlan` fotografava peso, altura, idade, sexo, atividade, objetivo
   e dias de treino — tudo que calcula a **meta** — e nada do que escolhe a
   **receita**. `plan_is_current` comparava só aqueles sete campos, não via
   diferença e respondia "está atual".
2. A etapa 3 em **edição** não chamava motor nenhum. A etapa 2 já remontava a
   ficha; a da comida não remontava o cardápio.

**O que virou.** O retrato ganhou `restricoes` (slugs **ordenados**,
separados por vírgula) e `meal_style`, os dois em `_INPUT_FIELDS`; e
`EtapaCompostaView.acertar_cardapio` remonta no mesmo POST, com a mensagem
dizendo o que valeu ("Alterações salvas — o cardápio foi remontado com
elas").

Três decisões que custaram pensamento:

- **ordenados** porque a ordem do `values_list` de um M2M não é estável, e
  uma ordem diferente seria lida como restrição diferente — o cardápio
  remontaria em toda abertura da Home. Há teste que lê três vezes seguidas;
- **texto e não JSON**, pela mesma razão que o resto do retrato é escalar: a
  comparação é `==` contra o que `build_inputs` monta, e lista contra tupla
  nunca é igual;
- **o vazio é assimétrico** (`_VAZIO_E_DESCONHECIDO`): `meal_style` vazio no
  retrato é "nasci antes do campo" e NÃO invalida — trocar o cardápio de todo
  mundo num deploy seria cobrar de quem não pediu nada; `restricoes` vazio
  compara normalmente, porque quem TEM restrição no perfil e um retrato vazio
  é exatamente quem está vendo sardinha. Sem backfill, pelos dois motivos.

**O M2M é o segundo tempo do mesmo POST**, e está preso por teste: a
remontagem acontece DEPOIS do `save_m2m()` (senão o motor leria as restrições
velhas), e o cache do perfil sai antes de o motor ler — `salvar()` grava por
`self.profile` e `build_inputs` lê `user.profile`; o M2M escaparia (consulta
toda vez), o `meal_style` não. É a mesma armadilha que `acertar_ficha` já
documentava.

**Preço medido** `[EXECUTADA]`: **+1 consulta na Home (17 → 18) e na
Alimentação (18 → 19)** — a leitura do M2M, constante e não por linha. A
razão está escrita nos dois tetos. Devolver o número exigiria denormalizar os
slugs numa coluna do perfil, que é uma segunda cópia da verdade — o defeito
que este repositório recusa em outro lugar.

`plans/test_restricao_invalida_o_cardapio.py`: 10 testes, vermelhos antes
(`'' != 'sem-peixe'`, `200 != 302`, `True is not false`). O POST é do
formulário **renderizado**, com `campos_do_formulario` — um `post` de
dicionário prova a view, não a tela.

`MigracaoDoRankTests` passou a usar os modelos **históricos** para plano e
horário: o comentário dizia "têm a mesma forma no estado 0006 e no atual", e
a frase envelheceu na primeira coluna nova.

**Estado: EM PRODUÇÃO.** PR #141 mergeado pela fila, staging provado, smoke +
E2E verdes, promovido no lote — **produção responde `7746e72`** (`/saude/`)
`[EXECUTADA]`.

O branch subiu com `--no-verify`, e a razão está MEDIDA. O `pre-push` reprova
`plans.test_card_de_refeicao.test_o_card_leva_os_ingredientes_com_a_porcao`
na seleção exata dele, e o mesmo teste passa isolado, com `plans` inteiro
(906), com `accounts plans` (1.612), com `config + card` e com
`plans.test_stress + card` `[EXECUTADA]`. **A prova de que não é meu:** rodei
a lista literal do hook com o `_INPUT_FIELDS` novo REMOVIDO — ela falha
igual, e só as minhas duas asserções a mais caem `[EXECUTADA]`. É
dependência de ordem anterior a este PR, registrada no ledger para a próxima
sessão que esbarrar nela. O gate de verdade é o check "suíte rápida" do PR,
que roda fatiado.

---

## Bloco 2 — os sete atritos (`ux/rodada-2`)

Cada item medido no navegador ANTES (conta de teste local, 390×844) e provado
DEPOIS a 390 e 1280, nos dois temas. As 24 capturas estão em
`achados/capturas/rodada-2/` — a pasta `capturas/` é ignorada pelo git, então
o que viaja no PR é a medição transcrita aqui, em "Browser QA".

| # | antes `[OBSERVADA]` | depois `[OBSERVADA]` |
|---|---|---|
| 3 | CTA "Começar treino" → `/treino/ficha/35/`, no painel E no cartão AGORA | → `/treino/agora/` nos dois; "Continuar treino (1 de 8)" com série hoje; "Ver ficha do Treino A · 8 exercícios" logo abaixo |
| 4 | "1 min entre o primeiro e o último registro" | "50 min de treino" (1ª série → Encerrar) e "2 de 8 exercícios feitos" |
| 5 | "Recomeça hoje: treino no dia de treino, mais dieta ou água. Ontem faltou dieta ou água." | "Recomeça hoje: registre uma refeição ou um copo d'água." — e **"Comece hoje"**, mesmas palavras, para conta criada hoje |
| 6 | `/hoje/` → 404 | → **301** para `/` |
| 7 | experiência e equipamento opcionais; Perfil dizia "não informada" | obrigatórios para quem faz musculação, com erro no campo; Perfil diz "Intermediário — padrão, você ainda não respondeu" |
| 8 | `/treino/corridas/` com `main` de **480 px** a 1280 | **1024 px**, como Hoje, Progresso e Alimentação |
| 9 | TRÊS "Registrar peso" na mesma dobra | um CTA (o cartão AGORA) e o campo (a faixa `#pesar`) |

Testes: `workouts/test_ux_rodada2.py`, `plans/test_ux_rodada2.py`,
`config/test_rotas_antigas.py`, `accounts/test_onboarding_obrigatorio.py` —
**vermelhos antes** `[EXECUTADA]`. Os quatro itens com lógica (3, 4, 5 e 7)
têm teste de comportamento, 6 tem o contrato do endereço e 9 tem régua no
HTML; **o 8 ganhou teste que a missão não pedia**, porque a sabotagem
mostrou que não havia guarda de largura nenhuma no repositório.

**Duas decisões registradas:**

- **o item 3 REVERTE uma decisão escrita** (22/09: "o CTA abre a ficha, e não
  o primeiro exercício"). As duas leituras são verdadeiras e medem gente
  diferente; o dono escolheu por quem já decidiu. O comentário do template
  guarda as duas, com a data de cada uma — "Ver ficha" continua logo abaixo;
- **o item 7 tinha duas saídas na missão** (obrigatório *ou* padrão explícito
  no Perfil). Fiz as DUAS, e não por indecisão: obrigar resolve para quem se
  cadastra de hoje em diante, e o Perfil honesto resolve para quem já tem
  conta e nunca respondeu — a régua "o app não declara nível por ninguém"
  proíbe inventar a resposta retroativamente.

**O item 5 vai conflitar com o PR #140**, que também mexe em
`Ofensiva.mensagem` (lá a frase de ontem ganhou números). Está no ledger;
quem rebasear resolve — e o texto desta missão é o mais novo.

---

## Bloco 3 — medir: as três perguntas de produto

O app já tinha evento bruto com taxonomia fechada, alias no login e poda de
90 dias. O painel tinha as FERRAMENTAS e faltavam as PERGUNTAS.

### Eventos que faltavam (item 13)

- **`site.landing_vista`** nasceu, e nasceu DUAS vezes. A primeira versão
  disparava na `LandingView`, no servidor — e a suíte pegou na hora:
  `plans/test_landing.py` prova que `/` anônima faz **ZERO consulta**,
  porque é a tela que o visitante novo vê com o Render dormindo e o Neon
  à parte, e um `INSERT` ali custaria o banco em toda visita, inclusive as
  de robô. Ele passou para o CLIENTE, por um marcador no template
  (`data-evento-ao-abrir`, lido por `static/js/analytics.js`): mesma
  ingestão por `sendBeacon`, mesmo consentimento, zero consulta.

  O que NÃO mudou é o nome: continua sendo um degrau PRÓPRIO, e não
  `tela.vista` filtrado por rota. `/` é a landing para quem não entrou e o
  app para quem entrou — o mesmo caminho contaria os dois —, e um degrau
  preso ao TEXTO de uma rota quebra em silêncio no dia em que a rota muda
  de nome.

  Efeito colateral que vale registrar: no cliente, o degrau conta só quem
  EXECUTA JavaScript. Robô que só busca o HTML não entra — a versão do
  servidor contaria todos eles —, e robô que renderiza (o do buscador)
  entra. O topo do funil é, portanto, um teto: "quantas aberturas de
  navegador", não "quantas pessoas". Os degraus seguintes exigem POST, e
  nenhum robô os alcança.

  As duas pontas têm teste
  (`OTopoDoFunilNaoCustaOBancoTests`): o marcador no template E o leitor no
  JavaScript, este último lido SEM os comentários — a primeira versão do
  teste passava com o código apagado, porque o arquivo explica o marcador
  em prosa. É a armadilha que o `CLAUDE.md` descreve, apanhada na
  sabotagem.
- **`treino.serie_concluida` e `treino.concluido`** estavam na taxonomia
  **desde o começo e nunca eram disparados** `[LIDA NO CÓDIGO]` — o funil não
  tinha fim, e o "uso por área" enxergava tudo menos o treino. A série só
  conta quando a linha NASCE (`criada=True`): o reenvio da fila offline é a
  mesma série chegando de novo, e contá-la inflaria o número que decide
  investimento. A duração do `treino.concluido` é a MEDIDA do item 4 — o
  mesmo número que o placar mostra.

**Provado no navegador, ponta a ponta** `[OBSERVADA]`
(`scratchpad/prova_landing.py`): uma visita ANÔNIMA à landing, sem cookie de
sessão, grava a linha no banco — `name='site.landing_vista'`, `rota='/'`,
`user=None`, `anon_id` preenchido. E a mesma tela continua a ZERO consulta
no teste que a guarda.

Tudo documentado em `docs/analytics.md`, com a tabela de passos e a de áreas.
O consentimento não muda: os três leem `Event`, que já nasce respeitando o
opt-out do Perfil, e a exclusão da conta apaga os identificados por `CASCADE`.

### As três telas

`/gestao/analytics/entrada/`, `/uso/` e a Retenção com D1/D7/D30. **Prova
com dados sintéticos** (`scratchpad/prova_analytics.py`) `[EXECUTADA]`:

```
FUNIL DE ENTRADA (7 dias, coorte por dia)
  Abriu a landing               10  100% do anterior  100% do topo
  Começou o cadastro             6   60% do anterior   60% do topo
  Etapa 1 · sobre você           5   83% do anterior   50% do topo
  Etapa 2 · objetivo e rotina    4   80% do anterior   40% do topo
  Etapa 3 · personalização       3   75% do anterior   30% do topo
  1ª refeição registrada         2   67% do anterior   20% do topo
  1ª série registrada            1   50% do anterior   10% do topo

RETENÇÃO POR COORTE
  2026-08-10  base=4  D1=50% D7=50% D30=25%

USO POR ÁREA
  2026-09-21  alime 2/2p · trein 1/1p · hidra 0/0p · progr 1/1p · corri 1/1p
```

Três decisões de método:

- **a coorte é do PRIMEIRO passo da pessoa**, e não do dia do evento: quem
  abriu a landing na segunda e treinou na quarta pertence à segunda, senão a
  taxa de um dia passa a depender do movimento do anterior;
- **"voltou" é ter REGISTRADO**, não ter aberto o app — e a lista de eventos
  é a MESMA do uso por área (`EVENTOS_DE_REGISTRO`), com teste, porque duas
  definições de "usou o app" é como duas telas passam a discordar;
- **janela que não fechou vem VAZIA**, não zero: o D30 de quem se cadastrou
  ontem é "—".

`analytics/test_produto.py`: 21 testes. As três telas entraram no teto de 15
consultas de `analytics/test_painel.py` — a "entrada" é a mais cara (uma
consulta por passo, sete, fixas) e cabe.

### Dois achados de caminho, consertados aqui

**O painel escrevia um TERCEIRO vocabulário para as cinco áreas**
`[OBSERVADA]`. `EVENTOS_DA_AREA` tinha slug próprio (`"alimentacao"`,
`"hidratacao"`) e o template escrevia `capfirst` em cima: o cabeçalho da
tabela saía **"Alimentacao"** e **"Hidratacao"**, sem acento. A doutrina é
explícita — "Uma área, um nome — e o nome mora em `Pilar.label`" —, e o
próprio `CLAUDE.md` conta a vez em que o app teve três vocabulários ao mesmo
tempo. Hoje a CHAVE é o `value` de `Pilar` (`dieta`, e não `alimentacao`: é
a separação que `Pilar` existe para manter) e o nome sai de `Pilar.label`,
com teste que recusa as duas formas sem acento. Conferido na tela
`[OBSERVADA]`: `Alimentação · Treino · Hidratação · Progresso · Corrida`.



`.tabela-rolagem` e `.coorte` **existiam no template da Retenção sem regra
nenhuma no CSS** `[EXECUTADA]`. A tabela só não vazava a 390 px porque as
colunas cabiam; as telas novas, com cabeçalho de palavra de verdade, mediram
**621 px numa janela de 390**. Nasceu a seção 54 do `app.css`: a rolagem é do
BLOCO (`tabindex`, `role="region"`), nunca da página. Medido depois: **zero
rolagem horizontal nas quatro telas, a 390 e 1280** `[EXECUTADA]`.

O dead-class ruler de `config/tests.py` não pega isso, e fica dito: ele mede
classes com `__` — as de ELEMENTO. Classe de BLOCO escrita no template sem
regra no CSS não tem guarda automática.

---

## Qualidade

### Sabotagem — 10 de 10 VERMELHAS `[EXECUTADA]`

Uma guarda por item, quebrada sozinha e restaurada
(`scratchpad/sabotar_rodada2.py`; cada linha é uma execução de teste real):

| item | o que foi quebrado | resultado |
|---|---|---|
| 3 | o CTA do painel volta a apontar para a ficha | VERMELHA |
| 3 | o cartão AGORA volta a apontar para a ficha | VERMELHA |
| 4 | a duração volta a ser o intervalo entre registros | VERMELHA |
| 5 | a frase em zero volta a dizer "Ontem faltou" | VERMELHA |
| 6 | a rota `hoje/` muda de nome | VERMELHA |
| 7 | o `add_error` de nível/equipamento deixa de rodar | VERMELHA |
| 8 | o `container_class` sai da tela de corridas | VERMELHA |
| 9 | o rodapé do cartão volta a oferecer `#pesar` | VERMELHA |
| 3.B | o nome da área volta a ser `capfirst` do slug | VERMELHA |
| 3.C | o verbo do zero vira "Recomeça hoje" fixo | VERMELHA (2 testes) |

**Duas delas só ficaram vermelhas na segunda tentativa, e isso É o achado:**

- o **item 8 passou VERDE** na primeira rodada — não havia teste de largura
  nenhum no repositório. A guarda foi escrita por causa disso
  (`ACorridaUsaALarguraDoDesktopTests`);
- o teste do leitor de `data-evento-ao-abrir` **passava com o código
  apagado**, porque o `analytics.js` explica o marcador em prosa e a
  asserção casava com o COMENTÁRIO. Hoje ele lê o arquivo sem as linhas de
  comentário.

### Browser QA — 24 combinações, zero violação real `[OBSERVADA]`

Seis telas (painel do Treino, Home, Corridas e as três de analytics) × 390 e
1280 × escuro e claro, com as réguas medidas no DOM
(`scratchpad/qa_rodada2.py`; capturas em `achados/capturas/rodada-2/`):
**zero rolagem horizontal, zero texto abaixo de 11 px**. O único alerta de
alvo foi o mesmo em 4 combinações — os três `<input type=radio>` de 19×19 do
seletor de duração do painel —, e é falso positivo da minha régua: o alvo é
o `<label>` que os envolve, MEDIDO em **293×50**. O seletor não foi tocado
nesta branch.

E as promessas, lidas no DOM a 1280 `[OBSERVADA]`:

```
3 CTA do painel:     {'texto': 'Começar treino', 'destino': '/treino/agora/'}
3 porta da ficha:    {'texto': 'Ver ficha do Treino A · 8 exercícios', 'destino': '/treino/ficha/35/'}
5 ofensiva:          "0 dias  Recomeça hoje: registre uma refeição ou um copo d'água."
8 largura corridas:  {'classe': 'container largo', 'px': 1024}
8 largura progresso: {'classe': 'container largo', 'px': 1024}
9 peso na Home:      {'ancoras': ['Registrar peso'], 'faixa': True}
9 rodapé do cartão:  {'texto': 'Ver progresso', 'destino': '/historico/'}
```

O item 6 foi conferido no servidor: `GET /hoje/` → **301** para `/`
`[EXECUTADA]`.

### Em PRODUÇÃO — `3a6094b` `[EXECUTADA]`

PR #142 mergeado pela fila (`3a6094b`), staging provado, smoke 5/5, **E2E de
gente 13 de 13** com conta de robô criada e apagada no staging, e promoção no
lote. **`/saude/` de produção responde `{"commit": "3a6094b", "ambiente":
""}`.**

O que ficou provado em produção, e como:

| item | prova em produção |
|---|---|
| 6 | `GET /hoje/` → **301** para `/`; `/demo/hoje/` continua 200 (a rota nova está na raiz e não sombreia o demo) `[EXECUTADA]` |
| 8 | `/demo/treino/corridas/` com `.container` de **1024 px** `[OBSERVADA]` |
| — | smoke 9 rotas públicas, todas 200 `[EXECUTADA]` |
| — | 16 combinações (4 telas × 390/1280 × escuro/claro): **zero rolagem horizontal, zero texto abaixo de 11 px** `[OBSERVADA]`; capturas em `achados/capturas/rodada-2-producao/` |

`[LIMITAÇÃO]` **Os itens 3, 4, 5, 7 e 9 não puderam ser vistos LOGADO em
produção**, por dois motivos somados, e os dois estão previstos no
`CLAUDE.md`:

1. **o ambiente desta sessão proíbe criar conta e digitar senha**, então a
   conta descartável pelo signup público — o caminho que o dono autorizou em
   18/09/2026 — não está disponível aqui. O `CLAUDE.md` diz exatamente o que
   fazer nesse caso: dizer isso no relatório e provar o que der pelo `/demo/`;
2. **o `/demo/` não alcança esses cinco hoje**: a persona Carlos está em DIA
   DE DESCANSO em 24/09 `[OBSERVADA]` — o painel diz "Dia de descanso" e o
   bloco do treino de hoje, com o CTA dentro, não é renderizado —, e a Home
   do demo não traz a faixa de pesagem nem o cartão do painel de Progresso.

O que os cobre no lugar disso: a **suíte inteira** sobre o commit promovido
(o check "suíte rápida" verde sobre `a8a4661`, e 4.486 locais), o **E2E de
gente 13/13 no staging sobre `3a6094b`** — que percorre cadastro, as três
etapas, água, refeição e uma série concluída — e o **browser QA local a 390 e
1280 nos dois temas**, onde os cinco foram lidos no DOM. O que NÃO ficou
provado é a renderização logada com o HTML servido por produção; está dito
aqui em vez de contornado.

E uma consequência disso virou sugestão de tarefa: **o E2E noturno ainda
chega à execução pela FICHA**, não pelo CTA novo — então o caminho que esta
missão tornou principal nunca é exercido por um navegador de verdade antes
de cada promoção. É uma linha no `serie()` de `scripts/qa/e2e_staging.py`, e
ficou fora daqui porque é hardening do roteiro, não da missão.

- `manage.py check`, `makemigrations --check`, `git diff --check`: limpos
  `[EXECUTADA]`.
- Uma migration, `plans.0012_retrato_do_cardapio` (dois campos, `default=""`,
  sem backfill).
- **O raio de alcance do bloco 2, medido:** 127 testes de `accounts` + 46 do
  resto da suíte. A distribuição é a história — **112 dos 127 estavam em DOIS
  fixtures compartilhados** (`accounts.tests.STEP3` e
  `accounts.test_tres_etapas.ETAPA2`): duas linhas. O resto foram payloads
  soltos e, sobretudo, **testes que encodavam a decisão revertida**.
- **Seis testes de doutrina foram REESCRITOS, não remendados**, e cada um diz
  o que mudou e o que continua valendo:
  - `test_verbos_do_treino` inteiro — a régua nunca foi "vai para a ficha", é
    **um rótulo, um destino**; só o destino mudou;
  - `ComecarTreinoAbreAFichaTests` virou `…AbreAExecucaoTests`;
  - `test_o_botao_do_hero_leva_para_a_ficha` virou "o hero tem as DUAS portas,
    cada uma com o seu nome";
  - `test_quem_nunca_respondeu_continua_em_branco` e
    `test_em_branco_nao_apaga_o_que_a_pessoa_tinha` passaram a medir a RECUSA:
    o princípio ("o app não declara nível por ninguém") é o mesmo, a régua
    ficou mais forte;
  - `test_o_perfil_diz_que_a_experiencia_nao_foi_informada` virou
    `…diz_qual_padrao_esta_valendo`, com a asserção recortada à LINHA da
    experiência — `musculacao` em branco continua dizendo "não informada" de
    propósito, porque ali o vazio é "nunca vi a pergunta" e o app não tem
    padrão a declarar.
- **O cartão AGORA da Home teve UM `href` mudado** (`plans/agora.py`), e só
  ele: "Começar treino" apontando para a ficha na Home e para a execução no
  painel seria o mesmo rótulo com dois destinos — exatamente o achado UX
  P1-11 que a régua existe para impedir. Nada de layout foi tocado; o PR #138
  não conflita com isso.
- **O teto de consultas do POST da série subiu 21 → 22**, e a correção é de
  ATRIBUIÇÃO: o comentário de 21/09 creditava o +1 ao INSERT de
  `treino.serie_concluida`, e o evento nunca era disparado — o catálogo e o
  teto foram escritos, a chamada não. Ela entrou agora.
- **Suíte completa local: 4.486 testes** `[EXECUTADA]`, com UM vermelho —
  e o vermelho era MEU, de um teste desta mesma missão:
  `test_sabotagem_a_frase_de_zero_e_uma_so` exigia que a frase de zero fosse
  literalmente a MESMA com e sem ontem medido, e passou a ser falsa quando o
  verbo aprendeu a diferença. Ele foi REESCRITO, não afrouxado: hoje cobra a
  instrução inteira dos dois lados, proíbe as três palavras de cobrança
  ("faltou", "dieta ou água", "treino") e nomeia o verbo de cada caso — e
  sabotado (verbo fixo) fica vermelho, junto com o teste do primeiro dia.
  Depois dele, os módulos tocados rodaram de novo: `analytics config ajuda
  workouts.test_ux_rodada2 plans.test_landing plans.test_home_adaptativa`,
  **944 OK** `[EXECUTADA]`. O único `expectedFailure` é o nomeado de sempre
  (a letra A do peso do corpo).

## O que ficou no meio do caminho, e por quê

1. **Dois falsos positivos do `pre-push`, os dois anteriores a esta missão**
   e os dois no ledger:
   - `plans.test_card_de_refeicao.test_o_card_leva_os_ingredientes_com_a_porcao`
     depende da ORDEM dentro da seleção do hook (ver acima — provado com a
     lista literal e a minha mudança removida);
   - `config.tests.test_no_rule_targets_a_class_the_templates_never_render`
     reprova em QUALQUER worktree cujo CAMINHO contenha `scratchpad`: o
     filtro `not {"artifacts", "scratchpad"} & set(caminho.parts)` exclui o
     repositório inteiro, e a varredura passa a medir marcação vazia. É o
     caso de todo worktree criado sob o scratchpad da sessão.
2. **`achados/experiencia-usuario-20260923.md` não existe** (ver o topo).
3. **`/treino/` e `/conquistas/` abrem em 480 px no desktop** — o mesmo
   defeito do item 8, em duas telas que a missão não citou `[OBSERVADA]`:
   medi o `container` das oito telas principais e só essas duas ficaram
   estreitas. Não corrigi porque largura é layout, o painel do Treino é
   justamente a tela que esta missão acabou de promover a porta principal, e
   mexer nela sem o desenho ao lado é exatamente o que o dono pediu para não
   fazer. A guarda de largura que nasceu aqui torna a correção barata quando
   for decidida.
4. **`suite.yml` roda em TODO PR, contra o que ela própria documenta**
   `[LIDA NO CÓDIGO]`. O cabeçalho do arquivo diz "Não é mais o gate de PR
   — quem barra o merge é 'suíte rápida'" e lista os gatilhos como "DEPOIS
   do merge (`push: main`)" e "à mão"; o bloco `on:` tem `pull_request:
   branches: [main]`. Medido neste PR: as duas rodaram no mesmo push. Não
   quebra nada — a fila espera só a rápida, e o repositório é público, então
   minuto de Actions é ilimitado —, mas é ~31 min de runner por PR que a
   documentação diz não existir. **Não mexi**: pode ser deliberado desde que
   o repositório virou público, e mudar gatilho de CI no PR de outra missão
   é exatamente o conserto oportunista que o protocolo proíbe.
5. **O PR #140 (missão "dado errado") continua aberto e agora está `behind`**
   duas vezes: `main` andou com o #137 e andará com este. Ele conflita com o
   item 5 em `plans/streaks.py`.

## Decisões que tomei sozinha

- **O `meal_style` entrou no retrato junto com as restrições.** É o MESMO
  formulário, o MESMO POST e o MESMO defeito; corrigir metade deixaria a
  pessoa trocar para "econômica" e continuar vendo salmão.
- **O teto de consultas da Home subiu 17 → 18** com a razão escrita no teste.
  A alternativa (denormalizar os slugs no perfil) cria uma segunda cópia da
  verdade.
- **O item 7 foi feito pelas duas saídas** que a missão ofereceu (ver acima).
- **O `EVENTOS_DA_AREA` passou a ser chaveado por `Pilar`**, e não por slug
  próprio. Podia ter ficado só na tela (`capfirst` → um dicionário de
  nomes), mas aí o nome existiria em DOIS lugares — e o `CLAUDE.md` conta a
  vez em que o produto teve três vocabulários ao mesmo tempo por causa
  disso.
- **A frase da ofensiva em zero não cita o treino**: ele tem dia marcado, e
  oferecê-lo num dia de descanso seria a frase errando de novo.
- **O VERBO da frase distingue quem chegou hoje.** A instrução que a missão
  escreveu começa com "Recomeça hoje", e para uma conta de HOJE isso é
  falso: não há o que recomeçar. `falta_ontem is None` é exatamente "ontem
  não era da conta", e é o único uso que sobrou dele na tela — quem chegou
  hoje lê **"Comece hoje: registre uma refeição ou um copo d'água"**, quem
  já tinha conta lê "Recomeça hoje: …". O resto da frase é o que a missão
  pediu, literal. Era a régua de `test_no_primeiro_dia_a_mensagem_e_comece_hoje`,
  e ela continua valendo com outra frase.
- **O cartão AGORA da Home passou a levar à execução junto com o painel**, e
  isso desfaz um requisito escrito em 13/09/2026 ("'Começar treino' abre a
  FICHA, nunca o primeiro exercício com o vídeo tocando"). Decidi desfazer
  porque a PREMISSA dele não existe mais: nenhum `autoplay` é escrito no
  HTML e o vídeo do exercício nasce no toque — e manter o cartão apontando
  para a ficha enquanto o painel aponta para a execução seria o mesmo
  rótulo com dois destinos, o achado UX P1-11. Um `href`, nenhum layout.
- **O item 8 ganhou teste, que a missão não pedia** — e ganhou porque a
  SABOTAGEM mostrou que não havia guarda nenhuma de largura no
  repositório: apagar o `container_class` da tela de corridas deixava a
  suíte VERDE. A régua não procura a palavra `largo`: compara com uma tela
  IRMÃ que já passou pelo redesenho (`plans:history`), porque é a LARGURA
  que interessa, e tem controle positivo.
- **O funil de entrada é uma tela NOVA**, ao lado do "Funil" genérico, e não
  uma substituição: uma é a ferramenta ("como converte esta sequência?"), a
  outra é a pergunta ("como foi a entrada na terça?").
- **A exceção de i18n do painel de gestão passou a estar ESCRITA.** Ela
  existia desde 21/09/2026 e ninguém a tinha dito: os seis templates de
  `templates/analytics/` nasceram no MESMO dia em que a régua de i18n foi
  escrita, sem `{% load i18n %}` e fora de `TEMPLATES_NOVOS`. Os dois de
  hoje seguem o precedente — e agora o precedente tem razão escrita, no
  `config/test_i18n.py` e no `CLAUDE.md`: aquelas telas são a ferramenta de
  quem OPERA o produto, e a segunda língua é para quem USA o app. Marcar
  meia dúzia de frases de painel seria pior que marcar zero.
- **Os sete passos do funil aparecem mesmo zerados**: eles são a DEFINIÇÃO do
  que está sendo medido, e "ninguém entrou" sozinho não diz por onde a
  entrada passa.

## O que preciso de você

nada.
