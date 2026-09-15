# -*- coding: utf-8 -*-
"""nav.py — navegador headless por CDP para QA, UMA sessão por nome.

O `agent-browser` passou a ser bloqueado pelo Controle de Aplicativo do
Windows em 14/09/2026; o Chrome que ele baixou continua rodando. Este
arquivo fala CDP direto com um Chrome headless próprio por sessão.

Uso (sempre com o python do .venv):
  nav.py <sessao> open <url>                 -> título e URL final
  nav.py <sessao> eval "<js>"                -> valor JSON da expressão
  nav.py <sessao> click "<seletor css>"      -> clica no centro do elemento (rola até ele)
  nav.py <sessao> type "<seletor>" "<texto>" -> foca, limpa e digita
  nav.py <sessao> press <Tecla>              -> Enter, Tab, Escape...
  nav.py <sessao> viewport <largura> <altura>
  nav.py <sessao> screenshot <arquivo.png> [full]
  nav.py <sessao> cookie <nome> <valor> [dominio]
  nav.py <sessao> permissao <notifications|geolocation> <granted|denied|prompt> [origem]
  nav.py <sessao> offline on|off
  nav.py <sessao> url | title | text [max] | links | clicaveis
  nav.py <sessao> close

Cada sessão guarda o perfil em %TEMP%/nav-<sessao> (cookies sobrevivem entre
comandos) e o Chrome fica vivo entre comandos; `close` derruba. Saída sempre
em UTF-8. Nunca aponte para produção com escrita: só GET lá.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

CHROME = Path.home() / ".agent-browser" / "browsers" / "chrome-153.0.8010.36" / "chrome.exe"
BASE = Path(os.environ.get("TEMP", "/tmp")) / "nav-sessoes"
BASE.mkdir(parents=True, exist_ok=True)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _porta(sessao):
    return 9300 + (sum(ord(c) for c in sessao) % 600)


def _vivo(porta):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/json/version" % porta, timeout=2).read()
        return True
    except Exception:
        return False


def _abrir_chrome(sessao, porta, largura=390, altura=844):
    perfil = BASE / ("perfil-" + sessao)
    perfil.mkdir(parents=True, exist_ok=True)
    args = [
        str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--remote-debugging-port=%d" % porta, "--remote-allow-origins=*", "--user-data-dir=%s" % perfil,
        "--window-size=%d,%d" % (largura, altura), "--hide-scrollbars", "--lang=pt-BR",
        "--disable-background-timer-throttling", "about:blank",
    ]
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(60):
        if _vivo(porta):
            return
        time.sleep(0.25)
    raise SystemExit("Chrome não subiu na porta %d" % porta)


class Sessao:
    def __init__(self, nome):
        self.nome = nome
        self.porta = _porta(nome)
        if not _vivo(self.porta):
            _abrir_chrome(nome, self.porta)
        alvos = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % self.porta, timeout=5).read())
        paginas = [t for t in alvos if t.get("type") == "page"]
        if not paginas:
            novo = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/json/new?about:blank" % self.porta, timeout=5).read())
            paginas = [novo]
        self.ws = websocket.create_connection(paginas[0]["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self._id = 0
        self._viewport()
        self._offline()
        self.cmd("Page.enable"); self.cmd("Runtime.enable")

    def _viewport(self):
        cfg = BASE / ("viewport-" + self.nome + ".json")
        if cfg.exists():
            w, h = json.loads(cfg.read_text())
        else:
            w, h = 390, 844
        self.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=True)

    def cmd(self, metodo, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": metodo, "params": params}))
        while True:
            resposta = json.loads(self.ws.recv())
            if resposta.get("id") == self._id:
                if "error" in resposta:
                    raise SystemExit("CDP %s: %s" % (metodo, resposta["error"].get("message")))
                return resposta.get("result", {})

    def esperar_carga(self, timeout=30):
        fim = time.time() + timeout
        while time.time() < fim:
            estado = self.eval("document.readyState")
            if estado == "complete":
                time.sleep(0.35)
                return
            time.sleep(0.1)

    def eval(self, js, awaited=True):
        r = self.cmd("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=awaited)
        res = r.get("result", {})
        if res.get("subtype") == "error" or r.get("exceptionDetails"):
            desc = res.get("description") or json.dumps(r.get("exceptionDetails"))
            raise SystemExit("JS: " + desc)
        return res.get("value")

    def open(self, url):
        self.cmd("Page.navigate", url=url)
        self.esperar_carga()
        return {"title": self.eval("document.title"), "url": self.eval("location.href")}

    def centro(self, seletor):
        r = self.eval(
            "(function(){var e=document.querySelector(%s);if(!e)return null;e.scrollIntoView({block:'center',inline:'nearest'});"
            "var b=e.getBoundingClientRect();return {x:b.left+b.width/2,y:b.top+b.height/2,w:b.width,h:b.height,tag:e.tagName,text:(e.innerText||e.value||'').trim().slice(0,60)}})()"
            % json.dumps(seletor)
        )
        if r is None:
            raise SystemExit("seletor não encontrado: " + seletor)
        return r

    def click(self, seletor):
        c = self.centro(seletor)
        time.sleep(0.15)
        for tipo in ("mousePressed", "mouseReleased"):
            self.cmd("Input.dispatchMouseEvent", type=tipo, x=c["x"], y=c["y"], button="left", clickCount=1)
        time.sleep(0.6)
        self.esperar_carga(10)
        return {"clicou": c, "url": self.eval("location.href"), "title": self.eval("document.title")}

    def type(self, seletor, texto):
        self.click(seletor)
        self.eval("(function(){var e=document.querySelector(%s);e.focus();if('value' in e){e.value='';}})()" % json.dumps(seletor))
        self.cmd("Input.insertText", text=texto)
        self.eval("(function(){var e=document.querySelector(%s);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))})()" % json.dumps(seletor))
        return {"digitou": texto}

    def press(self, tecla):
        codigos = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "ArrowDown": 40, "ArrowUp": 38, "Space": 32}
        code = codigos.get(tecla, 0)
        for tipo in ("keyDown", "keyUp"):
            self.cmd("Input.dispatchKeyEvent", type=tipo, key=tecla, code=tecla, windowsVirtualKeyCode=code, nativeVirtualKeyCode=code, text="\r" if tecla == "Enter" else "")
        time.sleep(0.6)
        self.esperar_carga(10)
        return {"url": self.eval("location.href")}

    def viewport(self, w, h):
        (BASE / ("viewport-" + self.nome + ".json")).write_text(json.dumps([int(w), int(h)]))
        self.cmd("Emulation.setDeviceMetricsOverride", width=int(w), height=int(h), deviceScaleFactor=1, mobile=True)
        return {"viewport": [int(w), int(h)]}

    def screenshot(self, arquivo, full=False):
        params = {"format": "png"}
        if full:
            m = self.cmd("Page.getLayoutMetrics")
            cs = m.get("cssContentSize") or m.get("contentSize")
            params["clip"] = {"x": 0, "y": 0, "width": cs["width"], "height": cs["height"], "scale": 1}
            params["captureBeyondViewport"] = True
        r = self.cmd("Page.captureScreenshot", **params)
        Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
        Path(arquivo).write_bytes(base64.b64decode(r["data"]))
        return {"screenshot": arquivo, "bytes": Path(arquivo).stat().st_size}

    def permissao(self, nome, decisao, origem="http://127.0.0.1:8000"):
        """`notifications`/`geolocation` como `granted`, `denied` ou `prompt`,
        para a origem — é como se testa a tela de quem bloqueou."""
        self.cmd("Browser.setPermission", permission={"name": nome}, setting=decisao, origin=origem)
        return {"permissao": nome, "decisao": decisao}

    def offline(self, ligado):
        """Rede desligada (`on`) ou de volta (`off`) — é como se prova a fila offline.

        A emulação é DA SESSÃO CDP e morre quando a conexão fecha — e cada
        comando deste arquivo abre uma conexão nova. O estado fica num
        arquivo e é reaplicado em todo comando, como o viewport."""
        (BASE / ("offline-" + self.nome + ".json")).write_text(json.dumps(ligado == "on"))
        self._offline()
        return {"offline": ligado == "on"}

    def _offline(self):
        cfg = BASE / ("offline-" + self.nome + ".json")
        ligado = cfg.exists() and json.loads(cfg.read_text())
        self.cmd("Network.enable")
        self.cmd("Network.emulateNetworkConditions", offline=bool(ligado), latency=0, downloadThroughput=-1, uploadThroughput=-1)

    def cookie(self, nome, valor, dominio="127.0.0.1"):
        self.cmd("Network.setCookie", name=nome, value=valor, domain=dominio, path="/", httpOnly=True)
        return {"cookie": nome}

    def text(self, maximo=4000):
        return (self.eval("document.body.innerText") or "")[: int(maximo)]

    def links(self):
        return self.eval("[...document.querySelectorAll('a[href]')].map(function(a){return (a.innerText||a.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().slice(0,50)+' -> '+a.getAttribute('href')})")

    def clicaveis(self):
        return self.eval(
            "[...document.querySelectorAll('a,button,input,select,textarea,summary,[role=button],[onclick],label')].map(function(e){var b=e.getBoundingClientRect();"
            "return {tag:e.tagName,type:e.getAttribute('type')||'',classe:(e.className||'').toString().slice(0,60),texto:(e.innerText||e.value||e.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().slice(0,50),href:e.getAttribute('href')||'',w:Math.round(b.width),h:Math.round(b.height),y:Math.round(b.top+scrollY),visivel:!!(b.width&&b.height)}})"
        )


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 2
    sessao, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
    if cmd == "close":
        porta = _porta(sessao)
        if _vivo(porta):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/json/close" % porta, timeout=2)
            except Exception:
                pass
            try:
                s = Sessao(sessao); s.cmd("Browser.close")
            except SystemExit:
                pass
        print(json.dumps({"fechada": sessao})); return 0
    s = Sessao(sessao)
    try:
        if cmd == "open": out = s.open(args[0])
        elif cmd == "eval": out = s.eval(args[0])
        elif cmd == "click": out = s.click(args[0])
        elif cmd == "type": out = s.type(args[0], args[1])
        elif cmd == "press": out = s.press(args[0])
        elif cmd == "viewport": out = s.viewport(args[0], args[1])
        elif cmd == "screenshot": out = s.screenshot(args[0], full=(len(args) > 1 and args[1] == "full"))
        elif cmd == "cookie": out = s.cookie(args[0], args[1], *(args[2:3]))
        elif cmd == "permissao": out = s.permissao(args[0], args[1], *(args[2:3]))
        elif cmd == "offline": out = s.offline(args[0])
        elif cmd == "url": out = s.eval("location.href")
        elif cmd == "title": out = s.eval("document.title")
        elif cmd == "text": out = s.text(*(args[:1]))
        elif cmd == "links": out = s.links()
        elif cmd == "clicaveis": out = s.clicaveis()
        else:
            print("comando desconhecido: " + cmd); return 2
        print(json.dumps(out, ensure_ascii=False))
    finally:
        s.ws.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
