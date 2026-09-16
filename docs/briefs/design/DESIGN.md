# NutriPlan — DESIGN.md (contrato visual: direção CORTE)

Este arquivo é a fonte da verdade dos tokens e das regras. O que está aqui
não é sugestão: é decisão tomada e medida (contrastes recalculados por
teste em `config/tests.py` e por `scripts/qa/auditar_contraste.py`). Se
algo faltar, pergunte; não invente.

Reescrito em 16/09/2026 a partir da direção **CORTE**, proposta pelo Claude
Design e escolhida por critério em [`DIRECAO-ESCOLHIDA.md`](DIRECAO-ESCOLHIDA.md)
(veto do dono pendente). A spec anterior (Mesa & Ferro, direção C) sobrevive
na seção **"Mantido da spec anterior"** — e só ali. O que não está lá, saiu.

## Identidade

- **O que é:** PWA mobile-first, em português do Brasil, de alimentação,
  treino, corrida, hidratação e progresso — cinco pilares no mesmo nível.
  "Hoje" é o orquestrador do dia, não um pilar; Perfil é utilitário.
- **A ideia:** a silhueta da folha da marca — ponta em duas esquinas
  opostas, curva nas outras duas — vira o FORMATO de tudo: botão, campo,
  chip, mídia, faixa. Cada peça da tela é uma folha pequena. Editorial e
  quente: revista de cozinha que também sabe puxar barra. Tampe o nome e
  ainda é o NutriPlan.
- **Navegação:** barra inferior de QUATRO itens (Alimentação · Treino ·
  Progresso · Áreas) — medida a 320 px; cinco não cabem. A aba ativa é uma
  folha (recorte) cheia de `--brand`. No desktop a barra de cima leva os
  mesmos quatro links. **A navegação não muda.**
- **Tom:** direto, adulto, sem promessa. O NÚMERO é o protagonista de toda
  tela que mede — kg, séries, minutos, kcal, litros. Nada de texto
  motivacional genérico; recompensa é o número crescendo, não um adjetivo.
- **A marca** (`icon-192.png`) é arte rasterizada aprovada; não se redesenha.
  O wordmark é "NutriPlan", uma palavra, com "Plan" em `--brand`.

## Dois regimes, e o escuro é a base

**Ferro** (escuro) é o padrão: luz baixa de academia, papel escuro
(`#10120E`), lima como única cor de ação. **Papel** (claro) é DERIVADO dele
para quem prefere claro no sistema (`prefers-color-scheme: light`): osso
(`#F6F3EA`), oliva no lugar da lima. A execução do treino e a corrida em
andamento nascem em Ferro SEMPRE — `body.modo-foco`, escrito pelo servidor,
força o escuro por cima da preferência.

Estrutura no CSS (muda em relação à spec anterior, onde o claro era a
base): os valores moram UMA vez em `--ferro-*` e `--papel-*` no `:root`; o
`:root` mapeia `--x: var(--ferro-x)`; `@media (prefers-color-scheme: light)`
remapeia `--x: var(--papel-x)`; `body.modo-foco` remapeia de volta para
`var(--ferro-x)`. Nenhum hex fora das duas listas — `config/test_ferro.py`
é a trava.

## Tokens de cor — nomes do app, valores da direção

Os NOMES são os que o `app.css` e os testes já usam (`--bg`, `--surface`…);
a coluna "papel na direção" diz como a CORTE chama a mesma coisa.

