# Design system pelo Claude Design — a Mesa & Ferro ganha forma antes de virar CSS

Spec aprovada em conversa em 15/09/2026 (brainstorming, quatro perguntas e
três seções). Origem: o handoff do ChatGPT em
[`docs/briefs/2026-09-15-chatgpt-claude-design/`](../../briefs/2026-09-15-chatgpt-claude-design/README.md)
— os três Reels do @matheusgomes vistos e transcritos, o prompt do autor nas
quatro partes, e o prompt-mestre que o ChatGPT gerou. Esta spec pega o
**método** dos vídeos e o encaixa nas decisões que este repositório já tomou;
o que os vídeos fazem e aqui não cabe está listado em §10, com o motivo.

## 1. Objetivo

Dar forma visual à direção "Mesa & Ferro" (decidida pelo dono em 14/09/2026,
[`docs/briefs/design/direcao-c-mesa-e-ferro.md`](../../briefs/design/direcao-c-mesa-e-ferro.md))
**antes** de ela virar edição no `app.css`: criar o design system do
NutriPlan no claude.ai/design a partir da spec e do código real, gerar
mockups das seis telas que a onda 4 vai tocar, exportar, triar, e trazer de
volta ao repositório **só três coisas** — valores de token no `:root`,
referências visuais em `docs/`, e uma vitrine interna que renderiza as
parciais reais. A onda 3 do plano mestre (T3.1–T3.6) passa a ter um alvo
visual medido, em vez de nascer de tabela.

Resultado esperado, verificável:

- `artifacts/claude-design/seed/` montado e entregue com roteiro;
- projeto "NutriPlan" existindo no claude.ai/design do dono, com seis
  mockups revisados;
- export triado, inventário escrito, zero arquivo do export dentro de
  `templates/` ou `static/`;
- `app.css` com os tokens Mesa/Ferro em UM bloco de valores e DOIS gatilhos,
  suíte verde, catracas iguais ou menores;
- `/gestao/vitrine/` renderizando toda parcial de `templates/partials/` nos
  dois regimes, com teste que lê a pasta do disco;
- seis PNGs de referência em `docs/briefs/design/referencias/claude-design/`.

## 2. O que já está decidido e esta spec não reabre

| decisão | onde | consequência aqui |
|---|---|---|
| Sem framework de CSS; um `static/css/app.css`; tokens no `:root`; catraca de valor cru só desce | `CLAUDE.md` "Sem framework de CSS", `config/test_design_system.py` | nada do export vira segundo CSS; token entra no `:root` ou não entra |
| Barra de QUATRO itens; "Hoje" não é pilar; Perfil em Áreas | `CLAUDE.md`, plano mestre (preferências fechadas) | mockup que desenhe cinco abas é referência de PELE, não de navegação — a navegação não muda por esta spec |
| Direção C "Mesa & Ferro" corrigida: Mesa clara no app; Ferro na execução, na corrida em andamento e no tema escuro; classe `modo-foco` escrita pelo servidor; um bloco de valores, dois gatilhos | `direcao-c-mesa-e-ferro.md` §1–2, plano mestre C-DIR (A) | a tabela de tokens da direção C é a fonte da verdade; o Claude Design propõe, a spec decide |
| `:has()` proibido; classe de estado é do servidor | `CLAUDE.md` | `?regime=ferro` na vitrine escreve `modo-foco` no `<body>` no servidor |
| Movimento tem UMA linguagem (`--mov-*`, teto ZERO de duração à mão) | `CLAUDE.md`, `config/test_movimento.py` | mockup não introduz duração nem easing; motion já está feito (3a1009f) |
| Alvo de toque 44×44; texto ≥ 11 px; `tabular-nums` e vírgula decimal | `CLAUDE.md` | entram no `DESIGN.md` da semente como regra, para o Claude Design não desenhar contra |
| Ícones são o sprite `partials/icones.html`; nenhum emoji, nenhum Material Symbols | `CLAUDE.md`, grep em `templates/` | a semente leva o sprite; mockup com outro ícone é registrado como "não adotado" |

## 3. Fluxo e responsabilidades

```text
 CLAUDE CODE (esta sessão)            DONO, no claude.ai/design            CLAUDE CODE
 ─────────────────────────────        ─────────────────────────────        ─────────────────────────────
 F1 pacote-semente (§4)               F2 criar o design system (§5)        F4 triagem + inventário (§6)
    artifacts/claude-design/seed/        Opus 5 · Extra · "decida por mim"     artifacts/claude-design/export/
    + roteiro em docs/                F3 seis mockups + Share → Project     F5 tokens → app.css (§7)
                                         HTML → Export → zip                F6 referências → docs (§8)
                                                                            F7 vitrine em gestao/ (§9)
                                                                            F8 QA, fechamento, CLAUDE.md à mão
```

