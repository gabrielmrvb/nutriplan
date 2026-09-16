# NutriPlan — DESIGN.md (contrato visual para o Claude Design)

Este arquivo é a fonte da verdade dos tokens e das regras. O que está aqui
não é sugestão: é decisão tomada e medida (contrastes recalculados por
teste em `config/tests.py`). Se algo faltar, pergunte; não invente.

## Identidade

- **O que é:** PWA mobile-first, em português do Brasil, de alimentação,
  treino, corrida, hidratação e progresso — cinco pilares no mesmo nível.
  "Hoje" é o orquestrador do dia, não um pilar; Perfil é utilitário.
- **Navegação:** barra inferior de QUATRO itens (Alimentação · Treino ·
  Progresso · Áreas) — medida a 320 px; cinco não cabem. Um mapa de áreas
  na barra de cima lista os cinco pilares. **A navegação não muda.**
- **Tom:** direto, adulto, sem promessa. Número grande é o protagonista da
  tela (calorias, série, litros, peso). Nada de texto motivacional genérico.
- **Marca:** verde-floresta + branco + verde-folha, cores próprias que NÃO
  mudam com o tema (é a `icon-192.png` em `marca/`).

## Princípio: um material, dois regimes de luz

A comida acontece numa MESA — luz de cozinha, linho, branco. O treino
acontece no FERRO — luz baixa de academia, grafite, número grande. O que faz
os dois serem um app só é que TUDO fora da luz é idêntico. O regime é uma
classe escrita pelo servidor no `<body>` (`modo-foco`): a execução do treino
e a corrida em andamento nascem em Ferro; todo o resto é Mesa. O tema escuro
por preferência do sistema É o mesmo bloco de valores do Ferro.

## O que NUNCA muda entre Mesa e Ferro

Família tipográfica e eixo óptico; a escala de texto; os raios; a grade de
4 px; o sprite de ícones; o anel de progresso; a receita do botão; alvo de
toque; espaçamento entre cartões. **Só muda cor e densidade.** Nenhum
componente pode ter raio, tamanho de texto ou ícone diferente entre os
regimes.

## Tokens de cor (Mesa = padrão; Ferro = `body.modo-foco` e tema escuro)

| token | Mesa | Ferro | papel |
|---|---|---|---|
| `--bg` | `#f5f3ee` (linho) | `#0e1412` | chão |
| `--surface` | `#ffffff` | `#161d1a` | prato / cartão |
| `--surface-2` | `#efece4` | `#243029` | agrupamento dentro do cartão; ≥ 1,2:1 sobre `--surface` (U28) |
| `--surface-3` | `#ebe8de` | `#2c3a32` | célula vazia de gráfico, silhueta de vazio, hover |
| `--surface-focus` | `#e3f1e8` | `#123024` | UMA por tela: a próxima refeição, a série da vez |
| `--text` | `#141f1a` | `#f4f7f5` | texto |
| `--text-dim` | `#485550` | `#b6c1bb` | texto de apoio |
| `--text-mute` | `#55625c` | `#a0aca6` | rótulo, legenda (≥ 5,0:1 no pior fundo neutro) |
| `--brand` | `#0c6b40` | `#22c98a` | AGIR: CTA, link, aba ativa, foco |
| `--brand-strong` | `#08512f` | `#4ddb9f` | só `:active`/hover |
| `--brand-soft` | `#dff0e6` | `#0f2a20` | botão tonal, chip |
| `--folha` | `#3f9718` | `#6fcf4a` | FEITO (série registrada, arco do anel) + pilar Treino |
| `--agua` | `#1e6e96` | `#5fbdf0` | pilar Hidratação |
| `--agua-texto` | `#175877` | `#5fbdf0` | água como texto pequeno |
| `--brasa` | `#a63f18` | `#ff9a7a` | pilar Corrida |
| `--terra` | `#8a5109` | `#f2b04e` | pilar Progresso/peso |
| `--chama` | `#c8620a` | `#ffa53a` | ofensiva, só objeto gráfico |
| `--carb` | `#ad6d16` | `#e6b35d` | macro carboidrato |
| `--fat` | `#5568a6` | `#93a8de` | macro gordura |
| `--danger` | `#b3261e` | `#ff8a80` | erro, ação destrutiva |
| `--fio` | `rgba(20,31,26,.10)` | `rgba(255,255,255,.08)` | hairline de separação |
| `--fio-forte` | `rgba(20,31,26,.22)` | `rgba(255,255,255,.16)` | borda de campo |
| `--on-brand` | `#ffffff` | `#04140e` | texto sobre `--brand` |
| `--dia-a` … `--dia-e` | verde, azul, âmbar, violeta, coral | idem, claros | cor de sessão no painel de treino |

