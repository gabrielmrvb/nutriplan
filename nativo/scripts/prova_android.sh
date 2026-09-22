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
  # O socket é o do PROCESSO VIVO do app: `/proc/net/unix` guarda entradas
  # de processos já mortos, e o primeiro `grep` pegava um socket morto.
  local pid
  pid="$(adb shell pidof com.nutriplan.app | tr -d '
' | awk '{print $1}')"
  [ -n "$pid" ] || falhou "o app não está rodando"
  adb forward --remove-all >/dev/null 2>&1 || true
  adb forward tcp:9333 "localabstract:webview_devtools_remote_$pid" >/dev/null
  "$PY" "$AQUI/webview_cdp.py" 9333 | tee "$SAIDA/$1.json"
}

falhou() { echo "PROVA ANDROID FALHOU: $1" >&2; exit 1; }

# Derruba (ou devolve) a rede do emulador. `cmd connectivity airplane-mode`
# existe do API 33 em diante; em imagem que o recusa, o caminho é o dos
# rádios (`svc`). Confere pelo `dumpsys connectivity` em vez de confiar no
# código de saída — foi assim que o primeiro run do Actions morreu mudo.
rede() {  # $1 = on|off
  # `set -e` mata o script no primeiro comando não-zero, e o `adb` devolve
  # não-zero por motivos banais (o `cmd connectivity` não existe em toda
  # imagem, o `svc` reclama, o `dumpsys` é interrompido pelo `grep`). Aqui
  # dentro o -e sai, e o que decide é o ESTADO lido, não o código de saída
  # — foi assim que o primeiro run do Actions morreu mudo logo depois de
  # "== offline".
  set +e
  local estado i
  if [ "$1" = off ]; then
    adb shell cmd connectivity airplane-mode enable >/dev/null 2>&1
    adb shell "svc wifi disable; svc data disable" >/dev/null 2>&1
  else
    adb shell cmd connectivity airplane-mode disable >/dev/null 2>&1
    adb shell "svc wifi enable; svc data enable" >/dev/null 2>&1
  fi
  for i in $(seq 1 30); do
    estado="$(adb shell dumpsys connectivity 2>/dev/null | tr -d '\r' | grep -i 'Active default network')"
    case "$1:$estado" in
      off:*"network: none"*) echo "   rede off em ${i}x2s ($estado)"; set -e; return 0 ;;
      on:*"network: "[0-9]*) echo "   rede on em ${i}x2s ($estado)"; set -e; return 0 ;;
    esac
    sleep 2
  done
  set -e
  [ "$1" = off ] && falhou "a rede do emulador não caiu em 60 s: ${estado:-(dumpsys não respondeu)}"
  echo "aviso: a rede do emulador não voltou em 60 s (${estado:-sem leitura})" >&2
}

echo "== online"
rede on
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
rede off
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
rede on
adb shell cmd uimode night yes
sleep 3
abrir
adb exec-out screencap -p > "$SAIDA/android-03-online-escuro.png"
adb shell cmd uimode night no
echo "PROVA ANDROID OK"
