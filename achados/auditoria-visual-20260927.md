# Auditoria visual, tela a tela — 27/09/2026

Só medição e diagnóstico. Nenhuma linha de código mudou; o único produto é
este relatório. A régua é a do dono: **3 = nível de mockup de referência**
(composição, hierarquia, tipografia, cor, espaçamento), **0 = só funciona**.
A lei é o `DESIGN.md` (NERVURA · ANDAIME) e o `:root` do `app.css`.

## 0. Como foi medido

| item | valor |
|---|---|
| commit | **`7cdf876`** — o que `/saude/` de produção respondia às 18:3x de 27/09 |
| servidor | local (`runserver`), worktree destacado no commit, banco próprio `nutriplan_auditoria` com `seed_catalog` + `seed_workouts` + `seed_demo` |
| navegador | `agent-browser` (Chromium do próprio agent-browser), captura de **página inteira** |
| vistas | 390×844 escuro · 390×844 claro · 1280×900 claro |
| personas | **P1** "Rafa", academia completa, ABC (2 grupos/dia), intermediário, Ter·Qui·Sex·Dom, **dia 12 com histórico** · **P2** "Lu", só corre, **dia 1** · **P3** "Dani", casa/peso do corpo, iniciante, Seg·Qua·Sex, **dia 1, nada registrado** · e o anônimo |
| capturas | **206** de auditoria (anônimo 15, P1 67, P2 57, P3 67) + 30 de apoio (duas contas para refazer o placar) |
| medição por captura | `medir.js` (tipografia, espaçamento, alvos, cores, componentes, texto, regras do `DESIGN.md`, contraste composto) + **axe 4.12** (`wcag2a,wcag2aa,wcag21aa`) |
| medição estática | `app.css`, `templates/`, `static/js/` lidos no fonte (`estatico.py`) |

As três contas nasceram pelo **cadastro público local** (e-mail
`@nutriplan.invalid`, senha gerada e descartada), passaram pelas três etapas
do onboarding pela tela, e foram **apagadas pela tela** (`/conta/excluir/`
com a senha) — ver §12.

**Vocabulário de evidência** (o de `nutriplan-qa`): `[EXECUTADA]` número que
saiu de script sobre a página ou o fonte; `[OBSERVADA]` visto na captura;
`[LIDA NO CÓDIGO]`; `[HIPOTÉTICA]`.

### Como as notas foram dadas

Oito critérios, 0–3: **Co** composição · **Hi** hierarquia · **Ti**
tipografia · **Cc** cor/contraste · **Es** espaçamento/ritmo · **Ev** estado
vazio · **Vo** voz do texto · **Cs** consistência com o resto do app.

- **Ti, Es e Cc são regra sobre a medição**, sem opinião (`notas.py`):
  - **Ti**: parcela dos blocos de texto cujo tamanho NÃO é um degrau `--texto-*` (±0,05 px) — ≤15 % → 3 · ≤35 % → 2 · ≤60 % → 1 · >60 % → 0; −1 se a display (Big Shoulders) aparece abaixo de 20 px ou com peso fora de 800/900. O **cromo global** (a marca da barra de cima a 16,8 px e os seis links do desktop a 14 px) fica fora da nota da tela e entra como achado próprio (§6): sem isso, uma tela quase vazia tirava 0 por causa da barra.
  - **Es**: parcela dos espaçamentos ≠ 0 (margem, padding, gap) fora dos degraus `--espaco-*`/`--traco`/`--gap` — ≤30 % → 3 · ≤45 % → 2 · ≤60 % → 1 · >60 % → 0.
  - **Cc**: 3; −1 se a tela pinta mais de 5 cores que não são token; teto 1 se algum texto fica abaixo de AA.
- **Co, Hi, Ev, Vo e Cs são observados na captura**, e cada nota ≤ 2 tem o fato que a derrubou em §2–§8. `–` = não se aplica (a tela não tem estado vazio naquela persona).

O **mapa de calor** mostra o PIOR caso de cada tela entre personas e vistas: uma
tela só está no nível do mockup se aguenta todas. A média é de todas as células.
A matriz completa (tela × persona × vista) está em §11.

### Limites desta medição, ditos antes

- **Captura de página inteira desenha os fixos na posição da rolagem**: a
  barra de abas aparece no meio da página nas capturas de 390, e a barra de
  cima aparece no meio de "refeição aberta" (o preparo rolou até a refeição).
  É artefato da captura, não da tela. `[OBSERVADA]`
- **A primeira versão do `medir.js` contava conteúdo de `<details>` fechado**
  (o Chrome dá caixa a ele): acusou nove campos "Alimento" de 34 px que
  ninguém vê. Corrigido e **remedido** em tudo que continuava no mesmo estado;
  onboarding, Home/Treino de P1 e P3-descanso, ficha e execução ficaram com a
  medição v1 (poucos `<details>` nelas; o efeito é pequeno e só infla a
  contagem de textos).
- **Animação**: a captura sai ~0,7 s depois do `load`. O placar do treino
  põe os botões aos 1,0 s (`aparece`, `both`), e a primeira captura saiu sem
  eles — **refeita** com espera de 2,2 s e uma conta nova (P1c). O placar de
  P3 ficou com a captura antiga: os botões dele estão lá, fora do tempo da foto.
- **"Comi outra coisa" é a versão de PRODUÇÃO**, com `<datalist>` nativo: a
  busca com combobox é do PR #162, que não está em `7cdf876`.
- **O "fim" do treino foi alcançado por "Encerrar treino"** (treino parcial).
  O placar de treino COMPLETO (todas as séries) não foi capturado: exigiria
  concluir 15–25 séries pela tela.
- **O histórico de P1 foi semeado pelo ORM** com os serviços do app
  (`tracking.log_meal`, `ExerciseLog`, `HydrationLog`, pesagens, `avaliar`):
  números como "3 conquistas" e "Semana completa" são consequência da
  semeadura, não uso real. Nenhum achado abaixo depende do VALOR desses
  números — só de como a tela os desenha.
