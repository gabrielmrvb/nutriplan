# CORRIDA.md — o contrato do plano de corrida

Este documento decide O QUE uma sessão de corrida pede, semana a semana, para
quem escolhe um plano de 5K ou 10K: quantas sessões por semana, quantas
semanas o plano tem, o que cada sessão manda fazer e quanto custa em
quilocaloria por quilo por quilômetro. É para o motor de corrida o que
`TREINO.md` é para o motor de musculação — **todo número escrito nas tabelas
tem um teste em `workouts/test_corrida_md.py`**, que lê as tabelas deste
arquivo com um segundo parser (não o que o motor usa) e compara com o que
`workouts/doutrina_corrida.py` entrega. Mudar um número aqui sem mudar o
motor deixa a suíte vermelha; mudar o motor sem mudar aqui, também.

O parser é o MESMO de `TREINO.md` — `workouts/doutrina_md.py::faixa` e
`::tabelas`, extraído de `workouts/doutrina.py` para não copiar a leitura de
tabela markdown uma segunda vez. A diferença entre os dois documentos é só o
conteúdo: aqui não há faixa (`a–b`), cada sessão pede um número fechado de
minutos, porque não existe "teto de tempo" cortando a sessão de corrida como
corta a ficha de academia — a pessoa corre o que o plano pede.

## Planos

Quatro combinações: duas distâncias (5K e 10K) e dois níveis (iniciante e
intermediário). As quatro têm oito semanas e três sessões por semana — é o
formato que Couch to 5K e os programas de Hal Higdon já usam, e mudar a
cadência por combinação obrigaria a tela a explicar "por que este plano é
diferente" em vez de só mostrar "Semana N de 8".

| plano | nivel | semanas | sessoes_por_semana |
|---|---|---|---|
| 5k | iniciante | 8 | 3 |
| 5k | intermediario | 8 | 3 |
| 10k | iniciante | 8 | 3 |
| 10k | intermediario | 8 | 3 |

## Sessões

96 linhas: 4 planos × 8 semanas × 3 sessões, numa tabela SÓ — o parser lê
`| a | b | c |` genérico e indexa pela tupla do cabeçalho, então duas tabelas
com o mesmo cabeçalho se sobrescreveriam em vez de somar. `sessao` é a ordem
dentro da semana (1, 2, 3), não um dia fixo do calendário — a pessoa escolhe
quando corre, e "sessão 1 da semana 3" é a primeira corrida que ela registrar
naquela semana, não necessariamente a de segunda-feira. As quatro
progressões, explicadas antes da tabela:

**5K iniciante — Couch to 5K, comprimido de nove para oito semanas.** O
programa original do NHS tem nove semanas, e a nona repete a oitava: a
diferença entre elas é só a confirmação de que 30 minutos corridos se
sustentam duas semanas seguidas, não uma prescrição nova. Aqui as duas se
fundem numa oitava semana só — a fonte, abaixo, diz isso de novo para quem
for comparar linha a linha com o original.

**5K intermediário — Hal Higdon 5K Intermediate.** Três sessões de formato
fixo — fácil, intervalos, longo —, progredindo cerca de 10% por semana. A
semana 4 e a semana 8 são mais leves: a 4ª porque três semanas de aumento
seguido pedem uma pausa antes de continuar, a 8ª porque é a semana da prova,
e a sessão longa dela É a prova.

**10K iniciante — Hal Higdon 10K Novice, convertido para quilômetro.** O
original mede em milhas, de 2,5 a 5 — aqui convertido para quilômetro e para
minuto, num ritmo fácil de referência (6 min/km, o de quem está começando).
Semana 4 e semana 8 são de descarga: a distância recua antes de seguir
crescendo, e a última sessão da semana 8 é a prova de 10 km, e não mais um
treino — é por isso que ela não segue a descarga das outras duas.

