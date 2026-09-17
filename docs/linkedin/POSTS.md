# LinkedIn — série de cinco posts sobre o NutriPlan

Cinco posts em português, um por semana, sobre COMO o NutriPlan é construído com
agentes de IA — e não sobre "fiz um app". Cada um abre com um gancho, tem entre
900 e 1.300 caracteres, leva uma imagem PNG gerada a partir do design system
real (tokens do `app.css`, Bodoni Moda + Karla auto-hospedadas, capturas de
tela do commit de produção) e fecha com uma linha que conecta ao trabalho de
AI training / LLM evaluation sem pedir emprego.

**Idioma: português** (decisão do dono em 17/09; a primeira versão era em inglês, e a linha final que conecta a AI training / LLM evaluation continua). **Todo número foi medido em 17/09/2026** sobre `origin/main` = `56a43df`
(o commit que `/saude/` devolve em produção). A tabela de proveniência está
no fim. Nenhuma métrica é estimada.

Publicação: o post 1 sai à mão depois do "ok" no chat; os quatro seguintes
entram pelo agendamento nativo do LinkedIn (um por semana, mesmo dia e hora
do post 1), cada um também depois do "ok" com a captura.

Cada post está pronto para colar. O link do repositório vai no **primeiro
comentário**, não no corpo — o LinkedIn reduz o alcance de post com link
externo no texto; é a prática, não regra escrita.

---

## Post 1 — o app, em números

**Imagem:** `img/post-1-o-app-em-numeros.png` (1200×1500 — três telas reais:
Hoje, ficha, execução — e quatro números).

```
Construí um app completo de dieta e treino em 24 dias. Aqui está ele em números.

O NutriPlan gera a dieta e o programa de treino a partir de um perfil só — alimentação, treino, corrida, hidratação e progresso num único PWA, offline-first. Está no ar, e o código é público (link no primeiro comentário).

Os números, todos medidos hoje de manhã, nenhum estimado:

• 3.475 testes automatizados, em todo pull request — 22 a 29 minutos no CI
• 64.575 linhas de teste para 31.000 linhas de código de aplicação
• 63 exercícios, cada um com vídeo de demonstração curado
• 470 commits · 15 PRs mergeados nas últimas 12 horas
• 0 frameworks de CSS: um arquivo, 221 tokens de design, contraste medido por teste
• infraestrutura 100% gratuita: Render + Neon + GitHub Actions

Feito com Claude Code — quatro sessões em paralelo no fim. A ferramenta não é a história. O método é, e é dele que os próximos quatro posts falam: como os agentes se coordenaram numa branch só, por que "todos os testes passaram" não é evidência, o dia em que a ficha de treino era metade de um treino de verdade, e a escolha de um design system por nota, não por gosto.

Se você avalia saída de LLM profissionalmente, é assim que um fluxo agêntico rigoroso se parece por dentro.
```

**Primeiro comentário:**
```
Código: https://github.com/gabrielmrvb/nutriplan · No ar: https://nutriplan-xxfn.onrender.com (tem um /demo/ com dados fictícios — não precisa de conta)
```

---

## Post 2 — quatro agentes em paralelo, sem se atropelar

**Imagem:** `img/post-2-quatro-sessoes.png` (o fluxo: 4 sessões → ledger →
PR + CI → fila → deploy; números do dia).

```
Quatro agentes de IA empurraram código para o mesmo repositório por 14 horas. Zero push direto na main, zero merge quebrado. O arranjo foi este.

1. Um ledger compartilhado. Um arquivo de texto fora do git, uma linha por aviso: hora · sessão · arquivo · o que vou fazer. Lido antes de editar, escrito antes de commitar. 58 avisos em 14 horas. Conflito de merge é de quem faz o rebase — sem negociação.

2. Um gate que ninguém pula. A main é protegida para todo mundo, admin incluído. Todo PR roda a suíte inteira — 3.475 testes em Postgres 16, 22 a 29 minutos. 20 PRs, 63 rodadas de CI: 48 verdes, 7 vermelhas, 8 canceladas.

3. Uma fila de merge, um PR por vez. A fila do GitHub não existe em conta pessoal (a API responde 422), então um script faz o papel: traz a main, empurra, espera o verde, mergeia — próximo.

O que quebrou de verdade nunca foi o código. Foi coordenação: um PR ficou atrás da main quatro vezes enquanto os outros mergeavam (a fila resolveu), e uma rodada vermelha às 3h UTC eram fixtures cruzando a meia-noite.

É nisso que penso quando avalio modelos: as falhas interessantes raramente estão na resposta em si. Estão no que o sistema assumiu sobre todo o resto.
```

