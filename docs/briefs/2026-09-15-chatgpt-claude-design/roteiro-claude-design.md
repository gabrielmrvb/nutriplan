# Roteiro — criar o design system do NutriPlan no claude.ai/design

Traduz o Reel "Parte 1/2" do @matheusgomes para a semente deste repositório.
O formulário pode ter mudado desde o vídeo (setembro de 2026); adapte e anote
aqui o que mudou. Tempo: ~15 min, dos quais ~5 são a geração.

A semente está em `artifacts/claude-design/seed/` (montada por
`scripts/montar_semente.py`; capturas por `artifacts/claude-design/capturar.sh`).

## Criar o sistema

1. `claude.ai/design` → modelo **Opus 5**, esforço **Extra**.
2. "+" → **Design system → Create**. Nome: **NutriPlan**.
3. *Link code from your computer* → arraste `seed/codigo/` (é a subpasta de
   frontend: `app.css`, `base.html`, `partials/`).
4. *Add fonts, logos and assets* → arraste tudo de `seed/marca/`,
   `seed/capturas/` (13 PNGs) e `seed/telas/` (6 HTMLs autocontidos).
   Se o formulário recusar HTML, deixe as telas de fora — as capturas cobrem.
5. *Any other notes?* → cole `seed/nota.txt`.
6. Continuar. Nas perguntas:
   - grafia da marca: **NutriPlan**;
   - domínio/produto: *"alimentação, treino, corrida, hidratação e
     progresso — os cinco pilares do DESIGN.md"*;
   - qualquer pergunta sobre cor, raio, fonte ou componente: *"está no
     DESIGN.md; não inventar fora dele"*;
   - o resto: **decida por mim**.
7. Revisar. O que não bater com o `DESIGN.md`, pedir em texto na lateral
   ("o fundo Mesa é `#f5f3ee`, não branco puro"; "só quatro pesos de
   fonte"). Não aceite fonte nova: a fonte é decisão do repositório.

## Gerar os seis mockups

No mesmo projeto, com o design system NutriPlan selecionado e template
**blank**, um prompt por tela (Opus 5 · Extra). Cole cada bloco inteiro:

**Hoje (Mesa)**
> Tela "Hoje" do NutriPlan, 390 px, regime Mesa. Responde "o que eu faço
> agora": cartão AGORA no topo (a próxima refeição com hora, ou o treino em
> andamento), resumo do dia (anel de calorias com número grande, três macros
> em faixa e legenda), refeições do plano como lista — a da vez aberta, as
> outras colapsadas —, minicard de água com título "Água", anel, litros e
> "+250 ml", cartão de treino de hoje com a letra e a duração, aderência do
> dia. Barra inferior de QUATRO itens: Alimentação · Treino · Progresso ·
> Áreas. Estados: refeição vencida, refeição feita, água zerada. Use os
> componentes e tokens do DESIGN.md; nada além deles.

**Painel de treino (Mesa)**
> Tela "Treino" (`/treino/`), 390 px, Mesa. Responde "como é a minha
> semana": o treino de HOJE em destaque com uma ação primária "Abrir treino
> de hoje", e um cartão por sessão da semana (letra A/B/C, nome dos grupos,
> duração estimada, cor de sessão `--dia-*`), cada cartão é um link. NÃO
> lista exercícios. Estados: dia sem treino, semana completa.

**Ficha (Mesa)**
> Tela "Ficha" (`/treino/ficha/<id>/`), 390 px, Mesa. Responde "o que eu
> vou fazer hoje": lista numerada de exercícios — nome, séries × repetições,
> músculo, marcador do movimento principal —, seção "Complementares desta
> sessão", nota de tempo quando a ficha foi ajustada, e "Começar pelo
> primeiro". Cada linha é uma porta para a execução. Sem vídeo, sem campo de
> carga, sem cronômetro (isso mora na execução).

**Execução (FERRO)**
> Tela "Execução" (`/treino/agora/`), 390 px, regime FERRO (tokens da coluna
> Ferro). Responde "estou fazendo, e agora": UM exercício — vídeo curto no
> topo, "Exercício 3/7", carga atual com −2,5/+2,5 discretos, repetições,
> "Concluir série" como único primário, descanso com contagem, desfazer, e
> "carga da última vez". Número grande manda. Estados: descanso correndo,
> última série, exercício concluído.

**Progresso (Mesa)**
> Tela "Progresso" (`/historico/`), 390 px, Mesa. Responde "como estou
> indo": tiles de número grande (aderência %, kcal/dia, água média, treinos
> na semana), curva de peso com os últimos registros, barras de treino e
> água da semana, filtros Semana/Mês, conquistas como ícones do sprite (sem
> emoji). Estados vazios como convite, com uma ação.

**Entrada (Mesa)**
> Tela "Entrar" (`/conta/entrar/`), 390 px, Mesa, sem barra de navegação.
> Marca + wordmark + "Disciplina hoje. Resultados amanhã.", benefício em uma
> linha, campos e-mail e senha com rótulo e ajuda, "Entrar" primário,
> "Continuar com Google" secundário, links "Criar conta" e "Esqueci a senha",
> rodapé com Privacidade · Termos. Estados: erro no campo, sessão vencida
> ("O que você tocou não foi salvo — entre e refaça").

Revise cada mockup contra o `DESIGN.md`; peça ajuste do que não bater.

## Exportar

**Share → Project HTML → Export** (a opção "Standalone HTML" não é usada).
O zip cai em Downloads. Avise o Claude Code: "zip pronto em `<caminho>`".
Não renomeie nada e não copie para a raiz do projeto — a triagem é feita
em `artifacts/claude-design/export/`.

## O que mudou no formulário em relação ao vídeo

(anote aqui)
