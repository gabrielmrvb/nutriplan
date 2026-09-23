# Uma refeição parece uma refeição — a tela de Alimentação e o card

**Missão de 23/09/2026.** Base: produção em `fec1380`. Branch
`design/alimentacao`. Tudo abaixo foi medido no navegador (agent-browser,
Chromium 153) contra uma conta LOCAL de QA com plano montado, nos dois temas
e em 320/390/768/1280 px.

---

## O diagnóstico, conferido antes de tocar em nada

A auditoria disse: "horário, nome, alvo e um link *Ver opções*; fechado, um
retângulo vazio. Aberto, cada opção é UMA LINHA seguida de um REGISTRAR A
gigante — cinco botões empilhados por refeição". Medido em produção antes de
começar: `/demo/alimentacao/` tinha **2.143 px** a 390 px com tudo fechado e
**1.581 px** a 1280 px, com a coluna da direita vazia da metade para baixo.

O achado central da auditoria estava certo e é o que orientou tudo: **a
refeição não tinha conteúdo na tela**. Os ingredientes com quantidade já
existiam no banco — a lista de compras é feita deles — e nunca apareciam.

---

## PARTE 1 — o card vira uma refeição

### 1. As duas opções, sempre, como dois cards de receita

Cada horário mostra as duas receitas do dia lado a lado (≥ 768 px) ou
empilhadas (390 px), cada uma com: ilustração da família do prato, nome,
caloria em destaque, **os três macros** (antes só a proteína), tempo de
preparo e os ingredientes com a porção numa linha — "2 unidades de pão
francês · 3 ovos médios · 3 fatias de queijo muçarela".

A linha dos ingredientes sai de `MealOption.resumo_dos_itens`, que usa a
mesma `ingredient_list` da lista de compras: **zero consulta nova** (os
itens e as porções já vinham no `prefetch_related` da tela). Ela ABREVIA a
medida ("6,5 col. de sopa de aveia"): quatro ingredientes por extenso não
cabem em 390 px, e a versão por extenso está na receita, que é onde se
cozinha.

"Ver opções" saiu.

### 2. Um CTA por opção, e o rótulo aponta para o card

"Comi esta", não "Registrar A". **A letra saiu da interface inteira** — ela
existe para o rodízio, que é do servidor; `OptionLabel` continua no banco e
nas URLs da lista de compras. Só a primeira é verde (é a sugestão do dia);
a segunda é contorno. Para leitor de tela o botão nomeia a receita e o
horário (`aria-label="Registrar Iogurte com aveia em Lanche da manhã"`).

### 3. "Pulei" e "Comi outra coisa" viraram rodapé

Eram dois botões de 48 px com o mesmo peso do registrar, cinco vezes por
dia. Agora são uma linha discreta (`btn-link`, a língua do "desfazer") no pé
do card. As duas continuam fazendo exatamente o que faziam, com o mesmo
formulário e o mesmo `<datalist>` do catálogo.

### 5. Estado por refeição, escrito pelo servidor

`plans/agora.py` passou a escrever `slot.estado` — `resolvida`, `agora`,
`pendente` ou `futura` — ao lado do `marcador` que já existia. A tela desenha
quatro coisas a partir dessa palavra e **não recalcula nada**:

| estado | como aparece |
|---|---|
| `agora` | aberta, fio da marca, as duas receitas, CTA primário |
| `pendente` | uma linha: hora · nome · **"Não registrada · registrar"** |
| `futura` | uma linha: hora · nome · alvo em kcal |
| `resolvida` | o que foi comido, a caloria real e "desfazer" — com a borda verde de sempre |

**Só a refeição da vez nasce aberta.** A primeira versão desta missão abria
`agora` E `pendente` ("as duas são ação em aberto") — isso desfazia a decisão
medida de 20/09/2026 e, com cards de receita no lugar de linhas, poria dois
cardápios abertos na tela às 15h. Quem segurou foi
`test_a_vencida_fica_em_uma_linha_com_o_convite_a_registrar`, que já existia.

### 4. A receita: folha no celular, painel no desktop, tela sempre

`/refeicao/<slot>/receita/<opcao>/` é uma TELA de verdade: ingredientes um
por linha com a medida caseira, **modo de preparo em passos numerados**,
macros completos, "trocar por outra receita" e a porção.

Um markup só (`templates/plans/_receita.html`) em três lugares: a tela, a
folha que sobe no celular e o painel da direita no desktop. A folha e o
painel são LITERALMENTE a seção `#receita` recortada da página buscada — é a
mesma mecânica de "Outras formas" na ficha do treino. Sem JavaScript o link
navega e a receita aparece inteira.

**A porção (½ · 1 · 1½) é conta do servidor.** Cada valor é um endereço
(`?porcao=0.5`), então recarregar preserva a escolha e o botão já sai com o
valor certo. Ela multiplica kcal, macros e **todas** as quantidades —
inclusive o item que o motor marca como não escalável: `scale_factor` é o
motor ajustando a receita ao alvo (1,37 ovo não existe), `porcao` é a pessoa
dizendo que comeu metade do prato, e meio prato tem meio ovo. O número que a
tela mostra é o que vai para o histórico (`MealLog.porcao`, migration
`plans.0011`, default 1 sem backfill: todo registro anterior É uma porção
inteira).

