# Como o NutriPlan é testado hoje

Levantado do repositório. Responde uma pergunta: **como este projeto é testado
hoje?** — os comandos, as travas, onde as guardas moram e o que este ambiente
não consegue fazer.

Decidir *o que* testar para uma mudança específica é assunto do `SKILL.md`.

Se algo aqui divergir do repositório, **o repositório ganha** — e a divergência
entra na validação como achado.

---

## 1. Comandos

```bash
# Suíte completa — ~3 min
.venv/Scripts/python.exe manage.py test --noinput

# Um app, uma classe, um teste
.venv/Scripts/python.exe manage.py test workouts
.venv/Scripts/python.exe manage.py test config.tests.TouchTargetTests
.venv/Scripts/python.exe manage.py test demo.tests.DemoOnboardingTests.test_the_door_opens_without_a_session

# Migração faltando (o que o pre-commit checa)
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run --no-input
```

**Use sempre `--noinput`.** Um banco de teste órfão de execução interrompida faz
o Django *perguntar* se pode apagá-lo, e sem terminal isso morre com `EOFError`
— por um motivo que não tem nada a ver com o código. Os dois hooks já passam a
flag.

**O PostgreSQL é portátil e não sobe sozinho** depois de reiniciar a máquina
(`C:\Users\biel-\pgsql`, cluster em `C:\Users\biel-\pgdata\nutriplan`).
`scripts/start_db.ps1` liga. Sem ele, a suíte inteira falha na conexão.

---

## 2. A suíte

**692 testes** em 13 arquivos. Todos os apps do projeto têm cobertura.

| Arquivo | Testes | Assunto |
|---|---|---|
| `plans/tests.py` | 167 | Motor nutricional, cardápio, marcação, hidratação |
| `workouts/tests.py` | 163 | Ficha, cargas, drawer, sanfonas, exportação |
| `config/tests.py` | 82 | Deploy, contraste, alvo de toque, design system, movimento |
| `push/tests.py` | 63 | Service worker, manifesto, notificações, convite |
| `accounts/tests.py` | 55 | Usuário, perfil, onboarding |
| `demo/tests.py` | 53 | Modo demo inteiro |
| `plans/test_streaks.py` | 25 | Ofensiva |
| `supplements/tests.py` | 25 | Catálogo e checklist |
| `accounts/test_sync.py` | 15 | Fila offline no servidor |
| `push/test_offline.py` | 15 | Service worker e privacidade |
| `plans/test_stress.py` | 11 | Interface sob um ano de dados |
| `plans/test_weight_trend.py` | 11 | Média de peso e recalibração |
| `catalog/tests.py` | 7 | Alimentos e receitas |

**`forja/` tem testes próprios e NÃO fazem parte desta suíte** — é outro projeto
que mora na mesma pasta, fora do `INSTALLED_APPS`. Contar os arquivos com `find`
dá ~1400; o número do NutriPlan é 692.

Convenção: o nome do teste descreve o **comportamento**, e a docstring diz **por
que** aquilo importa, de preferência com o caso real que o motivou. Vale seguir
ao escrever teste novo — é o que faz a suíte se explicar sozinha.

---

## 3. Hooks de git

`core.hooksPath = scripts/hooks`. Instalação: `bash scripts/instalar_hooks.sh`.

**`pre-commit`** — rápido de propósito (~10 s). Roda três conferências:

1. migrações pendentes (`makemigrations --check`);
2. seis classes de estilo e toque:
   `config.tests.TouchTargetTests`, `ContrastTests`, `MotionTests`,
   `PillContrastTests`, `CustomPropertyTests`, `workouts.tests.ImpeccableStyleTests`;
3. **pasta de outro projeto no commit** — lista branca em `CONHECIDAS`; qualquer
   pasta nova no primeiro nível precisa entrar nela de propósito. Já barrou
   `.claude` uma vez, com razão.

*Nota:* `VisualRefinementTests`, `DesignSystemTests`, `TouchFeedbackTests`,
`GymReadyTests` e `HasSelectorTests` **não** estão na lista rápida, embora
protejam o mesmo tipo de coisa. Mudança de CSS pode passar no commit e só
falhar no push.

**`pre-push`** — a suíte inteira. É o último ponto barato: `git push` dispara o
deploy no Render.

Nenhum dos dois deve ser contornado com `--no-verify`.

---

## 4. Classes de regressão, por assunto

Procure aqui antes de escrever teste novo.

**Estilo, toque e movimento** (`config/tests.py`)
`TouchTargetTests` (44px altura **e** largura, com lista explícita de seletores)
· `ContrastTests` (WCAG recalculado dos tokens, inclusive fundos tingidos) ·
`PillContrastTests` (texto de pílula sobre a própria tinta) ·
`DayColourContrastTests` · `DesignSystemTests` · `MotionTests` (animação que
carrega informação + saída para movimento reduzido) · `TouchFeedbackTests` ·
`HasSelectorTests` (`:has()` não decide layout) · `VisualRefinementTests` ·
`GymReadyTests` · `MarcaTests` · `CustomPropertyTests` (variável usada e nunca
declarada).