---

## Post 3 — TDD, sabotagem e revisão adversarial

**Imagem:** `img/post-3-tdd-sabotagem.png` (o laço de quatro passos, os
números da suíte e três formas reais de um teste verde mentir).

```
Eu não confio em "todos os testes passaram". Dez vezes neste código, um teste verde estava mentindo.

Por isso toda guarda que importa passa pelo mesmo laço:

1. Vermelho primeiro — o teste falha antes de existir implementação.
2. Verde — a menor mudança que o faz passar.
3. Sabotagem — quebrar a guarda de propósito. O teste TEM de ficar vermelho. Se continua verde, o teste está errado, não o código. A sabotagem nunca entra no commit.
4. Revisão adversarial — um segundo agente, que não escreveu o código, caça asserção fraca e teste que passa por acidente.

Três jeitos reais de um teste verde ter mentido para mim:

• assertNotIn("data-x", html) passava porque o marcador também mora dentro do <script>. Ancore no texto visível, nunca no seletor.
• client.post(url, {...}) prova a view, não a tela. Renomeie um campo no template e continua verde. Envie o formulário renderizado.
• Oito threads sem Barrier nunca disputam de verdade. O teste do retry passou com o retry apagado — 5 de 8 gravações se perdiam e nada ficava vermelho.

Hoje: 64.575 linhas de teste para 31.000 de aplicação, 3.475 testes, em todo PR.

Avaliar a resposta de um LLM é a mesma disciplina. A pergunta nunca é "parece certo?" — é "o que precisaria estar quebrado para isto continuar parecendo certo?"
```

---

## Post 4 — o dia em que a ficha tinha 4 exercícios

**Imagem:** `img/post-4-ficha-de-quatro.png` (antes · referência · depois, o
que consertou, o benchmark de mercado).

```
Em 16 de setembro, às 6h30, meu app entregou a um intermediário um dia de peito com 4 exercícios e 13 séries. Um treinador entregaria 7 exercícios e 21 a 28 séries.

Ninguém reportou. Uma sessão de avaliação achou: um agente no papel de usuário novo e exigente, conta descartável, em produção, nota de 0 a 10 por área, com evidência. Treino: 5.

Depois ela rastreou a causa em vez de chutar: o catálogo tinha 4 exercícios de peito e 3 de tríceps; duas opções equivalentes por sessão pediam 6 e 6; e um teto semanal de volume batia antes do relógio. Nenhum ajuste de duração mudava nada.

O conserto não foi remendo:
• uma doutrina escrita, o TREINO.md — séries por exercício, por sessão, por semana, por nível e tipo de dia, fontes citadas (Schoenfeld, Helms, Israetel);
• testes que leem o documento e reprovam o motor contra ele, mais um teste dourado que nunca afrouxa;
• o catálogo: de 36 para 63 exercícios ativos, cada um com vídeo curado;
• um benchmark de 8 apps — cinco padrões em que 5+ convergem viraram itens de spec; onde um contradizia a doutrina, a doutrina venceu, por escrito.

Medido em produção no dia seguinte: 7 exercícios, 25 séries, ~59 minutos.

A nota não era o ponto. O rastro era. Nota só serve quando vem com a razão — em app de treino e em avaliação de modelo.
```

---

## Post 5 — um design system gerado, e escolhido entre três direções

**Imagem:** `img/post-5-design-system.png` (as três direções lado a lado com
a nota de cada uma, e os quatro números do sistema que entrou).

```
Três direções de design foram geradas para o meu app. Escolhi uma com critérios escritos antes de ver qualquer uma delas.

O brief foi para o Claude Design e voltou como três direções completas — NERVURA, CORTE, VENAÇÃO — as mesmas sete telas, escuro e claro, cada uma com tipografia e paleta próprias.

Seis critérios, de 0 a 5, em ordem fixa: identidade em um segundo (tampe o nome — ainda é este app?), número como herói a 390 px, tela de treino e frame de recompensa, escuro como base com contraste AA, custo sobre o CSS que já existe, risco de envelhecer mal.

Notas: 23 · 25 · 17. CORTE venceu nos dois critérios que são estrutura — identidade e custo — não nos que são gosto. Perdeu em "número como herói", e isso também está escrito.

Depois virou contrato:
• tokens escritos uma vez — o escuro é a base, o claro é derivado
• duas fontes auto-hospedadas, Bodoni Moda + Karla, 70.580 bytes num orçamento de 260 KB
• 274 pares de contraste medidos no CSS real, 0 reprovados
• o recorte em folha em todo botão, campo, chip e cartão — e um teste diz o que não pode ser pílula

Cada item é cobrado por teste: a spec não deriva em silêncio.

Escolher entre opções geradas é trabalho de rubrica. Escrever a rubrica antes de ver as opções é o que torna a escolha defensável — e reversível.
```

