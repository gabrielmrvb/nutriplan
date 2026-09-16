# Catálogo de exercícios e promessa de tempo — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para executar este plano tarefa a tarefa. Passos com `- [ ]`.

**Goal:** a copy de tempo diz só o que o gerador entrega; todo exercício tem
`padrao` e `equipment`; as opções de uma letra cobrem os mesmos padrões
COMPOSTOS por grupo anunciado; o catálogo cresce (inativo, até mídia
conferida) até sustentar duas opções cheias por letra; o volume semanal
direto fica a ±1 série do modelo em todo perfil; nenhum deploy reduz as
letras com 2 opções.

**Architecture:** `Padrao` (22 valores) e `PADROES_COMPOSTOS` em
`workouts/models.py`; `Exercise.padrao` com `CheckConstraint` (e outro em
`equipment`); `montar_opcoes(itens, n, principais)` reparte o grupo anunciado
por bloco de padrão composto (padrão único = compartilhado) e os isoladores
em rodízio; `equivalentes` exige os mesmos padrões compostos por grupo
anunciado; `workouts/opcoes_em_producao.py` conta letras com 2 opções para
o gate; catálogo novo em `exercises.json` com `active: false`, `padrao`,
`equipment`, `candidatos` de mídia e chave conferida em `media_map.json`;
`splits.json` lista os novos nas letras (o `is_active` os filtra até a
ativação).

**Tech Stack:** Django 5.2, PostgreSQL, `manage.py test` (RunnerUnico).

**Spec:** decisões do dono em 16/09/2026 (chat): F' (copy), taxonomia de 22,
reuso de `equipment`, régua de compostos, gate de deploy.

## Global Constraints

- Rótulos: "Rápido — até 30 minutos" / "Padrão — até 60 minutos" /
  "Completo — a sessão inteira, até 65 minutos" / "Sem limite rígido — o
  mesmo que Completo, até 65 minutos"; `TETO_POR_DURACAO[COMPLETO] = 65`.
- Nenhum exercício ativado sem mídia conferida; novos entram `active: false`.
- Nenhum teste apagado; adaptados com a razão escrita.
- Sem push, deploy ou produção nesta fase. Commits na branch.
- Testes novos em `workouts/test_catalogo.py`; `test_opcoes.py` estendido.

---

### Task 1: copy de tempo (F') — FEITA em `2b3abf5`

### Task 2: `Exercise.padrao` + constraints + seed

**Files:** `workouts/models.py`, `workouts/migrations/0022_padrao_de_movimento.py`,
`workouts/management/commands/seed_workouts.py`, `workouts/data/exercises.json`,
`workouts/test_catalogo.py`.

- [ ] Teste vermelho: todo `Exercise` semeado tem `padrao` em `Padrao`;
  `padrao == ''` e `equipment == ''` são recusados pelo banco
  (`IntegrityError`); `is_compound == (padrao in PADROES_COMPOSTOS)` nos 36;
  o seed depois da migration mantém os 36 com padrão.
- [ ] `Padrao` (22), `PADROES_COMPOSTOS` (8), campo `padrao` (`max_length=24`,
  `choices`, `default=""`), `CheckConstraint`s `padrao_nao_vazio` e
  `equipment_nao_vazio`.
- [ ] Migration: `AddField` → `RunPython` (mapa nome→padrão, 36 nomes) →
  `AddConstraint` ×2. Reverso: remove.
- [ ] `exercises.json` ganha `padrao`; seed grava `row["padrao"]` (KeyError se
  faltar — o build para).
- [ ] Verde; commit.

### Task 3: régua de compostos em `opcoes.py`

**Files:** `workouts/opcoes.py`, `workouts/services.py` (chamada de
`montar_opcoes` com `principais`), `workouts/test_opcoes.py`
(`Falso.Exercicio` ganha `padrao`), `workouts/test_catalogo.py`.

- [ ] Vermelho: `equivalentes` reprova 3 supinos vs 3 crucifixos (mesmo
  volume, mesmos minutos, grupo presente); aprova isoladores diferentes com
  compostos iguais. `montar_opcoes(..., principais=["chest"])` compartilha o
  padrão composto único e reparte os isoladores.
- [ ] Implementação: `_blocos_do_grupo`, `montar_opcoes(itens, n=2,
  principais=())`, `_padroes_compostos(op, grupo)`, régua em `equivalentes`.
- [ ] Sabotagem: régua ignorando compostos → vermelho; repartição sem
  compartilhar → vermelho.
- [ ] Verde nos módulos de opções; commit.

### Task 4: gate de opções por letra

**Files:** `workouts/opcoes_em_producao.py` (novo),
`workouts/management/commands/opcoes_por_letra.py` (novo),
`workouts/test_catalogo.py`, `CLAUDE.md`.

- [ ] `letras_com_opcoes()` → `{(split, letra): n}` com perfis transitórios
  (intermediário, padrão, um perfil por divisão), tudo desfeito ao sair.
- [ ] Teste: `sum(n >= 2) >= LETRAS_COM_OPCOES_EM_PRODUCAO` (16). Fica
  VERMELHO até a ativação da manhã — é o gate.
- [ ] Comando imprime a tabela; CLAUDE.md registra a regra.

### Task 5: catálogo (objetivo 3)

**Files:** `workouts/data/exercises.json`, `workouts/data/splits.json`,
`workouts/data/media_map.json`, `workouts/test_catalogo.py`, testes de
contagem adaptados (`workouts/tests.py:3580`).

- [ ] Tabela hoje/mínimo/recomendado por grupo e letra (fórmula
  `2·ceil(k/2)+floor(k/2)` e `2k`), com a regra "≥2 por padrão composto".
- [ ] Inserir exercícios `active: false` com `padrao`, `equipment`, `cue`,
  `secundarios`, `joints`, `candidatos` (mídia por busca) e chave em
  `media_map.json` conferida na free-exercise-db.
- [ ] `splits.json`: os novos entram nas letras onde a fórmula pede.
- [ ] Teste: seed idempotente com os novos; todo inativo novo tem chave no
  `media_map`; nenhum ativo sem os quatro contratos (já existe).
- [ ] Simulação: letras com 2 opções hoje / com os novos ativos; lista de
  ativação por letra.

### Task 6: propriedade do volume semanal (objetivo 4)

**Files:** `workouts/test_catalogo.py`.

- [ ] Para nível × dias (2–7) × preferência: volume direto semanal por grupo
  (`volume_da_semana`) vs o do modelo repetido pelas ocorrências, aparado
  pelo teto — diferença ≤ 1 série por grupo. Sem `hypothesis`: matriz
  exaustiva determinística (54 perfis), que é o domínio inteiro.

### Task 7: revisão adversarial (subagente somente leitura) → correções →
suíte completa → relatório.
