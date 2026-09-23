# A Home ao nível do mockup — o que foi medido, o que mudou, o que não entrou

**23/09/2026** · branch `home/mockup` · referência: [`achados/mockup-home.png`](mockup-home.png)
· provas em [`achados/home-acabamento-20260923/`](home-acabamento-20260923/)

A missão pediu para levar a tela Hoje (`/`) ao acabamento visual de um mockup
de referência, com dados reais e sem inventar nada. Este documento é o
relatório: o estado inicial medido, as três rodadas de comparação, as decisões
que tomei sozinha e as diferenças que sobraram — com a razão de cada uma.

---

## 1. O estado inicial (capturado antes de editar)

`achados/home-acabamento-20260923/antes-*.png`, conta local com os cinco
pilares declarados, 6 pesagens, 4 corridas e 1.250 ml de água.

| o que o mockup tem | o que a tela tinha |
|---|---|
| título da página e data por extenso | `<h1 class="vis-oculto">Hoje</h1>` — nenhuma âncora visível acima do cartão verde |
| herói de três colunas (o que é · a receita · as ações) | pilha com um botão verde de 970 px de largura, e nenhuma ação de registro |
| "Seu resumo de hoje" | `<h2 class="vis-oculto">Resumo do dia</h2>` |
| grade 3 + 2, cartões largos | cinco colunas de 238 px, com anel, barra e três botões espremidos em cada |
| subtítulo de contexto em cada cartão | rótulo e número, sem linha de contexto |
| semana em sete pontos (Treino e ofensiva) | não existia em nenhum dos dois |
| tendência de Corrida e Progresso | não existia |

Medido a 1280: a página inteira tinha 1.000 px de altura e o painel ocupava
250 px deles.

## 2. O que mudou

**Cabeçalho.** O `<h1>` voltou a ser visível dizendo o DIA — "Seu dia,
quarta-feira", com "23 de setembro de 2026" abaixo. Ele leva `page-head`,
então herda a nervura que assina todo título de tela; o respiro dela é medido
(100 px × sen 14° ≈ 24 px, mais 8 de `gap` — sem isso a régua risca o selo
"Visão geral", e riscou na rodada 1).

**Herói.** Três colunas no desktop (`grid-auto-flow: column`, para o cartão de
um filho e o de dois não abrirem coluna vazia), empilhadas no celular: o que é
(selo "AGORA · 14:30", nome da refeição, kcal e proteína **da receita** que o
botão registra), que receita é (medalhão redondo com a ilustração da família,
nome e tempo de preparo) e o que fazer ("Comi esta" primário + "Ver refeição"
em contorno). Registrar pela Home **devolve para a Home**
(`MarkMealView.DESTINOS`, lista fechada).

**Painel.** Cinco cartões em linhas de três com a sobra dividida
(`larguras_do_desktop`: 5 → 3+2, 4 → 2+2, 3 → 3), numa grade de seis colunas.
Cada cartão: marca (ícone em superfície), nome, **um fato de contexto**, o
número do dia e a ação com seta. Contorno de fio de 1 px, que existe pelo tema
CLARO — no escuro a superfície já separava.

**Duas leituras novas, ZERO consulta a mais:**

- a **semana em sete pontos** (`streaks.Ofensiva.semana`), desenhada duas
  vezes com perguntas diferentes: no Treino "havia treino, e foi feito?"; na
  ofensiva "o dia fechou?". Quatro formas distintas (disco, anel, risca, ponto
  pequeno) mais o dia por extenso em `vis-oculto` — o estado não é só cor;
- as **linhas de tendência** de Corrida e Progresso (`plans/sparkline.py`),
  com a régua de três pontos de dado real.

## 3. As três rodadas

| rodada | o que a comparação lado a lado achou | o que foi feito |
|---|---|---|
| **1** | medalhão VAZIO (o sprite das ilustrações não era incluído na Hoje); a nervura riscava o selo "Visão geral"; o ponto da linha fina no canto errado; "ALIMENTAÇÃO" escrito **na vertical** a 390 px; "registra/das" quebrado no meio | sprite incluído (só quando há receita); respiro da nervura medido; **coordenadas do SVG viraram texto**; `flex-wrap` no cabeçalho do cartão; `overflow-wrap: normal` no nome e no fato |
| **2** | 200 px de vazio entre o número e o botão nos cartões de baixo; a faixa da ofensiva espremia o texto num vão de 60 px a 390; no tema CLARO os cinco cartões liam como um bloco só | `grid-auto-rows: 1fr` removido (ele igualava todas as linhas entre si); a tira desce para a própria linha no celular; contorno de fio |
| **3** | o cartão saía "agachado" ao lado do mockup: mesmo conteúdo, metade do respiro; o número grande empatava com o título da seção | `gap` e `padding` do cartão no degrau de cima, `.painel__valor` em `--texto-3xl`, anel de 7,2rem acima de 75rem |

