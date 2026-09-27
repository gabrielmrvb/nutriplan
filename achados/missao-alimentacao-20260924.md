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

## O que preciso de você

Nada.
