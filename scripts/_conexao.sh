# Tira a senha da URL antes de ela virar argumento de linha de comando.
#
# Este arquivo é `source`ado por `backup.sh` e `restaurar.sh`. Não roda sozinho.
#
# ------------------------------------------------------------------ o defeito
# O cabeçalho do `backup.sh` prometia, desde que foi escrito, que "a URL entra
# por ambiente e nunca por argumento: argumento aparece em `ps`". A promessa
# era sobre como o SCRIPT é chamado, e estava certa — mas o `pg_dump` era
# chamado com `-d "$DATABASE_URL"`, então a URI inteira, com a senha dentro,
# virava o argv de um processo externo.
#
# Medido com um `pg_dump` impostor que grava o próprio argv:
#
#   -d
#   postgres://usuario:SENHA@host.exemplo/banco?sslmode=require
#
# Qualquer processo local que rode `ps -ef` durante o despejo lia isso. Numa
# máquina de uma pessoa só o atacante realista é malware — que tem caminhos
# mais fáceis —, mas o pior aqui não era o risco: era o comentário garantindo
# uma proteção que não existia. Documentação que promete o que o código não faz
# é como uma decisão futura é tomada errada.
#
# ---------------------------------------------------------------- a correção
# `PGPASSWORD` é lida pelo libpq do AMBIENTE, e ambiente não aparece em `ps`.
# A URL segue indo em `-d` porque ela carrega coisas que importam e que não são
# segredo — `sslmode`, e no Neon o `channel_binding`, sem o qual a conexão não
# roteia. Só a senha sai dela.
#
# Se a URL não tiver senha (autenticação por peer, por exemplo), nada acontece:
# não há o que esconder, e a URL passa intacta.

#: Preenchida por `esconder_senha_da_url`. É esta que vai para o `-d`.
URL_SEM_SENHA=""

esconder_senha_da_url() {
  local url="$1"
  URL_SEM_SENHA="$url"

  # `sed -n ... p` devolve vazio quando não casa, e não um erro: URL sem senha
  # é caso legítimo, não falha.
  local senha
  senha="$(printf '%s' "$url" \
    | sed -nE 's#^[a-zA-Z0-9+.-]+://[^:/@]+:([^@]*)@.*#\1#p')"

  if [ -z "$senha" ]; then
    return 0
  fi

  # A senha na URI vem percent-encoded; a `PGPASSWORD` é lida literal. Sem
  # decodificar, uma senha com `@` (escrito `%40`) chegaria errada ao servidor
  # — e o sintoma seria "autenticação falhou" no dia do desastre.
  #
  # A conversão só acontece quando há `%`: `printf '%b'` também interpreta
  # contrabarra, e passar por ele uma senha que não precisa disso seria
  # inventar um jeito novo de estragá-la.
  case "$senha" in
    *%*) senha="$(printf '%b' "${senha//%/\\x}")" ;;
  esac

  export PGPASSWORD="$senha"
  URL_SEM_SENHA="$(printf '%s' "$url" \
    | sed -E 's#^([a-zA-Z0-9+.-]+://[^:/@]+):[^@]*@#\1@#')"
}
