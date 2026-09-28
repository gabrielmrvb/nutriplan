# Pente-fino de qualidade — 28/09/2026

Sete frentes, ordem do dono: 3 → 1 → 5 → 6 → 2 → 7. O #162 não estava em `main` no início, então as ondas 1 e 3 esperam e a missão começou pela 5. Harness: o da auditoria visual (`notas.py` + `comparar.py`), servidor local 8218, banco `nutriplan_qualidade`, três personas pelo cadastro público (academia dia 12 em descanso, corredora dia 1, casa dia 1 em dia de treino), 390 escuro/claro e 1280.

## Onda 5 — estados

1. **Medido antes** [OBSERVADA], em 159 capturas: a corredora via "Treino · Sem ficha · Montar treino" na Home, "0 dias de treino · 0 recordes" nas Conquistas, com o vazio mandando para "Ver o treino" e só metas de treino em "Próximas", e no Progresso o tile e a seção de treino com "Abrir o treino de hoje".
2. **Dia 1, Hidratação:** "Últimos 7 dias" listava 22/09 a 27/09, antes de a conta existir, e cobrava "0/7". Agora a janela começa na conta, e no dia 1 o bloco não aparece.
3. **Dia 1, Progresso:** "Treinos 0 de 1 ↓" às 14h, para um treino que ainda podia acontecer. Agora hoje só conta quando já tem série, e o tile diz "Hoje é dia de treino."
4. **#138 (decisão do dono):** a Home de quem não faz musculação traz Alimentação e Corrida, sem cartão de treino. O Progresso troca o treino pela corrida. As Conquistas de quem não faz musculação mostram só metas de corrida e de alimentação. As regras novas (primeira corrida, 5/10/25 corridas, primeira refeição, 7/30 dias registrando) valem para todos; as de corrida aparecem só para quem corre. Registrado no `CLAUDE.md`.
5. **Custo:** "tem ficha?", corridas e dias com refeição saem numa consulta só. Progresso e Conquistas continuam no mesmo número de consultas (`plans.test_stress` verde).
6. **Provas:** 4 arquivos de teste novos, vermelhos antes. Sabotagem 7/7 vermelha. `plans` + `achievements`: 1.077 testes OK. Na revisão adversarial por subagente, nenhum achado.
7. **Notas Ti/Es/Cc:** remedidas nas mesmas cenas; nenhuma caiu (0 pioras). Os critérios observados sobem em Ev (estado vazio) na Home, nas Conquistas e no Progresso da corredora e na Hidratação do dia 1.
8. **Ficou de fora, com dono:** `/treino/` da corredora (hoje só texto e um link; o botão de ativar a musculação deveria ser o principal) e "Exercícios que já fiz" para quem não faz musculação. As duas telas estão em `templates/workouts/`, com a sessão da Parte 2 no ledger. Voltam no fim.
9. **Dia de descanso** (academia, dia 12): Home ("Descanso · Próximo: amanhã, A") e painel do Treino já davam o próximo passo. Nada a mudar.
10. **Capturas:** antes/depois no scratchpad da sessão (`av2/out-onda5-antes`, `out-onda5-depois`).
