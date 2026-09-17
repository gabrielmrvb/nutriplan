# Ficha única, troca por exercício e equipamento — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (esta sessão executa em linha, TDD por tarefa, sabotagem por guarda, revisão adversarial antes de cada PR). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a ficha de cada letra é UMA (a variação entre ocorrências é automática), a pessoa troca exercício por alternativa do mesmo padrão dentro do equipamento do perfil, e o equipamento filtra o catálogo antes de gerar.

**Architecture:** o motor de opções fica; `variacao_do_dia` escolhe a opção pelo ciclo; `EscolhaDeTreino` vira registro interno; `TrocaDeExercicio` aplica-se em memória sobre os itens (retrato intacto); `Profile.equipamento` + `TrainingPlan.equipamento` + mapa no `TREINO.md` (`doutrina.equipamentos_de`) filtram/substituem itens do modelo em `prescrever_opcoes(permitidos=...)`; versão rápida vira ação do painel com `EventoDeProduto`.

**Tech Stack:** Django 5.2, PostgreSQL, templates + `app.css` (sem framework), testes `manage.py test`, gate no CI + fila local.

**Spec:** `docs/superpowers/specs/2026-09-17-ficha-unica-design.md`

## Global Constraints

- Teste dourado (`workouts/test_ficha_de_verdade.py`) NUNCA afrouxa; `ADoseDoNivel…`, `test_treino_md` continuam mandando.
- Plano é retrato; ficha ajustada não é remontada; `customized_at` não é tocado pela troca.
- Frase de esforço ≤ 44 caracteres; alvo de toque 44×44; nada rola na horizontal; `:has()` proibido; número com vírgula.
- Orçamentos de consulta: execução 22, POST sem recorde 20/24, painel 25, Home 41, Progresso 27 — subir só com medição escrita.
- Cada PR: testes dirigidos → sabotagem → browser QA (320/390/430) → `check`/`makemigrations --check`/`diff --check` → commit → push (atalho) → PR → `enfileirar`.

---

## PR 1 — `treino/ficha-unica`: variação automática + rápida no painel

### Task 1: `variacao_do_dia` e a opção do dia sem escolha
**Files:** Modify `workouts/services.py` (junto de `sessao_do_dia`; `estado_do_treino` 3342–3355; `prescricao_de_hoje` 3140–3146; `series_de_hoje` 3177–3194; remover `opcao_recomendada`), `workouts/health_export.py` (`resumo_da_sessao` 118–127), `workouts/views.py` (`preparar_dia` 256–266, `ExercicioView` 1026–1038). Test: `workouts/test_ficha_unica.py` (novo).
**Interfaces:** Produces `services.variacao_do_dia(plan, dia, sessao, sessoes=None) -> int` (uma das `sessao.opcoes`); `services.opcao_do_dia(user, sessao, dia, sessoes=None) -> int` (escolha gravada do dia se for da sessão, senão `variacao_do_dia`).
- [ ] Teste que falha: plano 5 dias abc2 com data congelada em `SEGUNDA` (14/09): opção de A na semana 1 = 1, na semana 2 (A cai na quinta 24/09? — posição 3 → `3 // 3 = 1`) = 2, semana 3 = 1; letra que cai 2× na mesma semana usa opções diferentes; plano preso ao dia da semana alterna por semana; escolha gravada do dia vence a variação; `opcao_recomendada` não existe mais.
- [ ] Implementar; `estado_do_treino` sem `recomendada`; `EstadoDoTreino.precisa_escolher` some.
- [ ] Sabotagem: `p // n` → `p` (toda ocorrência opção 2) → vermelho; escolha ignorada → vermelho.

