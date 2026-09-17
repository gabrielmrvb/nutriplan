# As duas fontes do NutriPlan (direção CORTE, T3.2 — 16/09/2026)

| arquivo | família | eixos | bytes | origem |
|---|---|---|---|---|
| `bodoni-moda-latin.woff2` | Bodoni Moda (display) | `wght` 400–900, `opsz` 6–96 | 46 260 | Google Fonts, `bodonimoda/v28`, subconjunto **latin** |
| `karla-latin.woff2` | Karla (texto) | `wght` 400–800 | 24 320 | Google Fonts, `karla/v33`, subconjunto **latin** |

Total: **70 580 bytes** — o gate do `DESIGN.md` é 260 KB (`config/test_fontes.py`).
Os dois arquivos são exatamente os que a API de CSS do Google Fonts serve
para o subconjunto `latin` (`unicode-range` copiado para o `@font-face` do
`app.css`); medidos com fontTools: os dois têm `tnum` (numeral tabular),
cobrem o português (ã ç é í ó ú â ê ô à ü) e as 224/220 formas do latin.

A itálica da Bodoni Moda (53 756 bytes) ficou de fora de propósito: o
mockup a usava a 13–19 px em subtítulos e unidades, abaixo do piso de 20 px
que o contrato dá à display — esses textos são Karla. Sem consumidor, sem
arquivo.

Licença: SIL Open Font License 1.1, em `OFL-bodoni-moda.txt` e
`OFL-karla.txt` (Bodoni Moda © 2020 The Bodoni Moda Project Authors;
Karla © 2019 The Karla Project Authors). Sem `<link>` para o Google em
produção: os arquivos são servidos por `/static/fonts/` e pré-cacheados pelo
service worker.
