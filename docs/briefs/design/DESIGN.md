# NutriPlan — DESIGN.md (contrato visual: direção NERVURA · ANDAIME)

Este arquivo é a fonte da verdade dos tokens e das regras. O que está aqui
não é sugestão: é decisão tomada e medida (contrastes recalculados por
teste em `config/tests.py` e por `scripts/qa/auditar_contraste.py`). Se
algo faltar, pergunte; não invente.

Reescrito em 17/09/2026 a partir da direção **NERVURA** (Direção 1 do
Claude Design), escolhida pelo dono do produto por veto em
[`DIRECAO-ESCOLHIDA.md`](DIRECAO-ESCOLHIDA.md) — a base é o arquivo
`Direcao1-a`; do `Direcao1-b` entrou só o que pontua mais em identidade e
em execução/recompensa, item a item, na tabela daquele documento. A spec
anterior (CORTE, 16/09) sobrevive na seção **"Mantido da spec anterior"** —
e só ali. O que não está lá, saiu.

## Identidade

- **O que é:** PWA mobile-first, em português do Brasil, de alimentação,
  treino, corrida, hidratação e progresso — cinco pilares no mesmo nível.
  "Hoje" é o orquestrador do dia, não um pilar; Perfil é utilitário.
- **A ideia:** a folha da marca vira a NERVURA — uma régua diagonal a −14°
  que atravessa o número que manda na tela, sublinha o rótulo de seção e
  risca o placar do treino fechado. Tudo o mais é ANDAIME: réguas retas de
  2 px, quina reta, caixa alta condensada, verde-neon sobre o preto
  esverdeado da academia à noite. Atletismo brutalista: nada é caixa, tudo
  é régua e número. Tampe o nome e ainda é o NutriPlan pela diagonal e
  pela ponta de folha (o triângulo) que marca onde a barra chegou.
- **Navegação:** barra inferior de QUATRO itens (Alimentação · Treino ·
  Progresso · Áreas) — medida a 320 px; cinco não cabem. A aba ativa é
  ícone e rótulo em `--brand`, sem preenchimento. No desktop a barra de
  cima leva os mesmos quatro links. **A navegação não muda.**
- **Tom:** direto, adulto, sem promessa. O NÚMERO é o protagonista de toda
  tela que mede — kg, séries, minutos, kcal, litros. Nada de texto
  motivacional genérico; recompensa é o número crescendo, não um adjetivo.
- **A marca** (`icon-192.png`) é arte rasterizada aprovada; não se redesenha.
  O wordmark é "NutriPlan", uma palavra, com "Plan" em `--brand`.

## Dois regimes, e o escuro é a base

**Ferro** (escuro) é o padrão: palco `#050907`, chão `#0B140F`, verde-neon
`#43DF7A` como única cor de ação, laranja `#E8A33D` só para a CARGA.
**Papel** (claro) é DERIVADO dele para quem prefere claro no sistema
(`prefers-color-scheme: light`): chão `#F4F6F2`, verde-floresta `#106632`
no lugar do neon (o neon não é texto sobre claro). A execução do treino e a
corrida em andamento nascem em Ferro SEMPRE — `modo-foco`, classe que o
servidor escreve no `<html>` (`:root.modo-foco`), força o escuro por cima
da preferência. No `<html>`, e não no `<body>`: `--glass`, `--glow` e
`--halo` são receitas de `var()` do `:root` e resolvem onde são declaradas.

Estrutura no CSS (a mesma da CORTE): os valores moram UMA vez em
`--ferro-*` e `--papel-*` no `:root`; o `:root` mapeia `--x:
var(--ferro-x)`; `@media (prefers-color-scheme: light)` remapeia `--x:
var(--papel-x)`; `:root.modo-foco` remapeia de volta para `var(--ferro-x)`.
Nenhum hex fora das duas listas — `config/test_ferro.py` é a trava.

## Tokens de cor — nomes do app, valores da direção

