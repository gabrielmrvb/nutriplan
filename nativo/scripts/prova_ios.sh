#!/usr/bin/env bash
# A prova da Fase 1 no iOS, no simulador de um macOS (o runner do Actions;
# esta máquina é Windows e não tem Xcode):
#
#   1. constrói o app para o simulador SEM assinatura (é o que dá para fazer
#      sem a conta Apple Developer) e o instala num iPhone do simulador;
#   2. ONLINE: abre, espera, tira a captura;
#   3. OFFLINE: bloqueia a saída 80/443 do próprio runner com o pf (o
#      simulador usa a rede do host), reabre o app, tira a captura — a
#      tela tem de ser o shell offline do PWA (service worker no WKWebView,
#      que só existe com WKAppBoundDomains), e não a erro.html da casca;
#   4. libera a rede (também em `trap`, para o runner não ficar sem rede).
#
# O WKWebView não tem DevTools remoto no simulador sem o Safari: a prova
# do iOS é a captura + o log do app (`simctl launch --console`), e é dito
# no relatório como tal.
set -euo pipefail
SAIDA="${1:?pasta de saída}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
PROJETO="$AQUI/../ios/App/App.xcodeproj"
mkdir -p "$SAIDA"

liberar_rede() { sudo pfctl -d >/dev/null 2>&1 || true; }
trap liberar_rede EXIT

echo "== build (simulador, sem assinatura)"
xcodebuild -project "$PROJETO" -scheme App -configuration Debug \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$AQUI/../ios/build" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" \
  -skipPackagePluginValidation -skipMacroValidation build | tail -5
APP="$(find "$AQUI/../ios/build/Build/Products" -name 'App.app' -maxdepth 2 | head -1)"
[ -n "$APP" ] || { echo "App.app não foi produzido" >&2; exit 1; }

echo "== simulador"
UDID="$(xcrun simctl list devices available -j | python3 -c '
import json, sys
d = json.load(sys.stdin)["devices"]
cands = [(rt, dev) for rt, devs in d.items() if "iOS" in rt for dev in devs if dev["name"].startswith("iPhone")]
cands.sort(key=lambda x: (x[0], x[1]["name"]), reverse=True)
print(cands[0][1]["udid"])')"
xcrun simctl boot "$UDID" || true
xcrun simctl bootstatus "$UDID" -b
xcrun simctl install "$UDID" "$APP"

falhou() { echo "PROVA IOS FALHOU: $1" >&2; exit 1; }

# Abre o app e CONFERE que ele ficou de pé. Sem esta conferência o passo
# passava com a captura da TELA INICIAL do iPhone: `simctl launch` responde
# na hora, o app podia morrer em seguida, e ninguém reclamava (visto no run
# de 22/09/2026, o offline saiu com o ícone do NutriPlan na home).
abrir() {
  local pid i
  xcrun simctl terminate "$UDID" com.nutriplan.app >/dev/null 2>&1 || true
  pid="$(xcrun simctl launch "$UDID" com.nutriplan.app | awk -F': ' '{print $2}')"
  [ -n "$pid" ] || falhou "o app não subiu (simctl launch não devolveu pid)"
  sleep "${ESPERA_S:-40}"
  for i in 1 2 3; do
    # App do simulador é processo do HOST: o pid que o `simctl launch`
    # devolve se confere com `ps` daqui mesmo. (A primeira versão perguntava
    # ao `launchctl list` de dentro do simulador e nunca achava: reprovava
    # um app que estava rodando — MEDIDO no run do #120.)
    if ps -p "$pid" >/dev/null 2>&1; then
      return 0
    fi
    echo "   app fora do ar, reabrindo ($i)" >&2
    pid="$(xcrun simctl launch "$UDID" com.nutriplan.app | awk -F': ' '{print $2}')"
    sleep 10
  done
  falhou "o app não está rodando depois de abrir — a captura seria da tela inicial"
}

echo "== online"
abrir
xcrun simctl io "$UDID" screenshot "$SAIDA/ios-01-online.png"

echo "== offline (pf bloqueia 80/443)"
printf 'block drop out quick proto {tcp, udp} from any to any port {80, 443}\n' | sudo pfctl -Ef - 2>/dev/null || true
sleep 3
abrir
xcrun simctl io "$UDID" screenshot "$SAIDA/ios-02-offline.png"
liberar_rede

echo "== tema escuro, online"
xcrun simctl ui "$UDID" appearance dark
sleep 5
abrir
xcrun simctl io "$UDID" screenshot "$SAIDA/ios-03-online-escuro.png"
xcrun simctl ui "$UDID" appearance light
echo "PROVA IOS OK: capturas em $SAIDA (o app ficou de pé nos três estados; o CONTEÚDO da tela é julgamento visual — o WKWebView não expõe DevTools no simulador)"
