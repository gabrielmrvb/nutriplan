# Ficha de verdade — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a sessão entregue parece uma ficha de academia: intermediário, 5
dias, abc2, Padrão → A com ≥ 6 exercícios (≥ 4 peito, ≥ 2 tríceps), 21–28
séries diretas, 55–65 min nas duas opções; Completo 60–80 min.

**Architecture:** o TREINO.md é a fonte (lido por `workouts/doutrina.py`);
o motor lê dele a faixa por (nível, tipo de dia) e o teto semanal por
(nível, frequência); o catálogo dos 28 é ativado com mídia declarada; o
gate vira por letra; planos ativos não são remontados sem pedido; o hook de
push testa o SHA que sobe.

**Tech Stack:** Django 5.2, PostgreSQL, `manage.py test` (RunnerUnico),
`scripts/qa/nav.py` (CDP), Render.

**Spec:** `docs/superpowers/specs/2026-09-17-ficha-de-verdade-design.md`

## Global Constraints

- Teste dourado imutável (`workouts/test_ficha_de_verdade.py`): motor ou catálogo se ajustam, nunca o teste.
- Nenhum exercício ativado sem as duas fotos vistas; mosaico em `scratchpad/shots-dose/mosaico.html`.
- `MINUTOS_POR_DURACAO` intocado; `accounts`/`achievements` só o necessário.
- `TETO_RAPIDO_MIN = 40`; `TETO_POR_DURACAO`: Rápido 30, Padrão 60, Completo 90.
- Testes antigos adaptados com a razão, nenhum apagado. QA com `scripts/qa/nav.py`, capturas em `scratchpad/shots-dose/`.

---

### Task 0.1: `resumo_da_sessao` reusa a sessão e a escolha do painel; orçamento medido no pior dia

**Files:** `workouts/health_export.py:80-120`, `workouts/views.py:150-166`,
`plans/test_stress.py:100-200`.

- [ ] Teste: em `plans/test_stress.py`, `test_no_screen_grows_a_query_per_row`
  congela `django.utils.timezone.localdate` num dia de treino do fixture com
  série registrada hoje (segunda: `date(2026, 9, 14)`), e o docstring lista
  as consultas únicas da Home (41) e do painel (24). Rodar: vermelho no
  painel (27 > 24).
- [ ] `resumo_da_sessao(user, dia=None, sessao=None, escolha=None)`: quando
  `sessao` vem, não consulta `TrainingSession`; quando `escolha` vem, não
  chama `escolha_do_dia`; o descanso lê `sessao.exercises.all()` (prefetch)
  filtrando `opcao` em Python. O painel passa `sessao=hoje, escolha=hoje.escolha`.
- [ ] Verde em `plans.test_stress`; commit "Fase 0: o painel não refaz o que já tinha; orçamento medido no pior dia".

### Task 0.2: hook de pre-push testa o SHA que sobe

**Files:** `scripts/hooks/pre-push`, `CLAUDE.md` (incidente), `config/test_b9_disciplina.py` (o hook contém `git worktree add`).

- [ ] Teste: `config/test_b9_disciplina.py` lê `scripts/hooks/pre-push` e cobra `git worktree add` + `local_sha`.
- [ ] Hook: lê `local_ref local_sha remote_ref remote_sha` do stdin; `git worktree add --detach "$TMP" "$local_sha"`; copia `.env`; roda `"$PY" manage.py test --noinput` DENTRO do worktree com o python absoluto da raiz; `trap` remove o worktree. Recusa `local_sha` zero (delete).
- [ ] CLAUDE.md: incidente de 15/09 (3044 OK numa terça, main vermelho na quarta; árvore de trabalho ≠ HEAD).
- [ ] Commit isolado; push só da Fase 0 (`git push origin HEAD:main`), prova de deploy (`/saude/` 200 + `X-Request-ID`/título), smoke `scratchpad/smoke_prod.py`.

### Task 1: gate por letra

**Files:** `workouts/opcoes_em_producao.py`, `workouts/test_catalogo.py::GateDeOpcoesPorLetraTests`, `workouts/management/commands/opcoes_por_letra.py`, `CLAUDE.md`.

- [ ] Teste vermelho: `LETRAS_COM_OPCOES_EM_PRODUCAO` é um `frozenset` de 16 pares; o teste reprova listando cada letra do conjunto que saiu com 1 (hoje `abcd C`, `abcde D`).
- [ ] Implementação + comando imprime "perdeu: ..."; commit.

