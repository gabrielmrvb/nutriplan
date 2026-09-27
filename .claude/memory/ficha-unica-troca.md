---
name: ficha-unica-troca
description: a tela mostra UMA ficha por letra e a troca é por exercício, mas o motor continua gerando duas opções e um gate proíbe perder a segunda
metadata:
  type: business-rule
---
Desde 17/09/2026 (noite) a pessoa não escolhe entre opção 1 e 2: a
interação principal da ficha é "outras formas" — `TrocaDeExercicio` por
exercício, que vale em toda letra, semana e opção, aplicada EM MEMÓRIA por
`services.aplicar_trocas`, com a mesma dose, sem tocar em `SessionExercise`
nem em `customized_at`. O que surpreende: o MOTOR continua gerando duas
opções por letra (`SessionExercise.opcao`), e o gate permanente
`LETRAS_COM_OPCOES_EM_PRODUCAO` fica vermelho se qualquer letra perder a
segunda. "A tela só mostra uma" não autoriza simplificar o gerador.

Fonte: CLAUDE.md:1534-1560 (troca), :1737-1760 (opções), :1827-1840 (gate); workouts/services.py:1095
