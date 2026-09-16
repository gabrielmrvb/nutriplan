# Lote 1 da avaliação de 16/09/2026 — plano de execução

Fonte: `scratchpad/avaliacao/2026-09-16/RELATORIO.md` (sessão de avaliação;
capturas em `capturas/`). Só BUGS; nenhuma decisão de produto. Um commit por
item, na ordem pedida pelo dono. Protocolo: `nutriplan-missao` — teste
vermelho → correção → captura na mesma tela/viewport da avaliação → verde →
sabotagem → suíte → push → deploy provado (`/saude/` devolve `commit`) →
QA em produção com conta descartável → tabela antes/depois.

## Objetivo verificável

Cada item abaixo tem (a) um teste que reproduz o defeito e fica vermelho
antes da correção, (b) a correção, (c) uma captura em produção na mesma
tela e viewport da avaliação mostrando o defeito ausente. O relatório final
lista item / captura de antes / captura de depois.

## Fatos (lidos em 16/09 11:05)

- HEAD = `origin/main` = `1d99450`; produção responde `commit 1d99450`
  (`/saude/`), catálogo 64/64.
- Duas outras sessões editam ESTE worktree agora: "nutriplan - treino"
  (B9 "Principal": `_item_da_ficha.html`, `workouts/services.py`,
  `workouts/views.py`, `test_fluxo_do_treino.py`, não commitado) e
  "nutriplan design". Mensagens de coordenação enviadas às 11:07.
- `test_nutriplan` está em uso por outra execução; esta missão roda testes em
  `test_nutriplan_lote1` (`DATABASE_URL=...nutriplan_lote1`, banco criado
  vazio às 11:10). O `RunnerUnico` só recusa clones numéricos, então os dois
  não disputam.
- Hooks instalados (`core.hooksPath = scripts/hooks`); o pre-commit roda
  `makemigrations --check` e seis classes de estilo — com a `DATABASE_URL`
  exportada ele usa o banco isolado.

## Propriedade de arquivos

| item | arquivos | colide com outra sessão? |
|---|---|---|
| B13 | `templates/accounts/email_senha.html`, `accounts/tests.py` | não |
| B7 | `.env.example`/`render.yaml` (doc), chave gerada fora do repo | não |
| B1 | `templates/accounts/login.html`, `accounts/views.py` (mixins), `config/admin_entrada.py` | não |
| B2/B3/B4 | `accounts/forms.py` | não |
| B5+B35 | `workouts/views.py` (ConcluirSerieView), `achievements/views.py`, `achievements/services.py` | **sim** (views.py) — esperar commit do treino |
| B6 | `templates/pwa/sw.js`, `templates/pwa/offline.html`, `static/js/pwa.js`, `push/` | não |
| B8 | `workouts/views.py` (FichaDaSessaoView), `templates/workouts/ficha.html` | **sim** — esperar |
| B10 | `templates/partials/field.html` | não |
| B23–B25/B33 | `static/css/app.css` (:513-516, `.data-list`), `templates/accounts/profile.html` | **CSS: confirmar com design** |
| B26 | `app.css` (`.hero-macros__meta`) | CSS |
| B28 | `templates/workouts/agora.html`, `app.css` | treino + CSS |
| B32 | `app.css` (`.registro--agora`), `agora.html` | treino + CSS |
| U28 | `app.css` (bloco escuro / `.btn--quiet`) | CSS |
| D4 | `workouts/` (views, template do painel/ficha), `accounts/models.py`? | **sim** — por último |
| B11/U7 | `static/js/pwa.js`, `templates/plans/hydration.html`, `agora.html` | treino (agora.html) |

Ordem de execução: os "não" primeiro (B13, B7, B1, B2/B3/B4, B6, B10), depois
os que dependem do commit da sessão de treino e da resposta da de design.

## Reversível / irreversível

Tudo é código (reversível por revert). B7 cria uma chave VAPID: gerar fora do
repositório, nunca commitar a privada. Nada de migration prevista (D4 pode
precisar — decidir ao chegar; hoje `Profile.duracao_treino` já existe).

## Critérios de parada humana

Acesso ao painel do Render para a chave VAPID (B7) — se não houver, entregar a
chave pronta e o passo. Conflito de arquivo com outra sessão que não responder.

## Checkpoints

- [ ] plano commitado
- [ ] B13 · [ ] B7 · [ ] B1 · [ ] B2/B3/B4 · [ ] B5+B35 · [ ] B6 · [ ] B8 ·
  [ ] B10 · [ ] B23–B25/B33 · [ ] B26 · [ ] B28 · [ ] B32 · [ ] U28 · [ ] D4 ·
  [ ] B11/U7
- [ ] sabotagem por item · [ ] suíte completa · [ ] push · [ ] deploy provado ·
  [ ] QA em produção · [ ] relatório antes/depois
