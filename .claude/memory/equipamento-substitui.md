---
name: equipamento-substitui
description: o equipamento do perfil é obedecido por SUBSTITUIÇÃO (mesmo padrão e grupo, mesma dose), nunca por filtro — filtrar abre buraco nos modelos
metadata:
  type: business-rule
---
`Profile.equipamento` entrou em 17/09/2026; `substituir_por_equipamento`
roda ANTES de `prescrever_opcoes` e troca o item fora do perfil por
exercício ativo do mesmo `padrao` e grupo, com a mesma dose; sem
substituto, o item sai. Por que não filtrar: a prescrição copia MODELOS
curados de `splits.json`, e o filtro medido em 10/09 deixava oito modelos
sem grupo (`abcde-C` com zero exercícios). O default é "completa", não
vazio. O `TREINO.md` dizia "o motor FILTRA" até 27/09/2026; a palavra
certa é SUBSTITUI, e ela voltou a ser a do documento.

Fonte: CLAUDE.md:1400-1412; docs/briefs/treino/TREINO.md:340-369; workouts/services.py:1242