A lista de valores é FECHADA no servidor porque este número multiplica
caloria gravada: um `?porcao=99` forjado escreveria um dia de 280 mil kcal.
Medido: `?porcao=0.5` → 354 kcal; `?porcao=99` → 708, a inteira.

### 6. Ilustração por FAMÍLIA, e não foto por receita

Onze desenhos em SVG num sprite de 7,8 kB (cuscuz, mingau, ovos, pão,
tapioca, vitamina, prato feito, macarrão, iogurte, fruta, salada), com o
campo `MealTemplate.ilustracao` no catálogo (migration `catalog.0008`,
preenchida pelo nome). **Não são fotos** e a razão é a mesma que fez a
expansão de exercícios de 10/09 voltar atrás: 54 imagens exigem curadoria
(é o mesmo prato? a licença permite?) e este ambiente não VÊ foto para
conferir. Desenho próprio, sem licença de terceiro, com o peso contado por
teste.

As onze estão na **vitrine** (`/gestao/vitrine/`), num mosaico, nos dois
regimes — é onde você veta.

---

## PARTE 2 — o topo conta o dia

### 7. Antes da primeira refeição, a meta e o plano

O anel mostrava "0 de 2.839", a lista "0/5 refeições" e a barra "P 0 · C 0 ·
G 0": meia tela de zero. Agora, com nada registrado, ele mostra **2.839 kcal
no dia · a sua meta** e, ao lado, "o seu dia em 5 refeições · 148 g de
proteína"; a barra de macros mostra o alvo (P 148 g), que é a divisão que
ela desenha. Da primeira marcação em diante volta o par comido/meta.

Não é estado vazio com texto de consolo: é outra pergunta, respondida. A
palavra que decide está no servidor (`topo.modo`), não num `{% if %}`.

### 8. O cartão AGORA traz a receita

Quando a ação do dia é uma refeição, o cartão do topo mostra a ilustração, o
nome e a caloria da opção sugerida, com "Comi esta" ali mesmo e "Ver as duas
opções" como saída. Na tela Hoje ele continua sendo só o ponteiro — a mesma
parcial, sem a sugestão.

### 9. Depois de registrar, o topo responde

"1 de 5 refeições", "faltam 2.372 kcal", e a proteína diz se está no rumo —
comparando a fração de proteína comida com a fração de **caloria** comida,
com 10 pontos de tolerância. Um limiar absoluto ("70 % às 15h") inventaria
um horário que o plano de cada pessoa não tem.

---

## PARTE 3 — o desktop usa as duas colunas

### 10. A direita deixou de ser 1.500 px de nada

Medido a 1280 px antes: três cartões recolhidos no alto e o resto vazio,
enquanto a esquerda rolava cinco refeições. Agora ela abre com **a receita da
refeição da vez** (e "Ver a receita" TROCA esse painel em vez de abrir a
folha — quem decide é o layout, perguntado na hora, não um breakpoint
copiado no JavaScript), traz a **lista de compras da semana** resumida (3
itens + o total) e mantém "Entender minhas metas", "Dados do cálculo" e
"Lembretes" recolhidos, no fim. "Lembretes" era o único aberto entre dois
recolhidos.

O painel escolhe a refeição na mesma ordem do cartão AGORA: a da vez, depois
a vencida, depois qualquer uma com opção. Sem essa ordem, às 10h ele falava
do café das 7h enquanto o card aberto ao lado era o lanche das 10h37 — medido
no navegador.

---

## PARTE 4 — o celular

### 11. A da vez aberta, as outras em uma linha

Feito: cada refeição fechada é uma linha de 86 px (eram 150 px, porque o
cabeçalho de duas linhas ficava FORA do resumo).

**A meta de altura não foi atingida, e o número é este: 2.645–2.799 px com
uma refeição aberta, contra os 1.500 px pedidos.** A aritmética, medida a
390 px:

| bloco | px | de onde vem |
|---|---:|---|
| cartão AGORA com a receita | 271 | item 8 |
| anel + macros | 268 | item 7 |
| cabeçalho da seção | 52 | — |
| **refeição da vez aberta** | **802** | itens 1 e 6 (duas receitas com desenho, macros e ingredientes) |
| 4 refeições fechadas | 344 | item 11 |
| dois avisos do fim | 118 | "o que não mexer" |
| três blocos de consulta | 159 | item 10 |
| barras, rodapé e vãos | ~480 | o app |