Os NOMES são os que o `app.css` e os testes já usam (`--bg`, `--surface`…);
a coluna "papel na direção" diz como a NERVURA chama a mesma coisa. A
direção define dez cores; as outras são DERIVADAS e medidas
(`artifacts/paleta_nervura.py`, com os ajustes registrados).

| token | Ferro (padrão) | Papel (claro) | papel na direção |
|---|---|---|---|
| `--bg` | `#0B140F` | `#F4F6F2` | `--fundo`: o chão |
| `--canvas-topo` | `#050907` | `#E7EBE3` | `--palco`: o topo do gradiente do body |
| `--surface` | `#121E17` | `#E7EBE3` | `--fundo-2`: a faixa/seção |
| `--surface-2` | `#202F25` | `#DCE2DA` | agrupamento dentro da faixa (campo, chip, célula). A direção não tem terceiro degrau; este veio da régua U28 (≥ 1,2:1 sobre `--surface`; medido 1,22) |
| `--surface-3` | `#283C30` | `#D0D8CE` | hover; célula vazia (1,19 sobre a segunda) |
| `--surface-focus` | `#123120` | `#DDEFE2` | UMA por tela: a refeição da vez, a série da vez (`--brand` a ~10 %) |
| `--fio` | `rgba(169,187,174,.14)` | `rgba(11,20,15,.14)` | `--linha`: a régua de 1 px; sobre `--bg` dá o `#1E3326` da direção |
| `--fio-forte` | `rgba(169,187,174,.30)` | `rgba(11,20,15,.30)` | `--linha-forte`: o traço de 2 px de botão de contorno, chip e régua de seção (`#2C4A37`) |
| `--text` | `#F2F6F2` | `#0B140F` | `--tinta` |
| `--text-dim` | `#C9D6CC` | `#2E3F34` | apoio |
| `--text-mute` | `#A9BBAE` | `#46584B` | `--tinta-2`: rótulo, legenda (≥ 5,0:1 no pior fundo neutro) |
| `--brand` | `#43DF7A` | `#106632` | `--acento`: AGIR — CTA, link, aba ativa, foco, a nervura. No claro é verde-floresta (o `#106B32` da direção escureceu 4 % para 4,5:1 sobre a própria tinta) |
| `--brand-strong` | `#6AEB97` | `#0C5427` | só `:active`/hover |
| `--brand-soft` | `#0F2E1B` | `#D6EEDD` | tinta da ação: chip, botão tonal, trilha cheia |
| `--on-brand` | `#06240F` | `#FFFFFF` | `--sobre-acento`: texto sobre `--brand` |
| `--folha` | `#33C96A` | `#1D833F` | FEITO (série registrada, ✓, arco cheio) — o neon um tom para dentro; derivado, a direção tem um verde só |
| `--terra` | `#E8A33D` | `#814C10` | `--carga`: a CARGA (kg) e o pilar Progresso/peso (o `#8A5510` do claro escureceu 5 %) |
| `--brasa` | `#FF8E6E` | `#9E3E1A` | pilar Corrida (derivado) |
| `--agua` / `--agua-texto` | `#7CC7EA` | `#1E6E96` / `#175877` | pilar Hidratação (objeto / texto pequeno; derivado) |
| `--chama` | `#F2B04E` | `#9A6210` | ofensiva, só objeto gráfico (derivado) |
| `--carb` | `#E8A33D` | `#814C10` | macro carboidrato (= a carga) |
| `--fat` | `#A9BBAE` | `#46584B` | macro gordura (= o mudo) — proteína é `--brand` |
| `--danger` / `--danger-soft` | `#FF7A70` / `#3A1A18` | `#B1261E` / `#FDECEA` | erro, ação destrutiva |
| `--terra-soft` | `#3A2A10` | `#F3E6D0` | tinta da carga |
| `--dia-a` … `--dia-e` | `#4ADE9B` `#70C9FF` `#F6C453` `#CDB2FF` `#FFA998` | `#1C5E3E` `#225874` `#704B21` `#5F1ED0` `#8B3729` | cor de sessão no painel de treino (os de antes; no claro moveram 1–2 % para 4,5 sobre a própria tinta sobre o `--brand-soft` novo) |
| `--veu` | `rgba(4,8,7,.72)` | idem | fundo de modal |