Regras fixadas na aprovação:

1. **Nada do export vira código por cópia.** Token entra em `app.css`
   porque a direção C já o nomeia; HTML do Claude Design entra em `docs/`
   como referência, nunca em `templates/`.
2. **`CLAUDE.md` não é tocado por prompt.** O que os vídeos fazem com
   `AGENTS.md`/`CLAUDE.md`/`PRODUCT.md` (merge automático) aqui é edição
   humana, na seção "Design: o que já existe", no fechamento, com números.
3. **Superpowers + `nutriplan-missao` conduzem a execução**; o Agent Browser
   (`agent-browser`, sessão própria, saída em arquivo) prova cada tarefa a
   320 e 390 nos dois temas.

## 4. F1 — o pacote-semente

Local: `artifacts/claude-design/seed/` (fora do git, como `artifacts/` já
é). Conteúdo:

```text
seed/
├── DESIGN.md        contrato visual, ver abaixo
├── codigo/          cópias de static/css/app.css, templates/base.html, templates/partials/*
├── telas/           6 HTMLs autocontidos (scripts/exportar_telas.py)
├── capturas/        6 telas × {claro, escuro} a 390 px (agent-browser, prefers-color-scheme emulado)
├── marca/           logo.svg (extraída de partials/marca.html) e icones.svg (o sprite)
└── nota.txt         a frase para "Any other notes?"
```

**`DESIGN.md`** — escrito à mão a partir da direção C, com estas seções e
nada além delas: identidade (o que o app é, cinco pilares, pt-BR);
princípio ("um material, dois regimes de luz" e a lista do que NUNCA muda
entre Mesa e Ferro: família tipográfica, raios, grade de 4 px, sprite, anel,
botão); tokens Mesa/Ferro — a tabela de `direcao-c-mesa-e-ferro.md` §2 com
valor e papel, mais os contrastes medidos; tipografia (sistema hoje; fonte
própria só depois do gate de medição da T3.2 — o Claude Design não escolhe
fonte); espaçamento, raios, sombras, camadas e `--mov-*` que já existem em
`app.css`; regras de interface (44×44, ≥ 11 px, `tabular-nums`, vírgula
decimal, `min-width: 0`); componentes existentes (`card`, `btn`, `chip`,
`pill`, `tile`, `data-list`, `empty-state`, `hint`, `field`, `choice_cards`,
`marca`, `_conquista`, anel) com uma linha cada; e "o que este app não faz"
(gradiente roxo, vidro além dos quatro cartões, ícone-emoji, `:has()`,
animação decorativa).

**`telas/`** — `scripts/exportar_telas.py` ganha entradas em `TELAS` para as
seis telas desta spec: Hoje (`/`), painel de treino (`/treino/`), ficha
(`/treino/ficha/<id>/`), execução (`/treino/agora/`), progresso
(`/historico/`, `plans:history`) e entrada (`/conta/entrar/`). As entradas antigas ficam. O script já resolve login,
`ALLOWED_HOSTS` e assets embutidos; precisa do PostgreSQL de pé (`pg_ctl
start`) e do usuário demo.

**`capturas/`** — a T3.0 do plano mestre, feita aqui: cada uma das seis telas
a 390 px, tema claro e tema escuro, com o Agent Browser emulando
`prefers-color-scheme`. É evidência do ANTES; nada é alterado para capturar.

**`nota.txt`** — *"PWA mobile-first de alimentação, treino, corrida,
hidratação e progresso, em português do Brasil. Um material, dois regimes de
luz: Mesa (clara, alimentação e o app em geral) e Ferro (escura, execução do
treino e tema escuro). Tokens, regras e componentes estão no DESIGN.md — não
inventar cor, raio nem tipografia fora dele; o que faltar, perguntar."*

## 5. F2–F3 — o roteiro do dono no claude.ai/design

Vai para
`docs/briefs/2026-09-15-chatgpt-claude-design/roteiro-claude-design.md`,
com os passos do vídeo "Parte 1/2" traduzidos para a semente:

1. `claude.ai/design` → modelo **Opus 5**, esforço **Extra**.
2. "+" → **Design system → Create**; nome **NutriPlan**.
3. *Link code from your computer* → `seed/codigo/`.
4. *Add fonts, logos and assets* → `marca/`, `capturas/`, `telas/`.
5. *Any other notes?* → `nota.txt`.
6. Continuar (~5 min). Nas perguntas: grafia **"NutriPlan"**; domínio = os
   cinco pilares; e *"tokens e regras estão no DESIGN.md; não inventar fora
   dele"*. O resto, "decida por mim".