### Task 2: a ficha desenha uma lista; a execução sem "Opção"
**Files:** Modify `workouts/views.py` (`FichaDaSessaoView.contexto_das_opcoes` 583–670 → `contexto_da_ficha`; apagar `EscolherOpcaoView` 673–714), `workouts/urls.py` (linha 23), `templates/workouts/ficha.html` (42–47, 57–76, 78–91, 93–109, 111–157), `templates/workouts/agora.html` (166, 169–178), `templates/workouts/routine.html` (110–115, 514–540), `static/css/app.css` (`.opcoes*`, `.versoes*`, `.hoje__opcao`, `.agora__opcao-aviso`, `.sessao-cartao__versoes`). Tests: `workouts/test_opcoes.py` (`EscolhaDoDiaTests` → reescrever), `test_execucao_legivel.py` (70–77), `tests.py` 5642, `test_fluxo_do_treino.py` (326, 384), `test_rotacao.py` (226–240), `test_catalogo.py` (`SeletorDaRapidaTests`), `config/test_acoes_com_tela.py`.
- [ ] Testes que falham: a ficha de hoje tem UMA `<ol>` de itens, sem "Opção", sem `opcao--recomendada`, sem formulário `escolher`; a ficha de outro dia da semana mostra a variação daquela data; a execução não imprime "Opção" nem `agora__opcao-aviso`; `reverse("workouts:escolher")` não existe; o cartão do painel não diz "versões disponíveis".
- [ ] Implementar. `nomear_ocorrencias`/`agrupar_por_letra` intactos.
- [ ] Sabotagem: template com "Opção {{ … }}" de volta → vermelho.

### Task 3: versão rápida no painel + evento de uso
**Files:** Create `workouts/migrations/0027_evento_de_produto.py`; Modify `workouts/models.py` (`EventoDeProduto`), `workouts/views.py` (`VersaoRapidaHojeView`), `workouts/urls.py` (`hoje/rapida/`), `templates/workouts/routine.html` (cartão de hoje), `workouts/management/commands/medir_progressao.py` (usos em 30 dias), `config/test_acoes_com_tela.py` (DESTINO). Test: `workouts/test_ficha_unica.py`.
- [ ] Testes que falham: POST `hoje/rapida/` grava `EscolhaDeTreino.versao=rapido` na sessão de hoje e um `EventoDeProduto` (único por dia — segundo POST não duplica); POST com `completo=1` volta; GET → redirect painel; a ficha não tem mais `?versao=`; o painel mostra "Menos tempo hoje?" só em dia de treino sem série; `medir_progressao` imprime "versão rápida".
- [ ] Sabotagem: evento não gravado → vermelho; unique retirado → vermelho.

### Task 4: PR 1 — revisão adversarial, QA, fila
- [ ] Revisão adversarial (subagente `feature-dev:code-reviewer`, somente leitura) sobre o diff; corrigir o que for real.
- [ ] Browser QA local (nav.py): painel, ficha de hoje, ficha de outro dia, execução — 320/390/430; capturas em `shots-ficha/`.
- [ ] `check`, `makemigrations --check`, `diff --check`, commit, push, PR, `enfileirar`.

## PR 2 — `treino/equipamento`: a pergunta, o mapa, o filtro, o dourado por perfil

### Task 5: `Equipamento` no perfil e no plano
**Files:** Modify `accounts/models.py` (enum `Equipamento`, `Profile.equipamento`), `accounts/migrations/0035_equipamento.py`, `accounts/forms.py` (`TrainingForm`: campo, initial, save), `templates/accounts/onboarding/step.html`, `templates/accounts/profile.html`, `accounts/views.py` (`resumo_das_escolhas`), `workouts/models.py` (`TrainingPlan.equipamento`), `workouts/migrations/0028_equipamento_no_plano.py`, `workouts/services.py` (`equipamento_de`, `create_routine`, `rotina_invalida`). Tests: `accounts/tests.py`, `workouts/test_planos_ativos.py`, `workouts/test_equipamento.py` (novo).
- [ ] Testes que falham: default "completa" em conta nova e antiga (migration); formulário grava; mudar no perfil torna a rotina inválida e remonta; conta existente não remonta (plano "completa" == perfil "completa"); Perfil mostra "Equipamento".
- [ ] Implementar. Reescrever `OProdutoNaoPrometeAmbienteTests` (`test_capacidade_de_ambiente.py` 500–567) e `OCatalogoAindaNaoSustentaEquipamentoTests` (`test_experiencia.py` 449–509) para o contrato novo.

