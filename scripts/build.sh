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
#   4. seed — os tres comandos são idempotentes: no primeiro deploy populam o
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

# Falha fechado: com `errexit`, um erro aqui derruba o build ANTES de o app
# subir. O que se verifica e a configuracao de e-mail de producao — sem ela, a
# recuperacao de senha escreveria links validos no log da plataforma.
#
# DEPOIS do collectstatic, e nao antes: `check` importa a URLconf, e
# `config/urls.py` resolve `static()` em tempo de import para o redirecionamento
# do favicon. Com DEBUG desligado isso passa pelo storage com manifesto, que so
# existe depois do collectstatic — a verificacao rodando primeiro derrubava o
# build com "Missing staticfiles manifest entry", que nao tem nada a ver com o
# que ela veio verificar. Continua fechando o portao: nada sobe se ela falhar.
python manage.py check --deploy --fail-level ERROR
python manage.py migrate --no-input

# Os papéis administrativos, reconciliados com o que o código declara. Sem
# isto, `accounts/papeis.py` é documentação: tirar uma permissão de lá não a
# tira de ninguém, porque o grupo no banco guarda o que recebeu da última vez
# que alguém rodou o bootstrap. Idempotente, e DEPOIS do migrate porque
# resolve permissão contra os ContentTypes que a migração acabou de criar.
python manage.py sincronizar_papeis

python manage.py seed_catalog
python manage.py seed_workouts
# O usuário de demonstração, para /demo/ subir pronto. Depois dos outros seeds
# porque ele MONTA um plano e uma ficha com o motor de verdade, e o motor
# precisa do catálogo de alimento e de exercício já no banco.
python manage.py seed_demo