As quatro combinações (1280 e 390 px × escuro e claro) foram capturadas em
todas as rodadas; as comparações de desktop escuro estão na pasta de provas.

### As duas regressões que a LARGURA pegou

A faixa de três colunas nasceu numa media query — e media query mede a
JANELA, não o espaço que o cartão tem. Isso quebrou duas vezes, do mesmo
jeito, e as duas só apareceram porque a varredura de larguras existe:

1. **na tela vizinha** (Alimentação, a 1280 px);
2. **na própria Home, a 768 px**.

Nos dois casos o bloco de texto foi espremido até **o nome da refeição sair
escrito na vertical, uma letra por linha**. A correção é dupla — a faixa é
escopada por `.hoje` E só entra a partir de **60rem**, onde o container tem
~928 px (a 768 ele tem ~736, e a coluna de ações de 184 px mais o medalhão
não deixavam nada para o texto). Duas réguas leem o `app.css` e cobram as
duas coisas, com sabotagem.

Medido depois: 430, 768, 960, 1280 px — todas corretas.

### A regressão que a tela VIZINHA pegou

O cartão AGORA é um parcial usado por DUAS telas, e a faixa de três colunas
nasceu numa media query — que mede a JANELA. Na Home o cartão tem 1.024 px a
1280; na Alimentação ele mora na coluna esquerda do `split`, com ~420 px, e a
1280 a janela passa de 48rem nas duas. Na coluna estreita as três colunas não
couberam: o bloco de texto foi espremido até **o nome da refeição sair escrito
na vertical, uma letra por linha** (`vizinha-alimentacao.png` é a tela já
corrigida). A faixa passou a ser escopada por `.hoje`, e
`AFaixaDeTresColunasEDaHomeTests` lê o CSS e cobra o escopo — com sabotagem.

## 4. Validação

| o que | resultado |
|---|---|
| **axe-core 4.12.1** — 390, 320 e 1280 px, nos dois temas | **0 violações** nas seis combinações, 41 regras passando. 1 `incomplete` de `color-contrast` (pseudo-elementos: a nervura atrás do `h1`, o gradiente cônico do anel, o `clip-path` do botão) |
| **controle positivo do axe** | um `<img>` sem `alt` injetado no DOM → `violations: 1`. A varredura enxerga |
| **contraste** (`scripts/qa/auditar_contraste.py`, sobre o CSS real) | 274 pares, **0 reprovados** — o mesmo número de antes |
| **rolagem horizontal** | zero a 320, 390 e 1280, nos dois temas |
| **alvo de toque** | nenhum controle do `<main>` abaixo de 44 × 44 |
| **texto mínimo** | nenhum abaixo de 11 px |
| **foco pelo teclado** | Tab de verdade (não `.focus()`): anel de 2 px sólido visível |
| **ações no navegador** | +250 ml: 1.250 → 1.500 e volta para a Home; "Comi esta": registra, a pessoa **fica na Home**, o cartão passa a "2 de 5 registradas" e o herói aponta a próxima refeição |
| **sabotagem** | **13 de 13 vermelhas** (rodada de novo no fim). Duas ficaram VERDES na primeira passada e os dois testes foram corrigidos — ver abaixo |
| **testes novos** | 36 em `plans/test_home_acabamento.py` |
| **suíte completa** | 4.423 testes, 1 `expectedFailure` nomeada. A primeira execução achou UMA falha real — `assertContains(home, "Descanso")` sensível a maiúscula em `accounts` — corrigida |
| **larguras varridas** | 320, 390, 430, 768, 960 e 1280 px |
| **orçamento de consultas** | `plans/test_orcamento_da_home.py` (teto 17) verde — a semana e as duas linhas saem de leituras que a tela já fazia |
| **catracas de valor cru** | 109 `font-size` e 230 espaçamentos: exatamente os tetos, nenhum subiu |

### As duas sabotagens que ficaram verdes

