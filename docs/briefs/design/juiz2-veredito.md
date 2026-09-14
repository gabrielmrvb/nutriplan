# Juiz 2 de 2 — veredito sobre as três direções (14/09/2026)

Designer sênior, olho de produto. Só leitura, medição e proposta; nenhum
código alterado. Sessão headless própria (`juiz2`), fechada no fim.

## O que eu mesmo medi antes de dar nota

- **Pesos do sistema no Windows** [OBSERVADA, `/conta/entrar/`, spans
  separados]: "faltam 2830 kcal" a 40px em `system-ui` mede 300=274px,
  400=289, 500=295, 600=295, 700=310, 800=324. Confirma a medição da
  Direção A: o sistema DESENHA o 300 (Segoe UI Light) e 500/600 colapsam.
  Consequência para as três: hoje 14 pesos computados na Home
  (`juiz2-medir-home.json`) renderizam como cinco.
- **Baseline da Home** [OBSERVADA, `medir.js`, conta qa-execucao, 390px]:
  3.143px de altura, 6 `.card`, 64 elementos com borda, 25 com sombra, h1
  `40px/800/−1,4px`, 24 tamanhos de fonte, 14 pesos, 6 raios (14/18/22/28/
  50%/999), 15 fundos `rgb(12,107,64)`, 11 botões primários. É o "antes"
  que as três direções citam, e bate.
- **Execução a 320×568** [OBSERVADA]: o CTA "Concluir série" fica em
  y=593–641 com viewport de 568 — fora da dobra. O CTA sticky que as três
  propõem corrige defeito real.
