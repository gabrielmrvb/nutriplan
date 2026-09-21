# Briefs de pesquisa — 13 e 14/09/2026

Três auditorias independentes, cruzadas depois no
[plano mestre](../superpowers/plans/2026-09-14-plano-mestre.md). Cada brief
classifica os achados em A (requisito já decidido), B (evidência forte —
implementar com autonomia), C (decisão de produto que só o dono toma),
D (refutado, não volta) e E (lacuna real, declarada).

| brief | arquivo | o que cobre |
|---|---|---|
| Treino v2 | [`2026-09-13-treino-v2.md`](2026-09-13-treino-v2.md) | prescrição, ficha, vídeo, execução, registro, progressão, adaptação, equipamento |
| UX / onboarding / interação | [`../ux-audit/ux-master-brief.md`](../ux-audit/ux-master-brief.md) | 16 seções, P0–P3, screenshots ao lado em `../ux-audit/screenshots/` |
| Design visual | [`2026-09-14-design.md`](2026-09-14-design.md) | auditoria de telas, três direções, tokens, componentes, roadmap |

Anexos do brief de design: [`design/direcao-c-mesa-e-ferro.md`](design/direcao-c-mesa-e-ferro.md)
(a direção escolhida) e [`design/juiz2-veredito.md`](design/juiz2-veredito.md)
(o segundo juiz, com a medição da Home). As capturas que o brief de design
cita em `shots/…` somam 14 MB e ficam FORA do repositório (`artifacts/design-audit/shots/`
na máquina de quem auditou); o texto se sustenta sem elas.

Referências geradas no Claude Design em 16/09/2026 e a escolha do dono em
17/09: [`design/DIRECAO-ESCOLHIDA.md`](design/DIRECAO-ESCOLHIDA.md) —
**NERVURA · ANDAIME** (Direção 1), por veto do dono sobre as capturas; a
pontuação de 16/09 que dava a CORTE ficou como histórico — e, a partir
dela, o [`design/DESIGN.md`](design/DESIGN.md) reescrito; as sete telas do
sistema principal a 390 px no tema padrão, capturadas do app com a NERVURA
implementada, em
[`design/referencias/claude-design/`](design/referencias/claude-design/), e
as três direções lado a lado em `design/referencias/direcoes/`. O export inteiro
— o design system fiel à Mesa & Ferro (166 arquivos), o projeto das seis telas
daquela rodada e o das três direções — fica em `artifacts/claude-design/`,
fora do git; o inventário está em
[`2026-09-15-chatgpt-claude-design/inventario-export.md`](2026-09-15-chatgpt-claude-design/inventario-export.md)
e o que o Claude Design propôs e não entrou em
[`2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md`](2026-09-15-chatgpt-claude-design/proposto-nao-adotado.md)).
Spec e handoff: [`2026-09-15-chatgpt-claude-design/`](2026-09-15-chatgpt-claude-design/README.md).

Decisões C tomadas pelo dono em 14/09/2026: direção visual "Mesa & Ferro"
corrigida; Home com a refeição da vez aberta e as demais colapsadas;
onboarding em três telas com personalização progressiva.
