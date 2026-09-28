# Missão-mãe: fechar dívida e preparar para cobrar (27–28/09/2026)

**Entrou (em produção)**, com como desligar cada peça:
- **#167 — banco de teste por branch e vigia do runner.** Desligar: `NUTRIPLAN_BANCO_DE_TESTE=test_nutriplan`.
- **#166, #174, #179 — Sentry, projeto `nutriplan` na org `nutriplan-d0`.** Não manda cabeçalho nem IP; a prova final é o NUTRIPLAN-3. Desligar: apagar `SENTRY_DSN` no Render e remover a rota `/tarefas/erro-controlado/`.
- **#166 — backup diário cifrado.** Provado no run 36321961720, restaurado com 61 tabelas e 16.343 linhas iguais às de produção. Desligar: comentar o `schedule` do `backup.yml`.
- **#168 e #178 — regra do Starter e 750 h.** O lote não acorda mais o staging com a janela fechada. Desligar: reverter a ordem em `promover_lote`.
- **#173 — o ORM das quatro telas de treino foi para `workouts/telas.py`.** Faz parte do código; não se desliga.
- **#177 — um evento `treino.serie_concluida` por série.** O painel descarta a cópia gravada desde 24/09. Desligar: reverter o PR.
- **#190 — ficha única por cota.** Uma variante por letra, a regra de 16/09 invertida, corpo inteiro 1×/semana com 75 min. As 57 fichas ativas recebem a oferta "programa atualizado". Desligar: reverter o PR; fichas já montadas ficam como estão.
- **#182 — caça-bugs.** 49 achados (4 bloqueantes) em `achados/caca-bugs-20260927.md`.

**Pendente**
- **Decisões do dono:**
  - textos de LGPD (itens 3.1–3.4 do Gate 1);
  - aviso CRN/CREF;
  - os 3 pontos do #190: teste "ficha cheia", ABCDE letra E com 52 min, citação no CLAUDE.md;
  - corridas na exportação de dados;
  - tirar do `render.yaml` o banco vencido do Render.
- **Esperando a missao-b** (fora de main): services/ em `plans`, a letra errada da Home, o dia errado da fila offline, a faixa offline que cobre o botão, a linha "até 60 min" da Alimentação.
- **Agora destravados pelo #190:** os achados do caça-bugs em `workouts/` (sequência que zera depois da remontagem, série extra com duas abas, "0 kg", recorde da barra assistida).
- **Mão do dono:**
  - guardar a senha do backup no gerenciador;
  - apagar o NUTRIPLAN-2 no Sentry (sobra do diagnóstico).
