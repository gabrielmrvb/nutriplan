#!/usr/bin/env bash
# Restaura um dump num banco DESCARTÁVEL e verifica se o que voltou presta.
#
# Um dump que ninguém restaurou não é um backup — é a esperança de um. Este
# script existe para transformar essa esperança em fato, e o custo de rodá-lo é
# de segundos: o banco do NutriPlan tem 12 MB, e a restauração completa levou
# 0,3 s na primeira medição.
#
# Uso:
#   scripts/restaurar.sh caminho/do.dump [url-do-servidor-alvo]
#
# O alvo padrão é um Postgres local. Restaurar por cima de produção apagaria o
# banco de verdade, então o script SE RECUSA a apontar para qualquer host que
# não seja local — a menos que alguém escreva FORCA=1, que é longo o bastante
# para ninguém digitar por engano.
set -o errexit
set -o pipefail
set -o nounset

ARQUIVO="${1:-}"
ALVO="${2:-postgres://postgres@localhost:5432/postgres}"
BANCO="nutriplan_drill"

if [ -z "$ARQUIVO" ] || [ ! -f "$ARQUIVO" ]; then
  echo "uso: scripts/restaurar.sh caminho/do.dump [url-do-servidor-alvo]" >&2
  exit 1
fi

case "$ALVO" in
  *@localhost*|*@127.0.0.1*|*//localhost*|*//127.0.0.1*) ;;
  *)
    if [ "${FORCA:-}" != "1" ]; then
      echo "ERRO: o alvo não é local. Restaurar aqui APAGARIA o banco de" >&2
      echo "      destino. Se é mesmo isso que você quer, use FORCA=1." >&2
      exit 1
    fi
    ;;
esac

# ---------------------------------------------------------------- 1. o arquivo
echo "1/5 conferindo o arquivo..."
SOMAS="$(dirname "$ARQUIVO")/SHA256SUMS"
if [ -f "$SOMAS" ]; then
  # `grep -F` no nome inteiro e `awk` no primeiro campo, de propósito: o
  # sha256sum do Git para Windows marca modo binário com um asterisco antes do
  # nome, e um padrão ancorado em espaço não casa com essas linhas. O efeito
  # seria o pior possível — a verificação não falharia, ela sairia VAZIA, e o
  # script seguiria dizendo que estava tudo bem sem ter comparado nada.
  ESPERADA="$(grep -F "$(basename "$ARQUIVO")" "$SOMAS" | tail -1 | awk '{print $1}')"
  ATUAL="$(sha256sum "$ARQUIVO" | awk '{print $1}')"
  if [ -z "$ESPERADA" ]; then
    echo "     AVISO: este dump não está no SHA256SUMS; nada foi conferido." >&2
  elif [ "$ESPERADA" != "$ATUAL" ]; then
    echo "ERRO: sha256 não confere — o arquivo mudou depois do backup." >&2
    exit 1
  else
    echo "     sha256 confere"
  fi
else
  echo "     (sem SHA256SUMS ao lado; seguindo sem conferir)"
fi

# ------------------------------------------------------------- 2. restauração
echo "2/5 restaurando em $BANCO..."
psql "$ALVO" -q -c "DROP DATABASE IF EXISTS $BANCO;"
psql "$ALVO" -q -c "CREATE DATABASE $BANCO;"
DESTINO="${ALVO%/*}/$BANCO"
pg_restore --no-owner --no-privileges -d "$DESTINO" "$ARQUIVO"

# ------------------------------------------------------------------ 3. schema
echo "3/5 conferindo o schema..."
psql "$DESTINO" -q -c "
  SELECT
    (SELECT count(*) FROM information_schema.tables
      WHERE table_schema = 'public') AS tabelas,
    (SELECT count(*) FROM pg_indexes WHERE schemaname = 'public') AS indices,
    (SELECT count(*) FROM django_migrations) AS migrations,
    pg_size_pretty(pg_database_size(current_database())) AS tamanho;
"

# --------------------------------------------------------------- 4. contagens
# CONTAGEM, e só. Nenhuma linha é selecionada: este banco tem e-mail, peso
# corporal e histórico de treino de gente real, e um drill de restauração não
# precisa ver nada disso para provar que o dado voltou.
echo "4/5 contando linhas por tabela (sem ler conteúdo)..."
psql "$DESTINO" -q -c "
  SELECT relname AS tabela, n_live_tup AS linhas
  FROM pg_stat_user_tables
  WHERE n_live_tup > 0
  ORDER BY n_live_tup DESC, relname;
" 2>/dev/null || echo "     (estatísticas ainda não coletadas; rode ANALYZE)"

# ------------------------------------------------------------- 5. integridade
# Varre TODA chave estrangeira do banco, e não uma lista escrita à mão: lista
# escrita à mão envelhece na primeira migration que ninguém lembrou de refletir
# aqui, e passa a dar "tudo certo" sobre as tabelas de ontem.
echo "5/5 procurando linha órfã em toda chave estrangeira..."
psql "$DESTINO" -q -v ON_ERROR_STOP=1 -c "
DO \$\$
DECLARE r record; n bigint; total bigint := 0;
BEGIN
  FOR r IN
    SELECT cl.relname AS tabela, att.attname AS coluna,
           rcl.relname AS destino, ratt.attname AS destino_col
      FROM pg_constraint con
      JOIN pg_class cl ON cl.oid = con.conrelid
      JOIN pg_class rcl ON rcl.oid = con.confrelid
      JOIN pg_attribute att
        ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
      JOIN pg_attribute ratt
        ON ratt.attrelid = con.confrelid AND ratt.attnum = con.confkey[1]
     WHERE con.contype = 'f' AND array_length(con.conkey, 1) = 1
  LOOP
    EXECUTE format(
      'SELECT count(*) FROM %I t LEFT JOIN %I d ON t.%I = d.%I
        WHERE t.%I IS NOT NULL AND d.%I IS NULL',
      r.tabela, r.destino, r.coluna, r.destino_col, r.coluna, r.destino_col
    ) INTO n;
    IF n > 0 THEN
      RAISE WARNING 'ORFAS em %.% -> %: % linhas',
        r.tabela, r.coluna, r.destino, n;
      total := total + n;
    END IF;
  END LOOP;
  IF total > 0 THEN
    RAISE EXCEPTION 'integridade quebrada: % linhas orfas', total;
  END IF;
  RAISE NOTICE 'integridade referencial: nenhuma linha orfa';
END \$\$;
"

echo ""
echo "RESTORE OK — o backup volta."
echo "Apagando o banco de teste."
psql "$ALVO" -q -c "DROP DATABASE IF EXISTS $BANCO;"