| token | Ferro (padrão) | Papel (claro) | papel na direção |
|---|---|---|---|
| `--bg` | `#10120E` | `#F6F3EA` | `--fundo`: o chão |
| `--canvas-topo` | `#080A07` | `#FBF9F2` | a luz do topo (gradiente do body) |
| `--surface` | `#1A1D17` | `#EAE5D6` | `--fundo-2`: a FAIXA de borda a borda que substitui o cartão |
| `--surface-2` | `#22261E` | `#E1DBC8` | agrupamento dentro da faixa (campo, chip, célula) |
| `--surface-3` | `#2B3025` | `#DBD6C6` | hover; célula vazia de gráfico |
| `--surface-focus` | `#232A12` | `#EEF3D8` | UMA por tela: a refeição da vez, a série da vez (lima a 12 %) |
| `--fio` | `rgba(246,243,234,.10)` | `rgba(20,24,10,.12)` | `--linha`: a régua de 1 px que separa |
| `--fio-forte` | `rgba(246,243,234,.22)` | `rgba(20,24,10,.26)` | `--linha-forte`: borda de campo e de botão de contorno |
| `--text` | `#F6F3EA` | `#14180A` | `--tinta` (osso / tinta) |
| `--text-dim` | `#D6D2C4` | `#3E3F30` | apoio |
| `--text-mute` | `#B3AE9C` | `#54523F` | `--tinta-2`: rótulo, legenda (≥ 5,0:1 no pior fundo neutro) |
| `--brand` | `#C7F24A` | `#3F5A00` | `--acento`: AGIR — CTA, link, aba ativa, foco. Lima no escuro; OLIVA no claro (a lima não é texto sobre osso) |
| `--brand-strong` | `#DBFF6E` | `#2F4400` | só `:active`/hover |
| `--brand-soft` | `#2A3313` | `#E6EFC4` | tinta da ação: chip, botão tonal, trilha cheia |
| `--on-brand` | `#14180A` | `#F6F3EA` | `--sobre-acento`: texto sobre `--brand` |
| `--folha` | `#9BD130` | `#4E7A00` | FEITO (série registrada, ✓, arco cheio) — a lima um tom para dentro |
| `--terra` | `#D98E64` | `#7E4320` | `--argila`: a CARGA (kg) e o pilar Progresso/peso |
| `--brasa` | `#E8865E` | `#983B17` | pilar Corrida |
| `--agua` / `--agua-texto` | `#7CC7EA` | `#1E6E96` / `#175877` | pilar Hidratação (objeto / texto pequeno) |
| `--chama` | `#F2B04E` | `#9A5A10` | ofensiva, só objeto gráfico |
| `--carb` | `#D98E64` | `#7E4320` | macro carboidrato (a argila) |
| `--fat` | `#B3AE9C` | `#54523F` | macro gordura (o mudo) — proteína é `--brand` |
| `--danger` / `--danger-soft` | `#FF8A80` / `#3A1E1C` | `#A9241C` / `#FDECEA` | erro, ação destrutiva |
| `--terra-soft` | `#3A2A1A` | `#F3E6D6` | tinta da carga |
| `--dia-a` … `--dia-e` | `#4ade9b` `#6cc7ff` `#f6c453` `#cbb0ff` `#ff9d8a` | `#1c6141` `#225b77` `#734e21` `#621fd6` `#8e3a29` | cor de sessão no painel de treino (inalterado) |
| `--veu` | `rgba(4,8,7,.72)` | idem | fundo de modal |

Medido antes de virar contrato (`artifacts/paleta_corte.py`): todo texto ×
todo fundo ≥ 4,5:1 nos dois regimes, `--text-dim`/`--text-mute` ≥ 5,0 nos
fundos neutros, todo objeto gráfico × superfície ≥ 3:1; piores pares: Ferro
`--brasa`/`--brand-soft` 5,06, Papel `--brasa`/`--surface-3` 4,86. A
auditoria de 274 pares roda de novo sobre o CSS real na implementação.

**A regra de três** continua: cor de pilar aparece em pelo menos TRÊS
lugares da área (fio da faixa, arco/coluna, ponto do ícone) e em NENHUM
botão. **Um verde só age**: `--brand` é AGIR e `--folha` é FEITO; nenhum
outro verde. Foco é `--brand` em todo controle, anel com vão.

## O recorte — os raios

A folha é o token de raio. Quatro valores, assimétricos, e são eles que
substituem a escala 24/16/12/8:

- `--corte: 0 20px 0 20px` — botão, campo, chip, mídia, faixa de refeição,
  linha de exercício;
- `--corte-g: 0 40px 0 40px` — o prato/hero (o AGORA, o resumo do dia), a
  folha do frame de recompensa;
- `--corte-p: 0 12px 0 12px` — chip pequeno, célula, selo de opção;
- `--pill: 999px` — SÓ o ponto e o selo circular; nada clicável é pílula.

Ordem dos quatro valores: superior-esquerda 0 · superior-direita R ·
inferior-direita 0 · inferior-esquerda R — ponta em cima à esquerda e
embaixo à direita, como a folha do logo. Raio idêntico nos dois regimes.
Mídia (vídeo, foto do exercício) usa a mesma máscara. **O número da
recompensa nasce DENTRO da folha**, nunca cortado por ela (defeito do
mockup, não do contrato).

## Tipografia — duas fontes, com regra de uso

- **Display: Bodoni Moda** (variável; `opsz` 6–96, `wght` 400–900, itálica).
  Só para o que é HERÓI: títulos de tela, o nome da refeição/exercício, o
  número grande (kcal, kg, séries, minutos, %). **Nunca abaixo de 20 px** —
  didone tem fio fino que some em tela de baixa densidade, e não tem
  numeral tabular. O número grande usa `opsz` alto e `wght` 500–700.