**A regra de três:** cor de pilar aparece em pelo menos TRÊS lugares da área
(fio do prato, arco/coluna do gráfico, ponto do ícone) e em NENHUM botão.
Foco é `--brand` em todo controle. Nenhum gradiente com o violeta.

## Tipografia

- Hoje: `system-ui` (Segoe/SF/Roboto). Uma fonte própria (DM Sans Variable)
  está CONDICIONADA a medição de tamanho e será decidida no repositório —
  **não escolha fonte.**
- Quatro pesos apenas: 400 (corpo), 500 (rótulo), 600 (título), 700 (número).
- Escala (rem): xs .7 (11,2 px, o piso) · sm .8 · md .9 · base 1 · lg 1.15 ·
  xl 1.4 · 2xl 1.75 · 3xl 2.15 · display 3.1. Texto de interface nunca
  abaixo de 11 px. Número é `font-variant-numeric: tabular-nums` e usa
  vírgula decimal ("62,50").

## Espaço, raio, sombra, camadas, movimento

- Grade de 4 px; espaçamentos `--espaco-1…8` (4 … 32 px).
- Raios: `--radius-xl` 28 · `--radius-lg` 22 · `--radius` 18 · `--radius-sm` 14 · `--pill` 999.
- Sombras: `--shadow-rest` e `--shadow-lift` (uma de repouso, uma de
  elevação); `--edge` é o fio interno de luz. Nada além disso.
- Camadas (z-index), de baixo para cima: conteúdo → barra de cima →
  flutuante → navegação → aviso → bloqueio. Nada cobre a barra de baixo.
- Movimento: toque .1 s, estado .18 s, expansão .25 s, tela .2 s, modal
  .28 s, sucesso .5 s; passo 6 px; `prefers-reduced-motion` desliga tudo.
  Movimento confirma ação; não decora.

## Regras de interface

- Alvo de toque **44 × 44 px** (altura E largura). Texto ≥ 11 px.
- Nada rola na horizontal; todo contêiner de texto tem `min-width: 0`.
- Uma superfície de foco por tela. Um botão primário por tela.
- Estado vazio é convite (o que fazer a seguir), não constatação.
- Ações destrutivas ("zerar", "excluir conta") são secundárias, separadas e
  pedem confirmação.

## Componentes que já existem (não recriar; refinar)

`card` (com `card__head`, `card--conta`, `card--metas`, `card--prosa`) ·
`btn` (`--primary`, `--ghost`, `--quiet`, `--perigo`, `--sm`, `--block`; uma
escala de toque, `.96`) · `chip` / `chip-row` · `pill` (`--brand`, `--mute`,
`--warm`) · `tile` / `tiles` (número grande + rótulo + meta) · `data-list`
(`dt`/`dd`) · `empty-state` · `hint` · `field` (rótulo, ajuda, erro; rádios e
caixas viram cartões) · `choice_cards` (rádio como cartão com ícone) ·
`marca` e `marca_de_entrada` · `_conquista` (aviso ancorado embaixo, não
modal) · anel de progresso (calorias, água, treino) · `tabbar` (quatro itens)
· `app-bar` com mapa de áreas (`<details>`).

## O que este app não faz

Gradiente roxo; vidro (`backdrop-filter`) além dos quatro cartões do topo;
ícone-emoji na interface; Material Symbols; `:has()`; animação decorativa;
cinco abas; tela de login com só logo, campos e botão; "painel
administrativo" de números iguais ao texto.