7. Revisar; pedir ajuste do que não gostar, em texto, na lateral.
8. Gerar os **seis mockups** com os prompts prontos no roteiro — Hoje,
   painel, ficha, progresso e entrada em **Mesa**; execução em **Ferro** —,
   cada prompt com: a tela, o que ela responde, os estados que precisa
   mostrar, e "barra de quatro itens; navegação não muda".
9. **Share → Project HTML → Export** (a opção "Standalone HTML" não é usada);
   o zip cai em Downloads; avisar o Claude Code.

O roteiro avisa que o formulário pode ter mudado desde o vídeo (setembro de
2026) e que o dono adapta; e que a geração pode propor tokens diferentes —
a spec ganha (§7).

## 6. F4 — triagem e inventário do export

- Zip descompactado em `artifacts/claude-design/export/`. **Nada é apagado
  nem movido**: a pasta é o registro.
- `scripts/inventariar_export.py` (novo, sem Django) percorre a árvore e
  escreve `docs/briefs/2026-09-15-chatgpt-claude-design/inventario-export.md`:
  caminho, tamanho, sha256 e classe — **tokens/guidelines/readme** (lidos e
  comparados), **HTML de tela e de componente** (referência visual),
  **interno** (`_ds_bundle.js`, `_ds_manifest.json`, `.thumbnail`,
  `uploads/`, export aninhado; listados e ignorados), **incerto** (fica na
  lista para leitura humana). Nenhum arquivo sem classe — o script falha se
  sobrar um.
- A árvore que o vídeo mostra (`_adherence.oxlintrc.json`, `_ds_bundle.js`,
  `_ds_manifest.json`, `assets/`, `components/`, `*.html` standalone,
  `design-system-export/` aninhado, `export/`, `guidelines/`, `readme.md`,
  `SKILL.md`, `styles.css`, `templates/`, `tokens/`, `ui_kits/`, `uploads/`)
  é a hipótese de trabalho; o script classifica por padrão de nome e
  extensão, não por essa lista.

## 7. F5 — tokens no `app.css` (é a T3.1 do plano mestre)

- Mesa no `:root`. Ferro como **um bloco de valores** aplicado por **dois
  gatilhos**: `@media (prefers-color-scheme: dark)` e `body.modo-foco`.
  Sem duplicar a lista de valores — é a regra da direção C, e é o que o
  teste novo garante (abaixo).
- Comparação token a token entre `direcao-c-mesa-e-ferro.md` §2 e o que o
  Claude Design exportou em `tokens/`/`guidelines/`. **A spec ganha.** Cada
  diferença vai para
  `docs/briefs/2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md`
  com o valor dele, o nosso e uma linha de motivo — inclusive quando a
  proposta é melhor mas muda uma decisão fechada (aí é item para o dono, não
  adoção silenciosa).
- Renomeações previstas pela direção C (`--accent` → `--agua`, `--warm` →
  `--terra`, `--grad-brand` sai) acontecem aqui, com `grep` provando zero
  uso órfão antes do commit.
- Testes: `config/tests.py` recalcula contraste também para os tokens novos
  e para os pares que a direção C mede (`--text` sobre `surface-3`,
  `--brand` sobre `--brand-soft`, `--folha` sobre trilho, pilares em Ferro);
  `config/test_design_system.py` tem a contagem de tokens atualizada com a
  razão no commit; teste novo — **o bloco de Ferro tem os mesmos nomes de
  token nos dois gatilhos e nenhum nome fora do `:root`** (lido do CSS, não
  de lista à mão). A catraca de valor cru **só desce**.

## 8. F6 — referências

- Seis PNGs a 390 px dos mockups em
  `docs/briefs/design/referencias/claude-design/`, nomeados pela tela e pelo
  regime (`hoje-mesa.png`, `execucao-ferro.png`…). Precedente de imagem no
  repo: `docs/ux-audit/screenshots/`; as 14 MB de shots de 14/09 ficaram
  fora — o teto aqui é 250 KB por PNG, e o que passar disso fica em
  `artifacts/`.
- Os HTMLs do export ficam em `artifacts/`; `docs/briefs/README.md` ganha
  uma linha apontando para as referências e para esta spec.

## 9. F7 — a vitrine

- Rota `gestao/vitrine/`, view `VitrineView` no app `gestao`, protegida por
  `PainelDeGestaoMixin` — a permissão é `accounts.ver_painel_de_gestao`,
  não `is_staff`, pelo motivo escrito em `gestao/acesso.py`. `nav` nenhum;
  fora do shell offline; sem link na interface; `never_cache` como o resto
  do painel.
