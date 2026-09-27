---
name: saude-vivo
description: monitor externo bate em /saude/vivo/ (zero consultas), nunca em /saude/, que acorda o Neon e estoura a cota
metadata:
  type: reference
---
`/saude/` é readiness e consulta o banco; `/saude/vivo/` responde sem
banco. O Neon free hiberna após 5 min e dá 100 CU-h/mês; acordado o tempo
todo seriam ~182, e a cota estouraria por volta do dia 16. Um monitor em
`/saude/` derrubaria o banco no meio do mês.

Fonte: CLAUDE.md:2285-2292
