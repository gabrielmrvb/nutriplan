#!/usr/bin/env bash
# Despeja o banco de produção num arquivo, e PROVA que o arquivo presta.
#
# Existe porque o plano gratuito do Render não tem backup gerenciado e o banco
# tem data para ser apagado (23/09/2026). O que não estiver aqui não volta.
#
# A prova é a parte que importa, e ela é cicatriz: a primeira execução deste
# backup em produção gerou um arquivo de ZERO BYTE e imprimiu "BACKUP OK". O
# `pg_dump` era 16.9, o servidor era 18.4, e o cliente se recusa a despejar um
# servidor mais novo — mas a versão antiga do script perguntava "o arquivo
# existe?" em vez de "o comando deu certo?". Existia. Vazio.
#
# Por isso aqui se verifica, nesta ordem e falhando em qualquer uma:
#
#   1. o código de saída do pg_dump;
#   2. o tamanho do arquivo;
#   3. se o `pg_restore --list` consegue LER o que foi escrito — que é a única
#      checagem que olha para dentro, e a que pegaria um arquivo truncado.
#
# Uso:
#   DATABASE_URL='postgres://...' scripts/backup.sh [pasta-de-destino]
#
# A URL entra por ambiente e nunca por argumento: argumento aparece em `ps`,
# no histórico do shell e em log de CI. Nada aqui imprime a URL, e o `pg_dump`
# recebe a senha por variável, não por linha de comando.
set -o errexit
set -o pipefail
set -o nounset

# `dirname "$0"` e nao um caminho fixo: o script e chamado tanto da raiz do
# repositorio quanto de um runner de CI, e um caminho fixo quebraria num dos
# dois. Falhar aqui e melhor que seguir sem a protecao.
. "$(dirname "$0")/_conexao.sh"

PASTA="${1:-.}"
MINIMO_BYTES=1024

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERRO: defina DATABASE_URL no ambiente (não como argumento)." >&2
  exit 1
fi

mkdir -p "$PASTA"

# NÃO grava dentro de um repositório, e esta é a tranca principal.
#
# O padrão desta variável é a pasta atual, e o repositório do NutriPlan é
# PÚBLICO. Rodar isto da raiz deixaria um arquivo com e-mail, peso corporal e
# histórico de treino de gente real a um `git add -A` de distância da internet.
#
# Duas vezes um `git add -A` já trouxe uma pasta inteira de outro projeto para
# dentro deste repositório — está escrito no `.gitignore`, com nome e data. A
# terceira não pode ser um banco de dados.
#
# O `.gitignore` também cobre `*.dump`, mas ele é a SEGUNDA tranca: ignorar
# protege quem não digitou `git add -f`, e não protege quem grava o dump numa
# pasta que a regra não previu. Perguntar ao próprio git se o destino está sob
# controle de versão cobre os dois casos.
#
# `PERMITIR_NO_REPO=1` existe para o caso legítimo — um checkout descartável de
# CI, onde o arquivo morre no mesmo job — e é longo o bastante para ninguém
# escrever por engano.
# `env -u` antes do git, e isto NÃO é detalhe de estilo.
#
# Dentro de um hook do git, o próprio git exporta `GIT_DIR` e companhia no
# ambiente. Com `GIT_DIR` definida, `git -C "$PASTA" rev-parse` deixa de
# responder sobre a PASTA e passa a responder sobre o repositório da variável —
# devolvendo "true" para qualquer destino, inclusive `~/backups-nutriplan`, que
# é justamente o caminho que a documentação manda usar.
#
# Medido: com `GIT_DIR` apontando para este repositório, `rev-parse` numa pasta
# temporária fora dele devolveu `true`; com `env -u GIT_DIR`, devolveu "not a
# git repository". Quem pegou foi a suíte completa, que roda DENTRO do hook de
# push: quatro testes caíram de uma vez, todos pela mesma causa, e nenhum deles
# tinha caído quando rodei o arquivo sozinho.
if [ "${PERMITIR_NO_REPO:-}" != "1" ] \
  && env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE \
         -u GIT_OBJECT_DIRECTORY -u GIT_COMMON_DIR \
     git -C "$PASTA" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERRO: '$PASTA' está dentro de um repositório git." >&2
  echo "      Um dump aqui é dado de saúde a um commit de distância de ficar" >&2
  echo "      público. Escolha uma pasta fora do repositório:" >&2
  echo "" >&2
  echo "        scripts/backup.sh ~/backups-nutriplan" >&2
  echo "" >&2
  echo "      Se for mesmo um checkout descartável, use PERMITIR_NO_REPO=1." >&2
  exit 1
