# TREINO.md — o contrato do gerador de treino

Este documento decide QUANTO uma sessão tem e QUANTO uma semana aguenta, por
nível e por tipo de dia: exercícios por grupo, séries por exercício, séries
diretas por sessão, séries por grupo na semana, descanso e ordem. É para o
motor de treino o que `DESIGN.md` é para o visual. **Todo número escrito nas
tabelas tem um teste em `workouts/test_treino_md.py`**, que lê as tabelas
deste arquivo (uma linha por combinação, faixa como `a–b` ou inteiro) e as
compara com o que o gerador entrega. Mudar um número aqui sem mudar o motor
deixa a suíte vermelha; mudar o motor sem mudar aqui, também.

O vocabulário é o do `CLAUDE.md`: **letra** é a sessão do calendário (A, B, C);
**opção**, uma das versões equivalentes da mesma letra; **grupo anunciado**, o
que o nome da sessão promete (`WorkoutTemplate.main_groups`); **complementar**,
o que o modelo traz sem prometer (trapézio, antebraço, panturrilha, core);
**composto principal**, o composto de maior dose de cada grupo, um por grupo por
sessão. **Série direta** é a do grupo que o exercício trabalha; **série efetiva**
conta a direta por 1 e cada `secondary_muscles` por 0,5 (`PESO_SECUNDARIO`) — o
teto semanal é cobrado em efetivas, porque um tríceps de supino não substitui
um tríceps de tríceps, mas também não vale zero.

## Níveis

Três níveis, com as chaves `iniciante`, `intermediario` e `avancado` — as de
`Profile.experiencia`. Quem não respondeu é tratado como intermediário, o que
o app já praticava antes da pergunta existir. O nível muda a DOSE — quantos
exercícios, quantas séries, quanto a semana aguenta —, e não QUAIS exercícios
entram: rebaixar o agachamento por ser "complexo demais para iniciante" seria
tirar de quem está começando o movimento que mais interessa.

## Tipos de dia

Seis tipos, um por resposta a "quantos grupos esta sessão promete". A chave é
a do teste, e o mapa para os modelos de `splits.json` está fechado:

| chave | o que é | modelos |
|---|---|---|
| `um_grupo` | um grupo grande anunciado: Peito; Costas; Ombros (trapézio entra como complementar) | `abcde A`, `abcde B`, `abcde D` |
| `dois_grupos` | um grande e um pequeno: peito/tríceps, costas/bíceps, pernas/ombros; em Braços bíceps e tríceps são os dois pequenos (3 cada — o catálogo tem seis de cada) | `abc2 A–C`, `abcd A–C`, `abcde E` |
| `tres_grupos` | um grande e dois pequenos: peito/tríceps/ombro; costas/bíceps + antebraço e trapézio dividindo a terceira cota; quadríceps e posterior dividindo o grande + panturrilha | `abc A–C`, `abcde C` |
| `inferior` | quadríceps (grande) e posterior (pequeno); panturrilha e core complementares | `ab B` |
| `superior` | peito e costas (grandes); ombros, bíceps e tríceps (pequenos) | `ab A` |
| `full` | corpo inteiro num dia: quadríceps, peito, costas e posterior (grandes); ombros, bíceps e tríceps (pequenos) | `full A` |

Em "Pernas e ombros" quadríceps e posterior dividem a cota do grande. Em
"Costas, bíceps, antebraço e trapézio" antebraço e trapézio dividem a cota do
segundo pequeno. **Panturrilha e core são complementares em todo tipo de
dia, mesmo quando anunciados** ("Pernas completo"): no máximo dois exercícios
por opção, de duas a quatro séries — a cota de EXERCÍCIOS de pequeno não
vale para eles, e os testes cobram `min(pequeno, 2)`; as séries deles
entram em `series_diretas` só onde o nome os promete. `abcd D` ("Complementares") não é nenhum
dos seis: é o dia que só tem complementar, a Tabela A não o cobre, e ele
segue a dose do catálogo sob o teto da Tabela B — a única sessão fora do
contrato, dita aqui para ninguém procurar a linha.

## Tabela A — Por sessão

