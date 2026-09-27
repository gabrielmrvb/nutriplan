# Missão: nada preso cobre o exercício (24/09/2026)

Branch `treino/nada-cobre-o-exercicio`. Tudo abaixo foi **medido no
navegador** antes e depois — `elementFromPoint` no centro de cada elemento,
Chromium via `agent-browser`, conta de QA local, dia com treino, três
larguras × dois temas × vídeo aberto/fechado, mais o caso do relógio de
descanso rodando. Capturas em `achados/capturas-execucao-20260924/`
(28 arquivos, `antes-*` e `depois-*` com os mesmos nomes).

Vocabulário de evidência: `[EXECUTADA]` · `[OBSERVADA]` · `[LIDA NO CÓDIGO]`
· `[HIPOTÉTICA]`.

## O número que a missão pediu

A faixa livre é do fim do cabeçalho (mais o relógio de descanso, quando há)
até o topo do bloco preso de registro.

| vista | faixa livre antes | depois | bloco antes → depois |
|---|---:|---:|---|
| 390×844 | 355 px | **640 px** | 335 → **144 px** |
| 375×667 | 178 px | **463 px** | 335 → **144 px** |
| 375×667 + descanso | **25 px** | **400 px** | 335 → **144 px** |
| 430×932 | 355 px | **717–728 px** | 335 → **144 px** |

**A comparação é legítima mesmo com a ficha remontada no meio**, e isso é
aritmética, não sorte: a faixa livre é `janela − bottom − bloco − cabeçalho
− descanso`, e nada nela depende de QUAL exercício está na tela. Antes,
`844 − 94 − 335 − 60 = 355`; hoje, `844 − 0 − 144 − 60 = 640`. Os dois
valores medidos batem com a conta na casa do pixel.

O player vertical mede 391 px e cabe; antes ele era cortado pelo bloco
(`coberto por agora__registro`, medido).

**A guarda do dono, nas 12 combinações + 4 com descanso `[EXECUTADA]`:**
`.agora__nome`, `.agora__meta`, `.demo__abrir`, `.demo__cue` e o player
aberto devolvem eles mesmos em `elementFromPoint`. Nenhum aparece coberto em
nenhuma combinação. `button.demo__abrir` é clicado sem `force`.

## O que mudou, e por quê

1. **O bloco não reserva mais uma barra de abas que a tela não desenha.**
   `ModoTreinoView` põe `sem_tabbar = True` desde 20/09 e o `bottom`
   continuava em `calc(var(--tabbar-h) + …)`, corrigido só por uma media
   query de 60rem — no celular, nunca. Agora é
   `body:not(.tem-tabbar) .agora__registro { bottom: env(safe-area-inset-bottom) }`,
   classe do SERVIDOR e não largura, depois da regra geral. A media query
   saiu (virou regra sem consumidor). **Varri as 5 reservas de `--tabbar-h`
   do `app.css` `[LIDA NO CÓDIGO]`**: `.container`, `.ficha__acoes` e
   `.install`/`.fila` estão certas — aquelas telas TÊM barra (só
   `workouts/views.py:1442` desliga) —; `.agora__registro` e `.conquista`
   foram corrigidas.
2. **O bloco preso só tem o que o dedo usa entre duas séries** (~140 px, teto
   no token `--exec-bloco`): uma linha com carga e reps, e "Concluir série".
   Pastilhas "1 2 3 4" e "Anotar algo desta série" voltaram ao fluxo, ACIMA
   dele, com `scroll-margin-bottom` do tamanho do bloco. **Isto reverte o
   item 2 da B32 de 16/09** — está escrito no `CLAUDE.md`, ao lado dela, com
   a aritmética.
3. **O vídeo mede a faixa que sobra**, não `60vh`: `100dvh` menos cabeçalho,
   descanso, cabeça do exercício e bloco. O descanso entra por
   `agora--com-descanso`, classe do servidor — `:has()` é proibido aqui.
