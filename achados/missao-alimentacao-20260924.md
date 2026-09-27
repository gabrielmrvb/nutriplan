# A Alimentação sugere, não impõe — cinco decisões do dono

**Missão de 24/09/2026.** Base: `origin/main` em `7f8a4fc`. Branch
`alimentacao/sugere-nao-impoe`. Tudo abaixo foi medido no navegador
(agent-browser, Chromium 153) contra uma conta local de QA com cardápio
montado, em três horários congelados (09:00, 14:00, 20:00), 390 e 1280 px,
tema claro e escuro.

As cinco mudanças são decisões do dono depois de usar o app. Onde elas
conflitam com doutrina escrita, a decisão de hoje venceu e a regra anterior
foi substituída no `CLAUDE.md` **com data e motivo** — nenhuma foi apagada em
silêncio.

---

## O que mudou, e o que isso custava antes

### 1. O cartão AGORA saiu da Alimentação

Ele mostrava a refeição da vez com o mesmo botão que o primeiro card do
cardápio, três centímetros abaixo. Dois heróis para a mesma ação.

Fica na Hoje, que é o orquestrador do dia — e lá ele sempre foi um PONTEIRO
("Ver refeição"). O ramo do parcial que REGISTRAVA a refeição existia só para
a Alimentação (era ela quem passava `sugestao`): saiu junto, com o CSS que só
ele usava. `_agora.html` ficou menor e com um dono só.

### 2. Nenhuma refeição nasce aberta; a da vez é marcada

A doutrina de 20/09 ("só a refeição da vez nasce aberta") foi tomada quando
uma refeição aberta custava quatro linhas de texto. Desde 23/09 ela custa
dois cards de receita com ilustração, macros e ingredientes.

Agora toda refeição em aberto é uma linha, e quem abre é a pessoa. Para a
linha continuar achável sem abrir, a da vez e a vencida trazem no próprio
`<summary>` o selo que já existia no cabeçalho: **"Agora"** e **"Ficou para
trás"**. O servidor não mudou — `plans/agora.py` continua escrevendo
`slot.estado`, e o que mudou é o que a tela faz com a palavra.

**Altura da tela a 390 px, mesma conta, relógio congelado:**

| hora | antes (`7f8a4fc`) | depois | diferença |
|---|---|---|---|
| 09:00 | 2.568 px | **1.561 px** | −1.007 px (−39 %) |
| 14:00 | 2.580 px | **1.773 px** | −807 px (−31 %) |
| 20:00 | 2.596 px | **2.131 px** | −465 px (−18 %) |

A queda encolhe ao longo do dia porque à noite há mais refeições resolvidas,
e refeição resolvida nunca teve sanfona: ela mostra o que foi comido.

A 1280 px: 1.462 px, com a coluna da direita (o painel da receita) intacta.

### 3. O botão diz a ação: "Registrar"

"Comi esta" saiu de toda tela. O card já É a receita — dizer "esta" era o
card contando a mesma coisa duas vezes —, e na folha da receita aberta por
link não havia "esta" a que apontar.