Medido antes de virar contrato: todo texto × todo fundo ≥ 4,5:1 nos dois
regimes, `--text-dim`/`--text-mute` ≥ 5,0 nos fundos neutros, todo objeto
gráfico × superfície ≥ 3:1, chips de dia e pílulas sobre a própria tinta
≥ 4,5; piores pares: Ferro `--danger`/`--surface-3` 4,65, Papel
`--danger`/`--surface-3` 4,55. A auditoria de 274 pares roda de novo sobre
o CSS real na implementação e é gate de cada PR.

**A regra de três** continua: cor de pilar aparece em pelo menos TRÊS
lugares da área (régua, arco/coluna, ponto do ícone) e em NENHUM botão.
**Um verde só age**: `--brand` é AGIR e `--folha` é FEITO; nenhum outro
verde. Foco é `--brand` em todo controle, anel com vão.

## A quina reta e a nervura — os raios

A direção não tem raio: **zero `border-radius` em 390 declarações do
mockup**. A quina é reta, a régua é de 2 px, e o que é curvo é só o
círculo do anel de progresso (que fica). Os tokens:

- `--quina-g: 0`, `--quina: 0`, `--quina-p: 0` — os três degraus (prato /
  cartão-botão-campo / chip-célula) ficam como SLOTS, com o mesmo valor:
  um degrau só de cada vez pode voltar a ter raio numa direção futura sem
  mexer em regra nenhuma. `--pill` saiu: barra, trilha, ponto e selo são
  quadrados também (o ponto do macro é um quadrado de 8 px);
- `--traco: 2px` — a espessura das réguas: borda de botão de contorno e de
  chip, a régua sob o rótulo de seção, a régua da carga, a nervura;
- `--nervura: -14deg` — a diagonal. Um elemento de `height: var(--traco)`,
  `background: var(--brand)`, `transform: rotate(var(--nervura))`, com
  `transform-origin` na ponta de onde ela nasce. É decoração
  (`aria-hidden`), nunca o único sinal de estado;
- `--inclinado: polygon(0 0, 100% 0, 100% 74%, 0 100%)` — o CTA inclinado:
  a variante do botão primário em que a base sobe para a direita (a
  mesma inclinação que a nervura sugere). O `clip-path` vai no
  pseudo-elemento de fundo, NÃO no botão: o retângulo de 48 px continua
  sendo a área de toque e é ele que recebe o anel de foco;
- `--ponta: polygon(0 100%, 100% 0, 100% 100%)` — a ponta de folha: o
  triângulo em `--brand` que marca onde a barra de progresso chegou e que
  pousa no canto do placar da recompensa.

Mídia (vídeo, foto do exercício) é retângulo reto com uma régua de
`--traco` em `--fio-forte` em cima.

## Tipografia — duas fontes, com regra de uso

- **Display: Big Shoulders Display** (variável, `wght` 100–900; condensada,
  feita para caixa alta). Só para o que é HERÓI: título de tela, o nome
  da refeição/do exercício/da sessão, o número grande (kcal, kg, séries,
  minutos, %). Títulos e nomes em **caixa alta** (`text-transform:
  uppercase`), 800; o número grande em 900. **Nunca abaixo de 20 px.**
- **Medido com fontTools: a Big Shoulders NÃO tem `tnum`, e os dígitos são
  proporcionais** ("1" 316/2000 contra "0" 596). Por isso a display fica
  para o NÚMERO SOLTO — um por bloco, nunca em coluna. Toda coluna de
  números (a lista de pesagens, séries × reps, tabelas, tiles lado a lado
  com casas diferentes) é Archivo com `tabular-nums`. O número que CONTA
  (calorias, recompensa) reserva a largura em `ch` para não tremer.