fi

# `pg_dump` do cliente precisa ser >= servidor. Quando não for, ele falha com
# "server version mismatch" — e é melhor descobrir isso aqui, antes do dump,
# do que num arquivo vazio que ninguém abriu.
if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERRO: pg_dump não está no PATH." >&2
  echo "      No Windows: use os binários do PostgreSQL 18, não os do 16." >&2
  exit 1
fi

CARIMBO="$(date +%Y%m%d-%H%M%S)"
ARQUIVO="$PASTA/nutriplan-$CARIMBO.dump"

# Arquivo pela metade não sobrevive à falha, e isto é mais que arrumação.
#
# O `pg_dump` cria o arquivo ANTES de terminar de escrevê-lo. Com `errexit`,
# uma conexão recusada ou uma queda de rede no meio do despejo encerra o script
# na hora — antes da conferência de tamanho que apagaria o arquivo. O que
# sobrava era um `.dump` com carimbo de hoje e conteúdo incompleto, do lado dos
# backups bons, parecendo um deles.
#
# É a mesma família do defeito que originou este script: um arquivo que existe
# e não presta é pior que arquivo nenhum, porque ninguém procura o que parece
# estar ali. O `trap` é desarmado quando o backup prova que presta.
trap 'rm -f "$ARQUIVO"' EXIT

echo "1/4 despejando..."
# -Fc: formato custom, que o pg_restore lê seletivamente e comprime sozinho.
# --no-owner e --no-privileges: o dump precisa restaurar num banco cujo dono
# tem outro nome — que é exatamente o caso de um cluster descartável de teste,
# e do banco novo no dia em que este for trocado.
# A senha sai da URL e vai para `PGPASSWORD`, que o libpq le do ambiente.
# Medido antes da correcao, com um `pg_dump` impostor gravando o proprio argv:
# a URI inteira, com a senha, aparecia na linha de comando.
esconder_senha_da_url "$DATABASE_URL"
pg_dump -d "$URL_SEM_SENHA" -Fc --no-owner --no-privileges -f "$ARQUIVO"

echo "2/4 conferindo tamanho..."
TAMANHO="$(wc -c < "$ARQUIVO" | tr -d ' ')"
if [ "$TAMANHO" -lt "$MINIMO_BYTES" ]; then
  echo "ERRO: o dump tem $TAMANHO bytes — é o defeito do arquivo vazio." >&2
  rm -f "$ARQUIVO"
  exit 1
fi

echo "3/4 conferindo se o arquivo é legível..."
TABELAS="$(pg_restore --list "$ARQUIVO" | grep -c 'TABLE DATA' || true)"
if [ "$TABELAS" -lt 1 ]; then
  echo "ERRO: o dump não declara nenhuma tabela com dados." >&2
  exit 1
fi

# Aqui o arquivo já passou pelas três conferências: código de saída, tamanho e
# legibilidade. Só agora ele deixa de ser descartável.
trap - EXIT

echo "4/4 registrando a impressão digital..."
SOMA="$(sha256sum "$ARQUIVO" | cut -d' ' -f1)"
echo "$SOMA  $(basename "$ARQUIVO")" >> "$PASTA/SHA256SUMS"

echo ""
echo "BACKUP OK"
echo "  arquivo: $ARQUIVO"
echo "  tamanho: $TAMANHO bytes"
echo "  tabelas com dados: $TABELAS"
echo "  sha256: $SOMA"
echo ""
echo "Um dump que ninguém restaurou é uma esperança, não um backup."
echo "Rode: scripts/restaurar.sh $ARQUIVO"
