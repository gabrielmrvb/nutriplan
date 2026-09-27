# Missão B — quem entra não desiste (26–27/09/2026)

Branch `missao-b/quem-entra-fica`, a partir de `main` com #137 e #140 dentro.
PR aberto no fim, **sem merge**.

Vocabulário de evidência: `[EXECUTADA]` · `[OBSERVADA]` · `[LIDA NO CÓDIGO]` ·
`[LIDA NA DOCUMENTAÇÃO]` · `[HIPOTÉTICA]`. Achado: `BUG` · `UX REAL` ·
`OBSERVAÇÃO` · `FALSO POSITIVO` · `LIMITAÇÃO`.

---

## 0. O que ficou pronto, em uma tabela

| item | o que era | o que é | como está provado |
|---|---|---|---|
| **0** — um GET não grava | `achievements.resumo` desbloqueava dentro de um GET; `ConquistasView` chamava `avaliar` num GET | toda conquista nasce no POST que cria o fato; a retroatividade é `manage.py desbloquear_pendentes`, no build | `achievements/test_o_get_nao_grava.py` (5) + os 3 testes de retroatividade reescritos; sabotagem vermelha |
| **1** — a ficha de quem começa em casa | corpo inteiro não existia; a ficha de casa pedia paralelas, barra fixa e parede; "Carga" numa flexão | `Exercise.aparelho` + `split_for` com o nível e o equipamento; corpo inteiro até 3 dias; degrau mais fácil; sem campo de carga; placar em repetições | `workouts/test_ficha_de_casa.py` (25) + dourado intacto; 8 sabotagens |
| **2** — a corrida entra na conta | `activity_factor` só contava dias de academia | `Profile.corrida`/`corrida_dias`/`corrida_minutos`; os dias entram no fator; quem declara deixa de receber o crédito do dia; água +500 ml no dia de corrida | `plans/test_corrida_no_calculo.py` (15) |
| **3** — "comi outra coisa" que acha | 102 alimentos, casamento por `casefold` COM acento; `<datalist>` de todos os nomes | TACO 4ª ed. (583 alimentos), `catalog/busca.normalizar` numa fonte só, endpoint com prefixo/8 sugestões/2 letras, aviso no card | `catalog/test_taco.py` (10) + `plans/test_comi_outra_coisa.py` (21) + `test_outra_coisa_datalist.py` reescrito; 3 sabotagens |
| **4** — o app de quem não levanta peso | aba "Treino", etapa 3 oferecendo Treino, "ficha montados", Progresso com "Treinos 0", e-mail mandando abrir a ficha, zero conquistas possíveis | aba Corrida, etapa 3 sem Treino, frase pelo banco, Progresso com Corrida antes, e-mail em três versões, 4 conquistas de corrida, porta da corrida no `/treino/` | `accounts/test_app_de_quem_nao_levanta_peso.py` (32); 8 sabotagens |
| **5** — etapa 2 limpa | equipamento pré-marcado; divisão perguntada a iniciante; erro sem rolar até o campo | nada pré-marcado; divisão só para intermediário/avançado; "FOCO NO ERRO" alcança a etapa 2; aceite acima do CRIAR CONTA | `accounts/test_etapa_2_limpa.py` |

**Commits, um por item:** `36e78bd` (item 1), `76db7e0` (item 5), `0e32afa`
(item 2), `efd98d4` (ajuste dos testes do 2), `a04c3cf` (doutrina 1/2/5),
`a198c1c` (item 0), `2f82fea` (item 3), `e2ee923` (item 4).

---

## 1. Persona por persona: antes e depois, com o texto exato

A fonte é `achados/experiencia-usuario-20260921.md`, seção 1. **LIMITAÇÃO
declarada:** o relatório pedido citava também `-20260923.md`, que **não
existe** — o relatório da rodada 2 é `achados/missao-fechar-e-medir-20260924.md`
(e o de 23/09 é `achados/missao-alimentacao-20260923.md`, de outra missão).
`persona1.md` / `persona3.md` nunca existiram, como o dono já registrou.