- **Texto: Archivo** (variável, `wght` 100–900; tem `tnum`). Corpo,
  rótulo, legenda, lista, e TODO número pequeno — com
  `font-variant-numeric: tabular-nums` e vírgula decimal ("62,50",
  "2.100 kcal").
- Arquivos: auto-hospedados em `static/fonts/` (woff2, subconjunto latin do
  Google Fonts, `font-display: swap`, OFL ao lado), com gate de tamanho no
  teste: **≤ 260 KB no total** — medido em 17/09/2026: 70 364 bytes
  (`config/test_fontes.py`). Sem `<link>` para o Google em produção. O
  service worker pré-cacheia as duas.
- Escala (rem, piso 11 px): xs .7 (11,2) · sm .8 · md .9 · base 1 · lg 1.15 ·
  xl 1.4 · 2xl 1.75 · 3xl 2.15 · display 3.1 (49,6) · herói 4.5 (72). O
  título de tela é 2xl em caixa alta condensada (a condensada faz 28 px
  parecer 22 de largura — é por isso que a NERVURA cabe "LANCHE DA MANHÃ"
  numa linha a 390); o herói é o MAIOR objeto de toda tela que mede.
- Pesos: Archivo 400 · 500 · 600 · 700; Big Shoulders 800 · 900. Seis, e a
  lista é fechada (`config/test_fontes.py`).

## Rótulos de seção

O sobretítulo da NERVURA é o que abre cada bloco: **caixa alta, Archivo
600, 11–12 px, `letter-spacing: .16em`**, em `--brand` quando é o rótulo
do bloco que manda ("AGORA · 11:00", "EXERCÍCIO 3/7 · TREINO B") e em
`--text-mute` nos demais ("PROTEÍNA", "CARGA", "REPETIÇÕES"). Quem o
segue é o herói. O piso de 11 px vale para ele também (o mockup desceu a
10; a implementação sobe). Sob o rótulo do bloco que manda vai a régua
de `--traco` em `--fio-forte` ou a nervura — nunca as duas.

## Espaço, sombra, camadas, movimento

- Grade de 4 px. Alvo da direção: `--e1…e7` = 4 · 8 · 12 · 16 · 24 · 32 · 48.
  **O CSS de hoje ainda roda os sete degraus fracionários** (4 · 5,6 · 8 ·
  11,2 · 14,4 · 16 · 24) e 243 valores crus; o remap move pixel em toda tela
  e é lote próprio com captura antes/depois (decisão do dono, 16/09). Ao
  desenhar, use a grade da direção; ao ler o app, saiba que ele ainda está
  na antiga.
- **Sem cartão com sombra.** `--shadow-rest`, `--shadow-lift`, `--shadow-deep`
  e `--edge` não desenham nada (`0 0 0 0 transparent`, não `none`, que não
  entra em lista de `box-shadow`); os nomes ficam. Hierarquia é por
  tipografia, cor e RÉGUA: a seção abre com uma régua de `--traco` em
  `--fio`, o bloco que manda com a nervura. `--inlay` (contorno por
  dentro) continua para o bloco afundado. `--veu` continua para o modal.
- Camadas (z-index), de baixo para cima: conteúdo → barra de cima →
  flutuante → navegação → aviso → bloqueio. Nada cobre a barra de baixo.