### Task 6: o mapa no TREINO.md e o filtro no motor
**Files:** Modify `docs/briefs/treino/TREINO.md` ("Mapa de equipamento"), `workouts/doutrina.py` (`equipamentos_de`), `workouts/services.py` (`prescrever_opcoes(permitidos=None)`, `substituir_por_equipamento`, `_prescricao_confere`), `workouts/test_treino_md.py`. Test: `workouts/test_equipamento.py`.
- [ ] Testes que falham: `equipamentos_de("casa_halteres") == {dumbbell, bodyweight}`; item de barra no modelo vira alternativa do mesmo padrão+grupo com halteres, mesma dose; sem alternativa, sai; a conferência (`_prescricao_bate`) reconhece a própria ficha filtrada; o perfil "completa" produz a ficha de sempre (dourado intacto).
- [ ] Sabotagem: substituição ignorando `padrao` → vermelho; `permitidos` ignorado em `_prescricao_confere` → vermelho (ficha julgada desatualizada).

### Task 7: dourado e gate por perfil; a lista do que falta
**Files:** Modify `workouts/test_ficha_de_verdade.py` (por perfil), `workouts/test_capacidade_de_ambiente.py` (AMBIENTES = os 4 perfis do mapa; vereditos medidos), `BACKLOG.md` (lista de exercícios a ativar por perfil), `CLAUDE.md`.
- [ ] Rodar o dourado nos 4 perfis; completa e básica verdes; casa e peso do corpo: medir e escrever a lista (mosaico `scratchpad/shots-ficha/mosaico-equipamento.html`).
- [ ] PR 2: revisão adversarial, QA (onboarding etapa 2, Perfil), fila.

## PR 3 — `treino/troca-por-exercicio`: "outras formas"

### Task 8: modelo e aplicação
**Files:** Modify `workouts/models.py` (`TrocaDeExercicio`), `workouts/migrations/0027_troca_de_exercicio.py`, `workouts/services.py` (`aplicar_trocas`, `alternativas_de(user, exercise, sessao)`, uso em `estado_do_treino`, `prescricao_de_hoje`, `series_de_hoje`), `workouts/views.py` (ficha, exercício, execução). Test: `workouts/test_troca.py` (novo).
- [ ] Testes que falham: troca aplicada na ficha, na execução e na leitura com a mesma dose; volume da sessão igual; persiste em outra letra e na semana seguinte; `ExerciseLog` no substituto; desfazer volta; `rotina_invalida`/`aviso_de_regenerar` não mudam; custo constante (uma consulta).
- [ ] Sabotagem: dose alterada na troca → vermelho; troca não aplicada em outra letra → vermelho.

### Task 9: a tela
**Files:** Modify `templates/workouts/exercicio.html` (cartão "Outras formas": foto + nome + botão), `templates/workouts/_item_da_ficha.html` ("outras formas" → leitura), `workouts/views.py` (`TrocarExercicioView`), `workouts/urls.py` (`trocar/`), `config/test_acoes_com_tela.py`, `static/css/app.css`.
- [ ] Testes que falham: alternativas do mesmo padrão dentro do equipamento do perfil, com `frames.0`; fora do perfil não aparece e o POST recusa; "no lugar de X" + histórico de X; desfazer.
- [ ] QA 320/390/430; PR 3.

## Prova em produção (item 6)
- [ ] `scratchpad/qa_fluxo_ficha.py`: signup (básica) → onboarding → ficha A (≥ 6) → capturas → troca (mesmo padrão, sem máquina) → execução grava no substituto → leitura mostra o histórico do original → desfazer → apagar; o mesmo em completa; demo intacto; `/saude/` = merge.
