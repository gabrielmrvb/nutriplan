# -*- coding: utf-8 -*-
"""As CAPTURAS de uma tela, nas larguras e nos temas que o B8 exige.

    .venv/Scripts/python.exe scripts/qa/telas.py <pasta> <base> <rota> [rota...]
        # a rota pode vir com ou sem a barra inicial: "demo/hoje/" evita a
        # conversão de caminho do Git Bash no Windows
        [--sessao <cookie sessionid>] [--larguras 390,1280] [--temas dark,light]
        [--medir]

Uma missão de redesenho vive de "antes e depois", e antes/depois só vale se as
duas fotos forem tiradas do mesmo jeito. Este script é esse "mesmo jeito":
`agent-browser` (o mesmo Chromium do E2E), viewport e `prefers-color-scheme`
emulados ANTES do `open`, movimento reduzido (captura estática não espera
animação), e o arquivo nomeado `<rota>-<largura>-<tema>.png`.

`--medir` acrescenta um JSON por tela com o que a auditoria mediu à mão:
altura da página, rolagem horizontal, alvos de toque abaixo de 44px, textos
abaixo de 11px e a largura útil do conteúdo — é o número que prova o "depois".
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.qa.e2e_staging import Navegador  # noqa: E402

#: O que a régua mede em cada tela, em UMA passada pelo DOM.
MEDIDAS = """({
  altura: document.documentElement.scrollHeight,
  rolagem_horizontal: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  largura_do_conteudo: Math.round((document.querySelector('main')||document.body).getBoundingClientRect().width),
  alvos_pequenos: [...document.querySelectorAll('main a, main button, main summary, nav a')]
      .map(e => [e.textContent.replace(/\\s+/g,' ').trim().slice(0,28), Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])
      .filter(([t,w,h]) => w && h && (w < 44 || h < 44)),
  texto_pequeno: [...document.querySelectorAll('main *')]
      .filter(e => e.children.length === 0 && e.textContent.trim())
      .map(e => parseFloat(getComputedStyle(e).fontSize)).filter(f => f > 0 && f < 11).length,
  h1: (document.querySelector('h1')||{}).textContent,
  titulo: document.title,
})"""


def capturar(pasta, base, rotas, sessao=None, larguras=(390, 1280), temas=("dark", "light"), medir=False):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    ab = Navegador("telas-%s" % pasta.name)
    medidas = {}
    for largura in larguras:
        for tema in temas:
            ab("open", "about:blank")
            ab("set", "viewport", str(largura), "900")
            # UMA chamada com os dois: `set media` substitui o estado de
            # emulação inteiro, e a segunda chamada apagava a primeira — as
            # capturas de 22/09/2026 saíram todas no tema claro, com "dark"
            # no nome do arquivo (o Ferro é a base; quem emula `light` é que
            # muda o tema). Vale a mesma régua do `e2e_staging`.
            ab("set", "media", tema, "reduced-motion")
            if sessao:
                ab("open", base + "/conta/entrar/", timeout=180)
                ab("eval", "document.cookie = 'sessionid=%s; path=/'" % sessao)
            for rota in rotas:
                # Rota SEM barra inicial é aceita ("demo/hoje/"): no Git Bash
                # do Windows um argumento que começa com "/" é convertido em
                # caminho do Windows antes de o Python ver ("C:/Program
                # Files/Git/demo/hoje/"), e o `open` recebia lixo.
                rota = "/" + rota.lstrip("/")
                nome = (rota.strip("/").replace("/", "-") or "raiz")
                ab("open", base + rota, timeout=180)
                # `--full` é o nome da opção no agent-browser (não
                # `--full-page`): com o nome errado ele salva em silêncio numa
                # pasta temporária e a captura do "depois" não existe.
                ab("screenshot", str(pasta / ("%s-%s-%s.png" % (nome, largura, tema))), "--full")
                if medir:
                    bruto = ab.eval(MEDIDAS)
                    try:
                        medidas.setdefault(nome, {})["%s-%s" % (largura, tema)] = json.loads(bruto)
                    except ValueError:
                        medidas.setdefault(nome, {})["%s-%s" % (largura, tema)] = {"bruto": bruto[:400]}
    if medir:
        (pasta / "medidas.json").write_text(json.dumps(medidas, ensure_ascii=False, indent=1), encoding="utf-8")
    return medidas


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    pasta, base = argv[0], argv[1].rstrip("/")
    rotas, sessao, larguras, temas, medir = [], None, (390, 1280), ("dark", "light"), False
    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg == "--sessao":
            i += 1
            sessao = argv[i]
        elif arg == "--larguras":
            i += 1
            larguras = tuple(int(x) for x in argv[i].split(","))
        elif arg == "--temas":
            i += 1
            temas = tuple(argv[i].split(","))
        elif arg == "--medir":
            medir = True
        else:
            rotas.append(arg)
        i += 1
    medidas = capturar(pasta, base, rotas, sessao, larguras, temas, medir)
    for nome, por_tela in medidas.items():
        for chave, m in por_tela.items():
            print("%-22s %-10s altura=%-6s rolagem_h=%-5s largura=%-5s alvos<44=%-3s texto<11=%s" % (
                nome, chave, m.get("altura"), m.get("rolagem_horizontal"),
                m.get("largura_do_conteudo"), len(m.get("alvos_pequenos") or []), m.get("texto_pequeno")))


if __name__ == "__main__":
    main(sys.argv[1:])
