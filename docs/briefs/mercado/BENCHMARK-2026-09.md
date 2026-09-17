# Benchmark de mercado — setembro/2026

Resumo dado pelo dono em 16/09/2026 para a missão "Padrões de mercado". É
**referência**, não spec: onde ele contradiz `docs/briefs/treino/TREINO.md`,
`DESIGN.md` ou uma decisão escrita no `CLAUDE.md`, a spec vence e a
divergência vai para "recomendo rever" no relatório.

**Apps comparados:** Hevy, Strong, Fitbod, MyFitnessPal, Yazio, MacroFactor,
Strava, Nike Run Club / Nike Training Club.

## O que só o NutriPlan faz

Ninguém entrega **dieta gerada + treino gerado + corrida** no mesmo produto.
O NutriPlan é o único. Não perder isso: nenhuma das mudanças abaixo pode
enfraquecer um pilar para parecer com um app de um pilar só.

## Padrões em que 5+ apps convergiram e o NutriPlan diverge

| # | padrão | quem faz | estado no NutriPlan (DELTA 16/09) |
|---|---|---|---|
| a | recorde pessoal celebrado **na hora** | Hevy, Strong, Fitbod, Strava, NRC | ausente — `load_history` já calcula `recorde_anterior`; falta o instante |
| b | gráfico de progressão **por exercício** | Hevy, Strong, Fitbod, MacroFactor (peso), Strava | ausente — detalhe do exercício é lista "Como fui" |
| c | carga/reps da **sessão anterior pré-preenchidas em cada série** | Hevy, Strong, Fitbod | parcial — vem a série anterior de HOJE; a mesma série da última sessão já é calculada e não é usada |
| d | registro **manual** de corrida com histórico | Strava, NRC, Fitbod | ausente — só GPS ao vivo |
| e | **medida caseira** exposta no cardápio | MyFitnessPal, Yazio, MacroFactor | ausente — grama escalada ("Aveia 282 g"); `FoodPortion` existe e não é lida |

## Corrida

Strava e NRC dão **registro manual e planos 5K/10K de graça**. Um pilar só
com GPS ao vivo parece inacabado. → registro manual, planos para iniciante e
intermediário, corrida conta como treino.

## Nutrição

A reclamação nº 1 da categoria é **paywall no código de barras**. O NutriPlan
não precisa de scanner — ele **gera** o cardápio. Precisa que o cardápio seja
**cozinhável** (medida caseira, unidade inteira) e **comprável** (lista com
mínimo de compra e fator cru).

## Preço-alvo futuro

Freemium, **R$ 11,90–14,90/mês** ou **R$ 79–99/ano**. Assinatura e pagamento
são onda futura — nada desta missão implementa cobrança.

## Fora desta onda (decisões futuras, não fazer)

Social (feed, seguir, comentar) · wearables (Health Connect, Apple Saúde, relógio)
· código de barras · assinatura.