### Persona 1 — Dani, 29, iniciante, treina em casa só com o peso do corpo

**Onde desistia (texto do relatório):** *"a etapa 2 do cadastro, com dois dias
marcados … a página acabou e não tem botão"*. E, passando dela, *"no primeiro
treino: a ficha A … é quatro variações de flexão de braço mais mergulho nas
paralelas (que ela não tem em casa) … e o treino fecha com '0 kg levantados' …
fiz tudo e o app diz que levantei zero"*.

**O que ela encontra agora** [EXECUTADA, navegador, 390×844, escuro, conta
local `qa-ana@nutriplan.invalid`]:

- a etapa 2 abre com o equipamento **em branco** e o CONTINUAR existe com
  qualquer número de dias (o `</div>` fora do `{% if %}` é de 22/09; o que a
  missão fez foi tirar a pergunta da divisão do caminho dela);
- o painel do treino diz **"Corpo inteiro"** (medido: `True`);
- a ficha de hoje **não tem um único exercício de paralelas, barra fixa ou
  parada de mão** (varredura do texto da página: lista vazia);
- a ficha traz a legenda da estreia (**"3 séries de 6 a 10 repetições"**);
- a execução **não tem campo "Carga"** (`input[name=weight_kg]` ausente —
  medido `False`, contra o `True` do Rafael no mesmo ponto, que é o controle
  positivo);
- axe: **0 violações** no painel, na ficha e na execução; zero rolagem
  horizontal; zero alvo de toque abaixo de 44 px.

### Persona 2 — Rafa, 27, academia completa, cético (o CONTROLE)

**Onde desistia:** *"Detalhes do programa … 30 de peito e 7 de perna por
semana, e o app diz que está certo"*. **Esse achado não é desta missão** — é
distribuição de volume, e está em "recomendo rever" (item 3 da lista, abaixo).

O que esta missão tinha de garantir é que **nada mudou para ele**, e mudou uma
coisa a favor: [EXECUTADA, mesma sessão]

- o painel dele continua de academia, a execução **tem** o campo "Carga"
  (`True`);
- ganhou a linha **"Corri hoje — registrar corrida"** no fim da semana, que era
  o único caminho que faltava para quem levanta peso E corre;
- axe 0 violações, sem rolagem horizontal, alvos ≥ 44 px.

### Persona 3 — Lu, 34, corre 5 km 3× por semana

**Onde desistia:** *"a etapa 2 do cadastro, sem dia de musculação … travou"*.
E depois: *"o app não enxergar a corrida como treino: a aba Treino diz 'Falta
dizer em quais dias você treina' … o Progresso não tem UMA linha sobre corrida
… em Conquistas … '3 dias de ofensiva — 401 / 3' … com zero conquistas
desbloqueadas"* e *"'comi outra coisa' não sugere nenhum alimento e sumiu com o
meu pão de queijo"*.

**O que ela encontra agora** [EXECUTADA, 390×844, escuro, conta local
`qa-lucas@nutriplan.invalid`]:

- a barra de baixo lê **`['Hoje', 'Alimentação', 'Corrida', 'Progresso',
  'Mais']`** — a terceira aba é a dela;
- o painel de treino diz que **não há ficha** e aponta a corrida;
- o **Progresso** abre `['Peso', 'Alimentação', **Corrida**, 'Água',
  'Conquistas']`, e os quatro tiles do topo são
  `['Peso', **'Corrida'**, 'Cardápio', 'Água']` — o tile "Treinos 0 de 0" deu
  lugar aos quilômetros;
- as **quatro conquistas de corrida** estão na tela ("Primeira corrida",
  "5 km de uma vez", "10 km de uma vez", "100 km somados");
