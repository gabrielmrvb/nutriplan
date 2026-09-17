# LinkedIn — o que muda no perfil

Perfil lido em 17/09/2026 na sessão logada do Chrome, sem tocar em nada
(`linkedin.com/in/gabriel-marques-64564a430`). Este arquivo diz o que
existe, o que muda e o texto final de cada campo, em inglês, pronto para
colar. **Nada é aplicado antes do "ok" no chat.**

## O que existe hoje (lido, não lembrado)

| campo | conteúdo atual |
|---|---|
| Nome | Gabriel Marques |
| Headline | Python Developer \| Backend \| Fluent English \| Open to AI Trainer & LLM Evaluation roles |
| Local | Araxá, Minas Gerais, Brasil · "Buscando emprego · Apenas recrutadores" |
| Sobre | 4 parágrafos em inglês (backend/automação; procura AI trainer / LLM evaluation; Python, escrita técnica, instruction-following e edge cases; remoto e freelance) |
| Experiência | **Desenvolvedor · Santa Clara** — sem data, sem descrição, sem local |
| Competências (6) | Revisão de texto · Anotação de dados · IA Prompting · Inglês · Redação técnica · "Python, Back-end, Git Lógica de programação, Resolução de problemas" (UMA competência com cinco nomes dentro) |
| Projetos | nenhum ("Nada para ver por enquanto") |
| Destaques (Featured) | nenhum |
| Idioma do perfil | Português (a headline e o Sobre estão em inglês) |

## 1. Projetos — NutriPlan (seção nova)

LinkedIn → Adicionar seção → Projetos. Campos, na ordem do formulário:

**Project name**
```
NutriPlan — diet, training and running in one PWA, built with AI agents
```

**Description** (limite do LinkedIn: 2 000 caracteres; este tem 1 348)
```
A progressive web app that generates a diet and a workout program from one profile — food, training, running, hydration and progress as five equal pillars, in Brazilian Portuguese, offline-first. Live in production on a fully free stack (Render + Neon + GitHub Actions).

What I care about is how it is built. Four Claude Code sessions worked in parallel on one branch, coordinated by a shared ledger; every PR runs the full suite on CI (3,475 tests, 22–29 min) behind branch protection that admins cannot bypass; every guard that matters is written test-first, then sabotaged on purpose to prove the test goes red, then reviewed by a second agent that did not write it. The product is evaluated in production with disposable accounts and graded per area with evidence; a market benchmark of 8 apps became spec items; the training engine follows a written doctrine (TREINO.md, sources cited) that the tests read, and the design system is a contract (DESIGN.md) enforced by tests — 274 contrast pairs measured, 0 failing.

Numbers on 17 Sep 2026: 470 commits in 24 days, 164 test files, 64,575 lines of tests for 31,000 lines of application code, 63 exercises with curated video, one CSS file with 221 tokens and no framework.

Stack: Django 5.2, PostgreSQL, vanilla CSS/JS, service worker with an idempotent offline queue, Web Push, GitHub Actions.
```

**Project URL**
```
https://github.com/gabrielmrvb/nutriplan
```
(a página `/demo/` de produção — `https://nutriplan-xxfn.onrender.com/demo/` —
entra no primeiro item de mídia, abaixo, porque o campo aceita UM link.)

**Dates:** Aug 2026 – Present (o repositório foi criado em 25/08/2026;
"currently working on this project" marcado).

**Associated with:** nenhum (projeto pessoal; não associar à Santa Clara).

**Media — três capturas, nesta ordem** (arquivos em `img/`, 1200×1500, tema
escuro, commit de produção):

| arquivo | título da mídia | descrição da mídia |
|---|---|---|
| `perfil-1-hoje.png` | Today | One screen for the day: the next meal, the calorie ring, water and the workout — in the order that matters now. Live demo: nutriplan-xxfn.onrender.com/demo/ |
| `perfil-2-ficha.png` | Workout sheet | Generated from a written doctrine: 7 exercises, 25 sets, ~59 minutes, two equivalent options — enforced by a golden test. |
| `perfil-3-agora.png` | Training mode | Set by set: load, reps, rest timer, undo. Every tap is an idempotent event and survives offline. |

## 2. Experiência — Santa Clara

O perfil tem só **"Desenvolvedor · Santa Clara"**. O repositório do NutriPlan
não menciona a Santa Clara em lugar nenhum (grep em `*.md`, `*.py`, `*.html`,
`*.json`: zero ocorrências), e a memória do projeto também não. Logo, o que
dá para completar sem inventar é:

| campo | hoje | proposto | por quê |
|---|---|---|---|
| Title | Desenvolvedor | **Developer** | só tradução — o resto do perfil está em inglês |
| Company | Santa Clara | Santa Clara | mantém |
| Employment type | vazio | **você preenche** | não há fonte |
| Start / end date | vazio | **você preenche** | não há fonte; o LinkedIn exige data de início para a entrada aparecer inteira |
| Location | vazio | Araxá, Minas Gerais, Brazil · *só se for verdade* | o perfil diz Araxá, o cargo pode não ter sido lá |
| Description | vazia | **fica vazia** | não há uma linha sequer no perfil ou no repo sobre o que foi feito lá; inventar cargo, data ou atividade está fora do combinado |
| Skills (na experiência) | — | Python · Back-End Web Development | são as duas que o próprio perfil já associa a "Developer"; nada além |

Se você quiser uma descrição, escreva 2–3 frases do que fez lá e eu traduzo
e encaixo no mesmo tom das outras seções.

## 3. Competências — acrescentar

Todas vêm do que o repositório prova (não de aspiração). Nomes no vocabulário
canônico do LinkedIn em inglês, para o autocompletar reconhecer:

| competência | prova no repositório |
|---|---|
| Django | Django 5.2, 6 apps, 76 migrations |
| PostgreSQL | banco de produção (Neon), constraints no banco (`CheckConstraint`, `UniqueConstraint`), `Least(F() + …)` para escrita concorrente |
| Test-Driven Development (TDD) | 3 475 testes, 164 arquivos, sabotagem obrigatória |
| Continuous Integration (CI) | `.github/workflows/suite.yml`, proteção de branch, fila de merge |
| GitHub Actions | suíte + lembretes (`lembretes.yml`) |
| Progressive Web Applications (PWA) | service worker, fila offline em IndexedDB, Web Push |
| Software Testing | revisão adversarial, testes de concorrência com `threading.Barrier`, orçamento de consultas |
| Web Accessibility (WCAG) | contraste medido por teste (4,5:1 / 3:1), alvo de toque 44 px, `aria-*` cobrados |
| Large Language Models (LLM) | quatro sessões de Claude Code em paralelo; avaliação com nota por área |
| AI Agents | ledger, contratos de subagente, revisão por agente que não escreveu o código |
| Technical Writing | `CLAUDE.md` (1 812 linhas), `TREINO.md`, `DESIGN.md`, briefs e relatórios com vocabulário de evidência |

E **desfazer a competência composta** "Python, Back-end, Git Lógica de
programação, Resolução de problemas" em cinco entradas separadas — hoje ela
não conta como nenhuma delas na busca de recrutador:

```
Python
Back-End Web Development
Git
Programming Logic
Problem Solving
```

Total: 11 novas + 5 da composta desfeita = 16 entradas, somando às cinco
que ficam (Revisão de texto · Anotação de dados · IA Prompting · Inglês ·
Redação técnica). Se quiser o perfil num idioma só, os equivalentes dessas
cinco são Proofreading · Data Annotation · Prompt Engineering · English ·
Technical Writing — e "Technical Writing" já está na tabela acima, então
nesse caso a tabela perde uma linha.

## 4. Sobre — um parágrafo a mais (opcional, pronto para colar)

O Sobre atual não cita o projeto. Sugestão: inserir este parágrafo **entre o
segundo e o terceiro** ("I'm currently looking for…" → *este* → "What I
bring…"), sem mexer no resto:

```
Right now I'm building NutriPlan (github.com/gabrielmrvb/nutriplan), a diet-and-training PWA developed with AI coding agents under a strict process: tests written first and sabotaged to prove they can fail, adversarial review by a second agent, a CI gate on every pull request, and evaluation in production with disposable accounts. 3,475 automated tests and counting — I write about the method on this profile.
```

Headline: **não muda**. "Open to AI Trainer & LLM Evaluation roles" é o alvo,
e o projeto entra como evidência, não como cargo.

## 5. Destaques (Featured) — depois do post 1 publicado

Fixar dois itens: o **post 1** e o **link do repositório**
(`https://github.com/gabrielmrvb/nutriplan`, título "NutriPlan — source
code", descrição "Django 5.2 · PostgreSQL · PWA · 3,475 tests"). O LinkedIn só
deixa destacar post já publicado, então este passo espera o "ok" do post 1.

## Ordem de aplicação (só depois do "ok" sobre este arquivo)

1. Projetos: criar o NutriPlan com o texto da seção 1 e as três mídias.
2. Competências: acrescentar as 11 da seção 3; desfazer a composta em cinco.
3. Experiência: só a tradução do título ("Developer"); datas e tipo ficam
   para você, porque não há fonte.
4. Sobre: inserir o parágrafo da seção 4 — se você quiser.
5. Destaques: depois de o post 1 estar no ar.

Cada passo vira uma captura antes de salvar, para conferência. Nada de
conectar, curtir, comentar ou mandar mensagem — o combinado é só perfil e
posts.
