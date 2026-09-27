---
name: template-e-css-armadilhas
description: armadilhas medidas de template e CSS que não estão no CLAUDE.md
metadata:
  type: reference
---
- `USE_L10N` escreve float com VÍRGULA: `cx="42,9"` num SVG é descartado pelo
  navegador — número de atributo sai sem localização (`unlocalize`).
- `grid-auto-rows: 1fr` iguala as LINHAS entre si, não os itens de uma linha.
- Separador "·" entre links de rodapé não sobrevive à quebra de linha (o
  irmão lidera a linha seguinte; `::after` fica dependurado): o vão separa.
- Seed é dono do que escreve: o demo dizia "312 conquistas" porque o seed
  não apagava o que tinha gravado antes.

Fonte: memória antiga `nutriplan-redesenho-hoje` (23/09/2026)
