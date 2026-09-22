#!/usr/bin/env bash
# A prova da Fase 1 no Android, num emulador já ligado (CI ou máquina):
#
#   1. instala o APK de debug e abre o app; ONLINE, a página é o NutriPlan
#      e o service worker está controlando a página (Runtime.evaluate pelo
#      DevTools remoto do WebView — texto, não captura);
#   2. modo avião; reabre o app; OFFLINE, a página é o shell offline do PWA
#      servido pelo worker (`[data-shell-offline]`), e não a erro.html da
#      casca — é o "funciona offline com o mesmo service worker" pedido;
#   3. tira a captura dos dois estados, nos dois temas, e devolve a rede.
#
# Uso: prova_android.sh <apk> <pasta-de-saída>   (adb no PATH; websocket-client no python)
set -euo pipefail
APK="${1:?apk}"
SAIDA="${2:?pasta de saída}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
mkdir -p "$SAIDA"

adb wait-for-device
adb shell 'while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ]; do sleep 2; done'
adb install -r "$APK"

abrir() {
  adb shell am force-stop com.nutriplan.app
  adb shell am start -n com.nutriplan.app/.MainActivity >/dev/null
  sleep "${ESPERA_S:-35}"
}

sonda() {  # $1 = nome do arquivo JSON
  local pid
  pid="$(adb shell 'cat /proc/net/unix' | grep -o 'webview_devtools_remote_[0-9]*' | head -1 | tr -d '\r')"
  adb forward tcp:9333 "localabstract:$pid" >/dev/null
  "$PY" "$AQUI/webview_cdp.py" 9333 | tee "$SAIDA/$1.json"
}

falhou() { echo "PROVA ANDROID FALHOU: $1" >&2; exit 1; }

echo "== online"
adb shell cmd connectivity airplane-mode disable || true
sleep 3
abrir
adb exec-out screencap -p > "$SAIDA/android-01-online.png"
sonda online
"$PY" - "$SAIDA/online.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))["pagina"]
assert "NutriPlan" in r["titulo"], r
assert r["url"].startswith("https://nutriplan-xxfn.onrender.com/"), r
assert r["swControlando"] is True, "o service worker NÃO controla a página na casca: %s" % r
print("online OK: título=%r, service worker controlando" % r["titulo"])
EOF

echo "== offline (modo avião)"
adb shell cmd connectivity airplane-mode enable
sleep 6
abrir
adb exec-out screencap -p > "$SAIDA/android-02-offline.png"
sonda offline
"$PY" - "$SAIDA/offline.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))["pagina"]
assert r["shellOffline"] is True, "sem rede a casca não mostrou o shell offline do PWA (worker): %s" % r
assert r["erroDaCasca"] is False, r
print("offline OK: shell do PWA servido pelo service worker")
EOF

echo "== tema escuro, online de novo"
adb shell cmd connectivity airplane-mode disable
adb shell cmd uimode night yes
sleep 6
abrir
adb exec-out screencap -p > "$SAIDA/android-03-online-escuro.png"
adb shell cmd uimode night no
echo "PROVA ANDROID OK"