`exercicios_grande` e `exercicios_pequeno` valem POR GRUPO da classe (em
`superior`, 2 grandes × `exercicios_grande` + 3 pequenos × `exercicios_pequeno`).
`series_por_exercicio` é a faixa de qualquer exercício da sessão montada: o
composto principal no topo, o isolador podendo ficar no piso — e dois cortes
ainda levam um isolador a 2: o relógio (`escolher_para_o_tempo`) e o teto
semanal (`aparar_opcoes`, quando o grupo bate no `teto_efetivo` da Tabela B:
o ombro de "Pernas e ombros" a 2× com o secundário de todos os supinos e
remadas). Abaixo de 3 sem uma dessas duas razões é defeito, e o teste cobra.
`series_diretas` soma os exercícios dos grupos ANUNCIADOS (`main_groups` do
modelo — a panturrilha conta em "Pernas completo", que a anuncia, e não em
"Costas e bíceps", onde trapézio e antebraço são complementares); o
complementar não anunciado (zero a dois por opção, de duas a três séries)
fica fora dessa soma — é a mesma conta do teste dourado, que só olha "Peito e
tríceps". `duracao_min` é medida por `segundos_da_sessao` sobre a sessão
inteira, complementares incluídos, com **Completo** (teto 90): é a sessão
que nada corta pelo relógio; Padrão para em 60 e Rápido em 30.

**A tabela foi MEDIDA, não estimada** (17/09/2026): as duas colunas da
direita cobrem, arredondadas para fora de 5 em 5 minutos, todas as letras
de todos os modelos de cada tipo, nas duas opções, com o catálogo de 63
ativos — `scratchpad/dose_medir_tudo.py` na sessão da missão. Onde a
medição discordou da primeira versão, a medição venceu, e o motivo está na
lista abaixo.

| nivel | tipo_de_dia | exercicios_grande | exercicios_pequeno | series_por_exercicio | series_diretas | duracao_min |
|---|---|---|---|---|---|---|
| iniciante | um_grupo | 3 | 0 | 2–3 | 10–14 | 30–40 |
| iniciante | dois_grupos | 3 | 2 | 2–3 | 14–18 | 40–60 |
| iniciante | tres_grupos | 3 | 2 | 2–3 | 16–20 | 40–55 |
| iniciante | inferior | 3 | 2 | 2–3 | 14–18 | 50–65 |
| iniciante | superior | 2 | 1 | 2–3 | 18–24 | 55–70 |
| iniciante | full | 1 | 1 | 2–3 | 18–24 | 55–70 |
| intermediario | um_grupo | 4 | 0 | 3–4 | 12–20 | 40–50 |
| intermediario | dois_grupos | 4 | 3 | 3–4 | 21–28 | 55–75 |
| intermediario | tres_grupos | 4 | 2 | 3–4 | 21–28 | 55–70 |
| intermediario | inferior | 3 | 3 | 3–4 | 20–26 | 60–75 |
| intermediario | superior | 2 | 1 | 3–4 | 24–30 | 70–80 |
| intermediario | full | 1 | 1 | 3–4 | 20–26 | 65–75 |
| avancado | um_grupo | 4 | 0 | 3–4 | 16–24 | 40–55 |
| avancado | dois_grupos | 4 | 3 | 3–4 | 22–28 | 55–80 |
| avancado | tres_grupos | 4 | 2 | 3–4 | 22–32 | 55–75 |
| avancado | inferior | 3 | 3 | 3–4 | 20–26 | 60–75 |
| avancado | superior | 2 | 1 | 3–4 | 24–30 | 70–80 |
| avancado | full | 1 | 1 | 3–4 | 20–26 | 65–75 |

A linha de referência é o intermediário em `dois_grupos`: 4 exercícios do
grande, 3 do pequeno, 3 a 4 séries, 21 a 28 diretas — sete exercícios que
fecham a semana com peito=4 e tríceps=3, o contrato de variedade do
`CLAUDE.md`. As outras dezessete derivam dela, e cada coluna fecha com as
vizinhas: exercícios × piso não passa do piso de `series_diretas`, e
exercícios × topo mais o complementar cobre o topo.

**O que mudou em relação à referência do dono, e por quê** — cada ajuste tem
uma conta, escrita para poder ser desfeita:

- **iniciante em `2–3`, não `3`**: o composto principal fica em 3 (o supino
  de quatro do catálogo vira três para ele); acessório e isolador em 2 ou 3.
  A ACSM (2009) põe o novato em 1 a 3 séries — e sete exercícios travados em
  3 dão 21, onde nenhuma faixa chega. É o mesmo modelo dos outros níveis com
  a dose do nível: o iniciante aprende os mesmos movimentos com menos série,
  e `preencher_ate_a_faixa` desce até o topo da faixa antes de subir.
- **`tres_grupos` iniciante com 3 do grande, não 2**: na divisão ABC o grupo
  cai UMA vez, e dois exercícios de peito a 3 séries são 6 na semana — abaixo
  do piso 8 da Tabela B. Com 3 são 9.
- **`tres_grupos` com a MESMA faixa de séries de `dois_grupos` e o grande em
  4 (intermediário e avançado), os pequenos em 2**: o teste dourado vale
  para "Peito, tríceps e ombro" de 3 e 4 dias do mesmo jeito que para "Peito
  e tríceps" — 4 de peito, 21–28 séries, 55–65 minutos —, e três pequenos
  em 3 dariam dez exercícios e 31 séries antes de qualquer preenchimento.
  Quatro de peito, dois de tríceps, dois de ombro: oito exercícios, a ficha
  de academia de peito com dia de ombro.
- **`superior` com 1 por pequeno, não 2**: 2|2 são dez exercícios e 30 a 40
  séries, o dobro da faixa 22–28 do próprio brief; 3|2 são doze.
- **`full` com 1 por grande em todos os níveis**: são quatro grandes; dois por
  grande dão onze exercícios e mais de 85 minutos para quem treina uma vez por
  semana. O nível muda a dose por exercício, não a lista.
- **`superior` e `full` iniciante 18–24**: nove exercícios por opção, e os
  compostos principais (três em `superior`, quatro em `full`) ficam em 3 —
  medido, 21 nos dois.
- **`um_grupo` intermediário 12–20 e avançado 16–24**: "Peito" e "Costas"
  de cinco dias têm QUATRO exercícios por opção, e quatro a quatro séries
  são 16 — o topo do brief (20 e 24) só chega em "Ombros", que tem seis.
  Mais catálogo de peito e de costas é o que devolve as linhas do brief.
- **`dois_grupos` avançado 22–28, não 26–32, e o avançado igual ao
  intermediário em Completo**: sete exercícios a quatro séries são 28, o
  máximo físico da linha; e "Braços" fecha em 23–24. O que separa os dois
  níveis hoje é a Tabela B — o teto semanal deixa o avançado com 28 em
  "Costas e bíceps" onde o intermediário para em 26 — e não a sessão. Cinco
  de peito para o avançado é dívida de catálogo, dita abaixo.
- **`inferior` com 3 do grande, e o avançado com 4|3, 3|3, 3|3 e 2|1 em vez
  de 5|3, 4|3, 5|3 e 3|1 — DÍVIDA DE CATÁLOGO, não decisão de treino**: cada
  opção recebe metade do modelo, e o modelo não passa do catálogo ativo: seis
  quadríceps dão 3 por opção; oito peitos dão 4; seis ombros dão 3; quatro
  peitos em `superior` dão 2. O avançado ganha o resto pela dose (4 séries
  em tudo, 28 a 32 diretas), não pela quantidade. O que devolve as linhas do
  brief: 4 quadríceps, 2 peitos, 2 tríceps e 2 ombros a mais no catálogo,
  com mídia conferida (`docs/superpowers/specs/2026-09-17-ficha-de-verdade-design.md`).
- **durações 10 a 15 minutos abaixo do brief**: o brief mediu relógio de
  academia; a coluna mede `segundos_da_sessao` — 40 s por série, 80/60 s de
  descanso, 5 min de aquecimento, 130 s de aproximação por composto, nada
  depois do último exercício. É o número que a ficha mostra e o único que um
  teste confere. Simulado linha a linha nas duas pontas da faixa de séries e
  arredondado para fora, de 5 em 5.

## Tabela B — Por semana, por grupo, pela FREQUÊNCIA com que o grupo cai na semana

Duas colunas com papéis DIFERENTES, e a diferença é a decisão do dono de
16/09/2026 ("não baixe a sessão para caber"):

