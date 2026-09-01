#!/usr/bin/env bash
# Copia um banco para outro e PROVA que a cópia bateu, tabela por tabela.
#
# Feito para a janela de cutover, e o desenho todo serve a uma coisa: encurtar
# o tempo entre "tirei o dump" e "o app está escrevendo no destino". Tudo que
# for escrito na origem depois do dump se perde na troca — então dump, restore
# e conferência acontecem no mesmo comando, e não em três sessões separadas
# com horas entre elas.
#
# Para 12 MB isso é questão de segundos. Não existe motivo para inventar
# replicação lógica aqui.
#
# Uso:
#   ORIGEM_URL='postgres://...' DESTINO_URL='postgres://...' scripts/migrar.sh
#
# As duas URLs entram por ambiente, nunca por argumento, e nada aqui as
# imprime — nem em mensagem de erro.
set -o errexit
set -o pipefail
set -o nounset

: "${ORIGEM_URL:?defina ORIGEM_URL no ambiente}"
: "${DESTINO_URL:?defina DESTINO_URL no ambiente}"

TRABALHO="$(mktemp -d)"
ARQUIVO="$TRABALHO/migracao.dump"
trap 'rm -rf "$TRABALHO"' EXIT

contar () {
  # Contagem REAL, não estimativa: `n_live_tup` do pg_stat depende de ANALYZE
  # e num banco recém-restaurado ainda é zero, o que faria a comparação passar
  # comparando nada com nada.
  psql -d "$1" -tAF, -v ON_ERROR_STOP=1 -c "
    SELECT string_agg(linha, E'\n' ORDER BY linha) FROM (
      SELECT format('%s=%s', c.relname,
                    (xpath('/row/c/text()',
                     query_to_xml(format('SELECT count(*) AS c FROM %I.%I',
                                         n.nspname, c.relname),
                                  false, true, '')))[1]::text::bigint) AS linha
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE c.relkind = 'r' AND n.nspname = 'public'
    ) t;"
}

echo "1/5 contando a ORIGEM..."
ANTES="$(contar "$ORIGEM_URL")"
echo "     $(printf '%s' "$ANTES" | grep -c .) tabelas"

echo "2/5 despejando..."
pg_dump -d "$ORIGEM_URL" -Fc --no-owner --no-privileges -f "$ARQUIVO"
TAMANHO="$(wc -c < "$ARQUIVO" | tr -d ' ')"
if [ "$TAMANHO" -lt 1024 ]; then
  echo "ERRO: dump de $TAMANHO bytes. Cliente pg_dump mais velho que o" >&2
  echo "      servidor produz exatamente isso. Use os binários do 18." >&2
  exit 1
fi
echo "     $TAMANHO bytes"

echo "3/5 restaurando no DESTINO..."
# Sem --clean e sem --create: o destino é um banco novo e vazio, criado pelo
# provedor. `--exit-on-error` porque restauração meio-feita é pior que
# restauração que falhou: ela parece ter dado certo.
pg_restore --no-owner --no-privileges --exit-on-error -d "$DESTINO_URL" "$ARQUIVO"

echo "4/5 contando o DESTINO..."
DEPOIS="$(contar "$DESTINO_URL")"

echo "5/5 comparando tabela por tabela..."
if [ "$ANTES" = "$DEPOIS" ]; then
  printf '%s\n' "$ANTES" | sed 's/^/     /'
  echo ""
  echo "MIGRACAO OK — todas as tabelas bateram."
  echo "Agora troque a DATABASE_URL e reinicie o serviço."
else
  echo "DIFERENCA ENTRE ORIGEM E DESTINO:" >&2
  diff <(printf '%s\n' "$ANTES") <(printf '%s\n' "$DEPOIS") >&2 || true
  echo "" >&2
  echo "NAO troque a DATABASE_URL. O destino não é cópia fiel da origem." >&2
  exit 1
fi