- **Axe não mede contraste sobre o palco em gradiente**: 3.157 nós ficaram
  como "incompleto". Por isso o contraste foi recalculado por composição de
  fundo (§7), com controle positivo (o `h1` sobre o palco dá 17,2:1, que é o
  par `--text`/`--bg` da tabela do `DESIGN.md`).

## 1. Mapa de calor (pior caso por tela)

| tela | Co | Hi | Ti | Cc | Es | Ev | Vo | Cs | média |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Landing | 1 | 2 | 2 | 3 | 0 | – | 3 | 2 | 1,95 |
| Cadastro | 2 | 3 | 2 | 3 | 2 | – | 3 | 3 | 2,57 |
| Entrar | 2 | 3 | 2 | 3 | 2 | – | 3 | 3 | 2,57 |
| Onboarding 1 | 1 | 3 | 1 | 3 | 1 | – | 2 | 2 | 2,00 |
| **Onboarding 2** | 1 | 1 | 0 | 2 | 0 | – | 2 | 1 | **1,27** |
| **Onboarding 3** | 1 | 2 | 1 | 3 | 0 | – | 2 | 1 | **1,43** |
| Home | 2 | 1 | 1 | 3 | 1 | 1 | 1 | 1 | 1,83 |
| **Treino · dia de treino** | 0 | 1 | 0 | 1 | 1 | 1 | 2 | 1 | **1,42** |
| Treino · descanso | 2 | 2 | 1 | 3 | 1 | 3 | 3 | 2 | 2,12 |
| Treino · sem musculação | 1 | 1 | 2 | 3 | 1 | 2 | 3 | 2 | 2,04 |
| Ficha | 1 | 2 | 3 | 3 | 2 | – | 2 | 1 | 2,26 |
| Execução · série | 1 | 1 | 2 | 3 | 1 | – | 3 | 2 | 2,07 |
| Execução · descanso | 1 | 1 | 2 | 3 | 1 | – | 3 | 1 | 1,83 |
| Execução · fim | 1 | 1 | 3 | 3 | 2 | – | 1 | 2 | 2,08 |
| Alimentação · fechada | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 1,93 |
| Alimentação · refeição aberta | 2 | 1 | 1 | 2 | 2 | – | 2 | 2 | 1,83 |
| Alimentação · comi outra coisa | 2 | 2 | 1 | 2 | 2 | 1 | 2 | 1 | 1,72 |
| Corrida | 2 | 2 | 1 | 3 | 0 | 2 | 1 | 2 | 2,13 |
| Progresso | 1 | 2 | 2 | 2 | 2 | 2 | 1 | 1 | 1,87 |
| Conquistas | 2 | 2 | 1 | 3 | 0 | 1 | 1 | 1 | 1,83 |
| Histórico (exercícios que já fiz) | 2 | 2 | 2 | 3 | 0 | 2 | 2 | 2 | 2,36 |
| **Conta · Mais** | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | **3,00** |
| Conta · Perfil | 1 | 1 | 2 | 3 | 2 | – | 1 | 2 | 1,71 |
| **Ajuda** | 1 | 2 | 0 | 3 | 0 | – | 3 | 1 | **1,60** |
| **/demo/** | 2 | 1 | 1 | 3 | 0 | – | 2 | 2 | **1,67** |

Leitura de colunas: **Es é a pior coluna do app** (15 das 25 telas com 0
ou 1 — quase metade dos espaçamentos fora da escala, §6); **Cc é a melhor** (só um
componente abaixo de AA em 206 capturas, §7). **Nenhuma tela rola na
horizontal e nenhum texto está abaixo de 11 px, em nenhuma das 206
capturas** `[EXECUTADA]`. A única tela no nível do mockup em quase tudo é a
**Mais** (`/areas/`, 3,00) — ela é a referência interna de como as outras
podem ficar.

## 2. As cinco telas mais distantes do mockup, e o porquê medido

> **Correção (27/09, depois da primeira versão):** a medição de espaçamento
> contava `--pad` (1,25rem = 20 px, o padding do cartão) como valor cru. Ele é
> token. Com ele: **46 % dos espaçamentos fora da escala, não 52 %**, e a nota
> Es sobe em nove telas — o que tira o Perfil (agora 1,71) do quinto lugar e põe
> o `/demo/` (1,67). E `--brand` aparece em **15** porcentagens, não 17.

### 2.1 Onboarding · etapa 2 (1,27)

- **3.067 px de altura a 390** (P1; 3,6 telas) para uma etapa. O CONTINUAR
  fica a ~3.000 px. `[EXECUTADA]`
- **Cinco formas diferentes de "escolha uma opção" na mesma tela**
  `[OBSERVADA]`: cartão com ícone em grade 2×2 (objetivo) · cartão largo com
  visto no canto (atividade, musculação) · **rádio redondo** em lista
  (experiência, equipamento — o `DESIGN.md` pede "rádios e caixas
  quadrados") · segmentado de dias · cartão com chips (divisão). O
  `choice_cards` existe e resolveria as cinco.
- **61 % dos blocos de texto fora da escala** (título do cartão de escolha a
  15,2 px, 14 tamanhos distintos) e **62 % dos espaçamentos fora**
  `[EXECUTADA]`.
- Hierarquia: oito perguntas com o mesmo peso de rótulo, sem agrupamento
  visual entre "objetivo", "rotina" e "academia".
- Voz: "Ajusta o volume semanal de cada grupo muscular"; "Trapézio,
  antebraço, panturrilha e abdômen entram junto, sem virar um dia à parte" —
  vocabulário de quem já treina, na etapa em que duas das três personas de
  21/09 desistiam.

### 2.2 Treino · dia de treino (1,42)

- **A 1280 a grade quebra**: o botão "Ver ficha do Treino A" fica sozinho
  na coluna da esquerda e a lista de sessões começa **~280 px abaixo**, com o
  vão vazio entre os dois (P1 e P3). `[OBSERVADA na captura, medido em pixel]`
- **19 tamanhos de texto distintos, 53 % fora da escala** (P1) — o maior
  número entre todas as telas `[EXECUTADA]`. O CTA **"COMEÇAR TREINO" é
  Big Shoulders a 16 px** (a regra é nunca abaixo de 20), e o "%" do anel é
  Big Shoulders **700** a 14,4 px (a lista fechada é 800/900).
- **"Fazer outro treino" é um `<summary>` de 25 px de altura** (alvo < 44) com
  o triângulo nativo do navegador — o único `<details>` do app com esse
  marcador; os outros dizem "abrir".
- **P3, dia 1**: segunda, quarta e sexta desta semana — dias ANTERIORES à
  conta existir — aparecem como `day-chip--pulado`, esmaecidos a **2,86:1 no
  claro** e 4,0:1 no escuro (o único texto abaixo de AA do app, §7). Quem
  entrou hoje é recebido com três faltas.
- **Dois primários na mesma tela** depois da primeira série (P3):
  "CONTINUAR TREINO (1 DE 5)" e "COMPARTILHAR O QUE JÁ FIZ" — e o segundo é
  **Archivo 14,4** em caixa alta, não a display: uma segunda tipografia de
  botão primário.

### 2.3 Onboarding · etapa 3 (1,43)

- **2.740 px a 390**; o "CALCULAR MINHA ESTIMATIVA" fica a ~2.600 px.
- **As cinco áreas aparecem duas vezes seguidas**: como lista de caixas ("O
  que você quer acompanhar?") e de novo como cartões com ícone ("Qual vem
  primeiro?"). O sexto cartão, "Não quero priorizar agora", não tem ícone
  nem descrição — é o único do grupo assim. `[OBSERVADA]`
- **68 % dos espaçamentos fora da escala** e 52 % dos textos `[EXECUTADA]`.

### 2.4 Ajuda (1,60)

- **82 % dos blocos de texto fora da escala** (as perguntas em 13,x px e os
  títulos de bloco em 20,8 px, que não é degrau) e **73 % dos espaçamentos
  fora** — as duas piores medições do app `[EXECUTADA]`.
- **Anônimo a 390, a barra de cima quebra palavra**: "NutriPla / n",
  "Entra / r", e o "CRIAR CONTA" ocupa um terço da barra. `[OBSERVADA, nos
  dois temas]`
- As perguntas da FAQ são **botões cinza com texto centralizado** — a única
  sanfona do app com essa cara (as outras são "título · abrir").
- A 1280 a página é uma coluna de ~440 px numa janela de 1.265.

### 2.5 /demo/ (1,67)

- **Nenhuma ação primária na capa** — a vitrine do produto abre sem dizer o
  que fazer; "Sobre o demo" é o único link da barra. `[OBSERVADA]`
- **46 % dos textos fora da escala** (os `dt` a 11,8 px, o título "As telas do
  aplicativo" a 16,8) e **58 % dos espaçamentos fora** `[EXECUTADA]`.
- "Quem está usando": o valor de DIVISÃO quebra em cinco linhas numa coluna de
  ~150 px. `[OBSERVADA]`
- Voz: "Hoje: o **orquestrador** do dia" — a palavra do `CLAUDE.md`, não do
  produto.

### 2.6 Logo atrás: Conta · Perfil (1,71)

- **3.672 px a 390** (4,4 telas), doze blocos `[EXECUTADA]`.
- O único primário da tela é **"RECALCULAR METAS"**, no topo de uma tela de
  ajustes; "Sair da conta" é um botão **preenchido de perigo** no meio de seis
  contornos. `[OBSERVADA]`
- Voz: o subtítulo diz **"Editar qualquer bloco recalcula sua dieta"** — a
  regra de linguagem de 21/09 (estimativa, nunca "dieta"/"plano" para a
  alimentação) vale para a Home, a Alimentação e a landing, e esta frase
  escapou dela.
- A 1280 as duas colunas terminam em alturas muito diferentes (a da direita
  acaba em ~780 px, a da esquerda em ~1.340).

## 3. Defeitos pontuais que pesam mais que a média

A média esconde isto: são poucas linhas cada, e estão nas telas mais usadas.

| # | o quê | onde | medida | classe |
|---|---|---|---|---|
| 1 | **O campo de carga tem 36 px de largura e corta o número**: "59,50" aparece como "5⁹" | Execução · série e descanso, P1, **390** (a 1280 tem 123 px e cabe) | `input.registro__carga` 36×52 px `[EXECUTADA]` | BUG · P0 (alvo < 44 e o número herói da tela ilegível, a cada série) |
| 2 | **"Agora" vira "Ag…"** no chip da refeição da vez | Alimentação, 390, as três personas | caixa 46 px, o texto precisa de 50 `[EXECUTADA]` | BUG · P1 (cinco refeições por dia) |
| 3 | **O aviso de conquista cobre "desfazer última série" e "Anotar algo desta série"**, e traz um segundo primário (COMPARTILHAR) abaixo de CONCLUIR SÉRIE | Execução · descanso, P1 e P3 | `[OBSERVADA]` | UX REAL · P1 |
| 4 | **A nervura do placar atravessa o "1"** (séries) e a unidade "kg levantados" fica solta, ~50 px à direita e acima da linha de base do número | Execução · fim, todas | `[OBSERVADA]`; o `DESIGN.md` pede "unidade colada … na mesma linha de base" | UX REAL · P2 |
| 5 | **Home de quem disse que não faz musculação oferece "Sem ficha — A sua ficha ainda não foi montada · Montar treino"**, enquanto a aba Treino diz "Você disse que não faz musculação" | Home, P2 | `[OBSERVADA]` | UX REAL · P1 |
| 6 | **Dias anteriores à conta marcados como "pulado"**, a 2,86:1 | Treino, P3 dia 1, claro | `[EXECUTADA]` (axe e composto concordam) | BUG · P0 (contraste abaixo de AA) |
| 7 | **"Buscar no YouTube" tem 21 px de altura** | Execução, P3 (exercício sem vídeo) | `[EXECUTADA]` | BUG · P0 (alvo < 44) |
| 8 | **A dica do exercício sem vídeo quebra letra a letra** numa coluna de ~45 px ("ombro / s;") | Execução, P3, 390 | `[OBSERVADA]` | UX REAL · P1 (já registrada na Missão B como fora de escopo; Missão C) |
| 9 | **Encerrar sem série nenhuma abre um placar de zeros**: "PEITO E TRÍCEPS FECHADO · 0 séries feitas · 0 de 7" | Execução · fim, conta sem série | `[OBSERVADA]` | UX REAL · P2 |
| 10 | **"−96 % vs. a última vez"** num treino encerrado com 1 de 25 séries | Execução · fim, P1 (primeira captura, sobrescrita pela refeita; o número foi lido na tela) | `[OBSERVADA]` | UX REAL (tom punitivo) · P2 |
| 11 | **Hidratação duas vezes na mesma dobra**: o AGORA "REGISTRAR 500 ML" e o cartão com +250/+500/+750 logo abaixo | Home, P2 e P3 | `[OBSERVADA]` | UX REAL · P2 |
| 12 | **Progresso diz "Nenhuma série anotada… Abrir o treino de hoje"** a quem só corre e, a P3, num dia de descanso | Progresso, P2 e P3 | `[OBSERVADA]` | UX REAL · P2 |
| 13 | **Conquistas convida quem só corre a "VER O TREINO"** ("A primeira chega quando você registrar a primeira série") | Conquistas, P2 | `[OBSERVADA]` | UX REAL · P2 |
| 14 | **A lista "Trocar por outra receita" do painel lateral é cortada no meio de uma linha** (rolagem interna sem sinal) | Alimentação, 1280 | `[OBSERVADA]` | OBSERVAÇÃO · P3 |
| 15 | **"59,50kg" sem espaço** na ficha; "59,50 kg" na execução e no Progresso | Ficha, P1 | `[OBSERVADA]` | OBSERVAÇÃO · P3 |
| 16 | **Ficha de P3: o quadrado da foto repete o número da linha** ("1" no selo e "1" no quadrado) nos 3 de 5 exercícios sem foto | Ficha, P3 | `[OBSERVADA]` | UX REAL · P2 |

## 4. Tokens fora do sistema, por arquivo

### 4.1 No fonte `[EXECUTADA, estatico.py]`

| arquivo | categoria | nº | o que é |
|---|---|---|---|
| `static/css/app.css` | `font-size` cru | **108 declarações, 27 valores** | `.82rem` ×17 · `.72rem` ×14 · `.78rem` ×11 · `.76rem` ×8 · `.85rem`/`.88rem` ×7 · `1.05rem`/`.92rem`/`.95rem` ×5 · `.74rem` ×4 · … (a catraca do repositório diz 107) |
| `static/css/app.css` | espaçamento cru | **192 declarações, 50 valores** | `.75rem` ×25 · `.6rem` ×20 · `.85rem` ×18 · `.4rem` ×16 · `.3rem` ×14 · `.2rem`/`.8rem` ×12 · `.55rem` ×11 · … |
| `static/css/app.css` | **tinta `color-mix()` sem token** | **63 usos** | `--brand` em **15 porcentagens** (6, 9, 12, 13, 20, 22, 24, 26, 28, 30, 32, 34, 42, 45, 60 %), `--terra` em 8, `--danger`/`--chama`/`--agua` em 3 cada. O `DESIGN.md` diz "um verde só age"; o app tem um verde em quinze intensidades escritas à mão |
| `static/css/app.css` | cor literal | 10 | `.demo__rotulo`/`.demo__fechar` (`rgba(0,0,0,.62)`, `#fff`), `.demo--aberta` (`#000`), `::backdrop` das duas folhas (`rgb(0 0 0/.55)`), `.macro-bar` (sombra `rgba(0,0,0,.28)`), `.conquista` (sombra `rgba(0,0,0,.45)`), `.auth--entrada::before` (gradiente) |
| `static/css/app.css` | sombra literal | 3 | `.conquista { box-shadow: 0 12px 32px rgba(0,0,0,.45) }` — o `DESIGN.md` diz "sem cartão com sombra"; `.entrada__logo .marca` (brilho); `.macro-bar` (inset) |
| `static/css/app.css` | token local com literal | 2 | `.tela-ficha { --max: 58rem }`, `.agora--com-descanso { --exec-descanso: 4rem }` |
| `static/css/app.css` | quina, camada, duração, peso | **0** | nenhum `border-radius` cru (só o `50%` do anel), todo `z-index` é token, nenhuma duração crua (os dois `0s` achados são o zeramento do movimento reduzido), nenhum peso cru |
| `templates/500.html` | `<style>` próprio | 1.785 caracteres | um mini-sistema paralelo: `--linha` e `--dim` (nomes que não existem no `:root`), `#0b140f`, pilha de fonte do sistema em vez de Archivo, 44/18/22 px crus |
| `templates/partials/botao_google.html` | cor literal em SVG | 4 | as cores da marca do Google — exceção legítima |
| `templates/admin/accounts/user/change_form.html` | `style=` estático | 2 | tela do admin do Django, fora do app |
| `templates/` (resto) | `style=` calculado | 18 | todos `{{ }}` do servidor — a exceção escrita no `CLAUDE.md` |
| `static/js/*.js` | cor ou medida literal em `.style` | **0** | — |

### 4.2 Na tela `[EXECUTADA, medir.js]`

**22 cores pintadas que não são nenhum token** do regime ativo, todas tintas:
`--brand` a 9/12/20/24/26/28/30/32/34 % (fundos de selo, bordas de cartão,
marca da refeição, o cartão escolhido), `--surface` a 82 % (o prato
translúcido da Home e da Alimentação), a trilha dos macros a 26 % (três
cores), os dias do treino a 22 %, `--chama` a 16 %, `--danger` a 12/34 % (o
"Sair da conta") e o preto a 62 % do player do demo.

## 5. Componentes que existem em mais de uma versão

Medido pela assinatura de estilo calculado (tamanho, peso, família, caixa,
cor, fundo, borda, quina, padding, altura) de cada instância, a 390 escuro,
em todas as telas `[EXECUTADA]`:

| componente | versões | o que diverge |
|---|---|---|
| **botão primário** | **3** | Big Shoulders 22,4 px (o padrão) · **Archivo 14,4** em caixa alta ("COMPARTILHAR O QUE JÁ FIZ") · **`pesagem__salvar`**, um verde cheio SEM `btn--primary`, sem inclinação, Archivo 15,2 ("Salvar" do peso) |
| **botão de contorno** (`btn--ghost`) | 5 alturas | 44 · 49 · 52 · 53 · 71–80 px, e padding horizontal 12,8 / 16 / 18,4 px |
| **"Compartilhar"** | 2 | contorno nas Conquistas; primário cheio e inclinado no aviso da execução |
| **título de seção `h2`** | **5** | **Archivo 20,8 px sentence case (119 usos — e 20,8 não é degrau da escala)** · rótulo 11,2 px caixa alta .16em (o do `DESIGN.md`, 18 usos) · display 22,7 px (8) · 16,8 px (1) |
| `h3` | 3 | 11,2 caixa alta · 17,28 · 14,4 |
| **cartão `.card`** | **12** | padding 3,2 / 12 / 13,6 / 20 / 27,2 px; borda de 1 ou 2 px; fundo sólido ou `--surface` a 82 % |
| **escolha de opção** | **5** | ver §2.1 — cartão-ícone em grade, cartão largo com visto, rádio redondo, segmentado, cartão com chips |
| **sanfona `<details>`** | 4 | "título · abrir" · triângulo nativo ("Fazer outro treino") · "⌄" ("Ver as pesagens dia a dia", "trocar") · botão cinza centralizado (FAQ da Ajuda) |
| `field-input` | 2 | 15,36 px (campos `num`) e 16 px |
| `tile` | 2 | padding 3,2 e 11,2; borda 0 e 2 px |
| `pill` | 2 | com e sem caixa alta |
| **aba ativa** | 2 | barra de baixo: régua em cima, sem preenchimento (o `DESIGN.md`); barra de cima do desktop: **caixa preenchida** de `--brand-soft` |
| **verbo para o mesmo destino** | 3 | "Ver corrida", "Ver corridas", "Abrir corridas" → `/treino/corridas/`; "Ver cardápio", "Abrir o cardápio de hoje" → `/alimentacao/` |

## 6. Tipografia e espaçamento, medidos no app inteiro

`[EXECUTADA]`, 390 escuro, todas as capturas:

- **30 tamanhos de texto distintos em uso**; a escala tem 10. **36 % dos
  blocos de texto estão num tamanho que não é degrau.** Os mais frequentes
  fora dela: **12,2 px** (167 — macros do herói da Alimentação), **16,8 px**
  (149 — a marca da barra de cima, em TODA tela), **20,8 px** (119 — o `h2`
  de seção), **15,2 px** (64 — título do cartão de escolha), **13,6 px** (58
  — linhas de conquista e macros), **11,8 px** (43 — `dt` do demo). No
  desktop logado, os seis links da barra de cima estão a **14 px**, fora da
  escala.
- **A display abaixo de 20 px** em três lugares: o número do anel da Home
  (**18,4 px**), o CTA "COMEÇAR TREINO" da aba Treino (**16 px**) e o "%" do
  anel do treino (**14,4 px**, e em peso 700). A Archivo aparece a 800 em
  dois lugares (a lista fechada é 400–700).
- **Espaçamento: 46 % dos valores em uso estão fora da escala do `:root`**,
  e **só 28 % caem na grade da direção** (4·8·12·16·24·32·48). Os mais
  frequentes fora: 6,4 px (gap
  do botão), 12 px, 12,8, 13,6, 8,8, 18,4, 3,2, 4,8, 7,2, 9,6 px. O
  `DESIGN.md` já sabe disso ("o remap move pixel em toda tela e é lote
  próprio", decisão de 16/09) — a medição dá o tamanho do lote.
- **Nenhuma** vírgula decimal trocada por ponto encontrada no texto visível
  (o detector procurou "62.50" em todas as capturas). `[EXECUTADA]`

## 7. Alvos de toque e contraste

**Alvos < 44 × 44** `[EXECUTADA]`, depois de tirar o conteúdo de `<details>`
fechado e os links corridos em parágrafo (a exceção do WCAG 2.5.8):

| alvo | medida | onde |
|---|---|---|
| campo de carga | **36 × 52** | Execução, P1, 390 |
| `<summary>` "Fazer outro treino" | 289 × **25** (938 × 25 a 1280) | Treino, P1 e P3 |
| "Buscar no YouTube" | 201 × **21** | Execução, P3 |

**Contraste** `[EXECUTADA]`: 6.263 blocos de texto medidos por composição
de fundo em 111 capturas, mais o axe em todas as 206. **Uma única falha**, e
os dois métodos concordam: o nome e o marcador do `day-chip--pulado`
(opacidade sobre `--brand-soft`) — **2,86:1 no claro, 4,0:1 no escuro**,
alvo 4,5. O resto passa AA. Os botões primários foram tirados da conta
composta de propósito: o fundo deles é um `::before` inclinado que a
composição não enxerga, e o par `--on-brand`/`--brand` está na auditoria de
tokens do repositório.

## 8. Inventário de texto (microcopy)

Todo texto de botão, título, estado vazio e aviso visível nas capturas de
390 escuro está em `_harness/inventario.txt` (136 botões, 91 títulos, 10
estados vazios, 36 avisos). Marcados abaixo só os que caem em **J**
(jargão), **P** (tom punitivo) ou **I** (incoerência de voz); o resto está
na voz do `DESIGN.md` — direto, adulto, sem promessa.

| texto | onde | marca | por quê |
|---|---|---|---|
| "Mudou alguma coisa? Editar qualquer bloco **recalcula sua dieta**." | Perfil | I | a regra de 21/09 é "estimativa", nunca "dieta"/"plano" para a alimentação |
| "Falta treino, **dieta** ou água para manter a sequência hoje" | Home (ofensiva) | I | a mesma regra |
| "Sem ficha · A sua ficha ainda não foi montada · Montar treino" | Home, P2 | I | contradiz a resposta "não faço musculação" que a aba Treino respeita |
| "Nenhuma série anotada ainda … Abrir o treino de hoje" | Progresso, P2 e P3-descanso | I | séries para quem corre; "treino de hoje" num dia de descanso |
| "A primeira chega quando você registrar a primeira série de um treino · VER O TREINO" | Conquistas, P2 | I | idem |
| "**−96 %** vs. a última vez" | placar, treino encerrado | P | compara 1 série com um treino inteiro |
| "PEITO E TRÍCEPS **FECHADO** · 0 séries feitas" | placar sem série | P/I | celebra um treino que não aconteceu |
| dias "pulado" antes da conta existir | Treino, P3 dia 1 | P | três faltas no primeiro dia |
| "Ficou para trás" | Alimentação (refeição vencida) | P (leve) | é o estado; a marca podia só dizer a hora |
| "**Déficit −130 kcal/dia**", "macros", "saldo do dia", "proteína no rumo" | Alimentação | J | termos de nutrição sem explicação na mesma tela |
| "Empurrar — peitoral e **extensores do cotovelo**"; "peitoral, **sinergista e deltoide**" | Treino, Ficha | J | anatomia no subtítulo da sessão |
| "Ajusta o **volume semanal** de cada grupo muscular" | Onboarding 2 | J | na etapa em que as personas desistiam |
| "**aderência**", "descanso **combinado**", "combinado, sem série" | Progresso (legendas) | J | vocabulário interno do motor |
| "MELHORES CARGAS **1 DIA SEGUIDO**" | Progresso, P3 | I | selo de sequência de um dia |
| "Hoje: o **orquestrador** do dia" | /demo/ | J | a palavra do `CLAUDE.md`, não do produto |
| "o navegador não deixa a página acompanhar a localização em segundo plano" | Corrida (antes do CTA) | J | a limitação técnica vem antes da ação |
| "Importar de arquivo (**GPX/TCX**)" | Corrida | J | aceitável para quem tem relógio; é o terceiro botão da tela |
| "3 **conquistas**" (Mais) × "Desbloqueadas 3" × "0 **recordes**" (Conquistas) × cinco selos "**recorde**" (Progresso) | P1 | I | dois números para "recorde" na mesma conta (com histórico semeado — ver §0) |
| verbos para o mesmo destino | §5 | I | "Ver corrida"/"Ver corridas"/"Abrir corridas" |
| caixa dos títulos | app | I | `h1` em display caixa alta; `h2` em Archivo sentence case; rótulo em caixa alta pequena; "Conquistas"/"Minhas conquistas"/"MINHAS CONQUISTAS" |

## 9. Onde o `DESIGN.md` e o app divergem — recomendo rever

A spec vence proposta externa; aqui a divergência é entre a spec e o próprio
app, e a decisão de qual dos dois muda é do dono.

1. **Quatro abas × cinco.** O `DESIGN.md` diz "barra inferior de QUATRO
   itens … cinco não cabem" e lista "cinco abas" em "o que este app não faz";
   o app tem cinco (Hoje · Alimentação · Treino · Progresso · Mais) desde o
   redesenho de 22/09 — e a 390 elas cabem (nenhum alvo < 44, nenhuma
   rolagem). A 320, onde a spec mediu, esta auditoria não mediu. A spec está
   velha no número, e a conta dos 320 px precisa ser refeita com as cinco.
2. **Um terceiro nível de título que a spec não tem.** O `DESIGN.md` define
   o rótulo de seção (11–12 px, caixa alta) e o herói em display; o app usa,
   em 119 lugares, um `h2` em Archivo 20,8 px sentence case — nem rótulo,
   nem herói, nem degrau da escala. Ou ele entra na spec com um token, ou
   sai das telas.
3. **Rádio quadrado** na spec, **rádio redondo** no onboarding.
4. **"Um verde só age"** na spec, quinze tintas de `--brand` no CSS.
5. **"Sem cartão com sombra"** na spec, sombra de 32 px no aviso de conquista.
6. **Aba ativa sem preenchimento** na spec (e na barra de baixo); a barra
   de cima do desktop preenche.
7. **Unidade colada ao número na mesma linha de base** na spec; o placar a
   solta.

## 10. Proposta de ordem de ataque (não executada)

Ordem pela régua do `nutriplan-ux`: quem bloqueia a tarefa → frequência
(com a confiança dela) → menor esforço. Cada item diz a tela e o efeito
esperado, não a implementação.

1. **P0 — o campo de carga a 390** (§3.1). Frequência: uma vez por série,
   dezenas por treino (ALTA, estrutura do produto). É o número que a pessoa
   veio mudar, e hoje ele não se lê.
2. **P0 — os três alvos < 44** (§7) e o **contraste do dia "pulado"** (§3.6)
   — junto com a pergunta de produto que ele esconde: dia antes da conta não
   é falta.
3. **P1 — execução sem sobreposição**: o aviso de conquista não cobre
   "desfazer"/"Anotar" e não traz um segundo primário (§3.3); a dica do
   exercício sem vídeo com largura de leitura (§3.8, Missão C).
4. **P1 — Alimentação**: o chip "Agora" inteiro (§3.2); a refeição aberta com
   UMA ação principal em vez de quatro contornos iguais (§1, Hi 1). Cinco
   refeições por dia (ALTA).
5. **P1 — Home coerente com a resposta da pessoa**: quem não faz musculação
   não vê "Montar treino" (§3.5); hidratação uma vez por dobra (§3.11).
6. **P2 — dívida de sistema, em lotes com captura antes/depois** (é o que
   levanta a coluna Es e Ti do mapa inteiro de uma vez):
   a) o `h2` de 20,8 px vira degrau (ou rótulo) — 119 ocorrências;
   b) as tintas de `--brand` viram três ou quatro tokens nomeados;
   c) o remap de espaçamento para a grade da direção (já decidido como lote
      próprio em 16/09; a medição dá o tamanho: 46 % fora);
   d) um primário, um contorno, uma sanfona — as versões de §5 colapsam no
      componente que já existe.
7. **P2 — Onboarding 2 e 3** (as duas piores notas): uma forma de escolha só
   (`choice_cards`), agrupamento por assunto, as áreas uma vez. Frequência:
   uma vez por conta (BAIXA por tela, ALTA por consequência — é onde as
   personas desistiam). A reestruturação é decisão de produto; o que é só
   visual (a forma única de escolha) não é.
8. **P2 — placar** (§3.4, §3.9, §3.10): a nervura não atravessa número, a
   unidade colada, e o tom do treino parcial.
9. **P2 — desktop**: a grade do Treino (§2.2), o Progresso desbalanceado, as
   colunas estreitas de Ajuda e onboarding. Nenhuma decisão nasce no desktop
   (`nutriplan-ux`), por isso depois.
10. **P3 — Perfil e Ajuda** (§2.4, §2.5): ordem e agrupamento, a barra
    anônima que quebra palavra a 390, e a voz (§8).

**NÃO MUDAR** — o que está no nível e corre risco numa rodada de refinamento:
a **Mais** (`/areas/`, 3,00 — identidade, cartões onde há número, lista onde
não há; é o modelo para Perfil e Ajuda); **Cadastro e Entrar** (2,57);
a **tipografia da ficha e do histórico** (13 % e 7 % fora da escala, 49 % e
52 % na grade — as mais próximas da direção); o **Ferro forçado na execução**
no tema claro (a captura a 1280 claro sai escura, como o contrato manda);
**zero rolagem horizontal e zero texto abaixo de 11 px** em 206 capturas.

## 11. Matriz completa (tela × persona × vista)

Cada célula é `Co Hi Ti Cc Es Ev Vo Cs`, um dígito por critério (`–` = não
se aplica).

| tela | persona | tela capturada | 390 escuro | 390 claro | 1280 claro |
|---|---|---|---|---|---|
| Landing | anon | `landing` | `22230–32` | `22230–32` | `12230–32` |
| Cadastro | anon | `cadastro` | `23232–33` | `23232–33` | `23232–33` |
| Entrar | anon | `entrar` | `23232–33` | `23232–33` | `23232–33` |
| Onboarding 1 | p1 | `onboarding-1` | `23131–22` | `23132–22` | `13131–22` |
| Onboarding 1 | p2 | `onboarding-1` | `23131–22` | `23132–22` | `13131–22` |
| Onboarding 1 | p3 | `onboarding-1` | `23131–22` | `23132–22` | `13131–22` |
| Onboarding 2 | p1 | `onboarding-2` | `11021–21` | `11021–21` | `11120–21` |
| Onboarding 2 | p2 | `onboarding-2` | `22130–21` | `22130–21` | `12130–21` |
| Onboarding 2 | p3 | `onboarding-2` | `11021–21` | `11021–21` | `11120–21` |
| Onboarding 3 | p1 | `onboarding-3` | `12130–21` | `12130–21` | `12130–21` |
| Onboarding 3 | p2 | `onboarding-3` | `12130–21` | `12130–21` | `12130–21` |
| Onboarding 3 | p3 | `onboarding-3` | `12130–21` | `12130–21` | `12130–21` |
| Home | p1 | `home` | `23132–22` | `23132–22` | `23131–22` |
| Home | p2 | `home` | `22132111` | `22132111` | `22131111` |
| Home | p2 | `home-depois-da-corrida` | `22132111` | `22132111` | `22131111` |
| Home | p3 | `home` | `21132232` | `21132232` | `21131232` |
| Home | p3 | `home-dia-de-treino` | `21132232` | `21132232` | `21131232` |
| Treino · dia de treino | p1 | `treino` | `22031–22` | `22031–22` | `02031–22` |
| Treino · dia de treino | p3 | `treino-dia-de-treino` | `21112121` | `21112121` | `01111121` |
| Treino · descanso | p3 | `treino` | `22131332` | `22131332` | `22131332` |
| Treino · sem musculação | p2 | `treino` | `11332232` | `11332232` | `11231232` |
| Ficha | p1 | `ficha` | `22333–22` | `22333–22` | `22332–22` |
| Ficha | p3 | `ficha` | `12333–21` | `12333–21` | `12333–21` |
| Execução · série | p1 | `execucao-serie` | `11331–32` | `11331–32` | `22331–32` |
| Execução · série | p3 | `execucao-serie` | `12231–32` | `12231–32` | `22231–32` |
| Execução · descanso | p1 | `execucao-descanso` | `11331–31` | `11331–31` | `11331–31` |
| Execução · descanso | p3 | `execucao-descanso` | `11232–31` | `11232–31` | `11231–31` |
| Execução · fim | p1 | `execucao-fim` | `12332–22` | `12332–22` | `12332–22` |
| Execução · fim | p1 | `execucao-fim-sem-serie` | `11332–12` | `11332–12` | `11332–12` |
| Execução · fim | p3 | `execucao-fim` | `12333–22` | `12333–22` | `12332–22` |
| Alimentação · fechada | p1 | `alimentacao-fechada` | `22122–22` | `22122–22` | `22122–22` |
| Alimentação · fechada | p2 | `alimentacao-fechada` | `22132222` | `22132222` | `22122222` |
| Alimentação · fechada | p3 | `alimentacao-fechada` | `22132222` | `22132222` | `22122222` |
| Alimentação · refeição aberta | p1 | `alimentacao-refeicao-aberta` | `21122–22` | `21122–22` | `21222–22` |
| Alimentação · refeição aberta | p2 | `alimentacao-refeicao-aberta` | `21132–22` | `21132–22` | `21222–22` |
| Alimentação · refeição aberta | p3 | `alimentacao-refeicao-aberta` | `21132–22` | `21132–22` | `21222–22` |
| Alimentação · comi outra coisa | p1 | `alimentacao-comi-outra-coisa` | `22122121` | `22122121` | `22222121` |
| Alimentação · comi outra coisa | p2 | `alimentacao-comi-outra-coisa` | `22132121` | `22132121` | `22222121` |
| Alimentação · comi outra coisa | p3 | `alimentacao-comi-outra-coisa` | `22132121` | `22132121` | `22222121` |
| Corrida | p1 | `corrida` | `22332212` | `22332212` | `22331212` |
| Corrida | p2 | `corrida` | `22332212` | `22332212` | `22331212` |
| Corrida | p2 | `corrida-nova` | `23231–32` | `23231–32` | `23130–32` |
| Corrida | p2 | `corrida-com-registro` | `22332–22` | `22332–22` | `22331–22` |
| Corrida | p3 | `corrida` | `22332212` | `22332212` | `22331212` |
| Progresso | p1 | `progresso` | `22223–11` | `22223–11` | `12222–11` |
| Progresso | p2 | `progresso` | `22233211` | `22233211` | `12232211` |
| Progresso | p3 | `progresso` | `22233211` | `22233211` | `12232211` |
| Conquistas | p1 | `conquistas` | `22131–31` | `22131–31` | `22130–31` |
| Conquistas | p2 | `conquistas` | `22132111` | `22132111` | `22131111` |
| Conquistas | p3 | `conquistas` | `22132331` | `22132331` | `22131331` |
| Histórico (exercícios que já fiz) | p1 | `historico-exercicios` | `22333–32` | `22333–32` | `22333–32` |
| Histórico (exercícios que já fiz) | p2 | `historico-exercicios` | `22332222` | `22332222` | `22230222` |
| Histórico (exercícios que já fiz) | p3 | `historico-exercicios` | `22333232` | `22333232` | `22331232` |
| Conta · Mais | p1 | `conta-areas` | `33333333` | `33333333` | `33333333` |
| Conta · Mais | p2 | `conta-areas` | `33333333` | `33333333` | `33333333` |
| Conta · Mais | p3 | `conta-areas` | `33333333` | `33333333` | `33333333` |
| Conta · Perfil | p1 | `conta-perfil` | `11232–12` | `11232–12` | `11232–12` |
| Conta · Perfil | p2 | `conta-perfil` | `11232–12` | `11232–12` | `11232–12` |
| Conta · Perfil | p3 | `conta-perfil` | `11232–12` | `11232–12` | `11232–12` |
| Ajuda | anon | `ajuda` | `12031–31` | `12031–31` | `12031–31` |
| Ajuda | p1 | `ajuda-logado` | `22031–31` | `22031–31` | `12030–31` |
| /demo/ | anon | `demo` | `21131–22` | `21131–22` | `21130–22` |

Duas leituras que a matriz dá e o mapa não: **claro e escuro tiram a mesma
nota em tudo** (o Papel é uma tradução fiel do Ferro — a única diferença de
contraste é o dia "pulado"); e **o desktop derruba Composição em seis telas**
(Landing, Onboarding 1 e 2, Treino, Progresso, Ajuda) e só a sobe na
execução — onde a coluna larga devolve ao campo de carga a largura que falta
a 390.

## 12. As contas, e a prova de que sumiram

| conta | criada por | apagada por | no banco depois | login de novo |
|---|---|---|---|---|
| `qa-av-abc-20260927@nutriplan.invalid` (P1) | cadastro público local + 3 etapas pela tela | `/conta/excluir/`, com a senha | não | recusado, "E-mail ou senha" |
| `qa-av-corre-20260927@nutriplan.invalid` (P2) | idem | idem | não | recusado |
| `qa-av-casa-20260927@nutriplan.invalid` (P3) | idem | idem | não | recusado |
| `qa-av-abc2-…`, `qa-av-abc3-…` (P1b, P1c — refazer o placar) | idem | idem | não | recusado |

`[EXECUTADA]` As senhas foram geradas no script, guardadas num arquivo do
scratchpad durante a execução e apagadas no fim; nenhuma aparece aqui. O
banco `nutriplan_auditoria` é local e não tem dado de ninguém.

## 13. Onde está o material

Local, fora do Git (`achados/capturas/` é ignorado): as 236 capturas, a
medição de cada uma (`.json`) e o axe (`.axe.json`) em
`achados/capturas/auditoria-visual-20260927/<grupo>/<tela>__<vista>.*`; o
harness em `_harness/` (`auditar.py` percorre as personas, `medir.js` mede a
página, `estatico.py` lê o fonte, `agregar.py` e `notas.py` fazem as tabelas;
`inventario.txt`, `componentes.txt` e `metricas.txt` são as saídas brutas
citadas acima).