**10K intermediário — Hal Higdon 10K Intermediate.** O mesmo formato do 5K
intermediário — fácil, tempo run, longo —, com os números maiores que o 10K
pede. Semana 4 de descarga, semana 8 de descarga com a prova na sessão longa.

| plano | nivel | semana | sessao | descricao | minutos |
|---|---|---|---|---|---|
| 5k | iniciante | 1 | 1 | 8 × (1 min corrida + 1,5 min caminhada) | 25 |
| 5k | iniciante | 1 | 2 | 8 × (1 min corrida + 1,5 min caminhada) | 25 |
| 5k | iniciante | 1 | 3 | 8 × (1 min corrida + 1,5 min caminhada) | 25 |
| 5k | iniciante | 2 | 1 | 6 × (1,5 min corrida + 2 min caminhada) | 26 |
| 5k | iniciante | 2 | 2 | 6 × (1,5 min corrida + 2 min caminhada) | 26 |
| 5k | iniciante | 2 | 3 | 6 × (1,5 min corrida + 2 min caminhada) | 26 |
| 5k | iniciante | 3 | 1 | 2 × (1,5 min corrida + 1,5 min caminhada + 3 min corrida + 3 min caminhada) | 24 |
| 5k | iniciante | 3 | 2 | 2 × (1,5 min corrida + 1,5 min caminhada + 3 min corrida + 3 min caminhada) | 24 |
| 5k | iniciante | 3 | 3 | 2 × (1,5 min corrida + 1,5 min caminhada + 3 min corrida + 3 min caminhada) | 24 |
| 5k | iniciante | 4 | 1 | 3 min corrida + 1,5 min caminhada + 5 min corrida + 2,5 min caminhada + 3 min corrida + 1,5 min caminhada + 5 min corrida | 26 |
| 5k | iniciante | 4 | 2 | 3 min corrida + 1,5 min caminhada + 5 min corrida + 2,5 min caminhada + 3 min corrida + 1,5 min caminhada + 5 min corrida | 26 |
| 5k | iniciante | 4 | 3 | 3 min corrida + 1,5 min caminhada + 5 min corrida + 2,5 min caminhada + 3 min corrida + 1,5 min caminhada + 5 min corrida | 26 |
| 5k | iniciante | 5 | 1 | 5 min corrida + 3 min caminhada + 5 min corrida + 3 min caminhada + 5 min corrida | 25 |
| 5k | iniciante | 5 | 2 | 8 min corrida + 5 min caminhada + 8 min corrida | 26 |
| 5k | iniciante | 5 | 3 | 20 min corridos | 25 |
| 5k | iniciante | 6 | 1 | 5 min corrida + 3 min caminhada + 8 min corrida + 3 min caminhada + 5 min corrida | 28 |
| 5k | iniciante | 6 | 2 | 10 min corrida + 3 min caminhada + 10 min corrida | 28 |
| 5k | iniciante | 6 | 3 | 25 min corridos | 30 |
| 5k | iniciante | 7 | 1 | 25 min corridos | 30 |
| 5k | iniciante | 7 | 2 | 25 min corridos | 30 |
| 5k | iniciante | 7 | 3 | 25 min corridos | 30 |
| 5k | iniciante | 8 | 1 | 28 min corridos | 33 |
| 5k | iniciante | 8 | 2 | 28 min corridos | 33 |
| 5k | iniciante | 8 | 3 | 30 min corridos (5 km, a prova) | 33 |
| 5k | intermediario | 1 | 1 | 20 min fáceis | 20 |
| 5k | intermediario | 1 | 2 | 6 × 400 m forte com 200 m de trote | 25 |
| 5k | intermediario | 1 | 3 | 30 min longos | 30 |
| 5k | intermediario | 2 | 1 | 22 min fáceis | 22 |
| 5k | intermediario | 2 | 2 | 6 × 400 m forte com 200 m de trote | 25 |
| 5k | intermediario | 2 | 3 | 33 min longos | 33 |
| 5k | intermediario | 3 | 1 | 24 min fáceis | 24 |
| 5k | intermediario | 3 | 2 | 8 × 400 m forte com 200 m de trote | 30 |
| 5k | intermediario | 3 | 3 | 36 min longos | 36 |
| 5k | intermediario | 4 | 1 | 20 min fáceis | 20 |
| 5k | intermediario | 4 | 2 | 6 × 400 m forte com 200 m de trote | 25 |
| 5k | intermediario | 4 | 3 | 30 min longos | 30 |
| 5k | intermediario | 5 | 1 | 27 min fáceis | 27 |
| 5k | intermediario | 5 | 2 | 8 × 400 m forte com 200 m de trote | 30 |
| 5k | intermediario | 5 | 3 | 40 min longos | 40 |
| 5k | intermediario | 6 | 1 | 30 min fáceis | 30 |
| 5k | intermediario | 6 | 2 | 8 × 400 m forte com 200 m de trote | 30 |
| 5k | intermediario | 6 | 3 | 44 min longos | 44 |
| 5k | intermediario | 7 | 1 | 33 min fáceis | 33 |
| 5k | intermediario | 7 | 2 | 10 × 400 m forte com 200 m de trote | 35 |
| 5k | intermediario | 7 | 3 | 48 min longos | 48 |
| 5k | intermediario | 8 | 1 | 20 min fáceis | 20 |
| 5k | intermediario | 8 | 2 | 6 × 400 m forte com 200 m de trote | 25 |
| 5k | intermediario | 8 | 3 | 30 min corridos (5 km, a prova) | 30 |
| 10k | iniciante | 1 | 1 | 4 km corridos | 24 |
| 10k | iniciante | 1 | 2 | 4 km corridos | 24 |
| 10k | iniciante | 1 | 3 | 4 km corridos | 24 |
| 10k | iniciante | 2 | 1 | 4,8 km corridos | 29 |
| 10k | iniciante | 2 | 2 | 4,8 km corridos | 29 |
| 10k | iniciante | 2 | 3 | 4,8 km corridos | 29 |
| 10k | iniciante | 3 | 1 | 5,6 km corridos | 34 |
| 10k | iniciante | 3 | 2 | 5,6 km corridos | 34 |
| 10k | iniciante | 3 | 3 | 5,6 km corridos | 34 |
| 10k | iniciante | 4 | 1 | 4,8 km corridos | 29 |
| 10k | iniciante | 4 | 2 | 4,8 km corridos | 29 |
| 10k | iniciante | 4 | 3 | 4,8 km corridos | 29 |
| 10k | iniciante | 5 | 1 | 6,4 km corridos | 38 |
| 10k | iniciante | 5 | 2 | 6,4 km corridos | 38 |
| 10k | iniciante | 5 | 3 | 6,4 km corridos | 38 |
| 10k | iniciante | 6 | 1 | 7,2 km corridos | 43 |
| 10k | iniciante | 6 | 2 | 7,2 km corridos | 43 |
| 10k | iniciante | 6 | 3 | 7,2 km corridos | 43 |
| 10k | iniciante | 7 | 1 | 8 km corridos | 48 |
| 10k | iniciante | 7 | 2 | 8 km corridos | 48 |
| 10k | iniciante | 7 | 3 | 8 km corridos | 48 |
| 10k | iniciante | 8 | 1 | 4,8 km corridos | 29 |
| 10k | iniciante | 8 | 2 | 4,8 km corridos | 29 |
| 10k | iniciante | 8 | 3 | 10 km corridos (a prova) | 60 |
| 10k | intermediario | 1 | 1 | 30 min fáceis | 30 |
| 10k | intermediario | 1 | 2 | 20 min em ritmo firme (tempo run) | 20 |
| 10k | intermediario | 1 | 3 | 50 min longos | 50 |
| 10k | intermediario | 2 | 1 | 32 min fáceis | 32 |
| 10k | intermediario | 2 | 2 | 22 min em ritmo firme (tempo run) | 22 |
| 10k | intermediario | 2 | 3 | 55 min longos | 55 |
| 10k | intermediario | 3 | 1 | 35 min fáceis | 35 |
| 10k | intermediario | 3 | 2 | 25 min em ritmo firme (tempo run) | 25 |
| 10k | intermediario | 3 | 3 | 60 min longos | 60 |
| 10k | intermediario | 4 | 1 | 28 min fáceis | 28 |
| 10k | intermediario | 4 | 2 | 20 min em ritmo firme (tempo run) | 20 |
| 10k | intermediario | 4 | 3 | 45 min longos | 45 |
| 10k | intermediario | 5 | 1 | 38 min fáceis | 38 |
| 10k | intermediario | 5 | 2 | 27 min em ritmo firme (tempo run) | 27 |
| 10k | intermediario | 5 | 3 | 65 min longos | 65 |
| 10k | intermediario | 6 | 1 | 40 min fáceis | 40 |
| 10k | intermediario | 6 | 2 | 30 min em ritmo firme (tempo run) | 30 |
| 10k | intermediario | 6 | 3 | 70 min longos | 70 |
| 10k | intermediario | 7 | 1 | 42 min fáceis | 42 |
| 10k | intermediario | 7 | 2 | 32 min em ritmo firme (tempo run) | 32 |
| 10k | intermediario | 7 | 3 | 75 min longos | 75 |
| 10k | intermediario | 8 | 1 | 25 min fáceis | 25 |
| 10k | intermediario | 8 | 2 | 15 min em ritmo firme (tempo run) | 15 |
| 10k | intermediario | 8 | 3 | 60 min corridos (10 km, a prova) | 60 |