- **Contraste recalculado** (`juiz2-contraste.py`) contra a régua que a
  suíte JÁ cobra — `config/tests.py::test_the_quiet_text_clears_the_minimum_
  with_room_to_spare` exige **5,0:1** (não 4,5) para `--text-dim` e
  `--text-mute` sobre bg/surface/surface-2/surface-3/brand-soft nos DOIS
  temas:
  - A: `--text-3 #5e6a65` = **4,72 sobre surface-3** — abaixo da margem. A
    renomeia `--text-mute` para `--text-3`, o que faria o teste dar
    `KeyError` em vez de reprovar: a régua seria contornada por rename.
  - B: `--text-mute` 5,02 (raspando), `--on-pista-mute` 5,65 — passa. Mas
    **`--folha` sobre o novo `--surface-3 #dfe5e2` dá 2,91**, não os 3,05
    que o documento afirma: 3,05 é o valor contra o surface-3ATUAL (#e4eae7).
    Escurecer o trilho derrubou o gráfico abaixo de 3:1.
  - C: Mesa passa (text-mute 5,21). **Ferro `--text-mute #8f9b95` = 4,68
    sobre surface-3** — abaixo da margem; e como Ferro É o tema escuro, o
    teste do escuro reprova. `#96a29c` resolve (5,10 / 5,79 / 5,39).
  - As três: campo branco com borda a .21–.24 de alfa mede **1,55–1,67:1**
    contra branco. Nenhuma satisfaz 3:1 de fronteira de controle (WCAG
    1.4.11) — A afirma que satisfaz e não satisfaz. Hoje o campo tem
    preenchimento `--surface-2`, que é a pista visual; trocar por branco +
    fio fraco REMOVE a pista. Para 3:1 seriam ~.47 de alfa; alternativa
    é manter o preenchimento afundado.
  - `--dia-*` como texto sobre surface-2 (risco A.6): 6,26–7,06 em todas —
    o risco não se confirma.
- **Testes que as três contradizem sem citar** [LIDA NO CÓDIGO]:
  - `test_the_bars_fill_from_zero_when_the_screen_opens` exige
    `@keyframes encher` + `animation: encher`: a suíte DIZ que encher do
    zero ao abrir é "a única recompensa desta tela". "Anima só o que mudou"
    precisa citar isso e dizer por que a razão caiu — nenhuma cita. O
    `varrer` do anel, ao contrário, não tem teste e pode sair.
  - `test_pressing_anything_uses_the_same_scale` trava `.96` (uma escala,
    qualquer uma): A propõe .98, B e C .97. Trivial, mas mostra que não
    leram.
  - `test_a_regra_lida_e_mesmo_a_da_corrida` cobra `font-weight: 760`:
    A e C citam; B não.
  - `_tokens()` em `config/tests.py` só lê `#rrggbb` literal (7 chars):
    o "Ferro escrito UMA vez em variáveis privadas" da C faria o bloco
    dark conter `var(--_bg-foco)` e o teste de contraste do escuro ler
    zero tokens. Precisa escrever os hex literais nos dois blocos ou
    ensinar o parser — custo real, não citado.
- **Precedente que ajuda a C** [LIDA NO CÓDIGO `templates/base.html:88`]:
  `<body class="{% if … %}tem-tabbar{% endif %}">` já é classe escrita
  pelo servidor. `body.modo-foco` é a mesma técnica, uma linha.

## Notas (0–10 por critério; total em 60)

| critério | A Respiro | B Pista | C Mesa & Ferro |
|---|---|---|---|
| identidade própria | 6 | 8 | 8 |
| premium vs referências | 6 | 8 | 7 |
| consistência sistêmica | 9 | 7 | 9 |
| viabilidade no CSS atual | 7 | 6 | 6 |
| acessibilidade / contraste | 5 | 7 | 6 |
| respeita decisões medidas | 7 | 6 | 7 |
| **total** | **40** | **42** | **43** |

### A — "Respiro"

É o V2 levado até o fim: tinta em vez de sombra, número leve, verde raro.
Tudo mecanizável (7 tamanhos, 4 pesos, 2 raios, 1 primário) e a
consistência é a melhor das três. O problema é de tese: é EXATAMENTE a
gramática de Oura/Apple Saúde/Headspace, e o dono disse que "mais limpo"
não basta. Lado a lado com uma referência, A parece a referência — e uma
pessoa não diria "isso é o NutriPlan". Separação de cartão a 1,057:1 e
hairline a 1,24 são pensadas para OLED em quarto escuro; o app é aberto na
academia sob lâmpada fria. `--text-3` a 4,72 reprova a margem da suíte e o
rename esconderia a reprovação. O que A tem de melhor é a DISCIPLINA, e
ela se enxerta em qualquer direção.

### B — "Pista"

A única com mock, e o mock prova o argumento: o "40" a 72px, o bloco
escuro e o botão verde-vivo são a diferença mais VISÍVEL contra Hevy/Strong,
e o artboard da Home (2.830 display, cardápio em linhas com hora tabular) é
o melhor desenho de Home dos três. Onde B perde: (1) a metade de
alimentação, hidratação e progresso fica com identidade emprestada da
Direção A com quinas retas — o placar claro é "mais limpo"; (2) a
`--surface-focus` deixa de responder "o que eu faço agora" (doutrina do
`:root`) e passa a responder "onde está o treino": na Home o AGORA vira
filete e o bloco escuro é o Treino — a superfície de foco muda de pergunta;
(3) condensada 800 + preto + canto reto + tag "PR" é o vocabulário
Nike/Strava, o risco que o próprio documento chama de "app de corrida
masculino"; (4) a paleta cresce (cinco `-viva`) em vez de encolher; (5) erro
de medição em `--folha`/surface-3.

### C — "Mesa & Ferro"

A tese mais verdadeira para ESTE produto: comer e treinar são atividades com
luz diferente, e a unidade se prova pelo que não muda (raio, tipo, ícone,
grade). É a única direção que dá calor (linho) sem mascote nem foto — a
"substância sem calor" que as notas de referência apontaram como a lacuna
do NutriPlan contra Lifesum/Yazio. O ponto de ícone na cor do pilar é
pequeno, barato e ligado ao logo. A regra "modo-foco só redefine cor,
densidade e sombra" é testável e impede os dois apps. Onde C perde: não tem
mock, então "premium" é [HIPOTÉTICA]; o prato repete os três sinais que A
denuncia no hero atual (sombra + fio + raio 24); Ferro `--text-mute` a 4,68
reprova a margem; o mecanismo "escrito uma vez" quebra o parser do teste de
contraste; e "dark = Ferro em todo o app" é decisão que o próprio documento
deixa para o dono.

## Recomendação: **C — Mesa & Ferro**, com enxertos de B e A

Por quê C e não B, sendo que B tem 8 em premium: o brief pede diferença
clara CONTRA REFERÊNCIAS, e B demonstra isso só no treino — na alimentação
(a aba que abre o app, a área principal do produto) B é a Direção A com
quinas retas. C tem UMA tese que cobre o app inteiro, e a tese nasce do
produto (dois pilares de luz diferente) e não de um gênero de app. O que
B tem de comprovadamente melhor — o cockpit — cabe DENTRO do regime Ferro
de C sem contradizer nada: Ferro é onde a pista de B mora.

Por quê C e não A: A ganha em consistência empatada e perde em identidade e
em premium — e "mais limpo" foi o veredito insuficiente do V2.

### Enxertos obrigatórios (de B)

1. **Cockpit de carga** da execução: número a `clamp(3.5rem, 18vw, 4.5rem)`
   (72px a 390, 56 a 320) no lugar do `--texto-display-foco` de 56 fixo;
   régua de 2px `--folha` embaixo; −/+ de 56×56; "Última vez 40 kg × 8 ·
   07/09" numa linha fixa acima. Modelo de evento, `op_id` e fila não mudam
   (CROSS-WORKFLOW: TRAINING para a rota).
2. **Poster como capa 16:9 sangrando no topo** do cartão da execução, e o
   vídeo aberto substituindo a capa NO MESMO lugar com moldura de 8px —
   nunca dois players (CROSS-WORKFLOW: TRAINING para a curadoria).
3. **Placar 3-up `.stat`** com o MESMO desenho no painel, na execução e na
   corrida (valor 22/forte + unidade 11 + rótulo caps mute).
4. **CTA sticky em `bottom: calc(var(--tabbar-h) + 8px)`** na
   `--camada-flutuante` — medido: hoje a 320×568 o CTA fica em y=593.
5. **A régua "um bloco de esforço por tela" como TESTE**: em C vira "só
   `/treino/agora/` e a corrida em andamento escrevem `modo-foco`", contado
   por template — a régua de B, transposta.
6. **Barras/rails e a ficha de outro dia em cabeçalho claro** ("a cor diz
   não é hoje") — C já tem a regra do `<div>`; a cor reforça.

### Enxertos obrigatórios (de A)

7. **Um primário por tela, contado por teste** (`.btn--primary` ≤ 1 por
   template renderizado); a refeição da vez fica com tonal.
8. **Tirar a sombra do prato na Mesa**: fio de pilar 3px + `--surface` +
   raio 24 já são dois sinais; sombra fica SÓ na barra de baixo. Mesa
   termina com uma sombra na tela, não duas.
9. **`.metrica` com unidade colada na linha de base** e a regra "peso leve
   só ≥ 32px" — mesmo que C use 780 no display, a regra impede 450 em 12px
   de virar cinza apagado.
10. **Chevron único em CSS** e o sprite com traço acompanhando o peso do
    texto (C: traço 2 com 450/560 está coerente; não subir para 2,25 como B).
11. **`--dia-*` só como TEXTO do chip** sobre `--surface-2` (6,26–7,06:1
    medidos), sem disco colorido de 44px.

### Correções que a C precisa ANTES de virar lote

- Ferro `--text-mute` → `#96a29c` (5,10 no pior fundo; 5,79 em brand-soft).
- Bloco escuro com hex LITERAIS (ou parser estendido) para
  `test_dark_theme_*` continuar medindo.
- Campo: manter preenchimento `--surface-2` como pista de fronteira OU
  `--fio-forte` a ≥ .46 de alfa (2,93:1) — o .22 proposto mede 1,58.
- `encher` continua ao abrir (teste e docstring dizem por quê); só `varrer`
  sai. Escala de toque `.96`, não `.97`. `font-weight: 760` da corrida
  editado com razão escrita, no mesmo commit.
- Decisão do dono, explícita: tema escuro do sistema = Ferro em TODO o app
  (perde a Mesa) ou Ferro só nas superfícies com densidade de Mesa. Minha
  recomendação: Ferro inteiro — é o que mantém "um bloco de valores, dois
  gatilhos" e evita um terceiro regime.
- Prato do peso e a ordem do Progresso: CROSS-WORKFLOW: UX. Regra de
  prescrição, rota da classe `modo-foco`, curadoria de vídeo:
  CROSS-WORKFLOW: TRAINING.

### O que NÃO enxertar

- De B: `--surface-focus` escura na Home (o AGORA volta a ser a superfície
  de foco, e o foco é "o que fazer agora", não "onde está o treino");
  condensada; canto reto nas barras; `-viva` como família de tokens (em C
  o Ferro já tem os seus valores); mini-bloco escuro na Home — regime é por
  tela, não por cartão.
- De A: cartão sem fronteira nenhuma (1,057:1) e hairline como único
  separador; renomear `--text-mute`; 300 como peso de display (C usa 780 e
  o eixo óptico faz o trabalho de "leve" no corpo).

## Arquivos desta sessão

- `juiz2-contraste.py` — recálculo WCAG dos pares das três direções.
- `juiz2-medir-home.json` — baseline da Home (medir.js, 390px).
- `shots/juiz2-execucao-320.png` — execução a 320×568, CTA fora da dobra.
