# -*- coding: utf-8 -*-
"""Monta a semente do Claude Design em `artifacts/claude-design/seed/`.

    .venv/Scripts/python.exe scripts/exportar_telas.py      # antes: as telas
    .venv/Scripts/python.exe scripts/montar_semente.py

O que entra, e por quê (spec de 15/09/2026, §4):
  DESIGN.md   o contrato de tokens e regras (docs/briefs/design/DESIGN.md)
  codigo/     app.css, base.html, partials/ — o Claude Design parte da
              linguagem que já existe em vez de inventar
  telas/      os seis HTMLs autocontidos do exportador
  marca/      icon-192.png (a marca) e icones.svg (o sprite, sem Django)
  fonts/      as duas fontes próprias (.woff2 + OFL): o `@font-face` do
              app.css aponta para `../fonts/`, e as telas exportadas
              embutem o CSS — sem a pasta, o Claude Design veria a reserva
  capturas/   vazia aqui; a Task 5 enche com nav.py (6 telas × 2 temas)
  nota.txt    a frase para "Any other notes?"

Desde 17/09/2026 o sistema principal é a NERVURA · ANDAIME (veto do dono,
`DIRECAO-ESCOLHIDA.md`): a nota e o DESIGN.md que entram aqui são os dela.
"""
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "artifacts" / "claude-design" / "seed"
TELAS = ("10-hoje", "11-treino-painel", "12-treino-ficha", "13-treino-execucao", "14-progresso", "15-entrada")

NOTA = (
    "PWA mobile-first de alimentação, treino, corrida, hidratação e progresso, "
    "em português do Brasil. Sistema visual NERVURA · ANDAIME: o Ferro (escuro, "
    "academia à noite) é a base e o Papel (claro) o derivado; quina reta em "
    "tudo, traço de 2 px, a nervura diagonal a -14° como assinatura, o botão "
    "primário inclinado, Big Shoulders Display em caixa alta para título e "
    "número herói (nunca abaixo de 20 px) e Archivo para o texto. Tokens, "
    "regras e componentes estão no DESIGN.md — não inventar cor, raio nem "
    "tipografia fora dele; o que faltar, perguntar. As fontes estão em fonts/.\n"
)


def sprite_como_svg(raiz):
    """O sprite mora num template Django; o Claude Design lê SVG puro."""
    texto = (raiz / "templates" / "partials" / "icones.html").read_text(encoding="utf-8")
    texto = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", texto, flags=re.S)
    # Django tem três sintaxes de comentário/tag: {% %}, {{ }} e {# #}
    # O sprite usa a de linha para rotular cada símbolo — remover todos
    texto = re.sub(r"{%.*?%}|{{.*?}}|{#.*?#}", "", texto, flags=re.S)
    inicio = texto.find("<svg")
    fim = texto.rfind("</svg>") + len("</svg>")
    if inicio < 0 or fim < len("</svg>"):
        raise SystemExit("icones.html não tem um <svg>…</svg> reconhecível")
    return texto[inicio:fim].strip() + "\n"


def montar(raiz, destino, telas=TELAS):
    if destino.exists():
        shutil.rmtree(destino)
    for pasta in ("codigo", "telas", "marca", "fonts", "capturas"):
        (destino / pasta).mkdir(parents=True)
    contagem = {"codigo": 0, "telas": 0, "marca": 0, "fonts": 0}

    shutil.copy(raiz / "docs" / "briefs" / "design" / "DESIGN.md", destino / "DESIGN.md")
    (destino / "nota.txt").write_text(NOTA, encoding="utf-8")

    shutil.copy(raiz / "static" / "css" / "app.css", destino / "codigo" / "app.css")
    shutil.copy(raiz / "templates" / "base.html", destino / "codigo" / "base.html")
    contagem["codigo"] += 2
    (destino / "codigo" / "partials").mkdir()
    for parcial in sorted((raiz / "templates" / "partials").glob("*.html")):
        shutil.copy(parcial, destino / "codigo" / "partials" / parcial.name)
        contagem["codigo"] += 1

    shutil.copy(raiz / "static" / "icons" / "icon-192.png", destino / "marca" / "icon-192.png")
    (destino / "marca" / "icones.svg").write_text(sprite_como_svg(raiz), encoding="utf-8")
    contagem["marca"] = 2

    for fonte in sorted((raiz / "static" / "fonts").iterdir()):
        if fonte.suffix in (".woff2", ".txt", ".md"):
            shutil.copy(fonte, destino / "fonts" / fonte.name)
            contagem["fonts"] += 1

    for nome in telas:
        origem = raiz / ".ui_snapshots" / "html" / (nome + ".html")
        if origem.is_file():
            shutil.copy(origem, destino / "telas" / origem.name)
            contagem["telas"] += 1
        else:
            print("  aviso: tela ausente, rode scripts/exportar_telas.py antes:", origem.name)
    return contagem


if __name__ == "__main__":
    contagem = montar(RAIZ, DESTINO)
    print("Semente em", DESTINO)
    for pasta, n in contagem.items():
        print("  {:<8} {} arquivo(s)".format(pasta, n))
    if contagem["telas"] < len(TELAS):
        sys.exit("faltam telas em telas/ — exporte primeiro")
