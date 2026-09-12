# NutriPlan — Missão Mestre de Implementação · plano de execução

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> (inline, com checkpoints) — subagentes só onde houver tarefas de arquivos
> disjuntos, e nunca dois no mesmo arquivo (regra de propriedade do
> `nutriplan-missao`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar o NutriPlan ao nível definido nas auditorias — mobile-first,
identidade clara e premium, navegação e Áreas como estrutura intencional —
sem recomeçar nada, com deploy por subprojeto e prova em produção.

**Architecture:** Django 5.2 monolito com templates servidos; um `app.css` lido
de ponta a ponta; `pwa.js`/`fila.js`; PostgreSQL. Cada subprojeto termina em
software funcionando, testado, publicado e provado com smoke em produção. O
motor de treino, o motor nutricional, a fila offline e os contratos de
migration NÃO mudam; muda a superfície e o que a superfície esconde.

**Tech Stack:** Django 5.2.17 · PostgreSQL 16+ · CSS sem framework · JS sem
build · agent-browser 0.37.1 (QA) · Render (deploy) · Neon (banco).

**Spec:** a mensagem "NUTRIPLAN — MISSÃO MESTRE DE IMPLEMENTAÇÃO" de
12/09/2026, seções 1–5 completas e a 6 truncada em "como apropri"; o que a
mensagem não trouxe é lido de `BACKLOG.md` (o nível definido nas auditorias)
e de `CLAUDE.md` (as decisões fechadas). **Quando as seções 7+ chegarem, este
plano ganha um subprojeto por seção — sem parar o que já está em execução.**

## Global Constraints

- Mobile-first: validar em **320×568, 375×667, 390×844, 430 de largura**, tablet
  e desktop só como fallback. Zero rolagem horizontal; alvo de toque 44×44;
  texto ≥ 11px; CTA acessível com o teclado aberto; barra de baixo nunca cobre
  conteúdo.
- Identidade: fundo claro **`#f4f6f5`**, verde principal/CTA **`#0c6b40`**,
  verde folha **`#43A11B`**; premium, limpo, humano; sem cara de painel admin,
  sem cards iguais em série, sem excesso de bordas.
- Navegação inferior definitiva: **Alimentação · Treino · Progresso · Áreas**.
  Perfil dentro de Áreas; Áreas não repete a barra.
- Não recomeçar: sem trocar framework, sem arquitetura paralela, sem apagar
  dado real. Compatibilidade com perfis antigos preservada.
- Motor de treino intocado (ABC, A1/A2, 4/4/3/3, complementares, volume, teto,
  catálogo, vídeos, histórico). Motor nutricional intocado. Fila offline e
  `op_id` intocados.
- Cada subprojeto: dirigidos → sabotagem → QA agent-browser nas quatro
  larguras → suíte completa com **exit code real** → `check` →
  `makemigrations --check` → `git diff --check` → commit → push pelo `pre-push`
  → deploy → `/saude/` → smoke com controle positivo.
- Conta demo pública (`carlos.demo@nutriplan.invalid`) nunca é tocada por QA.
  Conta local de QA (`qa-redesign-treino@local.invalid`) só no banco de
  desenvolvimento, zero `ExerciseLog` ao fim de cada subprojeto.
- `artifacts/` e `stash@{0}` intocados. Nunca `git add -A`.

---

## Mapa de subprojetos

| # | subprojeto | fonte | entrega |
|---|---|---|---|
| SP0 | Fechar a missão em voo (`128aa1b`) | missão anterior | deploy + `/saude/` + smoke depois |
| SP1 | Verdade do ambiente e do repositório | reconhecimento | `CLAUDE.md` sem afirmações falsas; agent-browser como ferramenta de QA registrada |
| SP2 | Identidade clara-primeiro | spec §4 | tema claro como padrão, `--folha`, contraste medido, PWA e meta atualizados |
| SP3 | Navegação e Áreas como estrutura | spec §5–6 | topo sem Perfil redundante; Áreas hub sem duplicar a barra |
| SP4 | Composição por tela (Hoje, Treino, Progresso, Perfil, onboarding, entrada) | spec §4 | hierarquia, ritmo, tipografia, estados — uma tela por tarefa |
| SP5+ | Seções 7+ da spec (alimentação, treino, hidratação, progresso, corrida, onboarding, perfil, vídeos, segurança, performance) | spec quando chegar + `BACKLOG.md` | um plano por seção em `docs/superpowers/plans/` |

Cada subprojeto é um commit (ou poucos) e um deploy. Nada de SP4 começa antes
de SP2 estar em produção: composição sobre paleta errada é trabalho perdido.

---

### Task SP0.1: Push pelo portão e deploy de `128aa1b`

**Files:** nenhum (o commit já existe).

- [ ] **Step 1: Esperar o `pre-push`** — a suíte inteira contra a árvore de
  trabalho. Arquivo: `scratchpad/push.txt`, linha `PUSH_EXIT=`.
  Expected: `Ran 2730 tests` · `OK` · `PUSH_EXIT=0` · `128aa1b -> main`.
- [ ] **Step 2: Acompanhar o Render** — `curl -s https://nutriplan-xxfn.onrender.com/saude/`
  até 200 com o build novo (`X-Request-ID` presente; o commit aparece no painel).
- [ ] **Step 3: Smoke DEPOIS** — `python scratchpad/smoke_prod.py`.
  Expected: as 12 verificações que reprovavam na versão velha viram `ok`;
  `FALHAS: nenhuma`.
- [ ] **Step 4: Confirmar a conta demo intocada** — `digital(DEMO)` de
  `restaurar_qa.py` idêntica à de 10/09 (3 dias, plano 482, 230 logs).
- [ ] **Step 5: Registrar** — no relatório: `EXIT_REAL` da suíte 1/2/3 e do
  `pre-push`, 43 sabotagens, duas rotas de migration, commit e `origin/main`.

### Task SP1.1: `CLAUDE.md` deixa de dizer que Node não existe

**Files:**
- Modify: `CLAUDE.md` (seção "Limites reais deste ambiente", linha ~909)

**Interfaces:** nenhuma.

- [ ] **Step 1: Medir** — `node --version` → `v24.19.0`; `agent-browser --version`
  → `0.37.1`; Chrome 153 em `~/.agent-browser/browsers`.
- [ ] **Step 2: Reescrever o bullet**:

```markdown
- **Node 24 e npm 11 estão instalados desde 12/09/2026** (WinGet), e com eles
  o `agent-browser` 0.37.1 da Vercel, com Chrome 153 próprio em
  `~/.agent-browser/browsers`. É a ferramenta de QA de navegador: sessão
  própria (`AGENT_BROWSER_SESSION`), saída sempre para arquivo e `stdin`
  fechado — o daemon herda o stdout, e um pipe espera um EOF que nunca vem.
  Lighthouse e Playwright continuam de fora por decisão, não por falta de
  Node: o `agent-browser` cobre o que eles cobririam aqui. O Capacitor da
  Corrida continua bloqueado por Android Studio/Xcode, não por Node.
```

- [ ] **Step 3: Corrigir o BACKLOG** — em "Fundação mobile da Corrida",
  trocar "Nesta máquina não existem `node`, `npm`…" por "Node e npm existem
  desde 12/09/2026; faltam `java`, `gradle`, `adb`, `xcodebuild`".
- [ ] **Step 4: Commit** — `git add CLAUDE.md BACKLOG.md` ·
  `git commit -m "O ambiente tem Node, e o CLAUDE.md dizia que não"`.

### Task SP1.2: `docs/superpowers/plans/` entra no repositório

**Files:**
- Create: `docs/superpowers/plans/2026-09-12-missao-mestre.md` (este arquivo)

- [ ] **Step 1: Commit junto com SP1.1** (mesmo commit; é a mesma verdade).

### Task SP2.1: Tema claro vira o padrão, e o escuro vira a preferência

**Files:**
- Modify: `static/css/app.css:20-140` (o `:root` escuro) e `:354-400`
  (`@media (prefers-color-scheme: light)`)
- Modify: `templates/base.html:13-14` (`theme-color`)
- Modify: `config/settings.py` (`PWA_THEME_COLOR`, `PWA_LIGHT_COLOR`) e
  `push/views.py` (manifesto: `background_color`, `theme_color`)
- Test: `config/tests.py` (contraste WCAG recalculado a partir dos tokens —
  já existe; passa a medir a paleta clara como base), `push/tests.py`
  (manifesto), novo `config/test_tema_claro.py`

**Interfaces:**
- Produces: `:root` com a paleta clara; `@media (prefers-color-scheme: dark)`
  com a escura; `--folha: #43A11B` nos dois temas; `color-scheme: light dark`.

- [ ] **Step 1: Escrever o teste que falha** em `config/test_tema_claro.py`:

```python
"""O tema claro é o padrão, e o escuro é a preferência — não o contrário."""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


def bloco_root(css):
    inicio = css.index(":root {")
    fim = css.index("}", inicio)
    return css[inicio:fim]


class OClaroEOPadraoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.css = re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)

    def test_o_root_declara_a_paleta_clara(self):
        root = bloco_root(self.css)
        self.assertIn("--bg: #f4f6f5;", root)
        self.assertIn("--brand: #0c6b40;", root)
        self.assertIn("--folha: #43a11b;", root.lower())
        self.assertIn("color-scheme: light", root)

    def test_o_escuro_mora_na_preferencia(self):
        self.assertIn("@media (prefers-color-scheme: dark)", self.css)
        escuro = self.css.split("@media (prefers-color-scheme: dark)", 1)[1]
        self.assertIn("--bg: #070c0b;", escuro)
        self.assertNotIn("@media (prefers-color-scheme: light)", self.css)
```

- [ ] **Step 2: Rodar e ver falhar** —
  `manage.py test config.test_tema_claro` → FAIL (`--bg: #070c0b;` no root).
- [ ] **Step 3: Trocar os blocos** — mover o conteúdo do `@media (light)` para
  o `:root`, e o `:root` antigo para `@media (prefers-color-scheme: dark)`;
  acrescentar `--folha: #43A11B` (claro) e `--folha: #6fcf4a` (escuro, medido
  por contraste sobre `--surface`); `color-scheme: light dark` no root.
- [ ] **Step 4: `theme-color` e manifesto** — `PWA_LIGHT_COLOR` continua
  `#f4f6f5`; `PWA_THEME_COLOR` vira a cor clara na meta sem `media`, e a
  escura só sob `(prefers-color-scheme: dark)`; manifesto
  `background_color: #f4f6f5`, `theme_color: #0c6b40`.
- [ ] **Step 5: Rodar dirigidos** — `config.test_tema_claro config.tests
  push.tests` → OK (o contraste WCAG é recalculado dos tokens e precisa passar
  nos dois temas; se um par reprovar, ajustar o TOKEN, nunca o teste).
- [ ] **Step 6: Sabotar** — devolver `--bg: #070c0b` ao root → o teste fica
  vermelho; restaurar.
- [ ] **Step 7: QA agent-browser** — `scratchpad/ab.sh` em 320/375/390/430:
  `/`, `/treino/`, `/treino/ficha/<hoje>/`, `/treino/agora/`, `/historico/`,
  `/areas/`, `/conta/perfil/`, `/conta/entrar/`; screenshot de cada; medir
  `getComputedStyle(document.body).backgroundColor` = `rgb(244, 246, 245)`;
  `scrollWidth - clientWidth = 0`.
- [ ] **Step 8: Commit** — `git add static/css/app.css templates/base.html
  config/settings.py push/views.py config/test_tema_claro.py` ·
  `git commit -m "O claro é o padrão do NutriPlan, e o escuro é a preferência"`.

### Task SP2.2: `--folha` ganha papel, e não só existência

**Files:**
- Modify: `static/css/app.css` (progresso, séries concluídas, selo de área
  principal, `.ficha-item--feito`, anel do treino)
- Test: `config/test_tema_claro.py`

**Interfaces:**
- Consumes: `--folha` de SP2.1.
- Produces: `.ring--treino`, `.ficha-item__estado--feito`, `.modulo__selo`,
  `.progress__fill` usando `--folha` para "feito/ganho"; `--brand` continua
  sendo AÇÃO (CTA, links, foco).

- [ ] **Step 1: Teste** — `--folha` aparece em pelo menos quatro regras
  fora do `:root`, e nenhuma delas é `.btn--primary` (ação é `--brand`).
- [ ] **Step 2: Falhar** → **Step 3: aplicar** → **Step 4: passar**.
- [ ] **Step 5: QA** — na ficha com uma série anotada (conta local de QA;
  apagar o `ExerciseLog` depois), o "1/4" e o anel usam a folha; o CTA
  continua no verde principal.
- [ ] **Step 6: Commit** — `"A folha é o verde do que foi feito; o principal é o do que se faz"`.

### Task SP2.3: Suíte, deploy e smoke do SP2

- [ ] Suíte completa com `EXIT_REAL` · `check` · `makemigrations --check` ·
  `git diff --check` · push pelo `pre-push` · Render · `/saude/` · smoke com
  `backgroundColor` medido em produção via agent-browser.

### Task SP3.1: O topo não repete o Perfil

**Files:**
- Modify: `templates/base.html:160-220` (app-bar)
- Test: `config/test_nomenclatura.py` (barra e mapa por destino — já existe),
  `accounts/tests.py` (`TodaTelaTemPortaTests`)

- [ ] **Step 1: Medir** — listar todo `href` para `accounts:profile` fora de
  `/areas/` e do próprio Perfil. Expected hoje: o "Sair"/avatar do desktop.
- [ ] **Step 2: Teste** — `base.html` renderizado em `/treino/` não contém
  link para `accounts:profile` fora de `<nav class="tabbar">`/`app-bar__link`
  "Áreas"; `/areas/` contém exatamente um.
- [ ] **Step 3–4: falhar/aplicar/passar.** **Step 5: Commit.**

### Task SP3.2: Áreas concentra o secundário sem duplicar a barra

**Files:**
- Modify: `templates/accounts/areas.html`, `accounts/views.py:928-1010`
- Test: `accounts/test_areas.py` (novo)

**Interfaces:**
- Produces: contexto `areas` (Corrida, Hidratação com fato do dia),
  `ferramentas` (Lista de compras, Suplementos se ativo, Conquistas, Perfil,
  Exportar para o Saúde), `mostra_gestao`.

- [ ] **Step 1: Teste** — `/areas/` NÃO linka `plans:today`,
  `workouts:routine`, `plans:history` (a barra já leva); linka
  `workouts:corridas`, `plans:hydration`, `plans:shopping`,
  `achievements:lista`, `accounts:profile`, `workouts:health_export`; e
  cada módulo tem alvo ≥ 44px (régua de `config/tests.py`).
- [ ] **Step 2–4: falhar/aplicar/passar.** **Step 5: QA 320/390.**
  **Step 6: Commit.**

### Task SP3.3: Suíte, deploy e smoke do SP3.

### SP4 — Composição por tela

Um plano próprio, escrito quando SP2 estiver em produção:
`docs/superpowers/plans/2026-09-1x-composicao-por-tela.md`, uma tarefa por
tela (Hoje, Treino painel, ficha, execução, Progresso, Áreas, Perfil,
onboarding 1–7, entrar/criar), cada uma com: medição antes (agent-browser,
quatro larguras), hierarquia proposta pela skill `nutriplan-ux`, mudança,
medição depois, teste de estrutura, commit.

### SP5+ — Seções 7 em diante da spec

Um plano por seção, quando o texto chegar. Enquanto não chega, os itens
abertos do `BACKLOG.md` que cabem sem decisão humana entram como SP5:
`SyncedOperation.podar()` nunca chamado (linha 610), `atraso_de_hidratacao`
com datetime naive (1587), falha ao enfileirar sem sinal na tela (1700),
`/conta/social/` sem porta (509).

---

## Self-review

- **Cobertura da spec** — §1 (autonomia) governa a execução; §2 (não
  recomeçar) é restrição global; §3 (mobile-first) é o Step de QA de toda
  tarefa; §4 (identidade) = SP2 + SP4; §5 (navegação) = SP3.1; §6 (Áreas) =
  SP3.2, com o texto truncado suprido pelo `areas.html` atual e pela regra
  "não repete a barra". §7+ não existe neste texto: SP5+.
- **Placeholders** — nenhum "TBD"; SP4 e SP5 são remetidos a planos próprios
  com nome e gatilho, que é o que a skill manda para subsistemas
  independentes.
- **Consistência** — `--folha` definido em SP2.1 e consumido em SP2.2; a régua
  de toque é a de `config/tests.py` em SP3.2 e SP4.