- **"comi outra coisa" acha**: digitando `feijao` (sem acento) vêm oito
  sugestões — `Feijão carioca cozido`, `Feijão preto cozido`, `Feijão, broto,
  cru`, `Feijão, carioca, cozido`, … — com o catálogo curado ANTES da tabela;
  `cuscuz` devolve três; uma letra não abre lista;
- e **o pão de queijo continua não existindo** — mas agora o app DIZ, ao lado
  do campo: *"Não encontramos "pao de queijo" no catálogo. Você pode registrar
  assim mesmo — a refeição fica salva sem contar a caloria deste item."* A TACO
  4ª edição não tem pão de queijo (nem pizza, nem salsicha, nem granola); o que
  mudou não é a cobertura total, é o app parar de falhar em silêncio.
- axe 0 violações em Hoje, Progresso e Conquistas; sem rolagem horizontal;
  alvos ≥ 44 px.

### As contas de QA, e a prova de que sumiram

Três contas **locais**, no banco `nutriplan_missaob` desta máquina — nunca
produção, nunca a conta do dono. Criadas por `scratchpad/personas_qa.py` com o
perfil de cada persona do relatório, e **apagadas PELA TELA** ao terminar
(`POST /conta/excluir/` com a senha, o caminho de quem tem senha):

```
qa-ana:      login=302  exclusao=302  | login depois=200 "E-mail ou senha"
qa-rafael:   login=302  exclusao=302  | login depois=200 "E-mail ou senha"
qa-lucas:    login=302  exclusao=302  | login depois=200 "E-mail ou senha"
```

O `302` da exclusão é a tela aceitando; o `200` com "E-mail ou senha" no login
seguinte é a recusa (sucesso seria 302). Depois disso, as únicas contas
`@nutriplan.invalid` no banco são as do seed do demo (`carlos.demo`,
`ana.demo`) e uma de outra sessão (`dani-antes`) — **o demo ficou intacto**
[EXECUTADA].

---

## 2. Nota por área, ao lado da original

**LIMITAÇÃO:** a tabela original (seção 4 do relatório de 21/09) é **por
ÁREA**, não por persona — não existe "Treino (P1) = 3" nela. O `3` do critério
é a nota de **onboarding**, que é exatamente onde P1 e P3 desistiram; `treino`
valia 6. As duas linhas estão abaixo, e o critério é avaliado nas duas
leituras.

| área | era | agora | por quê |
|---|---|---|---|
| onboarding | **3** | **7** | o CONTINUAR não depende mais da pergunta da divisão (ela saiu do caminho de quem começa), nada vem pré-marcado, o erro rola até o campo, e o aceite está acima do CRIAR CONTA. Não é 8/9 porque a etapa 2 continua sendo a tela mais longa do cadastro e nada disso foi medido com gente de verdade. |
| hoje / dieta | **5** | **7** | "comi outra coisa" acha 685 alimentos, sem acento, com sugestão a partir da segunda letra e o aviso ao lado do card quando não acha. O que não mudou: "às seis da tarde o app me diz que AGORA é o almoço" — é a janela do AGORA, e não estava no escopo. |
| treino | **6** | **8** | a ficha de casa deixou de pedir aparelho que não existe, o iniciante começa no degrau mais fácil, o placar conta repetições em vez de "0 kg", e a corrida tem porta aqui. O 30×7 de volume do Rafa continua aberto — é "recomendo rever". |
| corrida | **6** | **8** | a corrida entra na meta, o Progresso a mostra (antes do treino, para quem não levanta peso), e existem quatro conquistas dela. Falta o lanche de carboidrato no dia de corrida, que é decisão de produto. |
| progresso | **4** | **7** | os números pararam de brigar: um GET não grava mais (a mesma tela lida duas vezes dá o mesmo número), o "401 / 3" já tinha caído na missão A, e o cartão vazio de treino deu lugar à corrida de quem corre. |