- `series_diretas_semana` é a **faixa-alvo da MÉDIA do ciclo** para um grupo
  treinado `ocorrencias` vezes por semana. É o que a literatura chama de
  volume semanal produtivo: Schoenfeld, Ogborn & Krieger (2017), a
  meta-análise dose-resposta, acham ganho crescente até ≥ 10 séries por
  grupo por semana, com a curva achatando acima disso; Helms e Baz-Valle
  (2022) põem o intermediário em 10–20; e o MRV de Israetel (o máximo
  recuperável) fica perto de 20–22 para peito e quadríceps treinados 1× e
  sobe com 2 a 3 sessões — é daí que a linha `2` vai até 24 para os grupos
  grandes. A média é medida sobre o ciclo inteiro da divisão com a ROTAÇÃO
  CONTÍNUA (abaixo): em `abc2` com 5 dias cada letra cai 5 vezes em 3
  semanas, a frequência de todo grupo é 5/3, e a faixa que vale é a
  interpolada entre `1` e `2`;
- `teto_efetivo` é o **teto de APARO da PIOR semana** — a semana do ciclo em
  que a letra cai `ocorrencias` vezes —, cobrado em séries EFETIVAS
  (secundária vale meia) no pior caso das opções. Ele é deliberadamente MAIOR
  que o topo da faixa mais os secundários porque a sessão do teste dourado
  (4 de peito, 21–28 séries) não é reduzida para a semana caber: 16 de peito
  duas vezes são 32 diretas, e o aparo só entra acima de 40. A margem é
  ABSOLUTA (8 a 2×, 9 a 3×, igual em todo nível — o secundário vem do
  catálogo, não do nível; com margem proporcional o iniciante a 2× perdia o
  terceiro peito).

`ocorrencias` é quantas sessões da semana TREINAM o grupo — direto ou como
secundário (`services.grupos_treinados`), pela divisão E pela frequência: o
ombro de "Pernas e ombros" cai três ou mais, porque metade de cada supino e
de cada remada é ombro; contar só o anunciado dava ao ombro o teto de UMA
vez (23) com vinte efetivas vindas dos outros dias, e o aparo tirava um dos
três exercícios de ombro do dia que se chama "Pernas e ombros". Com a
rotação, toda letra cai o MÁXIMO em alguma semana (`ocorrencias_das_letras`):
em 5 dias com ABC, A, B e C recebem o teto de 2× — e "Pernas e ombros"
deixou de ser a letra de 1×.

| nivel | ocorrencias | series_diretas_semana | teto_efetivo |
|---|---|---|---|
| iniciante | 1 | 8–12 | 15 |
| iniciante | 2 | 12–18 | 28 |
| iniciante | 3 | 16–22 | 33 |
| intermediario | 1 | 10–20 | 23 |
| intermediario | 2 | 16–24 | 40 |
| intermediario | 3 | 20–28 | 45 |
| avancado | 1 | 12–22 | 28 |
| avancado | 2 | 18–26 | 45 |
| avancado | 3 | 22–30 | 50 |

### A rotação contínua do ciclo, e a média medida em 3 semanas

Até 16/09/2026 o ciclo recomeçava toda segunda-feira: em 5 dias com ABC era
A B C A B toda semana, peito e costas caíam 2× e "Pernas e ombros" 1× —
quadríceps em 7 diretas, ombro em 9, para sempre. O desequilíbrio era do
CALENDÁRIO, não do motor. Desde 17/09 a semana seguinte continua de onde a
anterior parou (A B C A B → C A B C A → B C A B C; `TrainingPlan.
inicio_do_ciclo`, `services.letra_do_dia`), e em 3 semanas cada letra cai 5
vezes. O plano de antes da rotação continua preso ao dia da semana (não é
remontado; a Home pergunta), como manda a política da Fase 5.

Medido em 17/09/2026, média semanal de séries DIRETAS por grupo sobre 3
semanas, no pior caso por dia (a opção mais pesada no grupo):

