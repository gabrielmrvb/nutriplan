# -*- coding: utf-8 -*-
"""Pergunta ao WebView do app (Android) o que ele está mostrando — pelo
DevTools remoto, não pela captura de tela.

O build de debug expõe `localabstract:webview_devtools_remote_<pid>`; com
`adb forward tcp:9333 localabstract:...` este script lê `/json` e avalia
JavaScript na página. É a prova textual da Fase 1: online, o título é o do
NutriPlan e `sw.js` aparece como alvo (o service worker REGISTROU dentro da
casca); em modo avião, a página é o shell offline do PWA servido pelo
worker (`[data-shell-offline]`), e não a `erro.html` da casca.

    python webview_cdp.py 9333            # imprime JSON com título, url, alvos e o que a página é
"""
import json
import sys
import urllib.request

try:
    from websocket import create_connection  # websocket-client
except ImportError:  # pragma: no cover - dependência do runner/máquina
    create_connection = None

JS = (
    "JSON.stringify({titulo: document.title, url: location.href,"
    " shellOffline: !!document.querySelector('[data-shell-offline]'),"
    " erroDaCasca: !!document.querySelector('main .marca') && /Sem conex/i.test(document.title) && !document.querySelector('[data-shell-offline]'),"
    " swControlando: !!(navigator.serviceWorker && navigator.serviceWorker.controller),"
    " texto: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 160)})"
)


def alvos(porta):
    with urllib.request.urlopen("http://127.0.0.1:%s/json" % porta, timeout=10) as r:
        return json.load(r)


def avaliar(ws_url, js):
    # O DevTools do WebView recusa origem desconhecida (403): sem cabeçalho
    # Origin ele aceita, como faz o próprio chrome://inspect.
    ws = create_connection(ws_url, timeout=15, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
        while True:
            resposta = json.loads(ws.recv())
            if resposta.get("id") == 1:
                return json.loads(resposta["result"]["result"]["value"])
    finally:
        ws.close()


def main(porta="9333"):
    if hasattr(sys.stdout, "reconfigure"):  # o console do Windows é cp1252 e o JSON vai para arquivo
        sys.stdout.reconfigure(encoding="utf-8")
    lista = alvos(porta)
    pagina = next((a for a in lista if a.get("type") == "page"), None)
    resultado = {
        "alvos": [{"tipo": a.get("type"), "titulo": a.get("title"), "url": a.get("url")} for a in lista],
        "temServiceWorker": any(a.get("type") == "service_worker" or "sw.js" in (a.get("url") or "") for a in lista),
    }
    if pagina and create_connection:
        resultado["pagina"] = avaliar(pagina["webSocketDebuggerUrl"], JS)
    elif pagina:
        resultado["pagina"] = {"titulo": pagina.get("title"), "url": pagina.get("url"), "aviso": "sem websocket-client: só o /json"}
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return resultado


if __name__ == "__main__":
    main(*sys.argv[1:])
