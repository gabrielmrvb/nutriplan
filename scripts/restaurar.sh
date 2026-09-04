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
#   BACKUP_PASSPHRASE='...' scripts/restaurar.sh caminho/do.dump.gpg
#
# O alvo padrão é um Postgres local. Restaurar por cima de produção apagaria o
# banco de verdade, então o script SE RECUSA a apontar para qualquer host que
# não seja local — a menos que alguém escreva FORCA=1, que é longo o bastante
# para ninguém digitar por engano.
set -o errexit
set -o pipefail
set -o nounset

. "$(dirname "$0")/_conexao.sh"

ARQUIVO="${1:-}"
ALVO="${2:-postgres://postgres@localhost:5432/postgres}"
BANCO="nutriplan_drill"

if [ -z "$ARQUIVO" ] || [ ! -f "$ARQUIVO" ]; then
  echo "uso: scripts/restaurar.sh caminho/do.dump[.gpg] [url-do-alvo]" >&2
  echo "     (se for .gpg, defina BACKUP_PASSPHRASE no ambiente)" >&2
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

# ------------------------------------------------------- 1a. cifrado? decifra
#
# O backup guardado é `.gpg`, e o dia de usá-lo é o pior dia possível para
# descobrir que falta um passo. Aceitar o cifrado direto encurta a recuperação
# para um comando — a conferência do sha256 acima já rodou sobre o `.gpg`, que
# é o arquivo que de fato foi guardado.
#
# O arquivo decifrado vive num temporário e some no fim, inclusive se algum
# passo abaixo falhar: é dado de saúde em claro, e não fica no disco por
# distração.
case "$ARQUIVO" in
  *.gpg)
    if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
      echo "ERRO: este arquivo está criptografado." >&2
      echo "      Defina BACKUP_PASSPHRASE no ambiente (não como argumento)." >&2
      exit 1
    fi
    echo "1a/5 decifrando..."
    DECIFRADO="$(mktemp)"
    trap 'rm -f "$DECIFRADO"' EXIT
    printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --quiet \
      --pinentry-mode loopback --passphrase-fd 0 \
      --decrypt -o "$DECIFRADO" "$ARQUIVO"
    ARQUIVO="$DECIFRADO"
    ;;
esac

# ------------------------------------------ 1b. o cliente consegue ler isto?
#
# Achado medindo os backups que existem nesta máquina: quatro dos cinco estão
# no formato PGDMP 1.16, escrito por um `pg_dump` 18.x contra o servidor 18.4
# do Render. O `pg_restore` que costuma estar no PATH aqui é o 16.9, e ele
# recusa esse formato com "unsupported version (1.16) in file header".
#
# Sem esta checagem, o script morre na linha do `pg_restore` com essa frase —
# que não diz o que fazer, e aparece exatamente no dia em que alguém está
# tentando recuperar o banco. A mensagem abaixo diz.
echo "1b/5 conferindo se este cliente lê o arquivo..."
if ! ERRO_LISTA="$(pg_restore --list "$ARQUIVO" 2>&1 >/dev/null)"; then
  echo "ERRO: o pg_restore do PATH não consegue ler este dump." >&2
  echo "      $(pg_restore --version)" >&2
  echo "      $ERRO_LISTA" >&2
  echo "" >&2
  if printf '%s' "$ERRO_LISTA" | grep -qi "unsupported version"; then
    echo "      O arquivo foi escrito por um pg_dump MAIS NOVO que este" >&2
    echo "      cliente. Restaure com um cliente de versão igual ou maior." >&2
    for CANDIDATO in "$HOME/pg18/pgsql/bin" /usr/lib/postgresql/18/bin; do
      if [ -x "$CANDIDATO/pg_restore" ] || [ -x "$CANDIDATO/pg_restore.exe" ]; then
        echo "" >&2
        echo "      Nesta máquina existe um em:" >&2
        echo "        PATH=\"$CANDIDATO:\$PATH\" scripts/restaurar.sh $ARQUIVO" >&2
        break
      fi
    done
  fi
  exit 1
fi
echo "     $(pg_restore --list "$ARQUIVO" | grep -c 'TABLE DATA') tabelas com dados"

# ------------------------------------------------------------- 2. restauração
echo "2/5 restaurando em $BANCO..."
# Vale sobretudo para o caminho de desastre: com `FORCA=1` o alvo e um servidor
# de verdade, e sem isto a senha dele iria no argv de tres processos seguidos.
esconder_senha_da_url "$ALVO"
psql -d "$URL_SEM_SENHA" -q -c "DROP DATABASE IF EXISTS $BANCO;"
psql -d "$URL_SEM_SENHA" -q -c "CREATE DATABASE $BANCO;"
# A query string sobrevive: `?sslmode=require` e, no Neon, o `channel_binding`
# nao sao enfeite — sem eles a conexao nao roteia. Trocar so o ultimo segmento
# do caminho preserva o resto da URL.
case "$URL_SEM_SENHA" in
  *\?*) DESTINO="${URL_SEM_SENHA%%\?*}" ; QUERY="?${URL_SEM_SENHA#*\?}" ;;
  *)     DESTINO="$URL_SEM_SENHA" ; QUERY="" ;;
esac
DESTINO="${DESTINO%/*}/$BANCO$QUERY"
pg_restore --no-owner --no-privileges -d "$DESTINO" "$ARQUIVO"

# ------------------------------------------------------------------ 3. schema
echo "3/5 conferindo o schema..."
psql -d "$DESTINO" -q -c "
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
psql -d "$DESTINO" -q -c "
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
psql -d "$DESTINO" -q -v ON_ERROR_STOP=1 -c "
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
psql -d "$ALVO" -q -c "DROP DATABASE IF EXISTS $BANCO;"
