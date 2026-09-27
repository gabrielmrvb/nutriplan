---
name: segredos-historico-auditado
description: o histórico inteiro do git foi varrido atrás de segredo em 20/09/2026 e está limpo — não refaça
metadata:
  type: reference
---
Antes de o repositório virar público, os 570 commits de todas as branches
passaram por gitleaks, trufflehog e busca pelos VALORES reais: zero segredo,
nada rotacionado nem reescrito. Refazer é desperdício. Daqui para frente quem
barra é o pre-commit (gitleaks + `scripts/segredos.py`).

Fonte: CLAUDE.md "SEGREDO NÃO ENTRA EM COMMIT"; memória antiga `nutriplan-repo-publico`
