# Progresso: de extrato a tela de evolução

**Sessão `progresso-mais` (3146901b), 23/09/2026.** Redesenho de `/historico/`.
A tela de **Mais** (`/areas/`, itens 11–15 do pedido) **não entrou**: a missão
foi interrompida por uma missão nova do dono, e o que está aqui é o que ficou
provado. O que falta está na seção 6.

Diagnóstico do dono, reproduzido no ambiente de desenvolvimento com duas
contas sintéticas e medido no navegador antes de qualquer edição.

---

## 1. O antes, medido

`manage.py semear_progresso` cria as duas contas que a tela precisa provar —
a de **três dias** (o que todo mundo vê na primeira semana) e a de **seis
semanas** (onde os gráficos têm o que desenhar), de forma determinística.

| conta | antes | depois |
|---|---|---|
| 3 dias | **24 linhas de semana**, sete delas começando em 03/08 — antes de a conta existir —, 18 "—" e "0,0 km" | **zero** linha anterior ao cadastro; mapa de 3 dias, sem barra de semana |
| 6 semanas | mesmas 24 linhas, sem período selecionável e sem tendência | seletor de período, 4 tiles com direção, 4 mapas + 4 séries de barras |

A régua nova é `plans/evolucao.janela`: o recorte começa no máximo em
`primeiro_dia_da_conta`, e **tudo** que a tela desenha sai dele.

> "Buraco na série é informação" continua verdade — e vale para buraco DENTRO
> da série. Fora dela não há buraco: não havia app. Uma semana de 03/08 numa
> conta de 21/09 não diz "você não treinou"; diz que o app não sabe o que
> perguntar.

## 2. O que foi entregue, item a item

| # | pedido | estado |
|---|---|---|
| 6 | estados vazios que nunca mostram semana anterior ao cadastro | **feito** — regra única, com teste e sabotagem |
| 1 | seletor Semana · Mês · 3 meses + 4 tiles de tendência | **feito** — `?p=`, sem JavaScript, lista fechada |
| 2 | peso como gráfico de verdade, campo compacto no rodapé | **feito** — linha com pontos nas pesagens, eixo de datas, média móvel de 7 dias |
| 3 | treino: heatmap, volume por semana, recordes, sequência | **feito** |
| 4 | alimentação com seção própria | **feito** — heatmap, kcal média por semana, top 3 receitas |
| 5 | água e corrida no mesmo padrão | **feito** — corrida só para quem correu, com ritmo |
| 8 | explicações atrás de um "?" | **feito** |
| 9 | um sistema de gráfico só | **feito** — `plans/graficos.py`, SVG inline, sem biblioteca |
| 10 | desktop 2×2, 390 px empilhado, período fixo ao rolar | **feito** |
| 7 | conquistas como estavam | **não tocado**, como pedido |
| 11–15 | a tela **Mais** | **NÃO FEITO** (seção 6) |

## 3. Três defeitos que só o navegador pegaria

1. **Coordenada de SVG localizada.** O app é pt-BR e o Django formata número
   com vírgula: o eixo saía `y="140,0"`, atributo inválido, e o gráfico não
   desenhava — sem erro no console e sem nada vermelho num teste que só
   confira o status. `{% localize off %}` em volta de todo SVG, com
   `plans/test_progresso_tela.OSvgDaTelaEValidoTests` prendendo.
2. **A classe de leitor de tela que este app não tem.** Escrevi `sr-only`; a
   classe daqui é `vis-oculto`. O texto do "?" aparecia visível e quebrava o
   cartão.
3. **A média móvel invisível.** Com pesagem semanal, cada janela de sete dias
   tem um ponto só: a "média" saía idêntica à linha, escondida embaixo dela,
   com uma legenda prometendo o que não se via. Ela só nasce quando alguma
   janela tem mais de um ponto.

## 4. Decisões que tomei sozinha

1. **A paleta é a que o app já tem.** O pedido falava em "roxo corrida"; roxo
   não existe nesta paleta e inventar uma matiz é mexer em direção visual de
   que o `DESIGN.md` é dono. Treino usa `--folha` (o verde do que FOI FEITO,
   que é a distinção que o app já tinha escrita), alimentação `--carb`
   (o laranja da barra de macros), água `--agua`, corrida `--brasa`, peso
   `--terra`. **Recomendo rever** se o roxo for direção.
2. **Não há faixa de meta no gráfico de peso**, porque não há peso-alvo: o
   `Profile` guarda o OBJETIVO (emagrecer/manter/ganhar), não um número.
   Desenhar a faixa exigiria inventar a meta.
3. **A lista de progressão de carga ("60 → 62,50 kg") saiu** e "Seus
   recordes" ficou no lugar — é o que o pedido lista para o Treino, e o
   número por exercício continua na tela de execução.
4. **Sem colunas de semana quando há uma semana só**: uma barra sozinha
   desenha 100% de si mesma.
5. **A prévia fantasma é da TELA, não de cada cartão** — repetida quatro
   vezes numa rolagem, a explicação vira ruído.
6. **O período viaja em `?p=`**: funciona sem JavaScript, entra no histórico
   do navegador e dá para guardar nos favoritos.

## 5. Custo e provas

- **10 consultas** para o painel inteiro, e o número **não muda** entre
  "Semana" e "3 meses" (há teste que compara os dois). O orçamento da rota
  subiu de 29 para 31, com a razão escrita no `plans/test_stress.py`.
- **Suíte completa** verde.
- **Navegador**: 20 combinações (2 contas × 2 temas × 360/390/430/768/1280) —
  zero violação do axe a 390 nos dois temas, zero rolagem horizontal, zero
  alvo abaixo de 44 px, zero texto abaixo de 11 px.
- Capturas de antes e depois nas duas contas, dois temas, 390 e 1280.

## 6. O que NÃO foi feito

- **A tela Mais (`/areas/`), itens 11 a 15.** Nada dela foi tocado: continua
  com "ÁREAS SEM ABA", cards de tamanhos desiguais e o Perfil mostrando
  "2.372 kcal por dia" como se fosse métrica. A captura do antes está no
  material da missão.
- **Código morto que este redesenho criou e que não removi**:
  `plans.views._curva_de_peso`, `workouts.progresso.progressao_de_carga` e
  `workouts.progresso.km_corridos` agora só são chamados pelos próprios
  testes. Remover produto + teste é mudança própria, e misturá-la num
  redesenho já grande piora a revisão.