4. **Quem sobe ao abrir o vídeo é a CABEÇA do exercício.** Primeira tentativa
   rolava o `.demo` para `start`: ele parava em 68 px, logo abaixo do
   cabeçalho como se queria, **e levava o nome para −9 px** `[OBSERVADA]` —
   um vídeo sem o nome por cima é vídeo de que exercício? A rota de leitura
   divide o mesmo script e não tem `.agora__topo`; lá o alvo continua sendo a
   demonstração.

## Dois defeitos que eu mesmo introduzi, e a medição pegou

Registrados porque a missão é sobre medir, e o instrumento também erra.

1. **O bloco transbordava o próprio teto.** `max-height: var(--exec-bloco)`
   prende a CAIXA, não o conteúdo, e o `overflow` é `visible`. Medido depois
   da primeira correção: caixa 136 px com 140 de conteúdo (transborda 4), e
   **168 com o selo "aguardando rede" ligado** (transborda 32) — o "Concluir
   série" saía da caixa e ficava sem o fundo `--surface` por baixo. Eu tinha
   escrito que o token "impede a próxima linha de conteúdo de devolver o
   bloco aos 335 px sem ninguém perceber", e do jeito que estava a linha nova
   passaria por cima sem a caixa mudar de tamanho: guarda que não confere.
   Correções: o selo saiu do bloco (é STATUS, não controle) e o teto foi a
   9rem = 144, acima do conteúdo real. Depois: **transbordo 0 nos quatro
   casos, com o selo ligado, e o CTA dentro da caixa** `[EXECUTADA]`.
2. **A sonda media durante uma rolagem animada.** Abrir o vídeo rola com
   `behavior: smooth` e a espera era de 2 200 ms fixos; numa execução o CTA
   saiu "coberto em qualquer posição", e a medição dirigida não reproduziu
   (bloco preso em 523–667, CTA 610–663, `elementFromPoint` devolvendo o
   próprio botão). Tempo fixo não é sincronia: a sonda agora espera o
   `scrollY` PARAR de mudar. Depois disso, **zero "coberto em qualquer
   posição" nas 12 combinações**.

## O achado que não estava na missão, e é de produção

**O `<script>` recriado na troca sem recarga perdia o nonce.** `[EXECUTADA]`

| momento | `<script>` no `<main>` | com nonce |
|---|---:|---:|
| carga inicial | 3 | **3** |
| depois de UMA série sem recarga | 3 | **0** |

A CSP de 22/09 é `script-src 'self' 'nonce-…'` sem `unsafe-inline`. A troca
recria cada `<script>` com `createElement` — que é o que os faz rodar,
porque `innerHTML` não executa script — e o elemento novo não herda nonce.
O navegador os recusa **em silêncio**.

O que a pessoa via, da primeira série em diante: "ver vídeo" na tela sem
abrir nada, os degraus de carga (−2,5/+2,5) mortos e o relógio de descanso
congelado. Provado `[EXECUTADA]`: antes, clicar "ver vídeo" depois da série
deixava `aberta: false, player: false`; depois da correção, `aberta: true,
player: true`.

Por que passou despercebido: **a própria troca mora no `<main>`**. Sem o
nonce ela morria junto, o "Concluir série" seguinte voltava a ser POST com
recarga — e a recarga consertava tudo. O defeito se apagava a cada duas
séries.

Não dá para copiar o nonce do nó velho: ele veio do HTML **buscado** e
carrega o nonce daquela resposta. Vale o desta página, guardado em
`document.currentScript.nonce` no topo do script (dentro de callback,
`currentScript` é `null`). `workouts/test_nonce_na_troca.py` prende os dois
lados, e a varredura dele vale para a próxima tela que trocar HTML por
fetch: `config/test_csp.py` lê o TEMPLATE, e script criado em tempo de
execução não passa por lá.

## A varredura do fluxo (item 5 do dono)

Todo controle de `<main>` (`a[href]`, `button`, `input`, `select`,
`summary`), com a pergunta feita **depois de rolar até ele** — o que sobra é
o que nenhuma rolagem resolve. A 375×667 e a 390×844 `[EXECUTADA]`:

| tela | controles | fora de alcance |
|---|---:|---|
| execução, primeira série | 16 / 20 | nenhum |
| leitura do exercício ("Outras formas") | 15 | nenhum |
| descanso rodando | 20 | nenhum |
| "Anotar algo" ABERTO | 16 | nenhum |
| fim do treino (placar) | 3 / 4 | nenhum |

Zero rolagem horizontal em todas.

**Dois falsos positivos meus, registrados porque custaram tempo:**

- a primeira varredura acusou o checkbox e o campo de "Anotar algo" como
  cobertos — eles estavam dentro de um `<details>` **fechado**, que no
  Chrome continua tendo caixa. `FALSO POSITIVO`; o filtro agora ignora
  conteúdo de `<details>` fechado, e o caso REAL (nota aberta) foi medido à
  parte e está limpo;
- a segunda varredura deu "4 controles" em toda tela porque o laço que
  conclui o treino rodava **dentro** do laço das larguras: a segunda largura
  media o placar achando que media a execução. Corrigido pela ordem das
  fases; sem isso o "nada fora de alcance" seria um teste que passa pelo
  motivo errado.

E uma armadilha de instrumento, da mesma família do `check` que sai 0 sem
marcar: **`.agora__concluir` clicado com `weight_kg` vazio não faz nada** —
o campo é `required` e o navegador barra o envio sem erro. A sonda reportava
`descanso 0` como se a tela não tivesse relógio. Hoje ela preenche o campo e
**falha alto** quando o relógio não nasce.

## Provas

- **TDD**: 10 testes vermelhos antes da implementação, depois 14 em
  `workouts/test_nada_cobre_o_exercicio.py` + 3 em
  `workouts/test_nonce_na_troca.py` + 1 varredura.
- **Sabotagem 100 % vermelha** (`scratchpad/sabotar.py`), **7 de 7**, com
  controle positivo verde nos três módulos: bloco voltando a reservar a
  tabbar · teto do vídeo sem a cabeça · carga e reps em duas linhas · rolagem
  voltando para a demonstração · nonce removido · selo de rede voltando para
  dentro do bloco · alguém recriando `<script>` sem nonce. Uma âncora nasceu
  errada (indentação da grade) e a sabotagem AVISOU em vez de passar —
  "âncora não achada" conta como falha no script, de propósito: sabotagem que
  não aplica o defeito é sabotagem que não mede nada.
- **Suíte completa**: 4 516 testes. A primeira passada deu 3 falhas, todas
  analisadas e nenhuma regressão de comportamento — uma dependia da ORDEM DOS
  ATRIBUTOS da tag do formulário (`test_serie_sem_recarga` casa a string
  `…registro--agora" method="post" data-sem-recarga`, e o `id` novo entrou no
  meio dela; foi para o fim da tag) e duas congelavam o estado que a decisão
  do dono muda (`"menos carga mais"` numa faixa só, e `max-height: 60vh`).
  As duas últimas foram atualizadas com a razão escrita, mantendo a intenção
  original de cada uma.
- **E2E noturno**: passo `video` entre `serie` e `tema-claro` (PASSOS vai a
  14), com a régua geométrica; `config/test_e2e_noturno.py` verde (13), e o
  navegador falso responde JSON em vez de `true` — senão o roteiro passaria
  com o vídeo atrás do bloco.

## Recomendo rever (é decisão de produto, não mexi)

1. **Conteúdo do fluxo atrás do `sticky` logo depois de abrir o vídeo.** Com
   o vídeo aberto a 375×667, "Série N de M", as pastilhas e a nota ficam sob
   o bloco NAQUELA posição de rolagem; rolando, chega-se a todos. É o
   comportamento normal de um rodapé preso, e resolvê-lo exigiria ou um
   vídeo menor ou um bloco que se esconde ao rolar — os dois são decisão sua.
2. **O `<details>` "Anotar algo" cresce logo acima do bloco.** Hoje cabe;
   se ganhar mais um campo, vira o mesmo problema outra vez.

## O que preciso de você

**Nada.**
