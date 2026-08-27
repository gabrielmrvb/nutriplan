#!/usr/bin/env bash
# Build de produção: instala, prepara os estáticos e o banco.
#
# É o comando que Render/Railway rodam a cada deploy, antes de trocar o
# processo no ar. A ordem importa:
#
#   1. dependências
#   2. collectstatic — com DEBUG desligado o Django usa o storage com
#      manifesto, e sem o manifesto QUALQUER template que use {% static %}
#      quebra em tempo de execução. Isto precisa acontecer antes do site subir.
#   3. migrate — o schema tem que estar pronto quando o primeiro pedido chegar.
#   4. seed — os quatro comandos são idempotentes: no primeiro deploy populam o
#      catálogo, nos seguintes só atualizam o que mudou no JSON. Sem isto o app
#      sobe sem alimento e sem exercício, e o cadastro termina numa tela vazia.
#
# `set -o errexit` é o que faz o deploy FALHAR quando um destes passos falha,
# em vez de publicar uma versão quebrada.
set -o errexit
set -o pipefail
set -o nounset

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py seed_catalog
python manage.py seed_workouts
python manage.py seed_supplements
# O usuário de demonstração, para /demo/ subir pronto. Depois dos outros seeds
# porque ele MONTA um plano e uma ficha com o motor de verdade, e o motor
# precisa do catálogo de alimento e de exercício já no banco.
python manage.py seed_demo
