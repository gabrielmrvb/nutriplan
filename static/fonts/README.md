# As duas fontes do NutriPlan (direção NERVURA, 17/09/2026)

| arquivo | família | eixos | bytes | origem |
|---|---|---|---|---|
| `big-shoulders-display-latin.woff2` | Big Shoulders Display (display) | `wght` 100–900 | 35 436 | Google Fonts, `bigshouldersdisplay/v24`, subconjunto **latin** |
| `archivo-latin.woff2` | Archivo (texto) | `wght` 100–900 | 34 928 | Google Fonts, `archivo/v25`, subconjunto **latin** |

Total: **70 364 bytes** — o gate do `DESIGN.md` é 260 KB (`config/test_fontes.py`).
Os dois arquivos são exatamente os que a API de CSS do Google Fonts serve
para o subconjunto `latin` (`unicode-range` copiado para o `@font-face` do
`app.css`). Medidos com fontTools: as duas cobrem o português (ã ç é í ó ú
â ê ô à ü); **a Archivo tem `tnum`; a Big Shoulders Display NÃO tem** e os
dígitos são proporcionais ("1" 316/2000 contra "0" 596) — por isso a
display fica para título, nome e número SOLTO, e toda coluna de números é
Archivo com `tabular-nums` (regra do `DESIGN.md`, "Tipografia").

Licença: SIL Open Font License 1.1, em `OFL-big-shoulders-display.txt` e
`OFL-archivo.txt` (Big Shoulders © 2019 The Big Shoulders Project Authors;
Archivo © 2020 The Archivo Project Authors). Sem `<link>` para o Google em
produção: os arquivos são servidos por `/static/fonts/` e pré-cacheados pelo
service worker.

Antes (16–17/09, direção CORTE): Bodoni Moda + Karla, 70 580 bytes.