- Movimento com intenção — os `--mov-*` de sempre (toque .1 s, estado
  .18 s, expansão .25 s, tela .2 s, modal .28 s, sucesso .5 s, passo 6 px)
  mais **`--mov-nervura: .6s`** (a régua que risca) e **`--mov-cascata:
  .08s`** (o degrau entre os números do placar), e três momentos que se
  movem:
  - **registrar refeição**: a régua da linha da refeição ACENDE — de
    `--fio` a `--brand`, da esquerda para a direita, em `--mov-nervura`
    (`nervura-acende`);
  - **bater meta** (água, calorias): a nervura do bloco risca de novo e o
    número cresce UMA vez (`numero-cresce`, `--mov-sucesso`);
  - **última série do treino**: a tela vira placar — a nervura risca da
    base à ponta (`--mov-nervura`), o total de carga conta de 0 ao valor
    (`--mov-nervura`, mesma curva), os três números entram em sequência
    (`--mov-cascata` entre eles) e a ponta de folha pousa no canto; os
    botões só aparecem no fim, sem animação. Total 1,0 s — depois a tela
    fica quieta até o toque.
  Nada mais se move. `prefers-reduced-motion` desliga tudo, inclusive as
  view transitions: o frame final aparece pronto.

## Regras de interface

- Alvo de toque **44 × 44 px** (altura E largura); botão padrão 48 px
  (`--alvo`). Texto ≥ 11 px.
- Nada rola na horizontal; todo contêiner de texto tem `min-width: 0`.
- Uma superfície de foco por tela. Um botão primário por tela — e é ele
  que leva a inclinação; contorno e quieto são retângulos de `--traco`.
- Foco é `--brand` em todo controle: anel de 2 px com `outline-offset: 2px`
  (vão) sobre opção marcada; borda + anel de 1 px no campo; campo inválido
  em foco fala só `--danger`.
- Estado vazio é convite (o que fazer a seguir), não constatação.
- Ações destrutivas ("zerar", "excluir conta") são secundárias, separadas e
  pedem confirmação.
- Número herói: Big Shoulders 900, unidade colada em Archivo a 12,8/600
  `--text-dim` na mesma linha de base; a CARGA é o único herói em
  `--terra`.

## Componentes que já existem (não recriar; refinar)

`card` é a SEÇÃO: `--surface`, sem sombra, quina reta, régua de `--traco`
em `--fio` no topo; o prato (o AGORA) leva a nervura em vez da régua ·
`btn` (`--primary` `--brand` cheio e INCLINADO; `--ghost` contorno de
`--traco` em `--fio-forte`; `--quiet`; `--perigo`; `--sm`; `--block`;
todos retos; uma escala de toque, `.96`) · `chip` / `chip-row` (quadrado,
contorno de `--traco`, caixa alta .16em; o escolhido cheio de `--brand`)
· `pill` (selo quadrado em `--brand-soft`/`--terra-soft`; só selo) · `tile`
/ `tiles` (número grande em Big Shoulders 900 + rótulo em caixa alta +
meta em Archivo) · `data-list` (`dt`/`dd`) · `empty-state` · `hint` ·
`field` (rótulo em caixa alta, ajuda, erro; campo reto com régua embaixo
em `--fio-forte`, que vira `--brand` no foco; rádios e caixas quadrados)
· `choice_cards` (rádio como caixa de contorno com o visto quadrado) ·
`marca` e `marca_de_entrada` · `_conquista` (aviso ancorado embaixo, não
modal) · anel de progresso (calorias, água, treino: trilha em `--fio`, arco
em `--folha` — o círculo é a única curva) · barra de progresso (reta, com
a ponta de folha no fim do preenchido) · `tabbar` (quatro itens; a ativa
em `--brand`, sem preenchimento) · `app-bar` (marca à esquerda; no
desktop, os quatro links).

## As sete telas do contrato

Entrar · Hoje · Dieta (refeição aberta com opções A e B) · Ficha com duas
opções · Execução (UM exercício; Ferro sempre) · Progresso · **Frame de
recompensa** (a última série do treino — a tela vira placar: "TREINO B
FECHADO", total de carga em `--brand`, séries, minutos, vs. última, o
recorde; "VER RESUMO DO TREINO" inclinado, "Voltar para Hoje" contorno).
Referência visual: os mockups da direção em
`artifacts/claude-design/export/direcoes/Direcao1-{a,b}.dc.html` e as
capturas em [`referencias/claude-design/`](referencias/claude-design/) e
[`referencias/direcoes/`](referencias/direcoes/).

