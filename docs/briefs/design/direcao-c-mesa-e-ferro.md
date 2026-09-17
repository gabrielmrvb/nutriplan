# Direção C — "Mesa & Ferro" (Híbrido Premium NutriPlan)

Proposta de direção de arte. Só pesquisa e proposta: nenhum código alterado.
Evidência: [OBSERVADA] = screenshot/medição desta auditoria; [LIDA NO CÓDIGO] =
app.css / templates / testes; [LIDA NA DOCUMENTAÇÃO] = CLAUDE.md;
[HIPOTÉTICA] = estimativa a confirmar. Contrastes medidos por
`contraste-direcao-c.py` nesta pasta.

## 1. Conceito

**Um material, dois regimes de luz.** A comida acontece numa MESA — luz de
cozinha, linho, ar, branco — e o treino acontece no FERRO — luz baixa da
academia, grafite, número grande, nada solto. O que faz os dois serem um app
só é que TUDO fora da luz é idêntico: a mesma família tipográfica com o mesmo
eixo óptico, os mesmos raios, a mesma grade de 4px, o mesmo sprite de ícones,
o mesmo anel, o mesmo botão. O que muda entre Mesa e Ferro é exclusivamente
um bloco de tokens de COR e um orçamento de DENSIDADE (padding e vão) — e a
regra está escrita: nenhum componente pode ter raio, tamanho de texto ou
ícone diferente entre os regimes.

O regime é uma classe escrita pelo servidor no `<body>` (`modo-foco`), nunca
`:has()` nem `prefers-color-scheme`: a execução (`/treino/agora/`) e a
corrida em andamento nascem em Ferro por decisão de produto; todo o resto é
Mesa. O tema escuro por preferência do sistema continua existindo e É o
mesmo bloco de valores do Ferro — quem prefere escuro vê o app inteiro em
Ferro. Um bloco de valores, dois gatilhos (`@media` e `.modo-foco`), zero
duplicação de intenção.