| perfil | peito | costas | tríceps | bíceps | ombro | quadríceps | posterior | panturrilha | trapézio | antebraço | core |
|---|---|---|---|---|---|---|---|---|---|---|---|
| intermediário 5d abc2, Padrão | **25,0** | 21,7 | 16,7 | 11,7 | 15,0 | 11,7 | 10,0 | 5,0 | 5,0 | 3,3 | 5,0 |
| intermediário 5d abc2, Completo | **26,7** | **26,7** | 18,3 | 16,7 | 15,0 | 13,3 | 13,3 | 6,7 | 5,0 | 5,0 | 5,0 |
| intermediário 4d ABC, Padrão | 17,3 | 18,7 | 8,0 | 6,7 | 8,0 | 10,7 | 10,7 | 10,7 | 4,0 | 4,0 | 4,0 |
| intermediário 3d ABC, Padrão | 13,0 | 14,0 | 6,0 | 5,0 | 6,0 | 8,0 | 8,0 | 8,0 | 3,0 | 3,0 | 3,0 |
| avançado 5d abc2, Completo | **26,7** | **26,7** | 18,3 | 20,0 | 18,3 | 13,3 | 13,3 | 6,7 | 5,0 | 5,0 | 5,0 |

O que a tabela diz, sem enfeite: pernas e ombro entraram na faixa de 10–20
(era 6–9 com o ciclo fixo); tríceps, bíceps e ombro, que só têm 2–3
exercícios por sessão, ficam entre 5 e 18 diretas mais o secundário dos
compostos; panturrilha, trapézio, antebraço e core são complementares (1–2
exercícios, 3–7 por semana) por decisão de modelo. E **peito e costas do
`abc2` passam do topo de 24 por 1 a 3 séries** — 25 no Padrão, 26,7 no
Completo —, porque a sessão de 4 exercícios do teste dourado a 5/3 por
semana dá exatamente isso. É o preço escrito da decisão de não baixar a
sessão; fica dentro do MRV de Israetel para peito a ≥ 2×, e é a única
linha em que a média do ciclo passa da faixa-alvo.

**Tolerância da média (decisão do dono, 17/09/2026): peito 25,0 no Padrão
está ACEITO, e o golden não baixa.** O teste da média
(`workouts/test_rotacao.py`, `OVolumeMedioEmTresSemanasTests`) cobra, para
o grupo grande a 2× no perfil do teste dourado (intermediário, 5 dias,
`abc2`, Padrão), o ALVO de 24 com tolerância de ± 2 — **26 é o teto da
média** —, e lê os dois números da tabela abaixo. A razão: ficha real de
academia faz 26–28 séries de peito por semana, e uma série a mais na média
de 3 semanas é ruído do ciclo (5 sessões em 3 semanas dão frações de 1/3),
não excesso. O Completo (26,7 de peito e costas) fica FORA da tolerância de
propósito: é a ficha inteira que a pessoa pediu ao escolher 90 minutos, e
está medido na tabela acima — cobrado pelo teste que impede a tabela de
envelhecer, não pelo teste da tolerância.

| medida | alvo | tolerancia |
|---|---|---|
| media_3_semanas_grande_2x | 24 | 2 |

A referência "10 a 20 séries por grupo por semana" é a de Schoenfeld,
Ogborn & Krieger (2017), a de Helms e a de Baz-Valle (12–20), e descreve o
grupo treinado UMA vez — de onde vem a linha `1`. A faixa SOBE com a
frequência porque o que limita a sessão é a fadiga local e o que limita a
semana é a recuperação: Israetel descreve o MRV subindo com 2 a 3 sessões por
semana, e Schoenfeld (2016, 2019) mede a frequência ajudando quando o volume
é alto. O teto de aparo sobe mais que a faixa pela conta que ancora o teste
dourado: **na pior semana do ciclo, "Peito e tríceps" duas vezes soma 32 de
peito** (4 exercícios × 4 séries × 2), e o aparo só pode entrar acima
disso (40 efetivas) — com o teto em 33 (uma primeira versão deste documento)
ele aparava a sessão a 24 séries e 57 minutos, que é o que o dono proibiu. A
média do ciclo é outra conta, e está medida acima. O iniciante a 2× ficou
em 12–18 e os tetos acompanharam. Quem quiser a semana mais curta escolhe
"Padrão — até 60 minutos", e o relógio apara antes do teto.

Três regras de leitura, para o teste e para quem for mexer no motor:

- **O teto de B vence A; a faixa de B é média.** A é a sessão, e ela vale
  inteira (o dourado); o teto efetivo de B é o que `aparar_opcoes` cobra na
  pior semana, e é ele que segura o ciclo — a 3× (`abc2` a 7 dias) o peito do
  intermediário fica em 3 por exercício, não em 4. A faixa de B não é cobrada
  por sessão nem por semana: é a média do ciclo, medida na tabela acima, e
  onde a sessão a ultrapassa isso está escrito, não escondido.
