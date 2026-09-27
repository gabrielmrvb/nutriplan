# Missão pente-fino 1 — os sete achados da varredura de 24/09/2026

Sete achados MEDIDOS numa varredura de 13 telas logadas (390×844 escuro e
1280×900 claro) contra produção `3a6094b`. Executada de 24 a 27/09/2026.
Cada item saiu numa branch própria, com teste que fica vermelho sem a
correção, e cada número abaixo foi tirado do navegador (agent-browser) contra
o código da branch — não estimado.

**Skills do superpowers, onde cada uma entrou:** `writing-plans` (o plano
`docs/superpowers/plans/2026-09-24-pente-fino-1.md`, com as Global
Constraints e uma task por achado) → `subagent-driven-development` (itens
1–4: um subagente por item, worktree próprio, `brief`/`report`/`package` e o
ledger `.superpowers/sdd/2026-09-24-pente-fino-1/progress.md`) →
`executing-plans` (itens 5, 6 e 7 — e o fechamento dos itens 3 e 4, quando o
subagente do item 3 morreu no teto de gasto mensal da conta) →
`test-driven-development` (vermelho antes de verde nos sete, com sabotagem em
cada régua nova) → `requesting-code-review` (revisão adversarial por item; os
pareceres estão no `progress.md`) → `verification-before-completion` (a seção
"O que eu provei, e como") → `finishing-a-development-branch` (uma branch por
item, PR, fila, staging, lote).

## O placar

| # | achado | branch | commit |
|---|---|---|---|
| 1 | CTA "CONTINUAR TREINO (1 DE 7)" em cinco linhas | `ux/cta-do-painel` | `0f530eb` |
| 2 | frase órfã "A e B fecham a mesma caloria" | `copy/sem-a-e-b` | `d2a5b3f` |
| 3 | quatro telas presas em 440 px no desktop | `ux/desktop-quatro-telas` | (ver abaixo) |
| 4 | `<text>` de 9 px no SVG do peso | `design/rotulo-do-grafico` | `716102f` |
| 5 | "Seus recordes" × "0 recordes" | `ux/pente-fino-1` | `1b25f72` |
| 6 | "Opção A"/"Opção B" na lista de compras | `ux/pente-fino-1` | `1b25f72` |
| 7 | "Nenhuma ainda" em manchete · "dias combinados" | `ux/pente-fino-1` | `1b25f72` |

## Item 1 — o CTA do painel do Treino não cabia numa linha

**Antes / depois, medidos nos quatro recortes** (390 e 1280 × escuro e
claro), com uma pessoa local de QA cujo dia de treino é hoje e com UMA série
registrada — o estado em que o rótulo tem números:

| | altura do botão | `flex-direction` |
|---|---|---|
| antes | **157 px** | `column` |
| depois | **54 px** | `row` |

Duas causas somadas, e as duas estão na régua: `.btn` é `inline-flex`, então
cada trecho de texto solto entre os `<span class="num">` virava um item de
flex próprio (cinco: `"Continuar treino ("`, `1`, `" de "`, `8`, `")"`), e
`.btn--hoje` ainda declarava `flex-direction: column` — sobra do desenho em
que o botão tinha um "eco" com o nome do exercício embaixo, removido em
22/09/2026, quando a ficha virou lista. O rótulo virou UM `<span>` e a regra
perdeu o `column`.

`workouts/test_cta_do_painel.py` prende as duas pontas (o rótulo é um filho
de primeiro nível do `<a data-hoje-cta>`; a regra não volta a declarar
`column`), e a catraca de espaço cru do design system desceu 229 → 228.

## Item 2 — a frase falava de "A e B" depois de A e B saírem da tela

O rótulo A/B saiu da interface em 23/09 (o card de receita parou de escrever
a letra) e três textos continuaram citando as letras: a dica abaixo do
cardápio na Alimentação, a resposta da Ajuda e o e-mail de boas-vindas. A
frase nova diz "as duas opções", sem mudar o sentido.