Elas são o achado mais útil desta missão, porque os dois testes estavam
errados do jeito que o `CLAUDE.md` registra como recorrente:

1. **"o herói perde o destino"** — o teste postava `{"de": "hoje"}` como
   dicionário, então continuava verde com o campo REMOVIDO do template.
   `client.post(url, {...})` prova a VIEW, não a TELA. Hoje ele extrai os
   campos escondidos do formulário RENDERIZADO e envia o que o navegador
   enviaria;
2. **"a semana futura diz que faltou"** — o teste varria `calcular()` atrás de
   dias futuros com treino previsto, e o usuário do fixture não tinha nenhum:
   a varredura media ZERO casos. Hoje o caso é montado à mão, com controle
   positivo (o mesmo dia, no passado, é "faltou").

## 5. Decisões que tomei sozinha

- **O herói da Home passou a registrar.** A doutrina dizia que ele era um
  PONTEIRO, para não pôr a escolha entre duas receitas na tela que existe para
  não ter escolha. A razão continua valendo e é por isso que ele oferece UMA
  opção — a primeira da projeção, a mesma que o card marca como recomendada —
  com "Ver refeição" ao lado. A missão pediu o par explicitamente.
- **"Comi esta" volta para a Home** (`de` + lista fechada). Sem isso a pessoa
  registrava na primeira dobra e se via noutra tela; medido no navegador.
- **Nenhuma frase de ânimo do mockup entrou.** No lugar de cada uma entrou o
  fato que contextualiza o número. Há teste varrendo as sete frases.
- **Os "···" não entraram**: menu sem função é promessa.
- **A linha da corrida conta SEMANAS COM CORRIDA**, não os oito baldes — senão
  uma corrida só virava uma reta no chão com um pico no fim.
- **O sprite das ilustrações entra na Hoje só quando há receita no herói.**
- **A Hoje ganhou largura própria** (`hoje-largo`, 72rem acima de 75rem), em
  vez de mexer no `largo` de 64rem, que é de todas as telas de conteúdo.
- **Fiz o `.painel__sub` em `--texto-sm`** (e não `--texto-xs`): é uma frase,
  não um rótulo, e a 11,2 px "em 8 semanas" lia como "em 8semanas".

## 6. Diferenças que sobraram em relação ao mockup

| diferença | por quê |
|---|---|
| **foto da receita no herói** → medalhão com a ilustração da família | o catálogo NÃO tem campo de imagem (`catalog/ilustracoes.py`, decisão de 23/09/2026: 54 receitas, 0 fotos, 11 famílias desenhadas). Um retângulo cinza esperando foto seria o buraco que a tela existe para não ter |
| **quinas arredondadas** → quinas retas | a direção NERVURA tem os três slots de quina em ZERO, está publicada no `DESIGN.md` e vale para o app inteiro. Mudá-la é decisão do dono (condição 3), não desta missão |
| **frases de ânimo** → fatos | decisão da própria missão ("sem frases motivacionais") |
| **"Marcar como concluída"** → só "Comi esta" | é o MESMO registro com outro nome |
| **links legais no rodapé** | a Home logada não os tem; eles moram nas telas de entrada (`partials/links_legais.html`) |
| **barra de navegação no topo** | o mockup é uma prancha sem a moldura do app; a tela real tem a barra e a tabbar |

## 7. Recursos pendentes

**Não há pendência que bloqueie a tela.** O que existe, medido:

- **fotos de receita: 54 receitas ativas, ZERO com foto, e não há campo para
  guardá-las.** Adicionar exigiria: um campo de imagem em `MealTemplate`, 54
  arquivos curados (licença conferida) e um mosaico de veto. A dimensão que o
  herói pediria é **um quadrado de 320 × 320 px** (o medalhão tem 5,2rem = 83
  px, e a tela dobra em telas densas); o card de receita da Alimentação pediria
  **480 × 320**. As **11 famílias** de ilustração em uso cobrem o lugar hoje,
  e esta é a contagem real por receita ativa: `prato` (16), `pao` (9),
  `tapioca` (6), `fruta` (5), `cuscuz` (4), `iogurte` (3), `macarrao` (3),
  `vitamina` (3), `mingau` (2), `ovos` (2), `salada` (1). O sprite tem doze
  símbolos — o décimo segundo é o padrão.
- **fonte**: nenhuma nova. A Home usa a Big Shoulders Display e a Archivo que
  já estão auto-hospedadas.
- **nada a comprar.**
