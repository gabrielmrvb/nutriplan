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

PASTA="${1:-.}"
MINIMO_BYTES=1024

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERRO: defina DATABASE_URL no ambiente (não como argumento)." >&2
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

mkdir -p "$PASTA"
CARIMBO="$(date +%Y%m%d-%H%M%S)"
ARQUIVO="$PASTA/nutriplan-$CARIMBO.dump"

echo "1/4 despejando..."
# -Fc: formato custom, que o pg_restore lê seletivamente e comprime sozinho.
# --no-owner e --no-privileges: o dump precisa restaurar num banco cujo dono
# tem outro nome — que é exatamente o caso de um cluster descartável de teste,
# e do banco novo no dia em que este for trocado.
pg_dump "$DATABASE_URL" -Fc --no-owner --no-privileges -f "$ARQUIVO"

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
