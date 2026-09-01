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
python manage.py seed_catalog
python manage.py seed_workouts
# O usuário de demonstração, para /demo/ subir pronto. Depois dos outros seeds
# porque ele MONTA um plano e uma ficha com o motor de verdade, e o motor
# precisa do catálogo de alimento e de exercício já no banco.
python manage.py seed_demo

# Acesso administrativo, quando a plataforma pedir.
#
# O Render gratuito não tem shell: não existe onde rodar um comando pontual
# contra produção. Sem isto, dar acesso administrativo exigiria abrir o banco
# na mão — que é exatamente o que o painel existe para evitar.
#
# `BOOTSTRAP_ADMIN_EMAIL` vazio ou ausente não faz nada. Preenchido, o comando
# roda; e como ele é idempotente, deixar a variável no painel para sempre é
# seguro: nos deploys seguintes ele diz "nada mudou" e segue.
#
# O comando NÃO cria conta, NÃO aceita senha e NÃO marca superuser. Um e-mail
# que não existe derruba o build de propósito — a alternativa seria um typo
# virando conta administrativa fantasma, publicada sem ninguém perceber.
# BOOTSTRAP ADMINISTRATIVO — ESTE BLOCO É TEMPORÁRIO E SAI NO PRÓXIMO COMMIT.
#
# Produção subiu com `staff = 0`: `/admin/` publicado e ninguém que consiga
# entrar. O Render gratuito não tem shell, então o único lugar que roda dentro
# de produção é o build — e por isso a promoção passa por aqui UMA vez.
#
# O identificador é a chave primária, e não o e-mail nem o hash dele. Este
# repositório é público: o e-mail é dado pessoal, e o SHA-256 de um e-mail não
# é anonimização — o espaço de endereços é enumerável, e testar candidatos
# contra o digest devolve o endereço. A PK é um inteiro sequencial que não
# carrega nada sobre a pessoa.
#
# `--bootstrap` é one-shot pela TRILHA: registrada a promoção inicial, ela não
# acontece de novo, nem que a conta perca o acesso depois. Um redeploy antigo
# não pode desfazer uma decisão administrativa.
python manage.py promover_admin --id 43 --bootstrap