### Task 2: TREINO.md e o leitor `workouts/doutrina.py`

**Files:** `docs/briefs/treino/TREINO.md` (novo), `workouts/doutrina.py` (novo), `workouts/test_treino_md.py` (novo).

**Interfaces (Produces):**
```python
class TipoDeDia(TextChoices): UM_GRUPO, DOIS_GRUPOS, TRES_GRUPOS, INFERIOR, SUPERIOR, FULL
def tipo_de_dia(main_groups: list[str], split: str) -> str
def faixa_de_series(nivel: str, tipo: str) -> tuple[int, int]          # séries diretas por sessão
def exercicios_por_grupo(nivel: str, tipo: str) -> tuple[int, int]      # (grande, pequeno)
def series_por_exercicio(nivel: str) -> tuple[int, int]
def teto_semanal(nivel: str, ocorrencias: int) -> int                    # séries efetivas
def faixa_semanal_direta(nivel: str, ocorrencias: int) -> tuple[int, int]
def duracao_esperada(nivel: str, tipo: str) -> tuple[int, int]
def descanso(composto: bool) -> tuple[int, int]
```
- [ ] Escrever o TREINO.md com as tabelas (formato parseável, uma linha por nível × tipo) e as fontes.
- [ ] Testes: o leitor devolve os números do documento (teste lê o markdown e compara com `doutrina`); cada regra tem um teste que cobra o GERADOR (sessão do perfil de referência dentro da faixa do documento; teto semanal; descanso; composto antes de isolador). Vermelho até a Task 4.
- [ ] Commit.

### Task 3: faixas e tetos do motor pelo TREINO.md; teste dourado

**Files:** `workouts/opcoes.py` (`FAIXA_POR_TETO_SEMANAL` → `doutrina.faixa_de_series`), `workouts/services.py` (`teto_semanal_de`, `faixa` em `prescrever_opcoes`, `aparar_opcoes` com teto por frequência), `accounts/models.py` (`TETO_POR_DURACAO[COMPLETO] = 90`, rótulos), `workouts/test_ficha_de_verdade.py` (novo), `workouts/test_catalogo.py` (labels), migration AlterField.

- [ ] Teste dourado vermelho (3 níveis × {3d ABC, 4d ABC, 5d abc2} × {Padrão, Completo}).
- [ ] Motor: `prescrever_opcoes` recebe `nivel`; faixa por tipo de dia; `aparar_opcoes` recebe `teto_por_grupo` (dict grupo → teto por frequência); Completo 90.
- [ ] Verde só depois da Task 4; commit junto.

### Task 4: ativação dos 28 com mídia e mosaico

**Files:** `workouts/data/exercises.json`, `workouts/data/animacoes.json`, `workouts/videos.py`, `workouts/management/commands/desativar_exercicio.py` (novo), `scratchpad/shots-dose/mosaico.html`, `workouts/test_catalogo.py` (ativos 35 → 63), `workouts/opcoes_em_producao.py` (conjunto sobe para 18 depois do deploy).

- [ ] Baixar as 56 fotos; VER cada par; mosaico.
- [ ] oEmbed dos candidatos de Short → `video` + `video_titulo` (`titulo_confere`); anatomia do mesmo padrão → `animacoes.json`.
- [ ] `active: true`; seed; `manage.py opcoes_por_letra` = 18; testes de contrato de mídia verdes; teste dourado verde.
- [ ] `desativar_exercicio "<nome>"`: `is_active=False` + `active: false` no JSON.

### Task 5: planos ativos

**Files:** `workouts/services.py` (`sync_active_routine`, `routine_is_current`), `workouts/models.py` (`TrainingPlan.aviso_dispensado_em`), migration, `plans/views.py` + `templates/plans/today.html` (aviso), `workouts/urls.py` + view `RegenerarTreinoView` / `DispensarAvisoView`, `demo/management/commands/seed_demo.py`, `workouts/test_planos_ativos.py` (novo).

- [ ] Testes vermelhos: plano antigo não muda ao abrir o painel; Home mostra o aviso; regenerar cria plano novo; dispensar esconde.
- [ ] Implementação; commit.

### Task 6: fechamento

- [ ] Sabotagem por regra do TREINO.md e do dourado; revisão adversarial; suíte completa; push; deploy; `/saude/`; smoke; QA em produção (conta descartável, abc2 5 dias, Padrão e Completo, capturas); apagar conta; demo intacta; relatório + notificação.