- **O grande é medido em DIRETAS; o pequeno, em EFETIVAS.** Tríceps, bíceps e
  ombros recebem metade de cada série dos compostos do dia, e os marcos da
  literatura são menores para eles por isso. Tríceps em `dois_grupos`
  intermediário a 2×: 12 diretas + 6 secundárias = 18 por sessão, 36 na
  pior semana — dentro do teto de 40. O teto vale em efetivas para os dois.
- **Duas divisões ficam abaixo do piso por construção, e uma frequência fica
  acima do topo.** `superior` no iniciante e no intermediário (peito com 2
  exercícios, 2×: 10 a 16) e `full` em todos os níveis (um exercício por
  grupo: 3 a 4) não alcançam o piso de B — é o preço de cinco ou sete grupos
  numa sessão, dito aqui em vez de fingido; ali o teste cobra só o teto. E a
  letra três vezes (`abc2` a 7 dias) passa do topo na pior semana: 4
  exercícios a 3 séries são 36 — vale o teto de 45, e a sessão NÃO perde o
  quarto exercício para caber numa faixa-alvo: trocar variedade contratada
  por número é o defeito que o 4/4/3/3 impede.

## Tabela C — Descanso e ordem

| tipo | descanso_s |
|---|---|
| composto | 80 |
| isolador | 60 |

São os dois valores que o catálogo já escreve em toda linha de `splits.json`:
Schoenfeld (2016) e Grgic (2017) medem descanso de um minuto ou mais como
suficiente para hipertrofia e o mais longo como melhor para o composto pesado;
80 e 60 são os degraus que `segundos_da_sessao` já conta ("1:20 min", "1 min").

A ordem tem três regras, e as três são de prescrição, não de estética:

- **o composto principal do grande abre a sessão** — é o que mais carga move e
  o que mais sofre com fadiga acumulada; dentro de cada grupo, compostos antes
  de isoladores; grande antes de pequeno; os complementares fecham, e um
  complementar realocado de outra letra entra por último;
- **pelo menos um composto por grupo anunciado que tenha composto no
  catálogo** — peito, costas, quadríceps, posterior, ombros e tríceps. Bíceps,
  antebraço, trapézio, panturrilha e core são isoladores por natureza;
- **num grupo GRANDE, isoladores são no máximo metade dos exercícios dele**:
  3 → 1 isolador, 4 → 2, 5 → 2. O pequeno pode ser todo isolador.

## Mapa de equipamento — o que cada perfil tem à mão

Quatro respostas no perfil (`accounts.models.Equipamento`, pergunta na
etapa 2 do onboarding e no Perfil, 17/09/2026), e o motor FILTRA o catálogo
antes de prescrever (`services.prescrever_opcoes(..., permitidos=)`). A
chave é o `Exercise.equipment` do catálogo; a coluna lista o que o perfil
PODE usar.

| perfil | equipamentos |
|---|---|
| completa | barbell, dumbbell, machine, cable, bodyweight |
| basica | dumbbell, machine, cable, bodyweight |
| casa_halteres | dumbbell, bodyweight |
| peso_corporal | bodyweight |

Como o filtro obedece, e por que ele não é um `filter()`: a prescrição não
SELECIONA exercícios — copia MODELOS curados de `splits.json` —, então tirar
o que o perfil não tem abriria buraco no modelo (medido em 10/09/2026: oito
modelos perdiam grupo em casa com halteres). O item fora do perfil é
SUBSTITUÍDO por exercício ativo do MESMO PADRÃO (`Exercise.padrao`) e do
mesmo grupo dentro do perfil que ainda não esteja no modelo, com a mesma
dose — supino reto com barra vira supino com halteres, mesmas quatro
séries; agachamento livre vira goblet. Sem substituto, o item sai, e a
cadeia de sempre (opções, preenchimento, teto, tempo) roda sobre o que
sobrou. `completa` não filtra nada e é a ficha de sempre: o teste dourado
e o gate por letra valem nela e em `basica`; `casa_halteres` e
`peso_corporal` são MEDIDOS e o que falta ao catálogo está listado no
`BACKLOG.md`. Perfil que muda torna a ficha inválida e remonta, como nível
e faixa de duração (`TrainingPlan.equipamento` é retrato); quem já tinha
conta ficou em `completa` sem remontar.

