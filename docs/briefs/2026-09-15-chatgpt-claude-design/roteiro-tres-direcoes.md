# Roteiro v2 — o Claude Design PROPÕE, a spec se adapta

Substitui, para a Task 7, o `roteiro-claude-design.md` (que gerou os seis
mockups fiéis à Mesa & Ferro em 16/09/2026 — export em
`artifacts/claude-design/export/telas/`, referências em
`docs/briefs/design/referencias/claude-design/`). Aquele resultado é a nota 6
do dono: "coerente mas genérico". O problema desta rodada é esse, e não polir.

**Objetivo:** quem usou uma vez e volta tem que pensar "que app foda".

## O que se pede (brief do dono, 16/09/2026)

- identidade reconhecível em 1 segundo — a FOLHA como sistema visual (forma,
  recorte, ritmo), não só como logo;
- uma fonte DISPLAY com personalidade para títulos e números, mais uma de
  texto; os dois arquivos entram no repositório depois (gate de tamanho);
- números como herói: kg, séries, minutos, kcal;
- tema ESCURO como padrão de academia, com o claro derivado dele;
- movimento com intenção: concluir série, fechar treino, bater meta são
  momentos de RECOMPENSA — e o resto é quieto;
- zero cartão branco com sombra genérica; hierarquia por tipografia e cor, não
  por caixas;
- três direções DISTINTAS (não variações), cada uma com seis mockups —
  login, home, ficha com duas opções, execução, dieta, progresso — e um
  **frame de recompensa**: a tela ao concluir a última série.

## O que continua valendo (não negociável)

WCAG AA em todo par texto/fundo (a auditoria mede 274 pares); alvo de toque
≥ 44 px em altura E largura; tudo em token (nenhum valor cru); movimento com
`prefers-reduced-motion` desligando tudo; o sprite de ícones de traço; PWA
mobile-first (390 px, uma coluna, barra de quatro itens). **Todo o resto é
negociável — raios, paleta, e a própria Mesa & Ferro.**

## Como rodar (claude.ai/design, Opus 5 · Extra)

Projeto NOVO, **sem** o design system NutriPlan anexado (ele ancoraria na
spec de hoje). Contexto anexado: `icon-192.png` (a marca, intocável),
`icones.svg` (o sprite), as 12 capturas de hoje (o que existe: a nota 6) e
este arquivo. Um prompt de conceito, depois dois prompts por direção.

### Prompt 0 — as três direções

> Você vai propor TRÊS direções visuais DISTINTAS para o NutriPlan (PWA
> mobile-first, pt-BR, de alimentação, treino, corrida, hidratação e
> progresso). O app de hoje está nas 12 capturas anexadas: coerente e
> genérico — nota 6. Quem usou uma vez e volta tem que pensar "que app foda".
> Brief: identidade reconhecível em 1 segundo, com a FOLHA da marca (anexada,
> não redesenhar) virando sistema visual — forma, recorte, ritmo, não só
> logo; uma fonte DISPLAY com personalidade para títulos e números (do
> Google Fonts, carregada por `<link>`) mais uma de texto; números como herói
> (kg, séries, minutos, kcal); tema ESCURO como padrão de academia e o claro
> derivado dele; movimento com intenção (concluir série, fechar treino, bater
> meta são momentos de recompensa; o resto é quieto); zero cartão branco com
> sombra genérica — hierarquia por tipografia e cor, não por caixas.
> Restrições fixas: WCAG AA em todo par texto/fundo; alvos ≥ 44 px; tudo em
> tokens CSS (nenhum hex ou px solto em regra); `prefers-reduced-motion`
> desliga o movimento; ícones só do sprite anexado (traço 2, grade 24) ou
> desenhados no mesmo idioma; 390 px, uma coluna, barra inferior de QUATRO
> itens (Alimentação · Treino · Progresso · Áreas). Para cada direção
> escreva: nome, a ideia em duas frases, o par de fontes, a paleta (tokens
> com hex, escuro e claro), o que a folha vira, e o que a distingue das
> outras duas. Não gere telas ainda.

### Prompts por direção (×3)

**Prompt A — `Direcao<N>-a.html`: login, home, dieta**
> Direção <N> ("<nome>"): gere `Direcao<N>-a.html`, um único HTML standalone
> a 390 px com três telas empilhadas e um seletor de tela no topo (andaime,
> fora do app): (1) Entrar — marca + wordmark + "Disciplina hoje. Resultados
> amanhã.", e-mail, senha, "Entrar", "Continuar com Google", "Criar conta",
> "Esqueci a senha"; (2) Home "Hoje" — o AGORA no topo (próxima refeição com
> hora), anel de calorias com número herói, macros, refeições com a da vez
> aberta, água com "+250 ml", treino de hoje, barra de quatro itens; (3)
> Dieta — a refeição aberta com as opções A e B, "Registrar A", "Pulei",
> "Comi outra coisa", lista de compras. Escuro por padrão; claro derivado via
> `@media (prefers-color-scheme: light)`. Tokens no `:root`, fontes por
> `<link>` do Google Fonts, sprite inline. Movimento só onde é recompensa.

**Prompt B — `Direcao<N>-b.html`: ficha, execução, progresso, recompensa**
> Direção <N> ("<nome>"): gere `Direcao<N>-b.html`, mesmo formato, com
> quatro telas: (4) Ficha do Treino B com DUAS opções (1 e 2) e a
> recomendada de hoje, lista numerada — nome, séries × repetições, músculo,
> "Principal" —, "Começar pelo primeiro"; (5) Execução — UM exercício, vídeo
> curto no topo, "Exercício 3/7", carga com −2,5/+2,5, repetições, "Concluir
> série" como único primário, descanso com contagem, desfazer, carga da
> última vez; (6) Progresso — tiles herói (aderência, kcal/dia, água, treinos
> na semana), curva de peso, barras da semana, conquistas com ícones do
> sprite; (7) FRAME DE RECOMPENSA — a tela no instante em que a ÚLTIMA série
> do treino é concluída: o que aparece, o que se move, por quanto tempo, e o
> mesmo frame com `prefers-reduced-motion`. Escuro por padrão, claro
> derivado. Mesmos tokens e fontes do arquivo `-a`.

Depois de cada geração: capturar, anotar o que o Claude Design escreveu de
razão de design (vai para o `direcoes.html`), seguir. Não pedir ajuste de
gosto: a rodada é para o dono ESCOLHER, não para eu afinar.

## Exportar

Share → HTML do projeto → Arquivo do projeto (zip). Salvar em
`artifacts/claude-design/export/direcoes.zip`, extrair em
`artifacts/claude-design/export/direcoes/`, rodar
`scripts/inventariar_export.py --estrito`. Renderizar cada tela nos dois
temas a 390 (`nav.py tema claro|escuro`) e montar
`scratchpad/shots-design/direcoes.html` — três colunas, uma por direção;
linhas por tela; claro e escuro lado a lado; o nome, o par de fontes e a
razão de cada direção no topo da coluna. **Parar aí: o dono escolhe.**