**O critério do dono:** *"se Treino (P1) não passar de 3 para ≥ 6 e Hoje/dieta
(P3) de 5 para ≥ 7, a missão não fechou"*. Nas duas leituras possíveis do
primeiro número, ele passa: **onboarding 3 → 7** (a área que estava em 3, e a
que derrubava P1) e **treino 6 → 8** (a área chamada Treino). **Hoje/dieta
5 → 7.** As notas são minhas, sobre o que foi medido no navegador — não são
usuário de verdade.

---

## 3. O que eu decidi sozinha (e a razão de cada uma)

1. **`Exercise.aparelho` em vez de reusar `equipment`.** "Peso do corpo"
   juntava "não preciso de nada" com "preciso de uma barra fixa", e era isso
   que punha paralelas na ficha de casa. Campo novo, 11 exercícios marcados por
   NOME na migration, e a substituição continua sendo por padrão+grupo.
2. **Corpo inteiro só para iniciante EM CASA (até 3 dias).** O dourado ficou
   vermelho quando a regra valia para todo iniciante — na academia a divisão
   por frequência continua sendo a certa. `PERFIS_DE_CASA` nomeia os dois
   perfis.
3. **Os DIAS de corrida entram no fator; os MINUTOS não.** É a doutrina de
   `calculations.py` aplicada igual: somar MET por fora depende de a pessoa
   saber quantos minutos corre de verdade.
4. **"Você declarou, entra na meta; não declarou, entra no dia."** Sem isso a
   corrida contaria duas vezes (~40 kcal/dia no fator + ~300 de uma corrida).
5. **A TACO pela cópia `brolesi/taco` (MIT, DOI).** É regenerada das planilhas
   originais e dá para citar. 14 das 597 linhas ficaram fora (sem energia, ou
   energia que não fecha com os macros em 15 %), com a exceção das bebidas
   alcoólicas escrita no arquivo.
6. **O `<datalist>` de todos os nomes saiu, e não ganhou um menor ao lado.**
   Duas listas de sugestão no mesmo campo abrem juntas no celular. Consequência
   assumida: **offline não há sugestão** — o registro continua funcionando,
   porque o casamento do nome é do servidor quando a fila drena.
7. **O curado ganha do importado na colisão de nome.** Os 102 têm porção,
   corredor de mercado e papel no prato, que o cardápio e a lista de compras
   leem.
8. **A aba de Corrida substitui a de Treino na POSIÇÃO dela**, e "Mais" perde
   `running` dos `navs` — com o pilar nas duas, as duas acendiam.
9. **O cartão de treino do Progresso só desaparece quando também não há dado.**
   Quem treinou antes de mudar a resposta continua vendo o próprio histórico.
10. **Quatro conquistas de corrida, nenhuma repetível**, e "10 corridas" ficou
    de fora: ela e os 100 km medem a mesma coisa.
11. **O e-mail de boas-vindas em três versões**, com a do "não perguntado"
    sendo a que sai hoje — o envio é no cadastro, antes da etapa 2.
12. **A porta da corrida volta ao `/treino/` como LINHA, não como cartão.** A
    decisão de 22/09 tirou um cartão de área da coluna lateral e continua de pé.
13. **`flex: 1 0 auto` → `1 1 auto` no `.fora`** (ver o achado 4.1): é a causa
    medida de uma rolagem horizontal, e a régua do app é não ter nenhuma.

---

## 4. Achados que a missão encontrou no caminho

### 4.1 `BUG` — a página rolava na horizontal com "Comi outra coisa" aberto

[EXECUTADA, 390 px] `.meal__secundarias .fora` era `flex: 1 0 auto`. Com
`flex-shrink: 0` o item nunca encolhe abaixo do conteúdo — e `min-width: 0`
**não** muda isso, porque ele só libera o limite automático; quem proíbe
encolher é o shrink. Com o card da refeição aberto e o formulário aberto, a
largura natural do campo "O que você comeu?" (~539 px) virava a largura do
`<details>`: **568 px dentro de um container de 293**, e
`document.documentElement.scrollWidth` ia de **375 para 609** numa janela de
390. Depois de `1 1 auto`: **375**, com tudo aberto.