A régua nova mede o TEXTO VISÍVEL do `<main>` (reusa `texto_visivel` e
`apenas_o_main` de `config/test_linguagem.py`, a mecânica da régua de
linguagem de 21/09): nenhuma tela do app escreve "opção A"/"opção B".

## Item 3 — quatro telas abriam como um celular no meio do monitor

**Medido com a MESMA conta e o MESMO cookie, minutos entre as duas leituras**
(tabela no escuro; no claro os números são idênticos — a diferença é de cor):

| tela | recorte | `<main>` antes | `<main>` depois | altura antes | altura depois |
|---|---|---|---|---|---|
| Treino | 1280 | 480 (440 úteis) | **1024 (984)** | 1.098 | **900** |
| Hidratação | 1280 | 480 (440) | **1024 (984)** | 1.817 | **1.567** |
| Conquistas | 1280 | 480 (440) | **1024 (984)** | 1.092 | **900** |
| Lista de compras | 1280 | 480 (440) | **1024 (984)** | 4.123 | **3.243** |
| Treino | 1024 | 480 (440) | **1009 (969)** | 1.098 | **900** |
| Hidratação | 1024 | 480 (440) | **1009 (969)** | 1.817 | **1.567** |
| Conquistas | 1024 | 480 (440) | **1009 (969)** | 1.092 | **900** |
| Lista de compras | 1024 | 480 (440) | **1009 (969)** | 4.123 | **3.243** |
| Progresso (controle) | 1280 | 1024 (984) | 1024 (984) | 2.194 | 2.194 |
| Hoje (controle) | 1280 | 1024 (984) | 1024 (984) | 900 | 900 |

Grade de duas colunas depois, a 1280: **480 + 480 px** nas quatro telas
(472,5 + 472,5 a 1024). `rolagemH` é **falso** em todos os recortes
medidos, antes e depois.

A Lista de compras chegou a esse número numa SEGUNDA volta, e o motivo está
na seção da revisão adversarial: com o `.split` em volta ela ficava com
colunas de 304 px (264 úteis), menos que os 295 úteis do mesmo cartão num
celular de 390 — larga no `<main>` e mais apertada no conteúdo. Sem o
`.split` são 480, e a altura vai de 2.635 para 3.243 porque "Como usar" e
"Seu cardápio" deixaram de ser uma faixa lateral fora do fluxo e viraram
duas células da grade. Ainda são 880 px a menos que os 4.123 de hoje.

**No celular (390) nada piorou, e duas telas encurtaram:** Treino 1.271 →
1.239 px e Hidratação 2.016 → 1.983; Lista de compras fica em 4.280,
idêntica; Conquistas 1.168 = 1.168. A razão do ganho é o segundo achado
deste item.

### O que este item achou de quebra, e que virou régua

Ao tirar o `<div class="split">` do painel do Treino, o filho ficou com
`split__main` sem pai. Não é cosmético: `.split__main` é `display: flex` com
`gap: var(--gap)` e, somado ao `.card + .card` que os cartões já têm, ele
DOBRA o vão entre cartões no celular. Medido a 390 px em /treino/: 1.271
(main) → 1.287 com a classe órfã → 1.239 sem ela.
`config/test_largura_do_desktop.py` ganhou `SplitMainSemSplitEhClasseOrfaTests`,
que varre `templates/` e ignora `{% comment %}` — duas telas EXPLICAM a
classe em comentário, para dizer por que não a usam.

E a norma do vão no celular está medida, e é DIVIDIDA: **32 px** nas telas
com `.split__main` (Progresso, Alimentação, Lista de compras, Perfil) e
**16 px** nas que são `.stack` direto (Conquistas). Treino e Hidratação
passaram para 16 — o `--gap` que o design system declara, igual ao da
Conquistas da mesma missão.

## Item 4 — o rótulo de 9 px do gráfico, e a medida que engana

Os 25 `<text>` dos gráficos de `/historico/` saíam com `font-size="9"`. O
piso do app é 11 px, e a régua que o cobra só varria CSS — este tamanho é
ATRIBUTO do `<text>`, escrito por `plans/graficos.py`.

