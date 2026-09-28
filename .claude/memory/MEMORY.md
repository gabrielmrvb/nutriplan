# Índice da memória do NutriPlan

Regras em [INSTRUCTIONS.md](INSTRUCTIONS.md). Teto: 130 linhas não em branco.

- [Direção visual NERVURA](visual-nervura.md) — DESIGN.md e o `:root` são a verdade; nunca uma cópia dos valores
- [Ficha única, troca por exercício](ficha-unica-troca.md) — a tela mostra uma; o motor gera duas e o gate proíbe perder a segunda
- [Equipamento substitui, não filtra](equipamento-substitui.md) — mesmo padrão e grupo, mesma dose; filtrar abre buraco no modelo
- [Veracidade](veracidade.md) — nada inventado; texto só afirma o que aconteceu; sem dado, pergunte ou diga
- [Autonomia: as cinco paradas](autonomia-4-condicoes.md) — fora delas, decida pelo princípio escrito e registre
- [Relógio congelado nos testes](relogio-congelado.md) — quarta 16/09/2026 12:00; date.today/now proibidos
- [JavaScript mora em pwa.js](js-em-pwa-js.md) — app.js não é servido
- [:has() proibido](sem-has.md) — classe escrita pelo servidor
- [Comentário de template](comentario-template.md) — `{# #}` é uma linha só; multilinha é `{% comment %}`
- [Cache do perfil no mixin](cache-perfil-mixin.md) — gravar por outra instância faz o motor ler o velho
- [Staging e promoção](staging-promocao.md) — merge só chega ao staging; produção em lote provado, 1×/hora
- [/saude/vivo/ para monitor](saude-vivo.md) — /saude/ acorda o Neon e estoura a cota
- [SMTP na 2525](smtp-2525.md) — Render free bloqueia 25/465/587; Django engole a falha
- [Conta de QA descartável](conta-qa-descartavel.md) — do agente, pelo signup, apagada pela tela
- [Infra gratuita](infra-gratuita.md) — todo gasto novo é condição de parada; o banco do Render venceu e não é rollback
- [Evidência parcial](evidencia-parcial.md) — diga como mediu; parcial não vira total
- [Sabotagem e controle positivo](sabotagem-e-controle-positivo.md) — teste só vale visto falhar; as formas que já passaram verdes aqui
- [Log fora do namespace](log-fora-do-namespace.md) — `nutriplan.*` ou nada sai em produção
- [QA local: armadilhas](qa-local-armadilhas.md) — 127.0.0.1, porta ocupada, cache de template, agent-browser, sondas
- [Patch pelo Bash](patch-pelo-bash.md) — heredoc come `\b`, crase e aspas; escreva por arquivo
- [Banco de teste por worktree](banco-de-teste-por-worktree.md) — `nutriplan_<x>` no `.env`; `--noinput` sempre
- [Template e CSS: armadilhas](template-e-css-armadilhas.md) — vírgula no SVG, `grid-auto-rows`, separador de rodapé, seed dono
- [Aviso ao dono](aviso-ao-dono.md) — só ao fechar ou pedir decisão, e só por `fundo.py notificar`
- [Sem 3D](sem-3d.md) — cancelado pelo dono em 06/09; vídeo real na execução
- [Fila local: armadilhas](fila-local-armadilhas.md) — ledger pelo tema, posse órfã, log do Actions
- [Histórico já auditado](segredos-historico-auditado.md) — 20/09 limpo; não refaça a varredura
