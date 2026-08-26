#!/usr/bin/env bash
# Liga os hooks versionados ao .git/hooks.
#
# O .git/hooks não é versionado, então os hooks moram em scripts/hooks e este
# comando os aponta. `core.hooksPath` em vez de cópia: assim editar o hook no
# repositório vale imediatamente, sem reinstalar.
set -o errexit
git config core.hooksPath scripts/hooks
chmod +x scripts/hooks/* 2>/dev/null || true
echo "✓ hooks ligados em scripts/hooks"
echo "  commit: migrações, alvos de toque e regras de estilo (~10s)"
echo "  push:   suíte completa"