- Template `gestao/vitrine.html` que **inclui as parciais reais** em todos
  os estados: `field` (padrão, foco, erro, desabilitado, com ajuda), os seis
  botões e a escala de toque, as famílias de cartão, `chip`/`pill`/`tile`,
  `data-list`, `empty-state`, `hint`, anel, `_conquista`, `choice_cards`,
  `marca`, `links_legais`, `botao_google`, e a barra de abas. Conteúdo
  fictício e curto/longo/quebrado, como o autor pede na Parte 3.
- `?regime=ferro` → a view escreve `modo-foco` no `<body>`; sem parâmetro é
  Mesa. Nunca `:has()`, nunca JavaScript decidindo o regime.
- `gestao/test_vitrine.py`: anônimo → login; autenticado sem permissão →
  403; com permissão → 200 nos dois regimes; e **toda parcial de
  `templates/partials/` é incluída pelo menos uma vez** — a lista vem de
  `os.listdir`, para a nona parcial não nascer fora da vitrine. Guarda
  contra o seletor-que-é-a-mesma-string: ancorar em classe ou texto
  visível, não em `data-*`.

## 10. O que fica de fora, e por quê

| dos vídeos / do prompt-mestre | aqui | motivo |
|---|---|---|
| pasta `design-system/` com componentes portados | não | um `app.css` e oito parciais é decisão do `CLAUDE.md`; o export é React |
| rota pública `/design-system` | `gestao/vitrine/` com permissão | vitrine é ferramenta de quem mantém, não parte do produto |
| `SKILL.md` gerado dentro do design system | não | as skills do repo estão em `.claude/skills/`; uma nona parcial não precisa de skill |
| merge automático em `AGENTS.md`/`CLAUDE.md`/`PRODUCT.md` | edição humana no fechamento | o `CLAUDE.md` é o contrato inteiro do produto |
| plugin `frontend-design` | não | não aparece em vídeo nenhum; o gosto aqui é a direção C |
| apagar `design-system-export` no fim | não; fica em `artifacts/` | é o registro; `artifacts/` já está fora do git |
| navegação com cinco itens / "Hoje" como aba (auditoria do ChatGPT) | não | decisão fechada e medida a 320 px |

## 11. Riscos e ressalvas

- **O formulário do Claude Design pode diferir do vídeo.** O roteiro
  descreve o que o vídeo mostra; o dono adapta e anota o que mudou no
  próprio roteiro.
- **O Claude Design pode ignorar o `DESIGN.md` e inventar.** Por isso a
  spec ganha e a lista "proposto e não adotado" existe; e por isso o pacote
  leva código e capturas, não só texto — é a régua do autor ("crua demais,
  ele inventa").
- **O export é React/Tailwind.** Só valores e imagens atravessam a fronteira;
  nenhum `Showcase.tsx` é lido como código.
- **A conta de QA em produção do chat do ChatGPT continua existindo.** Não é
  desta spec, mas está no README do handoff e precisa ser apagada.
- **Fonte própria** (T3.2) fica condicionada ao gate de medição do plano
  mestre; o Claude Design não decide fonte.

## 12. Critérios de aceitação (gate de fechamento)

1. `seed/` completo e roteiro entregue (F1) — evidência: listagem da pasta
   e as 12 capturas.
2. Projeto no claude.ai/design com seis mockups revisados pelo dono (F2–F3)
   — evidência: o zip.
3. `inventario-export.md` sem arquivo sem classe (F4).
4. `app.css`: Ferro em um bloco, dois gatilhos; `proposto-nao-adotado.md`
   escrito; suíte verde; catracas ≤ antes (F5).
5. Seis PNGs ≤ 250 KB em `docs/` (F6).
6. `gestao/vitrine/` 200 nos dois regimes para quem tem permissão, 403/login
   para quem não tem, teste de cobertura de parciais verde (F7).
7. QA com Agent Browser a 320 e 390, claro e escuro, nas seis telas e na
   vitrine, com saída em arquivo (F8).
8. `CLAUDE.md` "Design: o que já existe" atualizado à mão com os números
   medidos; `docs/sistema-visual.md` idem (F8).

## 13. Sequência

F1 → (dono: F2, F3) → F4 → F5 → F6 → F7 → F8. F1 e F7 não dependem do
export e podem andar enquanto o dono está no claude.ai/design; F5 e F6
esperam o zip. Cada fase fecha com teste e, quando toca tela, com QA de
navegador; publicação segue o `nutriplan-missao` (testes dirigidos → suíte
→ deploy → smoke).