`TAMANHO_ROTULO` foi a 12, com as margens recalculadas (ESQ 34 → 40, TOPO
10 → 12, BASE 20 → 24) para o rótulo maior não estourar o eixo. Medido:
**25 rótulos a 9 px → 25 a 12 px**, nenhum vazando a caixa do `<svg>`, em
390, 1024 e 1280, nos dois temas.

E a medição que ficou escrita no módulo, porque a primeira sozinha engana —
`getComputedStyle` devolve o DECLARADO, mas o glifo na tela é
`declarado × largura_do_svg / 320`:

| recorte | largura do `<svg>` | escala | pintado com 9 | pintado com 12 |
|---|---|---|---|---|
| 390, qualquer gráfico | 293 | 0,916 | 8,2 px | **11,0 px** |
| 1280, o peso (duas colunas) | 590 | 1,844 | 16,6 | 22,1 |
| 1280, as colunas (uma coluna) | 262 | 0,819 | 7,4 | **9,8** |

12 é o valor que faz o CELULAR — onde este app é usado — chegar ao piso.

## Itens 5, 6 e 7 — uma branch, quatro correções pequenas

**Item 5 — recorde é o que superou uma data anterior.** A varredura mediu uma
conta com UMA série (40 kg × 6) e viu duas telas dizendo o oposto sobre o
mesmo dado: "Seus recordes · Agachamento livre 40 kg × 6" no Progresso e
"0 recordes" nas Conquistas. As duas certas dentro da própria definição — e a
palavra era a mesma. Decisão do dono, aplicada: **a primeira série não é
recorde em lugar nenhum**. A lista virou "Melhores cargas" e
`evolucao.recordes` devolve `e_recorde` por linha — um `Exists` de registro
ANTERIOR do mesmo exercício com carga menor (`date__lt`: subir a anilha entre
a série 1 e a 2 do mesmo treino é aquecimento, não marca) — dentro do
`DISTINCT ON` que já existia: **uma consulta**, com `assertNumQueries(1)`,
porque `plans:history` tem teto medido. Oito testes, um deles cruzando as
duas telas.

Preço na tela, medido a 390: a `pill` de "recorde" empurra o valor para a
segunda linha nas linhas de nome curto (25 → 52 px). Para quem treina há
semanas quase toda linha tem a marca — e é verdade que tem; quem estreia é
que precisa ver a ausência dela.

**Item 6 — a lista de compras não fala "Opção A".** Os dois chips viraram
"Com a sugestão do dia" e "Com a outra opção"
(`plans.models.ROTULOS_DA_LISTA_DE_COMPRAS`). A letra continua no banco, no
`?opcao=` e no rodízio — é o que a docstring de `OptionLabel` sempre disse
que ela era.

