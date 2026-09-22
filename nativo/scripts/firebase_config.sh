#!/usr/bin/env bash
# Põe os arquivos de configuração do Firebase onde o build os lê:
#
#   android/app/google-services.json        (plugin google-services do Gradle)
#   ios/App/App/GoogleService-Info.plist    (FirebaseApp.configure() no launch)
#
# Os REAIS vêm do projeto Firebase do dono e nunca entram no git: chegam por
# segredo do Actions (base64 em FIREBASE_GOOGLE_SERVICES_JSON /
# FIREBASE_GOOGLE_SERVICE_INFO_PLIST) ou por arquivo local. Sem eles, entram
# os EXEMPLOS (`nativo/exemplo/`, projeto fictício): o app constrói e abre —
# o iOS sem o plist morre no `FirebaseApp.configure()` do plugin de push —
# e o push simplesmente não registra token. É o estado do CI até a conta
# Firebase existir.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$AQUI/.."
colocar() {  # $1 = variável (base64), $2 = exemplo, $3 = destino
  if [ -n "${!1:-}" ]; then
    printf '%s' "${!1}" | base64 -d > "$3"
    echo "$3: do segredo $1"
  elif [ -f "$3" ]; then
    echo "$3: já existe (local), mantido"
  else
    cp "$2" "$3"
    echo "$3: EXEMPLO (sem projeto Firebase — push não registra)"
  fi
}
colocar FIREBASE_GOOGLE_SERVICES_JSON "$RAIZ/exemplo/google-services.json" "$RAIZ/android/app/google-services.json"
colocar FIREBASE_GOOGLE_SERVICE_INFO_PLIST "$RAIZ/exemplo/GoogleService-Info.plist" "$RAIZ/ios/App/App/GoogleService-Info.plist"