Ele é **pré-existente** — provado removendo do DOM todos os elementos que esta
missão acrescentou (`.busca__lista`, `.busca__vazio`, o envoltório `.busca`): a
rolagem continuava em 609. A régua está em
`plans/test_comi_outra_coisa.py::test_o_formulario_aberto_nao_faz_a_pagina_rolar_na_horizontal`
(a asserção é sobre o CSS porque a suíte não tem motor de layout).

**AVISO PARA A SESSÃO `alimentacao` (9219ee0d):** você reescreveu
`.meal__secundarias` na branch `alimentacao/sugere-nao-impoe`. Esta é uma
mudança de UMA palavra na regra `.meal__secundarias .fora`; se a sua reescrita
mantiver `flex-shrink: 0` ali, a rolagem volta — e o teste acima fica vermelho.

### 4.2 `BUG` (meu, achado pela sabotagem) — a normalização tinha DUAS fontes

O `catalog/data/taco.json` gerado trazia uma chave `busca` pré-calculada. A
sabotagem que estraga `catalog.busca.normalizar` passou **VERDE** por causa
dela: as linhas da TACO continuavam achando porque liam o arquivo, não a
função. A chave saiu do JSON e o seed calcula. Com uma fonte só, a mesma
sabotagem fica vermelha em 5 testes.

### 4.3 `OBSERVAÇÃO` — a TACO não tem pão de queijo

Nem pizza, salsicha, granola, feijoada (esta foi descartada: 140 kcal
calculadas contra 117 publicadas) ou "peixe" genérico. São 597 linhas na 4ª
edição, e o que ela publica é o que existe. O que a missão consertou não é a
cobertura total — é o app **dizer** quando não acha, com a saída ao lado.

### 4.4 `LIMITAÇÃO` — o axe não mede contraste sobre gradiente

Em toda tela medida, `violations: 0` e `incomplete: 1` — sempre
`color-contrast` com *"Element's background color could not be determined due
to a background gradient / pseudo element"*. O contraste deste app é medido a
partir dos TOKENS, na suíte (`config/tests.py`, 274 pares), que é a régua que
enxerga o que o axe não enxerga.

### 4.5 `LIMITAÇÃO` — o harness, e duas armadilhas que custaram tempo

- **`fill` do agent-browser não produziu o evento `input`** que o `pwa.js`
  escuta: o campo ficava vazio e nenhuma sugestão nascia, enquanto um
  `dispatchEvent(new Event('input'))` à mão devolvia oito. O roteiro passou a
  `focus` + `keyboard type`, que é o caminho da pessoa.
- **`open /conta/sair/` responde 405** (sair é POST): a navegação falha e a
  sessão anterior continua de pé. A primeira execução mediu a conta da Ana
  achando que era a do Rafael. O roteiro agora limpa o cookie.
- E a armadilha que o `CLAUDE.md` já documentava e eu paguei de novo: **saída
  do agent-browser para ARQUIVO, nunca para um PIPE** — o daemon herda o stdout
  e o comando trava com o navegador já aberto.

### 4.6 A VARREDURA de axe, em uma tabela

16 combinações [EXECUTADA, agent-browser 0.38.1, axe-core 4.12.1]: Alimentação,
Progresso, Treino e Conquistas × 390×844 e 1280×900 × escuro e claro.

| | 390 escuro | 390 claro | 1280 escuro | 1280 claro |
|---|---|---|---|---|
| alimentação | 0 · 2116 px | 0 · 2116 px | 0 · 1809 px | 0 · 1809 px |
| progresso | 0 · 2761 px | 0 · 2761 px | 0 · 2027 px | 0 · 2027 px |
| treino | 0 · 855 px | 0 · 855 px | 0 · 900 px | 0 · 900 px |
| conquistas | 0 · 1498 px | 0 · 1498 px | 0 · 1425 px | 0 · 1425 px |