## Gasto

`fator_kcal_por_kg_km` é o mesmo número que `workouts/corrida.py::FATOR_KCAL_POR_KG_KM`
usa para transformar distância e peso em quilocaloria — o teste cobra que os
dois batem, porque um documento e um motor discordando em silêncio é pior do
que os dois errados juntos.

| medida | valor |
|---|---|
| fator_kcal_por_kg_km | 0,9 |

## Fontes

Só o que existe; nenhuma citação inventada.

- NHS (National Health Service, Reino Unido). *Couch to 5K.* Programa de nove
  semanas; comprimido para oito neste documento, fundindo a oitava e a nona —
  a nona repete a oitava (30 minutos corridos) só para confirmar que a
  distância se sustenta, e não é uma prescrição nova.
- Higdon, Hal. *5K Training — Intermediate.* halhigdon.com.
- Higdon, Hal. *10K Training — Novice.* halhigdon.com.
- Higdon, Hal. *10K Training — Intermediate.* halhigdon.com.
- American College of Sports Medicine (ACSM). *Guidelines for Exercise
  Testing and Prescription* — a equação metabólica da corrida (≈1 kcal/kg/km
  bruto), a mesma citada em `workouts/corrida.py::FATOR_KCAL_POR_KG_KM`.

## Como o motor obedece

Leitura, não decisão — o que decide está acima. `workouts/doutrina_corrida.py`
lê as três tabelas deste arquivo e é a única porta de entrada dos números no
motor: `planos()` devolve semanas e sessões por semana de cada combinação, e
`sessoes(plano, nivel, semana)` devolve as três sessões daquela semana, cada
uma com descrição e minutos. `fator_kcal()` devolve o mesmo fator que
`workouts/corrida.py` usa para o gasto calórico da corrida, e os dois
precisam bater — é o que `test_corrida_md.py` cobra. `PlanoDeCorrida` guarda
só plano, nível e a data em que a pessoa começou; toda vez que a tela precisa
saber o que a semana pede, ela pergunta a este documento, e não a uma cópia
gravada no banco.