## Como o motor obedece

Leitura, não decisão — o que decide está acima. `workouts/doutrina.py` lê as
três tabelas deste arquivo e é a única porta de entrada dos números no motor:
`TETO_POR_EXPERIENCIA` (12/20/24) e `FAIXA_POR_TETO_SEMANAL` passam a ser
derivados da linha — 12/20/24 era o teto de UMA ocorrência sem dizer que era.

- `preencher_ate_a_faixa` (`workouts/opcoes.py`) sobe isoladores e acessórios,
  até 4 por exercício (`TETO_SERIES_POR_EXERCICIO`), até a faixa de
  `series_diretas` da linha de A — só enquanto a semana do grupo cabe em B;
- `aparar_opcoes` (`workouts/opcoes.py`) cobra o `teto_efetivo` da linha
  (nível, ocorrências) de B, em efetivas, no pior caso das opções
  (`services.volume_da_semana`) — com as três travas de `aparar_volume_semanal`;
- `escolher_para_o_tempo` (`workouts/services.py`) corta pelo teto de tempo,
  nas cinco camadas de sempre: Rápido 30, Padrão 60, Completo 90
  (`TETO_POR_DURACAO`). `Completo` valeu 65 entre 16 e 17/09/2026, enquanto
  o catálogo de 35 ativos não passava de 61 minutos; com os 63 ativos e
  estas faixas ele voltou a 90;
- a versão rápida é a opção escolhida passando por `escolher_para_o_tempo` a
  40 minutos (`TETO_RAPIDO_MIN`); não é uma terceira ficha;
- `segundos_da_sessao` mede `duracao_min`; `volume_efetivo` mede `teto_efetivo`.

## Fontes

Só o que existe; nenhum DOI inventado.

- Schoenfeld BJ, Ogborn D, Krieger JW. *Dose-response relationship between
  weekly resistance training volume and increases in muscle mass: a systematic
  review and meta-analysis.* Journal of Sports Sciences, 2017; 35(11):
  1073–1082.
- Schoenfeld BJ, Contreras B, Krieger J, Grgic J, Delcastillo K, Belliard R,
  Alto A. *Resistance training volume enhances muscle hypertrophy but not
  strength in trained men.* Medicine & Science in Sports & Exercise, 2019;
  51(1): 94–103.
- Schoenfeld BJ, Ogborn D, Krieger JW. *Effects of resistance training
  frequency on measures of muscle hypertrophy: a systematic review and
  meta-analysis.* Sports Medicine, 2016; 46(11): 1689–1697.
- Schoenfeld BJ, Grgic J, Krieger J. *How many times per week should a muscle
  be trained to maximize muscle hypertrophy? A systematic review and
  meta-analysis of studies examining the effects of resistance training
  frequency.* Journal of Sports Sciences, 2019; 37(11): 1286–1295.
- Baz-Valle E, Balsalobre-Fernández C, Alix-Fages C, Santos-Concejero J. *A
  systematic review of the effects of different resistance training volumes on
  muscle hypertrophy.* Journal of Human Kinetics, 2022; 81: 199–210.
- Helms E, Morgan A, Valdez A. *The Muscle and Strength Pyramid: Training.*
  2ª edição, 2019.
- Israetel M. *Training Volume Landmarks for Muscle Growth.* Renaissance
  Periodization, divulgação (MEV/MAV/MRV) — vocabulário, não evidência revisada.
- American College of Sports Medicine. *Progression models in resistance
  training for healthy adults.* Position stand. Medicine & Science in Sports &
  Exercise, 2009; 41(3): 687–708.
- Schoenfeld BJ, Pope ZK, Benik FM, et al. *Longer interset rest periods
  enhance muscle strength and hypertrophy in resistance-trained men.* Journal
  of Strength and Conditioning Research, 2016; 30(7): 1805–1812.
- Grgic J, Lazinica B, Mikulic P, Krieger JW, Schoenfeld BJ. *The effects of
  short versus long inter-set rest intervals in resistance training on measures
  of muscle hypertrophy: a systematic review.* European Journal of Sport
  Science, 2017; 17(8): 983–993.
