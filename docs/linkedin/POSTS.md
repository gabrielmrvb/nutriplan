# LinkedIn — série de cinco posts sobre o NutriPlan

Cinco posts em inglês, um por semana, sobre COMO o NutriPlan é construído com
agentes de IA — e não sobre "fiz um app". Cada um abre com um gancho, tem entre
900 e 1.300 caracteres, leva uma imagem PNG gerada a partir do design system
real (tokens do `app.css`, Bodoni Moda + Karla auto-hospedadas, capturas de
tela do commit de produção) e fecha com uma linha que conecta ao trabalho de
AI training / LLM evaluation sem pedir emprego.

**Todo número foi medido em 17/09/2026** sobre `origin/main` = `56a43df`
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
I built a full diet + training app in 24 days. Here it is in numbers.

NutriPlan generates a diet and a workout program from one profile — food, training, running, water and progress in one PWA, in Portuguese, offline-first. It is live, and the code is public (link in the first comment).

The numbers, all measured this morning, none estimated:

• 3,475 automated tests, run on every pull request — 22 to 29 minutes on CI
• 64,575 lines of tests for 31,000 lines of application code
• 63 exercises, each with a curated demonstration video
• 470 commits · 15 PRs merged in the last 12 hours
• 0 CSS frameworks: one stylesheet, 221 design tokens, contrast measured by tests
• 100% free infrastructure: Render + Neon + GitHub Actions

Built with Claude Code — four sessions running in parallel by the end. The tool is not the story. The method is, and that is what the next four posts are about: how the agents coordinated on one branch, why "all tests passed" is not evidence, the day the workout sheet was half a real workout, and choosing a design system by score instead of taste.

If you evaluate LLM output for a living, this is what a rigorous agentic workflow looks like from the inside.
```

**Primeiro comentário:**
```
Code: https://github.com/gabrielmrvb/nutriplan · Live: https://nutriplan-xxfn.onrender.com (there is a /demo/ with fictional data — no account needed)
```

---

## Post 2 — quatro agentes em paralelo, sem se atropelar

**Imagem:** `img/post-2-quatro-sessoes.png` (o fluxo: 4 sessões → ledger →
PR + CI → fila → deploy; números do dia).

```
Four AI agents pushed to the same repo for 14 hours. Zero direct pushes to main, zero broken merges. Here is the setup.

1. A shared ledger. One plain-text file outside git, one line per notice: time · session · file · what I'm about to do. Read before editing, written before committing. 58 notices in 14 hours. Merge conflicts get resolved by whoever rebases — no negotiation.

2. A gate that nobody can skip. Main is protected for everyone, admins included. Every PR runs the full suite — 3,475 tests on Postgres 16, 22–29 minutes. 20 PRs, 63 CI runs: 48 green, 7 red, 8 cancelled.

3. A merge queue, one PR at a time. GitHub's queue is not available on personal accounts (the API answers 422), so a script takes its place: merge main in, push, wait for green, merge — next.

What actually broke was never the code. It was coordination: a PR went "behind" four times while others merged (the queue fixed that), and a red run at 03:00 UTC turned out to be fixtures crossing midnight.

I keep coming back to this when I evaluate models: the interesting failures are rarely the answer itself. They are in what the system assumed about everyone else.
```

---

## Post 3 — TDD, sabotagem e revisão adversarial

**Imagem:** `img/post-3-tdd-sabotagem.png` (o laço de quatro passos, os
números da suíte e três formas reais de um teste verde mentir).

```
I don't trust "all tests passed". Ten times in this codebase, a green test was lying.

So every guard that matters goes through the same loop:

1. Red first — the test fails before any implementation exists.
2. Green — the smallest change that makes it pass.
3. Sabotage — break the guard on purpose. The test MUST go red. If it stays green, the test is wrong, not the code. The sabotage never enters the commit.
4. Adversarial review — a second agent, one that did not write the code, hunts for weak assertions and passes-by-accident.

Three ways a green test lied to me, all real:

• assertNotIn("data-x", html) passed because the marker also lives inside the <script> tag. Anchor on the visible text, never the selector.
• client.post(url, {...}) proves the view, not the screen. Rename a field in the template and it stays green. Submit the rendered form instead.
• Eight threads with no Barrier never actually race. The retry test passed with the retry deleted — 5 of 8 writes were being lost and nothing was red.

Today: 64,575 lines of tests for 31,000 lines of app code, 3,475 tests, every PR.

Evaluating an LLM's answer is the same discipline. The question is never "does it look right" — it is "what would have to be broken for this to still look right?"
```

---

## Post 4 — o dia em que a ficha tinha 4 exercícios

**Imagem:** `img/post-4-ficha-de-quatro.png` (antes · referência · depois, o
que consertou, o benchmark de mercado).

```
On Sept 16 at 06:30 my app handed an intermediate lifter a chest day with 4 exercises and 13 sets. A coach would hand 7 exercises and 21 to 28 sets.

Nobody reported it. An evaluation session found it: an agent playing a demanding new user, on a disposable account, in production, grading each area 0–10 with evidence. Training: 5.

Then it traced the cause instead of guessing: the catalog had 4 chest and 3 triceps exercises; two equivalent options per session needed 6 and 6; and a weekly volume cap kicked in before the clock did. No duration setting changed anything.

The fix was not a tweak:
• a written doctrine, TREINO.md — sets per exercise, per session, per week, by level and day type, papers cited (Schoenfeld, Helms, Israetel);
• tests that read that document and fail the engine against it, plus a golden test that never loosens;
• the catalog: 36 → 63 active exercises, each with a curated video;
• a market benchmark of 8 apps — five patterns where 5+ converge became spec items; where one contradicted the doctrine, the doctrine won, in writing.

Measured in production the next day: 7 exercises, 25 sets, ~59 minutes.

The score was not the point. The trace was. A grade is only useful when it comes with the reason — in fitness apps and in model evaluation alike.
```

---

## Post 5 — um design system gerado, e escolhido entre três direções

**Imagem:** `img/post-5-design-system.png` (as três direções lado a lado com
a nota de cada uma, e os quatro números do sistema que entrou).

```
Three design directions were generated for my app. I picked one with a scoresheet written before I saw any of them.

The brief went to Claude Design and came back as three complete directions — NERVURA, CORTE, VENAÇÃO — same seven screens, dark and light, each with its own type and palette.

Six criteria, 0 to 5 each, in a fixed order: identity in one second (cover the name — is it still this app?), the number as hero at 390 px, the workout screen and its reward frame, dark-first with AA contrast, cost on top of the existing CSS, risk of ageing badly.

Scores: 23 · 25 · 17. CORTE won on the two criteria that are structure — identity and cost — not on the ones that are taste. It lost "number as hero", and that is written down too.

Then it became a contract, not a mockup:
• tokens written once — dark is the base, light is derived
• two self-hosted fonts, Bodoni Moda + Karla, 70,580 bytes of a 260 KB budget
• 274 contrast pairs measured in the real CSS, 0 failing
• the leaf-shaped cut on every button, field, chip and card — with a test listing what may not be a pill

Each one is enforced by a test, so the spec cannot drift quietly.

Choosing between generated options is rubric work. Writing the rubric before seeing the options is what makes the choice defensible — and reversible.
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