Os itens 1, 6, 7 e 8 somam ~1.400 px sozinhos. **1.500 px e "as duas opções
sempre visíveis, com foto, macros e ingredientes" são incompatíveis** —
chegar lá exige escolher: (a) uma opção visível e a outra atrás de um toque,
(b) o cartão AGORA fora desta tela (ele repete a receita da refeição da vez,
que está 600 px abaixo), ou (c) cards de receita sem ilustração no celular.
Não decidi por você: as três desfazem um item que a missão pede
explicitamente. O que fiz foi cortar tudo o que não era pedido — a prévia de
compras e o painel da receita **não existem no celular** (seriam a terceira
cópia do mesmo conteúdo e mais 700 px), e a refeição fechada caiu 150 → 86 px.

Comparação honesta: **2.143 px com tudo fechado e nada na tela** viraram
~2.700 px **com uma refeição inteira aberta** — dois pratos com desenho,
macros, ingredientes e ação. Por refeição fechada, a tela encolheu.

### 12. A folha da receita

Provada no navegador: abre sem navegar, troca de porção sem navegar (354 kcal
e `porcao=0.5` no formulário), troca de receita sem navegar, fecha no botão e
no fundo. `<dialog>` nativo: foco preso e Esc de graça.

---

## O que NÃO mexi, e por quê

- **O registro de um toque com "desfazer" visível** — intacto, inclusive a
  fila offline (a rota é a mesma, e a porção viaja no corpo como qualquer
  campo).
- **"Comi outra coisa" com busca no catálogo** — intacto; só mudou de peso.
- **Os dois avisos** ("A e B fecham a mesma caloria…" e "Cardápio de
  exemplo… não substitui nutricionista nem médico") — ficaram no fim, como a
  missão permitiu. O segundo é exigência legal escrita no `CLAUDE.md`.
- **A lista de compras e os Lembretes** — só mudaram de lugar.
- **A frase "Registre suas refeições para acompanhar o saldo do dia"** —
  cheguei a tirá-la e voltei atrás: o que o anel mostra é o CARDÁPIO, e o que
  falta ali é o SALDO, que continua ausente e continua precisando dizer por
  quê. Havia teste, e o teste estava certo.
- **Rolar a tela até a refeição da vez ao abrir** (item 5) — **não fiz, de
  propósito**: o cartão AGORA no topo já é a refeição da vez com o mesmo CTA,
  e rolar 600 px passaria por cima dele e do anel, que são os itens 7 e 8
  desta mesma missão. A ação está na primeira dobra sem rolagem nenhuma.

---

## Decisões que tomei sozinho

1. **Ilustração por família, não foto por receita** — curadoria de 54 imagens
   num ambiente que não vê imagem. Mosaico de veto na vitrine.
2. **A receita é uma tela**, não um bloco de script: modo de preparo é o que
   se lê com a mão na panela e precisa sobreviver a recarregar e a
   compartilhar.
3. **A porção escala o item não escalável** — senão o kcal da tela deixaria de
   ser o kcal do que foi comido.
4. **A porção vira campo do histórico** (`MealLog.porcao`), para "380 kcal"
   não parecer erro de dado ao lado de uma receita de 765.
5. **"Trocar por outra receita" não persiste** — é o que a pessoa comeu HOJE.
   Transformar isso numa preferência de semanas seria uma decisão grande
   tomada com o prato na mão; o rodízio já varia sozinho.
6. **A prévia de compras é cache de processo** (plano, semana): custava 6 das
   24 consultas da tela para mostrar três nomes. Com cache, a Alimentação
   fecha em **18** consultas (o piso desta arquitetura é 17, o da Home).
7. **O painel e a prévia são só do desktop** — no celular seriam a terceira
   cópia do mesmo conteúdo.
8. **`.meal--done` virou `.meal--resolvida`** e o bloco `.option*` (3.491
   bytes) saiu do CSS: o markup morreu com a reforma, e a comemoração verde
   da refeição feita estava apontando para uma classe que ninguém mais
   emitia.

---

## Provas

- **Suíte completa** — ver o fim deste arquivo.
- **Sabotagem: 12 de 12 vermelhas.** Quatro passaram VERDE na primeira
  rodada e as quatro viraram conserto: duas eram guarda fraca (o recorte do
  card vazava para o painel da direita, que fala das mesmas receitas) e duas
  eram sabotagem inócua minha (`[] or [...]` e um laço com reserva).
- **axe-core** a 390 px no escuro: **0 violações** nas duas telas (a única
  achada foi `heading-order`, do `<h4>` do nome da receita depois do `<h2>`
  da seção — virou `<h3>`).
- **Contraste**: 274 pares, 0 reprovados.
- **B8**: 320/390/768/1280 nos dois temas — 0 rolagem horizontal, 0 alvo
  abaixo de 44 px, 0 texto abaixo de 11 px.
- **Um dia inteiro registrado a 390 px**, no navegador: "Comi esta" pelo card
  → meia porção pela folha → "Pulei" → "Comi outra coisa" com alimento do
  catálogo → a última pelo card. O topo respondeu a cada passo
  (`plano` → "1 de 5" → "2 de 5" → "2 de 5 · 1 fora" → "3 de 5 · 1 fora") e
  os cinco cards terminaram com "desfazer".
- **Orçamento de consultas**: `plans:alimentacao` entrou na tabela de tetos
  com **18** (a Home continua em 17).