- **Texto: Karla** (400, 500, 600, 700). Corpo, rótulo, legenda, lista, e
  TODO número pequeno — com `font-variant-numeric: tabular-nums` e vírgula
  decimal ("62,50", "2.100 kcal"). Colunas de série/carga alinham em Karla,
  não em Bodoni.
- Arquivos: auto-hospedados em `static/fonts/` (woff2, subconjunto latin,
  `font-display: swap`), com gate de tamanho no teste: **≤ 260 KB no total**
  (T3.2 do plano mestre). Sem `<link>` para o Google em produção; o `<link>`
  do mockup é só do mockup.
- Escala (rem, piso 11 px): xs .7 (11,2) · sm .8 · md .9 · base 1 · lg 1.15 ·
  xl 1.4 · 2xl 1.75 · 3xl 2.15 · display 3.1 (49,6) · herói 4.5 (72). O
  título nunca passa de 28; o herói é o MAIOR objeto de toda tela que mede.
- Rótulos e sobretítulos em CAIXA ALTA com `letter-spacing: .14em`, em
  Karla 600 a 11–12 px. O piso de 11 px vale para eles também (o mockup
  desceu a 10; a implementação sobe).
- Pesos: quatro (400 · 500 · 600 · 700) em Karla; os degraus sintéticos
  (620/650/680/720/750/780) saem com a fonte própria.

## Espaço, sombra, camadas, movimento

- Grade de 4 px. Alvo da direção: `--e1…e7` = 4 · 8 · 12 · 16 · 24 · 32 · 48.
  **O CSS de hoje ainda roda os sete degraus fracionários** (4 · 5,6 · 8 ·
  11,2 · 14,4 · 16 · 24) e 244 valores crus; o remap move pixel em toda tela
  e é lote próprio com captura antes/depois. Ao desenhar, use a grade da
  direção; ao ler o app, saiba que ele ainda está na antiga.
- **Sem cartão com sombra.** `--shadow-rest`, `--shadow-lift` e `--edge`
  valem `none`; os nomes ficam (há teste que os lê) e a semântica muda:
  hierarquia é por tipografia, cor e FAIXA (`--surface` de borda a borda) —
  não por caixa. `--inlay` (contorno por dentro) continua para o bloco
  afundado. `--veu` continua para o modal.
- Camadas (z-index), de baixo para cima: conteúdo → barra de cima →
  flutuante → navegação → aviso → bloqueio. Nada cobre a barra de baixo.
- Movimento com intenção — os `--mov-*` de sempre (toque .1 s, estado
  .18 s, expansão .25 s, tela .2 s, modal .28 s, sucesso .5 s, passo 6 px)
  mais **`--mov-recompensa: .45s`**, e três momentos que se movem:
  - **registrar refeição**: o corte "abre" — a esquina reta vira curva por
    `--mov-estado` e volta (`corte-abre`);
  - **bater meta** (água, calorias): a esquina superior se desdobra e o
    número cresce UMA vez (`corte-desdobra`, `--mov-recompensa`);
  - **última série do treino**: a folha-lima sobe do canto inferior direito
    e ocupa a tela em `--mov-recompensa`; o total de carga conta do zero em
    `--mov-sucesso`; os três números (séries, minutos, vs. última) entram
    em cascata de 80 ms; os botões chegam parados. Total 1,0 s — depois a
    tela fica quieta até o toque.
  Nada mais se move. `prefers-reduced-motion` desliga tudo, inclusive as
  view transitions: o frame final aparece pronto.

## Regras de interface

- Alvo de toque **44 × 44 px** (altura E largura); botão padrão 48 px
  (`--alvo`). Texto ≥ 11 px.
- Nada rola na horizontal; todo contêiner de texto tem `min-width: 0`.
- Uma superfície de foco por tela. Um botão primário por tela.
- Foco é `--brand` em todo controle: anel de 2 px com `outline-offset: 2px`
  (vão) sobre opção marcada; borda + anel de 1 px no campo; campo inválido
  em foco fala só `--danger`.
- Estado vazio é convite (o que fazer a seguir), não constatação.
- Ações destrutivas ("zerar", "excluir conta") são secundárias, separadas e
  pedem confirmação.
- Número herói: `tabular-nums`, vírgula decimal, unidade colada em Karla a
  12,8/600 `--text-dim` na mesma linha de base.

## Componentes que já existem (não recriar; refinar)

