---
name: sabotagem-e-controle-positivo
description: teste que importa só vale depois de visto falhar; e sempre com controle positivo
metadata:
  type: feedback
---
Para cada teste que importa, escreva a sabotagem que deveria derrubá-lo e
rode; sem vermelho, o teste mede outra coisa. Inclua controle positivo (o
que deveria funcionar continua funcionando). Formas que já passaram verdes
aqui: a asserção casa com OUTRO lugar da página (`href="/ajuda/"` do Perfil;
"Registrar A" dentro de `aria-label="Registrar Arroz…"` — ancore com os
sinais de tag); `assertLogs` força o nível e esconde logger mudo em
produção; string comparada com objeto `Permission`. Operacional: COMMITE
antes de sabotar (`git checkout -- arquivo` apaga a edição não commitada —
aconteceu duas vezes); catraca de design é IGUALDADE (migrou valor cru para
token, aperte o teto no mesmo commit); `tornar_hoje` escolhe a letra e não
fabrica `ExerciseLog`; o gitleaks lê senha de teste em dicionário como
`generic-api-key` — falso positivo vai para o allowlist, nunca `--no-verify`.

Fonte: memórias antigas `teste-que-passa-pelo-motivo-errado`, `nutriplan-card-de-refeicao`, `nutriplan-auditoria-20260920`, `nutriplan-redesenho-do-treino`, `nutriplan-sequencia-por-presenca`, `nutriplan-legais-consentimento`