Por que isso é materialmente diferente de "variação de cor": as outras
direções escolhem UM clima para o app inteiro; esta declara que alimentação e
treino têm luminâncias diferentes de propósito, e prova a unidade pelo que
NÃO muda. É a mesma tese do CLAUDE.md sobre `--brand` × `--folha` ("dois
verdes com papéis diferentes"), levada ao nível do canvas.

## 2. Cor (Mesa = base; Ferro = `body.modo-foco` e `prefers-color-scheme: dark`)

| token | Mesa | Ferro | papel |
|---|---|---|---|
| `--bg` | `#f5f3ee` (linho) | `#0e1412` | chão |
| `--surface` | `#ffffff` | `#161d1a` | prato / cartão |
| `--surface-2` | `#efece4` | `#1d2622` | agrupamento dentro do cartão, trilho do anel |
| `--surface-3` | `#ebe8de` | `#26312b` | célula vazia de gráfico, silhueta de vazio |
| `--surface-focus` | `#e3f1e8` | `#123024` | UMA por tela |
| `--text` | `#141f1a` | `#f4f7f5` | |
| `--text-dim` | `#485550` | `#b6c1bb` | |
| `--text-mute` | `#55625c` | `#8f9b95` | ajustado depois — ver nota abaixo |
| `--brand` | `#0c6b40` | `#22c98a` | AGIR: CTA, link, aba ativa, foco |
| `--brand-strong` | `#08512f` | `#4ddb9f` | só :active/hover |
| `--brand-soft` | `#dff0e6` | `#0f2a20` | botão tonal, chip |
| `--folha` | `#3f9718` | `#6fcf4a` | FEITO + pilar Treino |
| `--agua` | `#1e6e96` | `#5fbdf0` | pilar Hidratação (era `--accent`) |
| `--agua-texto` | `#175877` | = `--agua` | água como texto pequeno |
| `--brasa` | `#a63f18` | `#ff9a7a` | pilar Corrida |
| `--terra` | `#8a5109` | `#f2b04e` | pilar Progresso/peso (era `--warm`) |
| `--chama` | `#c8620a` | `#ffa53a` | ofensiva, só objeto gráfico |
| `--carb` | `#ad6d16` | `#e6b35d` | macro |
| `--fat` | `#5568a6` | `#93a8de` | macro |
| `--danger` | `#b3261e` | `#ff8a80` | |
| `--fio` | `rgba(20,31,26,.10)` | `rgba(255,255,255,.08)` | hairline de separação |
| `--fio-forte` | `rgba(20,31,26,.22)` | `rgba(255,255,255,.16)` | borda de campo |
| `--on-brand` | `#ffffff` | `#04140e` | |

Medido (Mesa): `--text` 15,26 (bg) / 16,93 (surface) / 13,81 (surface-3);
`--text-dim` 7,04 / 7,80 / 6,20; `--text-mute` 5,76 / 6,39 / 5,21 (sobre
surface-3, pior caso); `--brand` como texto 6,58 sobre branco, 5,56 sobre
`--brand-soft`; branco sobre `--brand` 6,58; `--folha` 3,15 sobre surface-2
(trilho) e 3,03 sobre surface-3; `--agua` 4,77 / 4,48; `--chama` 3,42 /
3,29; `--carb` 3,57 / 3,36; `--fat` 4,54 / 4,26; `--brasa` 5,32 sobre
surface-2 e 6,28 como texto sobre branco; `--terra` 6,44 como texto.
Ferro: todos os pilares entre 6,4 e 9,1 sobre qualquer superfície;
`--text-mute` 4,68 sobre surface-3 (pior caso, acima de 4,5).

**Ajustes medidos depois da direção (16/09/2026), e o contrato é o DESIGN.md:**
`--text-mute` Ferro `#8f9b95` → `#a0aca6` (4,68 no pior fundo; a margem da
suíte é 5,0); `--surface-2` Ferro `#1d2622` → `#243029` e `--surface-3`
`#26312b` → `#2c3a32` (U28: a segunda superfície precisa de ≥ 1,2:1 sobre a
primeira, e sobre `#161d1a` o valor daqui dava 1,10; a terceira sobe junto
para o hover continuar existindo). Trilha de anel e de barra é `--fio`, não
`--surface-2` — superfície sobre superfície some no escuro.

**A regra de três.** Cor de pilar aparece em pelo menos TRÊS lugares da área
(fio do prato, arco/coluna do gráfico, ponto do ícone) e em NENHUM botão.
`--accent` como cor de foco morre: foco é `--brand` em todo controle.
`--dia-a…e` continuam como cor de sessão no painel de treino (o precedente
que o CLAUDE.md elogia); o roxo `--dia-d` não entra em gradiente nenhum.
`--grad-brand` (verde→azul) sai — um uso, e é a estética que o próprio
arquivo cita como "IA genérica".

## 3. Tipografia

- Família: **DM Sans Variable** (OFL), eixos `wght` 100–1000 e `opsz` 9–40,
  UM arquivo `static/fonts/dm-sans[opsz,wght].woff2` com subset latin +
  latin-ext, `font-display: swap`, fallback `system-ui`; entra no precache do
  service worker. Tamanho estimado 45–70 KB [HIPOTÉTICA]. `tnum` e `cv`
  de "1 com base" a confirmar no arquivo antes de adotar [HIPOTÉTICA].
  Por que ela: geométrica com terminais macios (o "humano" da mesa) e eixo
  óptico de verdade — a mesma família fecha em `opsz 40` no número de 48px
  (ferro, compacto, contraste alto) e abre em `opsz 14` no corpo (mesa,
  arejado). São os "dois tamanhos ópticos" do Nubank sem duas fontes.
  Não é framework nem build step: um arquivo estático servido pelo
  `collectstatic`.
- `font-optical-sizing: auto` no `body`; `font-variant-numeric: tabular-nums`
  em toda `.metrica`, `.stat__valor`, `.ring__value`, hora e grama.
- Pesos: QUATRO tokens e só eles — `--peso-texto: 450`, `--peso-medio: 560`,
  `--peso-forte: 680`, `--peso-display: 780`. Os 12 valores atuais colapsam
  nesses quatro (500–620 → 450/560; 650–780 → 680; 800 → 780).
- Escala (mantém os tokens, apaga os 120 crus): 11,2 · 12,8 · 14,4 · 16 ·
  18,4 · 22,4 · 28 · 34,4 · 48. `--texto-display` desce de 3.1rem para
  **3rem (48px)** e ganha um irmão `--texto-display-foco: 3.5rem (56px)`
  usado só pela carga na execução; a 320px os dois cedem a 2.5rem/2.75rem
  (a regra `.corrida__numero` já faz isso).
- Papéis: h1 = 28/680/−.02em (desce de 40); título de seção = 22,4/680;
  eyebrow = 11,2/560/caixa alta/+.08em, uma classe `.eyebrow`, cor `--text-mute`
  ou cor do pilar; corpo 16/450 lh 1.5; apoio 12,8/450; display 48/780/−.03em
  lh 1; unidade colada 12,8/560 `--text-dim` na mesma linha de base.
- Regra: o número display é o MAIOR objeto de toda tela que mede; o título
  nunca passa de 28.

## 4. Espaçamento

Grade de 4px inteira. Remapear os sete degraus: `--espaco-1: 4px`,
`-2: 8px`, `-3: 12px`, `-4: 16px`, `-5: 20px`, `-6: 24px`, `-7: 32px`,
`-8: 40px` (o degrau 8 existe agora porque 2.25/2.5/3rem já são usados crus:
empty-state, container desktop, install). Mesa: gutter de página 20px (16 a
320px), padding de prato 20, padding de cartão 16, vão entre seções 32, vão
dentro de seção 12. Ferro: gutter 16, padding 16, vão entre blocos 16, vão
interno 8 — é o orçamento de densidade, e ele mora em DOIS tokens
(`--pad`, `--vao-secao`) redefinidos em `.modo-foco`, não em regra por
componente. Os 247 espaçamentos crus (.2/.3/.4/.55/.6/.75/.85rem) caem no
degrau mais próximo da grade — move pixel, e por isso é lote próprio com
captura antes/depois.

## 5. Raios

`--radius-xl: 24px` (prato, hero, widget), `--radius-lg: 16px` (cartão de
lista, choice-card, capa de vídeo), `--radius: 12px` (botão, campo, tile de
stat), `--radius-sm: 8px` (nota, chip retangular, célula de gráfico, filho
de prato), `--pill: 999px` (chip de estado, segmented, aba). Cinco degraus
como hoje, mas com REGRA: caixa dentro de caixa leva `max(R_pai − padding_pai,
8px)` — prato 24/pad 20 → filho 8; cartão 16/pad 16 → filho 8. Controle
(botão, campo) não é caixa e fica em 12 sempre. Raios idênticos nos dois
regimes (é a regra que impede "dois apps"). `.card .card` proibido por teste.

## 6. Elevação

Mesa: sombra só em DOIS lugares — o prato da tela (hero) e a barra de baixo.
`--shadow-rest: 0 1px 2px rgba(20,31,26,.06), 0 8px 20px -14px rgba(20,31,26,.18)`;
`--shadow-lift` só sob o dedo / `:focus-within`. `--shadow-deep` SAI (preto
sem tinta no tema claro, CT-03). Todo o resto separa por `--fio` hairline e
degrau de superfície. Vidro fica só na barra de baixo. Ferro: ZERO sombra —
elevação por degrau de superfície + `--edge` (inset 1px rgba(255,255,255,.05)
no topo). O clarão radial de `--brand` 9% no alto do `body` continua nos dois
regimes com a mesma receita — é o que faz a passagem Mesa→Ferro ler como "a
luz baixou", não "trocou de app".

## 7. Ícones

Sprite único promovido a `base.html` (4 KB inline), ~14 glifos, grade 24,
traço 2, terminais redondos — e UMA decisão ortogonal que dá voz: cada glifo
tem **um ponto preenchido** (círculo r=2,5) na cor do pilar via
`fill: var(--cor-pilar)`, com o traço em `currentColor`. É duotone barato,
sem segundo arquivo, e é o mesmo motivo do "N com folha" do logo. Tamanhos:
20 na tabbar (hoje 21,6 — mantém), 24 em eyebrow e stat, 32 em estado vazio.
Emoji sai de Conquistas (troféu, halter, medalha entram no sprite). Chevron
único (▾ de texto sai). O mapa de áreas em `<details>` foi aposentado
(UX-01) — não há mais o que ficar sem ícone; a tela Áreas (`/areas/`)
ganha.

## 8. Cartões

Três famílias com papel escrito no CSS:
- `.prato` — o hero/widget: `--surface`, raio 24, `--shadow-rest`, padding 20
  (16 em Ferro), **fio de pilar 3px** no topo (inset, na cor do pilar da
  área), UMA por tela. É onde mora AGORA, o treino de hoje, o anel da água,
  o peso.
- `.cartao` — lista/grupo: `--surface`, hairline `--fio`, raio 16, sem
  sombra; itens separados por hairline; linha padrão 56px (64 com thumb).
- `.nota` — apoio: `--surface-2`, raio 8, sem borda, texto 12,8.
Cartão dentro de cartão proibido; a água na Home vira seção com fio `--agua`.
Em Ferro os três existem com os mesmos raios e a superfície escura.

## 9. Botões

Uma base `.btn` e quatro degraus: primário (`--brand` cheio, 52px, raio 12,
texto 16/680 `--on-brand`; `--brand-strong` só em :active); tonal
(`--brand-soft` + texto `--brand`, 48px, sem borda — substitui o ghost como
secundário); terciário (só texto `--brand` 14,4/560, alvo 44); perigo (borda
`--danger`, texto `--danger`; cheio só na confirmação final). Ícone-botão
44×44 raio 12 `--surface-2`. Stepper −/+ 44×44 tonal. Pressed `scale(.97)`
120 ms, uma regra em `.btn:active`. Loading: classe `.btn--ocupado` (spinner
16px + rótulo "…") escrita pelo `pwa.js` no clique — vale para `<a>` também.
As 14 famílias fora de `.btn` viram modificadores. Em Ferro o primário fica
`position: sticky; bottom: var(--tabbar-h)` na `--camada-flutuante`, nunca
acima da barra de baixo.

## 10. Inputs

Campo 52px, raio 12, fundo `--surface`, borda 1px `--fio-forte`; foco: borda
2px `--brand`, sem glow, sem anel azul; erro: borda `--danger` +
`aria-invalid` + mensagem 12,8 com ícone colada abaixo; label 12,8/560
acima; unidade como sufixo dentro do campo em `--text-mute`. Compacto 44px
só em Ferro. Carga na execução: `.metrica--entrada` 56/780 centrado, −/+
tonais de 44 nas laterais. Um componente de escolha (`choice-card`, raio 16,
hairline, selecionado = fio 2px `--brand` + `--surface-focus` + check 20px
sempre no canto superior direito) e um `segmented` (trilho `--surface-2`
pill, indicador branco com `--shadow-rest`) — radio/checkbox nativos dentro
de card saem. Checkbox de lista: círculo 24 dentro de alvo 44, marcado =
`--brand` + check. Date/time nativos continuam (CROSS-WORKFLOW: UX).

## 11. Movimento

Três durações: `--dur-1: 120ms` (pressed, hover), `--dur-2: 240ms` (details,
aba, foco), `--dur-3: 480ms` (celebração: série feita, anel avança, número
sobe); `--ease` mantido; `--ease-celebra: cubic-bezier(.34,1.3,.64,1)`.
Regra: anima só o que MUDOU, e o servidor marca com classe `--recem`
(mesma técnica de `serie-ok`, que hoje é órfão); anel nasce no valor final
salvo quando recém; `varrer` gratuito na abertura sai; `navigator.vibrate(10)`
onde existir. Troca de regime é navegação: sem transição. Reduced-motion
global continua.

## 12. Gráficos

Parcial `partials/sparkline.html` (SVG inline do servidor): 7–8 colunas,
64px de altura, meta tracejada em `--fio-forte`, hoje na cor do pilar,
outras em `--surface-3`, rótulo 11,2 embaixo. Peso: área 100×48 com pontos.
Anel: UMA parcial, hero 112px traço 10 e mini 40px traço 5, trilho
`--surface-2`, arco na cor do pilar (kcal = `--brand`? não: kcal = pilar
Alimentação = `--brand` chapado, sem varredura azul→verde). A 0% o anel
some no painel de treino. Vazio = silhueta em `--surface-3`. Macros = três
mini-anéis 40px P/C/G em vez de barra tricolor.

## 13. Telas

**Home (Mesa).** Ordem igual. Prato AGORA (fio `--brand`, eyebrow, título 22,
meta, CTA) é a única sombra. Abaixo, seção NUA "Hoje": display 48 "2.830"
+ "kcal restantes" + três mini-anéis. Faixa água/treino como `.stat-grid`
2-up num `.cartao`. Timeline: refeição da vez completa (A/B como segmented,
CTA primário, Pulei/Outra como terciários), demais como linhas 56px. Água =
seção com fio `--agua`, +250/+500/+750 tonais azuis. Ofensiva = stat com
`--chama`. Explicações viram `.nota` + details. Alvo ≤1.900px [HIPOTÉTICA].

**Treino.** Painel (Mesa): h1 28; prato "Treino de hoje" com fio `--folha`,
disco A, stat-grid 3-up, anel só >0%, um CTA. Sessões em `.cartao` de linhas
64px com disco `--dia-*`. Ficha (Mesa, densa): linhas 64 com thumb 56×56 do
poster, "4 × 6–10" tabular, chip Principal tonal. Execução (**Ferro**):
cabeçalho sticky com eyebrow da sessão + barra 4px `--folha`; poster como
capa 16:9 raio 16 com chip "ver vídeo"; nome 22/680 sem sublinhado; tira de
séries (feita `--folha` + check, atual `--surface-focus` + fio, pendente
contorno); "última vez 40 kg × 8" em mute; carga 56/780; reps 44; CTA
sticky; Músculos como terciário. Corrida em andamento também Ferro.

**Progresso (Mesa).** Prato do peso: display 48 "101,4" + "kg" + chip
`--terra` "+19,0 kg"; área 48px com pontos; registro dentro de details.
Treino: barras 8 semanas `--folha`; Água: 7 colunas `--agua`; Conquistas:
stat 3-up + lista com sprite. Vazios como silhueta; estado vazio de UMA
seção não abre a tela (CROSS-WORKFLOW: UX).

## 14. O que muda no app.css (sem reescrever tudo)

§1 tokens: `@font-face` + `--font`; quatro `--peso-*`; `--texto-display` 3rem
+ `--texto-display-foco`; espaço em grade 4px + `--espaco-8`; raios 24/16/12/8;
`--fio`/`--fio-forte` substituem `--border`/`--border-strong`; `--agua`,
`--brasa`, `--terra`, `--chama` (rename de `--accent`/`--warm` com papel);
`--shadow-deep` e `--grad-brand` saem; `--dur-1/2/3`; bloco Ferro escrito UMA
vez em variáveis privadas (`--_bg-foco…`) e aplicado por `@media (dark)` e
`body.modo-foco`. §5 cartões: `.prato/.cartao/.nota` + teste `.card .card`.
§10 botões: tonal; 14 famílias → modificadores; uma lista de :active. §11
formulário: uma receita de campo, `aria-invalid`. Novos: `.eyebrow`,
`.metrica`, `.stat/.stat-grid`, `partials/sparkline.html`, anel unificado.
Correções já medidas: `.semanas` colisão (SBS-01), `var(--linha)` (CT-11),
foco azul (CB-06), vinheta preta (CT-18). Catraca: `TETO_FONT_SIZE_CRU` e
`TETO_ESPACO_CRU` DESCEM; `test_tema_claro` atualiza o hex do fundo com a
decisão escrita; teste novo: nenhum `--agua` fora de seletor de água,
nenhum peso fora dos quatro tokens.

## 15. Riscos

1. Fonte: peso do woff2 e presença de `tnum` não medidos [HIPOTÉTICA];
   precache do SW cresce; `swap` causa um reflow na primeira visita.
2. Linho `#f5f3ee` sob o clarão verde de 9% pode amarelar — medir na tela,
   não no token; recuo: `#f6f5f1`.
3. Dois regimes viram "dois apps" se alguém mexer em raio/tipo dentro de
   `.modo-foco` — a regra precisa de teste (só tokens de cor/densidade no
   bloco).
4. Remapear `--espaco-*` move pixel em 247 lugares; lote próprio com captura.
5. `test_tema_claro` e a catraca hoje travam os valores atuais; a mudança
   passa por editar o teste com a razão escrita, não por desligar.
6. `body.modo-foco` exige que a view da execução escreva a classe (uma linha
   de contexto) — CROSS-WORKFLOW: TRAINING para a rota, não para a regra.
7. Ordem de blocos, o que sai da Home e do onboarding: CROSS-WORKFLOW: UX.
   Esta direção só veste.

## 16. Como a diferença se PROVA

Lado a lado, na mesma largura de 390px:
- Home atual × Home C × Yazio/Lifesum: na C o maior objeto é "2.830", não
  "Hoje"; há UMA sombra na tela (hoje 25 elementos com sombra [OBSERVADA]);
  o canvas é linho e não cinza-hospital.
- Execução atual × Execução C × Hevy/Strong: a C é a única tela escura do
  app, a carga tem 56px (hoje um input de 44px com placeholder "kg"
  [OBSERVADA]), a série feita é verde-folha com check e o CTA não sai da
  dobra a 320px (hoje fica sob a tabbar [OBSERVADA]).
- Alimentação C × Treino C sobrepostas: raios, grade, ícones e fonte
  coincidem pixel a pixel; só a luminância muda — é a prova de "um app".
- Números que a catraca passa a contar: tamanhos de fonte por tela 27 → ≤8;
  pesos 12 → 4; raios por tela 6 → 3; famílias de botão 21 → 1 + 4
  modificadores; sombras na Home 25 → 2; Home 3.143px → ≤1.900
  [HIPOTÉTICA até capturar].
- Windows × iPhone: hoje o h1 é Segoe UI Black num e SF Pro no outro
  [LIDA NO CÓDIGO]; na C o display é o mesmo desenho nos dois.