**Produção e deploy** (`config/tests.py`)
`DeployFilesTests` · `ProductionBehaviourTests` · `HealthTests` ·
`BuildScriptTests` (todos os seeds rodam, migrate antes deles) ·
`ResponseCompressionTests` · `SingleUserAppTests` (o módulo removido não volta).

**Treino** (`workouts/tests.py`)
`RoutineGenerationTests` · `RoutineSyncTests` · `WorkoutViewTests` ·
`LoadRecordingTests` · `RecordLoadViewTests` · `LoadInputFormatTests` (vírgula
decimal) · `LoadStepperTests` (degraus de 2,5 kg) · `RestTimerTests` ·
`RestBadgeTests` · `WeekAccordionTests` · `ExerciseAccordionTests` ·
`ExerciseDrawerTests` · `ExerciseHeaderLayoutTests` · `GymHardwareTests` ·
`HealthExportTests` (TCX) · `MuscleCoverageTests` · `SplitPreferenceTests` ·
`ImpeccableStyleTests`.

**Demo** (`demo/tests.py`)
`DemoNavegacaoTests` · `DemoSomenteLeituraTests` (nenhum POST escreve) ·
`DemoDadosTests` · `DemoSemSaidaParaLoginTests` · `DemoTelasNaoFicamVaziasTests`
· `DemoCadaRotaMostraSuaTelaTests` · `DemoNaoApodreceComOTempoTests` ·
`DemoCargasDeHojeTests` · `DemoOnboardingTests`.

**Offline e privacidade** (`push/test_offline.py`, `accounts/test_sync.py`)
`ServiceWorkerOfflineTests` · `LogoutPrivacyTests` · `QueueScopeTests` ·
`SyncedOperationTests` · `WaterReplayTests` · `SupplementReplayTests` ·
`IdempotentByNatureTests`.

---

## 5. Componentes e fluxos de alto risco

Onde um erro custa caro ou aparece tarde:

| Área | Onde mora | Por que é arriscada |
|---|---|---|
| Motor nutricional | `plans/calculations.py`, `meal_planner.py`, `services.py` | Muda o número que o app promete |
| Plano-retrato | `NutritionPlan`, `TrainingPlan` | Guardam números congelados; mexer reescreve histórico. `plan_is_current()` descarta o que não bate |
| Ficha customizada | `TrainingPlan.customized_at` | Desliga o gerador; sem isso, mudar um horário apaga o ajuste |
| Fila offline | `static/js/fila.js`, `SyncedOperation`, `op_id` | Quebra em silêncio; sintoma aparece dias depois |
| Middleware do demo | `demo/middleware.py` | Monta o app inteiro sob `/demo/`; erro alcança todas as telas |
| Autenticação e escopo | `accounts/` | Produto de uma pessoa; o módulo multiusuário foi removido de propósito |
| Geração da ficha | `workouts/services.py` | Remonta a semana inteira |

---

## 6. Offline e PWA

Cobertos pela fila: **água e marcação de refeição** — e são só esses dois.
`static/js/fila.js` tem a lista literal em `ROTAS`, e ela é a fonte.

Esta linha já listou quatro, e as duas que saíram saíram por motivos
diferentes. **Suplemento** esteve na fila de verdade — `326aaa2` a criou com a
rota dele — e saiu em `3536b61`, quando a funcionalidade inteira deixou o
produto. **Carga de série** saiu em 05/09/2026 com a funcionalidade INTACTA:
o corpo dela carrega um contador defasado que o replay usa para apagar série e
reescrever peso; ver `CAMPANHA — CARGA OFFLINE V2` no BACKLOG.

Uma versão anterior desta correção dizia que o suplemento "nunca esteve na
fila". Era falso, e o git desmente em uma linha
(`git log -S suplementos -- static/js/fila.js`). Fica registrado porque este
arquivo é lido como autoridade, e trocar uma linha velha por uma acusação
errada é pior que deixar a linha velha.

**Não** cobertos, e isso é decisão registrada no próprio `fila.js`: assistente de
treino, recalibragem de metas e geração de plano. As três leem estado do servidor
para decidir, e enfileirá-las produziria decisão tomada sobre dado velho.

`SyncedOperation` guarda `op_id` com unicidade `(user, op_id)` e validade de 30
dias. **Água SOMA e suplemento ALTERNA** — as duas precisam de `op_id`. Marcação
de refeição e carga usam `update_or_create` e já são idempotentes por natureza;
trocá-las por contador quebra a fila em silêncio.