**Item 7a — estado vazio não grita.** Os quatro `painel__valor` de PALAVRA da
Home ("Descanso", "Sem ficha", "Nenhuma ainda", "Sem pesagem") saíam na fonte
dos números (display, 900, caixa alta, 28 px). Ganharam
`painel__valor--palavra` — e a regra é **a da branch da Home (#138), copiada
verbatim**, para as duas mergearem sem briga.

**Item 7b — "dias combinados" virou "previstos".** Ninguém combinou dia de
treino com o app: a pessoa declarou no cadastro.

## A revisão adversarial, e o que ela mudou

Três revisões independentes (uma por branch aberta), com o pedido de achar
defeito real, teste que passa por acidente e comentário que mente. Elas
acharam **dois defeitos de verdade e uma conta errada**, e os três viraram
commit:

- **Item 5 marcava recorde onde não havia.** A régua era `Exists(data
  anterior com carga MENOR)`, e `achievements` sempre comparou com o
  MÁXIMO anterior. As duas só coincidem em histórico monótono: 60 kg em
  julho, 50 em agosto (deload), 60 em setembro — o `DISTINCT ON` fica com a
  linha mais recente das empatadas em 60, e ali existe sim uma data
  anterior com carga menor. A tela diria "recorde" para um dia que só
  empatou com o próprio pico. Agora é uma subconsulta com `Max`, e dois
  testes novos ficam vermelhos com a régua antiga.
- **Item 3 tinha alargado o `<main>` da Lista de compras e apertado o
  conteúdo.** A conta está na seção do item 3: 304 px por corredor com o
  `.split`, 480 sem ele.
- **Item 4 engolia `font-size="9px"` em silêncio** (um `except ValueError:
  continue` no scanner) e citava 11,1 px onde a escala da própria tabela dá
  11,5. O valor ilegível virou `-inf` e o scanner passou a ler aspas
  simples e `<tspan>`.

E uma alegação da revisão **não se confirmou na medição**: os rótulos de
data do gráfico de colunas não se sobrepõem no trimestre. A revisão supôs
uma data por barra (13 no trimestre); medido no navegador nos três
períodos, a 390 e a 1280, o gráfico desenha DUAS datas — primeira e última
— e o pior vão entre elas é 85,2 px a 1280 (era 96,6 com o rótulo de 9).

## O que a missão achou de quebra, e não estava no enunciado

- **`split__main` sem `.split` dobra o vão entre cartões no celular**
  (16 → 32 px). Régua nova, com parser de ancestrais depois da revisão.
- **A régua de classe órfã media a MÁQUINA**: ela descartava `scratchpad/`
  por parte ABSOLUTA do caminho, e o worktree de uma sessão do Claude Code
  mora dentro de um diretório com esse nome — zero `.py` lidos e duas
  classes reais (`senha__regras`, `senha__titulo`, que `accounts/forms.py`
  escreve com `mark_safe`) acusadas como CSS morto. Verde no CI, vermelho
  na máquina. Hoje o recorte é relativo à raiz.
- **`CHANGELOG.md` colidia entre sessões paralelas** — duas vezes em poucas
  horas, as duas por duas linhas do mesmo dia querendo existir. Virou PR
  próprio (`chore/changelog-union`): `merge=union` no `.gitattributes`,
  medido em três cenários com `git merge` de verdade, mais a regra de mão
  no `CLAUDE.md` (só ACRESCENTAR linha sob a data do dia). O mesmo dia
  mostrou o limite: resolver o `django.po` por união CORTA no meio de uma
  entrada — por isso a linha nomeia UM arquivo, não um padrão.
- **O marcador `*(gerência, não aparece para quem usa)*` do CHANGELOG é
  decorativo**: `ajuda/mudancas.py` coleta todo `- ` da seção, então os
  itens internos APARECEM em `/ajuda/o-que-mudou/`. Fora do escopo desta
  missão; virou tarefa à parte.

## Recomendo rever (nada aqui bloqueia)

- **O vão entre cartões no celular é DIVIDIDO**: 32 px nas telas com
  `.split__main` (Progresso, Alimentação, Lista de compras antes deste PR,
  Perfil) e 16 px nas que são `.stack` direto. Treino, Hidratação, Lista de
  compras e Conquistas agora estão nos 16 do design system; uniformizar as
  outras é mexer no espaçamento de três telas, e isso é decisão de produto.
- **Os gráficos de coluna do desktop pintam o rótulo a 9,8 px** mesmo com a
  constante em 12, porque o `viewBox` de 320 unidades é desenhado numa
  caixa de 262. A saída é dar a cada gráfico um `viewBox` proporcional à
  caixa — geometria, missão própria.
- **A `pill` de "recorde" custa altura no celular**: linhas de nome curto
  vão de 25 para 52 px a 390. Quem treina há semanas tem marca em quase
  toda linha.

## O que eu provei, e como

Classe de evidência por item, com o comando/medida que sustenta cada um.

| item | prova em teste | prova no navegador |
|---|---|---|
| 1 CTA | `workouts/test_cta_do_painel.py` (markup + regra de CSS), sabotagem vermelha | altura 157 → 54 px e `column` → `row` nos 4 recortes, com série registrada |
| 2 "A e B" | `config/test_linguagem.py` sobre o texto visível do `<main>`, mais o contrapeso da preposição | captura das 4 telas com a frase nova |
| 3 largura | `config/test_largura_do_desktop.py`, 3 pontas (largas · lista fechada de estreitas · `split__main` órfão por parentesco), todas vermelhas sob sabotagem | tabela de `<main>`/altura/colunas a 390, 1024 e 1280 nos dois temas, antes e depois, com `rolagemH` falso |
| 4 rótulo SVG | `config/test_design_system.py` (piso na constante + varredura de `<text>`/`<tspan>` com controle positivo), sabotagem vermelha | 25 rótulos 9 → 12 px, nenhum vazando, nos 3 recortes; declarado × pintado medido |
| 5 recorde | 10 testes em `plans/test_melhores_cargas.py`, inclusive `assertNumQueries(1)` e o cruzamento com `achievements` | lista do Progresso com e sem a marca |
| 6 rótulos da lista | `plans/test_lista_sem_a_e_b.py` (3) | chips da Lista de compras |
| 7 palavra/previstos | `plans/test_valor_de_palavra.py` (3) + `OTileDeTreinoDizPrevistosTests` | cartões da Home e tile do Progresso |

Suítes locais: `config`, `workouts`, `achievements` (2.252 testes) na branch do
item 3, e `plans`, `config`, `achievements`, `workouts` (3.175) na dos itens
5–7. As únicas falhas foram o falso positivo de ambiente já descrito (hoje
consertado), cinco `HashingError` do Argon2 por falta de memória com cinco
servidores de QA abertos, e `config.test_relogio.test_a_hora_e_a_da_suite_e_continua_andando`,
que compara a hora congelada (12:00) com a hora corrente e cai quando a
execução passa de 60 minutos — a fatia do CI não chega perto disso.

**O que eu NÃO provei:** o comportamento das quatro telas largas em
1440/1920 (medi 390, 1024 e 1280, que é a faixa do `container.largo`, que
trava em 1024); e o vão de 32 px das outras telas com `.split__main`, que
está medido mas não foi tocado.

## Produção, com conta descartável

Os sete itens entraram em `main` e subiram no lote; produção respondeu
`3fe74a7` em `/saude/` (`ambiente: ""`). O QA foi feito com conta criada
pelo signup público (`qa-e2e-pentefino-20260927@nutriplan.invalid`, senha
gerada e nunca impressa), reusando o harness do E2E noturno, nos quatro
recortes (390 e 1280 × escuro e claro) — e **a conta foi apagada pela tela
no fim, com o login recusado depois** (está no log). Nada do demo foi
tocado.

| item | medido em produção |
|---|---|
| 1 | CTA `altura: 54`, `flex-direction: row`, nos **quatro** recortes, com série registrada |
| 3 | `<main>` **1024 (984 úteis)** e colunas **480+480** nas quatro telas a 1280; 375/335 a 390; `rolagemH` falso em todos |
| 4 | rótulo do gráfico: **declarado 12, pintado 11,0** a 390 |
| 6 | chips "Com a sugestão do dia" e "Com a outra opção"; nenhuma tela com "Opção A" |
| 7a | `class="painel__valor painel__valor--palavra">Descanso` — e os valores de número seguem em Big Shoulders a 28 px |

Os itens 5 e 7b foram conferidos pelo `/demo/` logo depois (a conta nova não
tem histórico para a lista aparecer): `/demo/historico/` responde
**"Melhores cargas"** e **"previstos no período"**.

*(Duas leituras do roteiro precisaram de conferência à mão e ficam
registradas: a sonda de texto procurava a palavra "combinado" na tela
inteira e achava — mas nas frases da LEGENDA do mapa ("era dia combinado",
"cumprir o combinado") e num rótulo de descanso, não no tile; e "Melhores
cargas" não aparece para conta sem carga registrada.)*

## O que preciso de você

Nada.
