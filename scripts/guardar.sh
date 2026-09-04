#!/usr/bin/env bash
# Criptografa um dump e PROVA que ele volta antes de apagar o original.
#
# O projeto já aplica esta regra ao dump: `backup.sh` não diz "OK" porque o
# arquivo existe, e sim porque o `pg_restore --list` conseguiu LER o que foi
# escrito. A camada de criptografia não tinha a mesma exigência — o fluxo do
# GitHub cifrava, apagava o arquivo em claro e subia o `.gpg` sem nunca abrir
# o resultado.
#
# O modo de falhar disso é o pior que existe num backup: silencioso e tardio.
# Uma senha com espaço a mais, um `--passphrase-fd` lendo de onde não devia,
# uma flag trocada numa versão nova do gpg — qualquer um produz um arquivo que
# sobe, aparece verde, e só se revela inútil no dia em que alguém precisar
# dele. Que é exatamente o dia em que não há segunda tentativa.
#
# Então aqui o arquivo em claro só é apagado DEPOIS de o cifrado ter sido
# decifrado de volta e a impressão digital ter batido.
#
# Uso:
#   BACKUP_PASSPHRASE='...' scripts/guardar.sh caminho/do.dump
#
# A senha entra por ambiente e nunca por argumento: argumento aparece em `ps`,
# no histórico do shell e no log de CI. Nada aqui a imprime.
set -o errexit
set -o pipefail
set -o nounset

ARQUIVO="${1:-}"

if [ -z "$ARQUIVO" ] || [ ! -f "$ARQUIVO" ]; then
  echo "uso: BACKUP_PASSPHRASE='...' scripts/guardar.sh caminho/do.dump" >&2
  exit 1
fi

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERRO: defina BACKUP_PASSPHRASE no ambiente (não como argumento)." >&2
  echo "      Sem ela isto não é backup criptografado — é um banco de dados" >&2
  echo "      de saúde num arquivo solto." >&2
  exit 1
fi

if ! command -v gpg >/dev/null 2>&1; then
  echo "ERRO: gpg não está no PATH." >&2
  exit 1
fi

CIFRADO="$ARQUIVO.gpg"
CONFERENCIA="$(mktemp)"
# `trap` e não uma linha no fim: se qualquer passo abaixo falhar, o `errexit`
# encerra o script na hora, e sem isto o arquivo decifrado ficaria no disco —
# em claro, com o dado que a criptografia existe para proteger.
trap 'rm -f "$CONFERENCIA"' EXIT

echo "1/4 impressão digital do original..."
ORIGINAL="$(sha256sum "$ARQUIVO" | awk '{print $1}')"

echo "2/4 criptografando (AES-256)..."
# `--pinentry-mode loopback` é obrigatório no gpg 2.x para senha por descritor:
# sem ele o gpg tenta abrir um pinentry gráfico e trava num runner sem tela.
printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --quiet \
  --pinentry-mode loopback --passphrase-fd 0 \
  --symmetric --cipher-algo AES256 -o "$CIFRADO" "$ARQUIVO"

echo "3/4 decifrando de volta e comparando..."
printf '%s' "$BACKUP_PASSPHRASE" | gpg --batch --yes --quiet \
  --pinentry-mode loopback --passphrase-fd 0 \
  --decrypt -o "$CONFERENCIA" "$CIFRADO"

VOLTOU="$(sha256sum "$CONFERENCIA" | awk '{print $1}')"
if [ "$ORIGINAL" != "$VOLTOU" ]; then
  echo "ERRO: o arquivo decifrado não bate com o original." >&2
  echo "      O cifrado NÃO presta. O original foi mantido." >&2
  rm -f "$CIFRADO"
  exit 1
fi

echo "4/4 o cifrado volta; apagando o arquivo em claro..."
rm -f "$ARQUIVO"

TAMANHO="$(wc -c < "$CIFRADO" | tr -d ' ')"
SOMA="$(sha256sum "$CIFRADO" | awk '{print $1}')"
echo "$SOMA  $(basename "$CIFRADO")" >> "$(dirname "$CIFRADO")/SHA256SUMS"

echo ""
echo "GUARDADO OK"
echo "  arquivo: $CIFRADO"
echo "  tamanho: $TAMANHO bytes"
echo "  sha256:  $SOMA"
echo ""
echo "Provado nesta execução: o cifrado decifra e bate com o dump original."
echo "Sem a senha, este arquivo não é nada. Guarde-a FORA do GitHub."