(violações de axe · altura da página). **Zero rolagem horizontal e zero alvo de
toque abaixo de 44 px** em todas as dezesseis, mais as telas da Ana (painel,
ficha, execução) e do Rafael. A régua de 44 px isenta dois casos, e os dois
estão escritos no `CLAUDE.md`: link corrido dentro de parágrafo (WCAG 2.5.8) e
radio/checkbox dentro de um `<label>` que cumpre os 44 — a primeira versão da
minha régua não isentava o segundo e acusou os três rádios de "Seu programa",
cujo cartão mede 44.

### 4.7 A SUÍTE COMPLETA: 4.662 testes, e as CINCO que caíram eram contrato antigo

[EXECUTADA, local, 2.734 s] `Ran 4662 tests … FAILED (failures=5, expected
failures=1)`. As cinco prendiam exatamente o comportamento que a missão trocou,
e cada uma foi reescrita com a razão dentro:

| teste | o que ele prendia | o que passou a prender |
|---|---|---|
| `workouts.test_b3_treino.APortaDaCorridaTests` | ZERO porta de corrida no `/treino/` | UMA porta, e que ela é LINHA (`btn-link`), não cartão. A decisão de 08/09 tirou um CARTÃO da coluna lateral e continua de pé; o que ela produziu sem querer foi quem tem ficha E corre sem caminho nenhum. |
| `achievements.tests.CatalogoTests.test_nao_ha_conquista_de_dado_que_o_app_nao_tem` | `{treino, ofensiva, meta, recorde}` — corrida era "dado que o app não tem" | `corrida` entrou, porque `workouts.Corrida` existe. A régua não afrouxou: ganhou um teste NOVO ao lado provando que as quatro leem só os três campos que `reunir` agrega, e que nenhuma é repetível. |
| `plans.tests.ComiOutraCoisaTests` (o `<datalist>`) | "o catálogo é renderizado UMA vez" | "a sugestão não custa um nó de DOM POR ALIMENTO" — a propriedade, não o mecanismo. Mais a asserção de que a busca está na tela, senão "zero nós" ficaria verde numa tela que parou de sugerir. |
| `accounts.test_musculacao` (2 testes) | o cadastro de quem só corre | o payload da etapa 3 deles passou a ser `interesses=["corrida"]`: o `ETAPA3` compartilhado marca "Treino", que o item 4 deixou de oferecer a essa pessoa. Sem isso o POST era recusado e o teste media a validação, não a tela. |
| `accounts.test_edicao_preserva_respostas` | a experiência sobrevive a reabrir a etapa 2 | o fixture passou a responder `equipamento`: o campo deixou de nascer pré-marcado (item 5) e é obrigatório para quem faz musculação, então o reenvio do formulário renderizado era recusado com "Diga o que você tem para treinar". |

A `expected failure` é o dourado do peso do corpo na letra A, que já era
`@expectedFailure` nomeado antes desta missão.

### 4.8 `OBSERVAÇÃO` — um teste do relógio caiu por duração da suíte, não por regressão

`config.test_relogio.test_a_hora_e_a_da_suite_e_continua_andando` comparou 13
com 12 numa execução local ANTERIOR, que levou 89 minutos e cruzou a hora
congelada (`HORA_DA_SUITE = 12:00` + decorrido). É fragilidade do teste com
suíte longa nesta máquina, não mudança de comportamento — **na execução de
4.662 testes desta seção (45,6 min) ele NÃO caiu**, e o CI, que fatia em cinco,
não chega perto disso.

---

## 5. O que ficou de fora, e por quê

1. **O cartão da Home de quem não faz musculação** (item 4, primeiro bullet):
   **ADIADO por decisão do dono** até o veto do PR #138, que redesenha
   `templates/plans/today.html`, `_agora.html` e `_agua.html`. É o único item
   da lista do dono que não foi feito. Nada mais da missão toca a Home.