A régua nova está em `config/test_linguagem.py`
(`NenhumaTelaDizComiEstaTests`): o cardápio e a folha dizem "Registrar", e a
frase antiga não aparece em tela nenhuma de quem tem cardápio. O `aria-label`
continua nomeando receita e horário ("Registrar Iogurte com aveia em Lanche
da manhã") — numa lista de leitor de tela, cinco "Registrar" seguidos não
distinguiriam nada.

### 4. As duas opções pesam igual; a sugestão virou chip

O verde só na primeira lia como "faça a primeira". São cinco refeições por
dia com duas opções cada: dez botões primários seria pintar a tela inteira de
ação.

Os dois CTAs são `btn--ghost` — **mesma classe, medida no HTML** — e o rodízio
continua escolhendo a sugestão do dia (é ela que equilibra a lista de
compras): ele a anuncia com um chip **"sugestão de hoje"** dentro do card, em
minúsculas e sem preenchimento.

**Decisão registrada:** os dois de CONTORNO, e não os dois verdes. O verde
fica para o que ele identifica no app — a ação do dia na Hoje e o "Registrar"
do formulário de "Comi outra coisa", que é o único botão preenchido ali
dentro.

### 5. "Não comi" e "Comi outra coisa" viraram ações de verdade

Eram um `btn-link` de 15 px de altura de texto e um `<summary>` disfarçado de
link. Quem não comeu o que estava no cardápio — metade dos dias de qualquer
pessoa — ficava sem saída visível.

Agora são dois `btn--ghost` do mesmo tamanho, lado a lado (grade de duas
colunas; uma só abaixo de 24 rem, senão "Comi outra coisa" quebra em três
linhas a 320 px). Medido a 390 px: **143 × 70 px e 141 × 68 px** — o alvo de
44 px vem do `.btn`. "Pulei" virou **"Não comi"**, que é o que a pessoa fez,
dito sem gíria de aplicativo.

"Comi outra coisa" abre um campo de verdade: `<input>` com o `<datalist>` de
alimentos que já existia, texto de exemplo **"o que você comeu"** e o botão
"Registrar" ao lado. Fechado por padrão, `<details>` puro — funciona sem
JavaScript. Aberto, ocupa a largura toda das duas colunas.

O contrato não mudou: mesma URL (`plans:mark_meal`), mesmo `status`
(`skipped` / `off_plan`), mesmo `data-celebra` e a mesma idempotência da fila
offline.

---

## A prova

**No navegador** (agent-browser, conta de QA local, três servidores com o
relógio congelado em 09:00, 14:00 e 20:00):

| o que | medido |
|---|---|
| cartão AGORA na Alimentação | ausente nos três horários |
| refeições abertas ao carregar | **0** nos três horários, nos dois temas, a 390 e 1280 |
| a da vez marcada | "Agora" na linha correta em cada horário (07:30 às 9h; 11:00 às 14h; 17:52 às 20h no demo) |
| os dois CTAs | `btn--ghost btn--block` + "Registrar", os quatro do primeiro cartão |
| chip da sugestão | "sugestão de hoje" no primeiro card de cada refeição |
| "Comi outra coisa" | abre, tem `placeholder="o que você comeu"` e `list="alimentos-do-catalogo"`; registrou "Pastel na feira" e o cartão passou a mostrar a frase |
| "Não comi" | registrou: o cartão passou a "Refeição pulada" |
| rolagem lateral | nenhuma, a 390 e a 1280, nos dois temas |

**Em teste** (banco privado `nutriplan_alim`): `plans.test_opcoes_tocaveis`
21/21, `plans.test_card_de_refeicao` 30/30, `config.test_linguagem` 16/16,
mais `config.test_design_system`, `config.tests.TouchTargetTests`,
`config.test_i18n`, `config.test_acoes_com_tela`,
`push.test_toque_offline_na_tela`, `plans.test_home_adaptativa`,
`plans.test_hidratacao_v2`, `config.test_superficie_de_foco` e
`accounts.test_pilares` — todos verdes. Suíte completa antes do PR.

**Sabotagem, oito guardas, todas vermelhas pelo motivo certo:** devolver o
`open` à refeição da vez (9 falhas), tirar a marca da linha (6), voltar "Comi
esta" no cardápio (1), voltar o `btn--primary` na primeira opção (1), tirar o
chip (1), voltar "Pulei" como `btn-link` (1), devolver o cartão AGORA à
Alimentação (1) e voltar "Comi esta" na folha da receita (3).

---

## A revisão adversarial, e o que ela achou

A revisão de branch (opus, somente leitura) devolveu **NEEDS ONE FIX WAVE**
com um achado crítico que o meu QA não pegou — e a explicação de por que não
pegou é a parte que vale guardar.

### O defeito: a linha da refeição vencida espremia o nome a zero

Na `pendente`, a linha fechada ficou com DOIS rótulos longos e
não-encolhíveis lado a lado: o convite `"Não registrada · registrar"`
(`flex: none`) e a marca nova `"Ficou para trás"` (`flex: none;
white-space: nowrap`). `.meal__linha` é `display: flex` **sem `flex-wrap`**,
e o único filho com `min-width: 0` é o nome da refeição — que foi espremido a
**0 px**, virando uma letra por linha.

Medido a 390 px, no navegador, com o relógio congelado às 20h:
`"14:30 Almoço · Ficou para trás"` com **145 px de altura** e nome com
**0 px** de largura.

**Por que o meu QA não pegou:** a tabela de prova trazia "rolagem lateral:
nenhuma". Isso não prova nada neste app — `html` tem `overflow-x: hidden` na
raiz, então transbordo horizontal é **recortado**, nunca vira barra. E eu
medi a altura da PÁGINA, não a de cada linha. O estado `pendente` só existe
depois que uma refeição vence, e a captura das 9h — a que eu olhei — não
tinha nenhuma.

### O conserto: uma marca por linha

Na `pendente` a marca **substitui** o convite (os dois diziam a mesma coisa
com palavras diferentes), e `.meal__linha .meal__marca` passou a encolher
antes do nome (`flex: 0 1 auto`, `min-width: 0`, `text-overflow: ellipsis`).

| | antes da onda | depois |
|---|---|---|
| linha `pendente`, 390 px | 145 px de altura, nome 0 px | **44 px**, nome 50 px |
| transbordo horizontal | 23–82 px (recortado) | **0** |

E a régua que faltava: `test_a_linha_fechada_nao_espreme_o_nome_da_refeicao`
exige no CSS que a marca ceda antes do nome, e no HTML que a pendente traga
UM rótulo à direita. Sabotada (devolvendo o convite ao lado da marca), fica
vermelha.

### O resto da onda

- **As duas saídas tinham tamanhos diferentes de verdade.** `.fora__abrir`
  declara `min-height`, `padding`, `font-weight` e vem 3.000 linhas depois do
  `.btn` com a mesma especificidade — então vencia: 44 px contra 52, 16 px de
  texto contra 14,4. A igualdade que eu medi (70/68 px) era acidente da
  largura daquela coluna. Agora as duas medem **143×73 e 141×71, as duas com
  14,4 px**.
- **A Ajuda ensinava um botão que não existe mais** ("Pulei"), na mesma área
  do app em que o CHANGELOG anuncia o renome. Corrigida, junto com a vitrine
  da gestão e o README.
- **A régua do rótulo virou varredura de `templates/`** em vez de cinco
  rotas: a promessa escrita é "tela nenhuma", e uma tela nova com o rótulo
  velho passava.
- **Ramo morto no cabeçalho da refeição** (inalcançável desde que o cabeçalho
  virou só de quem tem `log`), com o rótulo antigo "Pendente" dentro. Apagado.
- **`CLAUDE.md` com dois números errados**: o alvo das secundárias (3,25 rem
  do `.btn`, não 44 px) e o teto de consultas (19, não 18 — e é TETO).

## A suíte completa

**4.506 testes, 2 falhas**, e nenhuma delas é da branch:

1. `plans.tests.HojeV2ViewTests.test_a_primeira_dobra_traz_uma_acao` — prendia
   o cartão AGORA NESTA tela. A missão previa o caso ("se algum teste prende o
   AGORA aqui, ele passa a prender a AUSÊNCIA"): virou
   `test_a_primeira_dobra_e_o_anel_e_nao_um_cartao_repetido`, que exige o anel
   e a ausência do cartão.
2. `config.tests.ResponseCompressionTests.test_no_rule_targets_a_class_the_templates_never_render`
   — **ambiental**. A régua de CSS órfão ignora arquivos `.py` sob
   `scratchpad/`, e este worktree mora em `scratchpad/wt-alim`: os `.py` do
   app inteiro ficam de fora, e `senha__titulo`/`senha__regras` (que nascem em
   `accounts/forms.py`) parecem órfãs. Reproduzido idêntico num worktree do
   commit base, **sem nenhuma mudança minha**. No CI e em qualquer worktree
   fora de `scratchpad/` passa.

## Decisões que tomei sozinha

1. **Os dois CTAs de contorno, não os dois verdes** (o dono deixou a escolha
   explícita). Motivo acima; é a decisão mais fácil de vetar — trocar
   `btn--ghost` por `btn--primary` nos dois é uma linha do template.
2. **O texto das marcas: "Agora" e "Ficou para trás".** O selo "Pendente" que
   existia no cabeçalho dizia o estado interno; na linha, ao lado de "Não
   registrada · registrar", o que faltava dizer era QUANDO ela era.
3. **O chip fica dentro do link do card**, acima do nome — é informação sobre
   a receita, e quem toca no card quer a receita.
4. **O ramo `sugestao` do `_agora.html` foi apagado**, em vez de deixado sem
   chamador. Código que não roda é dívida que parece funcionalidade.
5. **"Refeição pulada"** continua sendo o texto do CARTÃO já registrado. O
   dono renomeou a AÇÃO ("Pulei" → "Não comi"); o resultado é outra frase, e
   mudá-la sem pedido seria escopo que ninguém pediu.
6. **`align-items: stretch` + `display: grid` no formulário do "Não comi"**
   para as duas saídas terem a mesma altura quando uma quebra em duas linhas
   (medido: 52 px contra 68 antes do ajuste).

7. **Uma marca por linha na pendente** (25/09): a marca substituiu o convite
   "Não registrada · registrar" em vez de somar-se a ele. O convite dizia o
   que fazer; a marca diz quando era — e abrir a linha, que é um toque, mostra
   os botões. Vetável: trazer o convite de volta exige a linha quebrar
   (`flex-wrap`), e aí ela deixa de ser uma linha.

## O que não mudou

O card de receita (ilustração, macros, ingredientes, porção, "Ver a
receita"), a folha e o painel da receita, o anel e o `topo.modo`, a lista de
compras, `OptionLabel` no banco e o orçamento de 18 consultas de
`plans:alimentacao` — nada aqui custa consulta.

## Armadilhas desta missão (para a próxima sessão)

- **O service worker serve a página velha.** Depois de trocar template ou
  CSS, o navegador continuava mostrando a versão anterior — inclusive com o
  cartão AGORA que já não existia no código. Antes de medir:
  `navigator.serviceWorker.getRegistrations()` → `unregister()` e
  `caches.keys()` → `delete()`.
- **`congelado_em(...).__enter__()` não congela nada.** O contextmanager
  devolve um gerador sem referência forte; o coletor de lixo o fecha no
  primeiro ciclo, o `finally` roda `desligar()` e o servidor volta ao relógio
  de parede sem avisar. O certo é `Relogio(instante).ligar()` guardado numa
  variável de módulo. Sintoma: três servidores "congelados" em horas
  diferentes respondendo todos a mesma hora.
- **Matar o runserver pelo PID do `netstat` nem sempre mata.** Depois do
  `taskkill`, a porta continuava respondendo com o processo antigo — e o
  login falhava com "E-mail ou senha incorretos" porque o servidor velho
  tinha outro estado. Porta nova resolve em segundos; diagnosticar custou
  meia hora.
- **`agent-browser fill` não preenche campo de senha** (o valor volta vazio);
  `type` preenche. E `find role button click "ENTRAR"` acerta o botão do
  Google — o `<h1>` também se chama ENTRAR. Use o `@ref` do `snapshot -i`.
- **`git checkout --` para desfazer sabotagem apaga trabalho não commitado.**
  Uma restauração levou junto três tarefas. O script de sabotagem passou a
  guardar cópia antes de quebrar.
- **"Não rola na horizontal" não prova nada neste app.** A raiz tem
  `overflow-x: hidden`: o transbordo é recortado, e a medida que denuncia é
  `scrollWidth - clientWidth` de cada ELEMENTO, ou a altura da linha. Foi o
  que escondeu o defeito crítico desta missão.
- **Medir a página inteira esconde o defeito de uma linha.** A altura caiu
  1.000 px e, no meio disso, uma linha tinha triplicado. Meça o componente que
  você mexeu, no estado em que ele aparece (aqui: `pendente`, que só existe
  depois que uma refeição vence).

## O que preciso de você

Nada.