## O que este app não faz

Gradiente roxo; cartão branco com sombra; vidro (`backdrop-filter`) além da
moldura do app; ícone-emoji na interface; Material Symbols; `:has()` em
regra que decide layout; animação decorativa; cinco abas; tela de login
com só logo, campos e botão; "painel administrativo" de números iguais ao
texto; neon como TEXTO sobre claro (no claro a ação é verde-floresta);
canto arredondado em botão, campo, chip ou cartão; pílula.

## Mantido da spec anterior (CORTE, direção 2 — e o que ela herdou)

O que sobrevive, e por quê:

- os cinco pilares, "Hoje" fora deles, Perfil utilitário; a barra de
  QUATRO itens medida a 320 px; o mapa em `<details>` continua aposentado;
- os NOMES dos tokens do app (`--bg`, `--surface`, `--brand`, `--folha`,
  `--agua`, `--brasa`, `--terra`, `--chama`, `--carb`, `--fat`, `--fio`,
  `--fio-forte`, `--dia-*`, `--mov-*`, `--camada-*`) — mudam os valores, não
  os fios que os testes seguram;
- **Ferro é a base, Papel o derivado, `:root.modo-foco` força Ferro** — a
  estrutura das duas listas e dos três gatilhos, e a execução escrevendo
  a classe no `<html>`;
- duas fontes auto-hospedadas com gate de peso, `font-display: swap`,
  pré-cacheadas pelo service worker; a display só ≥ 20 px e só em herói;
- o sprite de 13 símbolos, traço 2 em CADA `<symbol>`, grade 24, uma vez por
  página e fora do shell offline (`config/test_sprite.py`);
- WCAG AA em todo par, com a margem de 5,0 para `--text-dim`/`--text-mute`,
  a régua U28 da escada de superfícies e a auditoria de 274 pares no CSS
  real;
- alvo 44 × 44; texto ≥ 11 px; `tabular-nums` e vírgula decimal; nada rola
  na horizontal; `min-width: 0`;
- tudo em token e as catracas de valor cru (`config/test_design_system.py`),
  que só descem; os três slots de quina (`--quina-g`/`--quina`/`--quina-p`
  no lugar de `--corte-g`/`--corte`/`--corte-p`) e "nada clicável é
  pílula" (agora nada é pílula);
- os `--mov-*` com `prefers-reduced-motion` desligando tudo, o `<details>`
  animado por JS, `view-transition-name` único por documento, uma escala
  de toque (`.96`) numa lista só; `--mov-cascata` de 80 ms;
- o placar do treino fechado (`services.Placar`: carga total, vs. última,
  recorde — contagem sobre o que a tela já tinha) e os dois botões dele;
  muda a pele, não a conta;
- foco na cor da ação com vão; campo inválido fala; um primário e uma
  superfície de foco por tela; estado vazio é convite;
- a vitrine em `/gestao/vitrine/` (`?regime=ferro` força o Ferro; o Papel
  se fotografa com `scripts/qa/nav.py tema claro`) e o teste que lê a
  pasta de parciais; `nav.py movimento normal|reduzido` para fotografar
  movimento;
- `--agua`, `--brasa`, `--terra`, `--chama` como cores de pilar com a regra
  de três; `--brand` AGIR e `--folha` FEITO;
- "Disciplina hoje. Resultados amanhã.", "Bom te ver de volta", "Você",
  nunca "nós".

O que SAIU com a direção: a folha como recorte (`--corte*`, 0/20/0/20 e
irmãos); Bodoni Moda e Karla; a folha-lima da recompensa (`folha-sobe`),
`corte-abre` e `corte-desdobra`; a lima `#C7F24A` e o osso `#F6F3EA`; o
prato com `--corte-g`; a aba ativa como folha cheia; `--pill`.
