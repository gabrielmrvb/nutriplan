# Padrões de mercado — Fase 3: dieta cozinhável (Lote 2 da avaliação)

Missão de 16/09/2026, Fase 3. Referência: `docs/briefs/mercado/BENCHMARK-2026-09.md`
(padrão e; "o cardápio precisa ser cozinhável e comprável"). Estado medido: `DELTA.md`
B15 (aberto, pior: "Aveia 282 g"), B16 (aberto, idêntico), B17, B14. Spec vence
proposta externa; divergências vão para "recomendo rever".

## O que já existe (não refazer)

- `catalog.FoodPortion(food, label, grams, is_default)` — 79 dos 102 alimentos
  têm porção; o `label` carrega o número ("1 colher de sopa", "1/2 unidade").
  **Nunca é lida** fora do seed. `MealOption.ingredient_list()` devolve
  `{"food", "quantity", "unit"}`; `today.html:637` imprime `quantity|floatformat:0 unit`.
- `plans/meal_planner.py`: `scale_for` com `MIN_SCALE 0,5 / MAX_SCALE 2,5`;
  café = 25 % da meta (`DAY_BLUEPRINT`). No perfil de referência (2 859 kcal,
  slot 715) os 16 cafés escalam 1,38×–2,50× (só a vitamina com amendoim, base
  550 kcal, fica abaixo de 1,5×). Base necessária: ≈ 480–520 kcal escaláveis.
- `plans/compra.py`: `FATOR_CRU` (8), `POR_UNIDADE` (7), `EMBALAGEM` (8);
  `converter(nome, quantidade, unidade) -> (texto, aproximado)`; **sem** mínimo
  de compra. `plans/shopping.py`: degraus 10/50/100 g, `shopping_list`.
- `plans/services.py::plan_is_current`: igualdade **exata** de entradas e saídas
  (`weight_kg` Decimal(5,2)) — 0,1 kg regenera o plano e reescolhe o cardápio.
  `rodizio.py` semeia por `user_pk:slot` + dia (não pelo plano), mas projeta
  sobre `slot.options` do plano ativo: plano novo = receitas novas.
- `plans/weight_trend.py::analisar`: "estabilizou → cortar 150" sem olhar `goal`;
  `RecalibrateView` só conhece `acao == "cortar"`. `Goal`: cut/bulk/recomp/maintain.

## 3.1 Medida caseira em toda quantidade

**Dado.** `FoodPortion` ganha `singular` e `plural` sem o número ("colher de
sopa" / "colheres de sopa"; "copo"/"copos"; "unidade média"/"unidades médias";
"fatia"/"fatias"; "ovo médio"/"ovos médios"…), preenchidos no
`catalog/data/foods.json` para as 85 porções (migração aditiva, `blank=True`;
o seed grava). O `label` antigo fica (admin e `__str__`). Regra: o plural é
**escrito**, não derivado — pt-BR não deriva "colher → colheres" por regra.

**Cálculo** (`plans/porcoes.py`, função pura): `medida_caseira(quantidade_g,
porcao) -> (n, rotulo)`: `n = quantidade / grams` arredondado a **meio** (0,5)
pelo `ROUND_HALF_UP` do app; `n < 0,5 → None` (mostra só grama); rótulo
singular se `n == 1`, plural senão; número com vírgula e sem zero à direita
("2", "2,5", "7,5"). Só a porção `is_default` conta.

**Tela.** `ingredient_list()` devolve também `caseira` (`n`, `rotulo`) e o
template mostra **"7,5 colheres de sopa (116 g)"**; sem porção, **"116 g"** como
hoje. Vale na Home (opções A/B), em "Comi outra coisa" NÃO (fora do escopo — o
campo pede grama; U16 fica).

**Café recalibrado** (decisão padrão da missão): as quantidades-base dos 15
cafés abaixo de 480 kcal sobem, mantendo a proporção da receita sensata
(mingau: aveia 50→80 g, leite 200→300 ml, banana continua 1 unidade não
escalável; pão: 1→2 unidades; ovos: 2→3; tapioca: 60→90 g…), até a base
escalável ficar em 480–540 kcal. Teste: para o perfil de referência, todo café
escala ≤ 1,5× e ≥ 0,7×. O registro do que mudou por alimento vai na tabela do
relatório e no commit. `MAX_SCALE` continua 2,5 (dietas de 3 500 kcal existem).

## 3.2 Lista de compras comprável

`plans/compra.py` ganha:

- `MINIMO_DE_COMPRA[nome] = (quantidade, unidade_base, rotulo_singular, rotulo_plural)`
  — a menor unidade de venda: azeite 500 ml ("garrafa"), óleo 900 ml, café 250 g
  ("pacote"), alface 1 unidade ("pé"), repolho 1 unidade, couve 1 maço (≈ 300 g),
  cebola 1 unidade (150 g), tomate 1 unidade (120 g), presunto/queijo fatiado
  100 g ("100 g" — o balcão vende por 100), iogurte 170 g ("pote"), requeijão
  200 g, pasta de amendoim 500 g, mel 250 g, aveia 200 g, granola 250 g…
- `FATOR_CRU` ganha as carnes e verduras cozidas de receita ativa: carne moída
  refogada 1,3; frango cozido/grelhado 1,35; peixe 1,25; couve refogada 1,25;
  espinafre 1,4; legumes cozidos 1,1 (rótulo "(cru)").
- `converter`: depois do cru e antes da unidade, se o alimento tem mínimo,
  arredonda **para cima ao múltiplo do mínimo** e escreve "1 garrafa (500 ml)",
  "2 pacotes (500 g)", "1 pé de alface". Sempre `aproximado=True`.

**Teste-régua** (`plans/test_lista_compravel.py`): para TODO alimento de
receita ativa (os ~50), `converter` devolve algo que não é grama/ml solto —
ou unidade, ou embalagem, ou mínimo, ou cru em kg — e nunca fração de unidade
de venda ("0,5 garrafa" proibido). Um alimento novo sem forma de compra fica
vermelho na hora.

**Divergência registrada:** `POR_UNIDADE` diz banana 90 g e `FoodPortion` diz
70 g. A porção vence (é o que a pessoa vê no cardápio); `POR_UNIDADE` passa a
ler `FoodPortion` quando existir. **Recomendo rever** se o dono souber de
onde veio o 90.

## 3.3 Pesar não regenera o cardápio

`plan_is_current` passa a tolerar `|peso_novo − plan.weight_kg| ≤ 1,5 kg`:
nesse caso o plano continua atual (entradas iguais exceto o peso dentro da
faixa; **as saídas não são comparadas**, porque mudariam só pelo peso). Fora
da faixa, ou com qualquer outra entrada diferente, nasce plano novo como hoje.
O "Recalcular" explícito de "Dados do cálculo" continua regenerando sempre.
**Nada do plano é editado** ("plano é retrato"): a meta fica a do peso do
retrato, e 1,5 kg movem a TMB em ~15 kcal — menos que o degrau de 10 g do
cardápio. Consequência aceita: o `gasto_kcal` da corrida (Fase 2) usa o peso do
retrato, até 1,5 kg defasado (≤ 1 % do gasto).

Testes: pesar +1,0 kg → mesmo plano, mesmas opções A/B do dia; +1,6 kg → plano
novo; `plans/tests.py:470-479` (82,4 → 78,0) continua regenerando; o texto
"Seus dados mudaram, então recalculamos" só aparece quando regenerou.

## 3.4 "Cortar 150 kcal" só para perda

`weight_trend.analisar` devolve `sugestao` em `{"cortar", "aumentar", None}`:
estabilizou 3 semanas → `cortar` se `goal == CUT`, `aumentar` se `goal == BULK`,
`None` para `MAINTAIN`/`RECOMP` (estabilidade é a meta). `RecalibrateView`
aceita `acao in {"cortar", "aumentar"}` (`kcal_adjustment ± 150`, com o piso
de `calculations.py` no corte e um teto simétrico no aumento). Template
`_peso.html`: botão e frase por sugestão; nada quando `None`.

## Testes

- `catalog/test_porcoes.py`: singular/plural preenchidos para as 85 porções
  (nenhum vazio), `medida_caseira` (meio, arredondamento, < 0,5, singular).
- `plans/test_cardapio_cozinhavel.py`: Home mostra "N rotulo (G g)" para
  alimento com porção e "G g" sem; os 16 cafés ≤ 1,5× no perfil de referência.
- `plans/test_lista_compravel.py`: a régua acima; `MINIMO_DE_COMPRA` nunca
  fraciona; carnes com fator cru.
- `plans/test_peso_tolerante.py`: 3.3.
- `plans/test_weight_trend.py`: 3.4 (estender).
- Intocados: `test_ficha_de_verdade.py`, `test_treino_md.py`, `test_corrida_md.py`,
  `ScalingTests.test_scale_is_clamped_to_edible_portions` (MAX_SCALE 2,5).

## Fora da Fase 3

"Comi outra coisa" com medida caseira (U16), substituição de receita (D8),
lista pela escolha registrada (D9), teto de água por IMC (D13).