2. **O lanche extra de carboidrato no dia de corrida** (item 2): não virou um
   sexto `MealSlot`. O cardápio é retrato do PLANO e os slots valem todo dia —
   um slot a mais apareceria também nos dias sem corrida, mudaria o denominador
   da aderência de TODOS os dias e daria calorias que a meta não previu
   justamente a quem já tem a corrida dentro dela. A alternativa honesta (mais
   carboidrato na divisão de macros de quem declara corrida, sem refeição nova)
   é decisão de produto.
3. **Sugestão de alimento offline.** Ver a decisão 6.
4. **A distribuição de volume que derrubou o Rafa** (30 de peito × 7 de perna
   por semana): é o motor de prescrição, não estava no escopo de nenhum dos
   seis itens, e mexer nele sem o dourado na frente é como se estraga uma
   ficha.

---

## 6. Recomendo rever

1. **O lanche do dia de corrida** — a forma honesta é macro, não refeição nova.
2. **Sugestão de alimento offline** — se o dono quiser, o caminho é o service
   worker cachear `/alimentos/buscar/` para os prefixos mais usados; um
   `<datalist>` ao lado da busca não serve (duas listas no mesmo campo).
3. **Volume por grupo na semana** (o achado do Rafa) — 30 de peito para 7 de
   perna passa nas réguas atuais porque elas medem teto, não equilíbrio.
4. **A TACO escreve o nome invertido** ("Queijo, requeijão, cremoso"). A busca
   lida com isso (o ramo "contém"), mas a SUGESTÃO mostra o nome como a tabela
   publica. Dá para humanizar, e isso é curadoria de texto sobre 583 linhas.
5. **`/conta/sair/` responder 405 no GET** é correto, mas um GET ali é o que
   um agente (ou um prefetch) tenta primeiro. Uma tela de confirmação com o
   POST dentro seria mais amável — e é o que a tela de sair já faz; o que não
   existe é a rota responder a um GET direto.

---

## 7. As capturas

28 PNG em **`achados/capturas/missao-b/`** (1,8 MB), no caminho que o pedido
nomeou. Elas **não entram no commit**, e isso é a regra do próprio repositório
(`.gitignore:77`, `capturas/`), com a razão escrita lá: *"prova de execução não
é código. Ficam no disco de quem rodou e vão para o relatório; versioná-las
encheria o repositório de PNG a cada run e faria um `git add -A` distraído
publicar a tela de uma conta de QA (22/09/2026 — aconteceu, e o commit foi
desfeito)"*. Os números que elas mostram estão todos neste relatório.

| arquivo | o que mostra |
|---|---|
| `ana-01-painel-390-escuro` | o painel dela dizendo "Corpo inteiro" |
| `ana-02-ficha-390-escuro` | a ficha sem aparelho, com a legenda da estreia |
| `ana-03-execucao-390-escuro` | a execução SEM o campo "Carga" |
| `rafael-01-painel-390-escuro` | o controle, com "Corri hoje — registrar corrida" |
| `rafael-02-execucao-390-escuro` | o controle positivo: a execução COM "Carga" |
| `lucas-01-hoje-390-escuro` | a barra com a aba Corrida |
| `lucas-02-treino-390-escuro` | o painel que não cobra dias de academia |
| `lucas-03-progresso-390-escuro` | Corrida antes, e o tile de km no lugar do de treino |
| `lucas-04-conquistas-390-escuro` | as quatro medalhas de corrida |
| `busca-01-nao-encontrado-390-escuro` | o aviso ao lado do campo, com a saída |
| `busca-02-sugestoes-390-escuro` | oito sugestões para "feijao", sem acento |
| `busca-03-registrado-390-escuro` | a refeição registrada com caloria |
| `axe-<tela>-<largura>-<tema>` (16) | a varredura da seção 4.6 |

---

## 8. O que preciso de você

**nada.**