---

## Proveniência dos números (medido em 17/09/2026, `origin/main` = `56a43df`)

| número | como foi medido |
|---|---|
| 3,475 tests · 22–29 min | `unittest` discovery sobre `origin/main`; log do CI: "Ran 3475 tests in 1311.7s" (`88619ed`) e "1728.9s" (`10dee4b`) |
| 64,575 / 31,000 lines | `git ls-files '*.py'` em `origin/main`, `test*.py` contra o resto sem `migrations/` |
| 164 test files | idem |
| 63 exercises with video | `workouts/data/exercises.json` (64 cadastrados, 63 `active`); `/saude/` em produção: 64 com vídeo |
| 470 commits · 24 days | `git rev-list --count origin/main`; dias distintos com commit desde 24/08 |
| 221 tokens · 1 stylesheet | `grep -cE '^\s+--[a-z][a-z0-9-]*:' static/css/app.css` (8 485 linhas) |
| 20 PRs · 15 merged in 12 h · 63 CI runs (48/7/8) | API do GitHub, `scripts/github.py` com o token do Git Credential Manager; primeiro merge 16/09 23:13Z, último 17/09 11:13Z |
| 0 direct pushes to main | `git log --first-parent --no-merges --since 2026-09-16T21:00Z origin/main` — o último push direto é `52d0e63`, anterior ao primeiro run do CI (21:52Z) |
| 58 notices · 4 sessions · 14 h | `C:\Users\biel-\nutriplan-ledger.md`: 18 (avaliação/Lote 1) + 15 (treino) + 14 (design) + 10 (mercado) + 1 (esta), de 16/09 18:38 em diante |
| GitHub queue → 422 | ledger 17/09 05:55 |
| "behind" 4× · red run at 03:00 UTC | ledger 17/09 06:11 e 00:21 |
| 10× a green sabotage | `.claude/skills/nutriplan-missao/SKILL.md` §5 ("Já aconteceu dez vezes nesta base") |
| 8 threads, 5 of 8 saved | `CLAUDE.md` ("Oito `append_set` simultâneos gravavam CINCO e perdiam três") |
| 4 ex · 13 sets · 33 min · grade 5/10 | relatório da avaliação de 16/09 06:30–08:20 (`scratchpad/avaliacao/2026-09-16/RELATORIO.md` da sessão Lote 1), §1 e §4 |
| 7 ex · 21–28 · 60–75 (reference) | idem, §4, "referência de academia dada no brief" |
| 7 ex · 25 sets · ~59 min (after) | tela `/treino/ficha/<id>/` renderizada localmente sobre `origin/main` com pessoa intermediária, 5 dias, abc2, Padrão (captura em `img/perfil-2-ficha.png`) |
| 36 → 63 · Schoenfeld/Helms/Israetel · golden test | `CLAUDE.md` (seções de 16–17/09), `docs/briefs/treino/TREINO.md`, `workouts/test_ficha_de_verdade.py` |
| 8 apps · 5 patterns | `docs/briefs/mercado/BENCHMARK-2026-09.md` |
| 23 · 25 · 17 · six criteria | `docs/briefs/design/DIRECAO-ESCOLHIDA.md` |
| 70,580 bytes · 260 KB gate · 274 pairs · 0 failures · 0/20/0/20 | `CLAUDE.md` (Design / Onda 3, T3.2, T3.3) e `config/test_fontes.py`, `scripts/qa/auditar_contraste.py` |
| capturas de tela | commit `origin/main` servido localmente, Chrome 153 headless por CDP, 390×844, tema escuro; imagens compostas por `scratchpad/gerar_imagens.py` desta sessão |

**Ressalva escrita:** o pedido citava "3.272 testes" e "22–28 min"; a
contagem real de hoje é **3.475** e o CI mediu **21,9 a 28,8 min** — os
posts usam o medido.