`card` vira **faixa**: `--surface` de borda a borda, sem sombra, raio
`--corte-g` no prato e `--corte` na lista; `btn` (`--primary` lima cheia,
`--ghost` contorno `--fio-forte`, `--quiet`, `--perigo`, `--sm`, `--block`;
todos com `--corte`; uma escala de toque, `.96`) · `chip` / `chip-row`
(`--corte-p`) · `pill` (`--brand`, `--mute`, `--warm`) só para selo · `tile` /
`tiles` (número grande em Bodoni + rótulo + meta em Karla) · `data-list`
(`dt`/`dd`) · `empty-state` · `hint` · `field` (rótulo, ajuda, erro; `--corte`;
rádios e caixas viram folhas) · `choice_cards` (rádio como folha com ícone) ·
`marca` e `marca_de_entrada` · `_conquista` (aviso ancorado embaixo, não
modal) · anel de progresso (calorias, água, treino: trilha em `--fio`, arco
em `--folha`) · `tabbar` (quatro itens; a ativa é folha cheia de `--brand`) ·
`app-bar` (marca à esquerda; no desktop, os quatro links).

## As sete telas do contrato

Entrar · Hoje · Dieta (refeição aberta com opções A e B) · Ficha com duas
opções · Execução (UM exercício; Ferro sempre) · Progresso · **Frame de
recompensa** (a última série do treino — o placar dentro da folha: total de
carga, séries, minutos, vs. última, o recorde; "Ver resumo do treino"
primário, "Voltar para Hoje" contorno). Referência visual: os mockups da
direção em `artifacts/claude-design/export/direcoes/Direcao2-{a,b}.dc.html`
e as capturas em [`referencias/direcoes/`](referencias/direcoes/).

## O que este app não faz

Gradiente roxo; cartão branco com sombra; vidro (`backdrop-filter`) além da
moldura do app; ícone-emoji na interface; Material Symbols; `:has()` em
regra que decide layout; animação decorativa; cinco abas; tela de login
com só logo, campos e botão; "painel administrativo" de números iguais ao
texto; lima como TEXTO sobre osso (no claro a ação é oliva).

## Mantido da spec anterior (Mesa & Ferro, direção C)

O que sobrevive, e por quê (Task 11 invertida — o resto saiu):

- os cinco pilares, "Hoje" fora deles, Perfil utilitário; a barra de
  QUATRO itens medida a 320 px; o mapa em `<details>` continua aposentado;
- os NOMES dos tokens do app (`--bg`, `--surface`, `--brand`, `--folha`,
  `--agua`, `--brasa`, `--terra`, `--chama`, `--carb`, `--fat`, `--fio`,
  `--fio-forte`, `--dia-*`, `--mov-*`, `--camada-*`) — mudam os valores, não
  os fios que os testes seguram;
- o sprite de 13 símbolos, traço 2 em CADA `<symbol>`, grade 24, uma vez por
  página e fora do shell offline (`config/test_sprite.py`);
- WCAG AA em todo par, com a margem de 5,0 para `--text-dim`/`--text-mute`
  e a auditoria de 274 pares no CSS real;
- alvo 44 × 44; texto ≥ 11 px; `tabular-nums` e vírgula decimal; nada rola
  na horizontal; `min-width: 0`;
- tudo em token e as catracas de valor cru (`config/test_design_system.py`),
  que só descem;
- os `--mov-*` com `prefers-reduced-motion` desligando tudo, o `<details>`
  animado por JS, `view-transition-name` único por documento, uma escala
  de toque (`.96`) numa lista só;
- foco na cor da ação com vão; campo inválido fala; um primário e uma
  superfície de foco por tela; estado vazio é convite;
- os dois gatilhos escritos uma vez (`config/test_ferro.py`) — invertidos:
  Ferro é a base, Papel o derivado, `body.modo-foco` força Ferro;
- a vitrine em `/gestao/vitrine/` (agora `?regime=papel` para o claro) e o
  teste que lê a pasta de parciais;
- `--agua`, `--brasa`, `--terra`, `--chama` como cores de pilar com a regra
  de três; `--brand` AGIR e `--folha` FEITO;
- "Disciplina hoje. Resultados amanhã.", "Bom te ver de volta", "Você",
  nunca "nós".

O que SAIU com a direção: Mesa como base clara; linho `#f5f3ee` e prato
branco; os raios 24/16/12/8 e a regra "caixa dentro de caixa"; as sombras
`--shadow-rest`/`--shadow-lift`/`--edge` como desenho; `system-ui` como
fonte; os onze pesos; o cartão como unidade de layout; o brilho difuso.