Background Sync existe no Chrome e **não existe no Safari do iPhone**. O
mecanismo principal é o evento `online` mais uma drenagem na abertura da página.

Arquivos: `static/js/fila.js`, `static/js/pwa.js`, `templates/pwa/sw.js`,
`templates/pwa/offline.html`.

---

## 7. Demo

`demo/middleware.py` monta a aplicação inteira sob `/demo/`, sem telas
duplicadas: tira o prefixo do caminho, liga `set_script_prefix("/demo/")` para
os `reverse()` voltarem com prefixo, e troca `request.user`.

- **Somente leitura**: métodos fora de `GET/HEAD/OPTIONS` são recusados antes da
  view, com `demo/acao_desativada.html`.
- **Duas personas**: Carlos (`carlos.demo@nutriplan.invalid`, onboarding
  concluído) e Ana (`ana.demo@nutriplan.invalid`, parada no último passo do
  wizard). A escolha é por caminho: rota sob `/conta/onboarding/` responde como
  Ana, o resto como Carlos.
- **Apelidos**: `/demo/hoje/` → painel do dia; `/demo/comecar/` → passo 1 do
  onboarding real.
- **Não apodrece**: quando a data vira, `_manter_o_dia_vivo` chama
  `seed_demo --somente-o-dia`, que refaz refeições, água **e cargas**.
- Seed: `manage.py seed_demo` (`--refazer`, `--somente-o-dia`), chamado pelo
  `scripts/build.sh` a cada deploy.

Rotas para conferir: `/demo/`, `/demo/comecar/`, `/demo/hoje/`, `/demo/treino/`,
`/demo/historico/`, `/demo/suplementos/`, `/demo/conta/perfil/`.

---

## 8. Rotas principais

```
/                          painel do dia          /historico/     /lista-de-compras/
/refeicao/<id>/marcar/     /refeicao/<id>/desfazer/
/recalcular/               /recalibrar/           /agua/
/conta/cadastro/ entrar/ sair/ perfil/ onboarding/ onboarding/<step>/
/treino/                   /treino/exercicio/<id>/carga/    /treino/exportar/saude.tcx
/suplementos/              /push/inscrever/       /push/cancelar/
/sw.js   /manifest.webmanifest   /offline/   /saude/   /admin/   /demo/
```

`/saude/` é o health check — é o que confirma que o deploy subiu.

---

## 9. Navegador disponível

O painel do navegador da sessão (`Claude_Browser`) roda um navegador de verdade:
navegar, ler o DOM como árvore de acessibilidade, clicar, digitar, preencher
formulário, ler console e rede, executar JavaScript na página, redimensionar
(inclusive emular mobile e tema claro/escuro) e capturar tela.

Duas armadilhas observadas neste projeto:

- **Captura pode falhar** quando o painel não está visível (*"the Browser pane is
  not displayed"*). Medição por `javascript_tool` e `read_page` continua
  funcionando — e para alvo de toque e estouro de largura ela é mais precisa que
  olhar a imagem.
- **`toggle` de `<details>` é assíncrono.** Medir logo depois de `.click()` lê o
  estado anterior. Espere um tique antes de ler.

Servir a página: `preview_start` com o nome do `.claude/launch.json`
(`nutriplan`, porta 8000) ou com uma URL. A produção também serve para medir —
`https://nutriplan-xxfn.onrender.com`, com `/demo/` acessível sem login.

---

## 10. Limitações deste ambiente

- **Node/npm/npx não estão instalados.** Sem Playwright, sem Lighthouse, sem
  qualquer ferramenta que dependa de `npx`.
- **Sem analytics.** O produto não coleta uso; não há como medir frequência real,
  abandono ou funil.
- **PWA não escreve no Apple Saúde nem no Health Connect** — não existe API web.
  `workouts/health_export.py` gera TCX para importar à mão.
- **Postgres portátil**, que não sobe sozinho depois de reiniciar.
- **Duas execuções simultâneas de `manage.py test` se derrubam.** As duas usam
  `test_nutriplan`; uma apaga o banco da outra no meio, e o sintoma é
  `database "test_nutriplan" does not exist` em classes aleatórias. Antes de
  culpar o código, confira se há outro `manage.py test` rodando. Para isolar:
  um settings que só troque `DATABASES["default"]["TEST"] = {"NAME": "outro"}`.
- **O banco gratuito do Render é apagado por volta de 23/09/2026.**

---

## 11. Deploy

`git push` dispara o Render. `scripts/build.sh` roda, com `errexit`:

```
pip install → collectstatic → migrate → seed_catalog → seed_workouts
→ seed_supplements → seed_demo
```

Build que passa prova que a migração rodou. Confirmação em `/saude/`.

*Nota:* rodar `build.sh` inteiro no Windows falha no `pip install --upgrade pip`
— restrição do próprio pip, não do projeto. Os passos seguintes rodam
normalmente um a um.
