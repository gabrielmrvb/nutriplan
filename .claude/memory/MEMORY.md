# Índice da memória do NutriPlan

Regras em [INSTRUCTIONS.md](INSTRUCTIONS.md). Teto: 130 linhas não em branco.

- [Direção visual NERVURA](visual-nervura.md) — DESIGN.md é a verdade; a referência da skill de UX tem tokens velhos
- [Ficha única, troca por exercício](ficha-unica-troca.md) — a tela mostra uma; o motor gera duas e o gate proíbe perder a segunda
- [Equipamento substitui, não filtra](equipamento-substitui.md) — mesmo padrão e grupo, mesma dose; "FILTRA" no TREINO.md engana
- [Veracidade](veracidade.md) — nada inventado; texto só afirma o que aconteceu; sem dado, pergunte ou diga
- [Infra gratuita](infra-gratuita.md) — todo gasto novo é condição de parada; prazo do Neon free não verificado
- [Autonomia: as quatro condições](autonomia-4-condicoes.md) — fora delas, decida e registre
- [Relógio congelado nos testes](relogio-congelado.md) — quarta 16/09/2026 12:00; date.today/now proibidos
- [JavaScript mora em pwa.js](js-em-pwa-js.md) — app.js não é servido
- [:has() proibido](sem-has.md) — classe escrita pelo servidor
- [Comentário de template](comentario-template.md) — `{# #}` é uma linha só; multilinha é `{% comment %}`
- [Cache do perfil no mixin](cache-perfil-mixin.md) — gravar por outra instância faz o motor ler o velho
- [Staging e promoção](staging-promocao.md) — merge só chega ao staging; produção em lote provado, 1×/hora
- [/saude/vivo/ para monitor](saude-vivo.md) — /saude/ acorda o Neon e estoura a cota
- [SMTP na 2525](smtp-2525.md) — Render free bloqueia 25/465/587; Django engole a falha
- [Conta de QA descartável](conta-qa-descartavel.md) — do agente, pelo signup, apagada pela tela
- [agent-browser e 127.0.0.1](agent-browser-127.md) — localhost resolve ::1 e o runserver não escuta
