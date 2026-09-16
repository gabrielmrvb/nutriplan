# -*- coding: utf-8 -*-
"""Inventário classificado do export do Claude Design (spec 15/09/2026, §6).

    .venv/Scripts/python.exe scripts/inventariar_export.py artifacts/claude-design/export [--estrito] [--saida CAMINHO]

Escreve docs/briefs/2026-09-15-chatgpt-claude-design/inventario-export.md
(ou o `--saida`, que existe para rodar contra uma árvore de ensaio sem
escrever em `docs/`). Nada é apagado nem movido: a pasta é o registro.
Classes:
  tokens      lidos e comparados com a direção C (tokens/, guidelines/, readme,
              styles.css, config de lint de aderência)
  referencia  HTML de tela ou de componente, imagens e fontes de assets —
              referência visual
  interno     bundle, manifesto, thumbnail, uploads, export aninhado
  incerto     precisa de leitura humana; `--estrito` recusa terminar com um

A estrutura documentada é a do Finder do Reel "Parte 2/2" (ver
docs/briefs/2026-09-15-chatgpt-claude-design/README.md). O zip real pode
vir diferente — uma `src/` de Vite, um `index.html` na raiz —, e fora das
pastas conhecidas a EXTENSÃO decide: html, imagem e fonte são referência;
css, json e md com "token", "design" ou "guideline" no caminho são tokens;
`.js` fora de `_ds_` e tudo o mais é incerto. Palpite não ganha classe.

O ZIP REAL CHEGOU em 16/09/2026, e são DOIS: o do design system (166
arquivos: `components/` em React `.jsx` + `.d.ts` + `.prompt.md`,
`ui_kits/pwa/*.jsx`, `guidelines/`, `reference/`, `tokens/`, `uploads/`,
`SKILL.md`) e o do projeto das seis telas (`Hoje.html`… + uma cópia do
sistema em `_ds/`). Os dois foram extraídos em SUBPASTAS do export
(`design-system/`, `telas/`), então a pasta conhecida pode estar em qualquer
nível do caminho — e não só no primeiro. Os `.zip` originais ficam na raiz
como `interno`. Componente React é REFERÊNCIA: o app é Django + templates,
e o `.jsx` é para ler, não para importar.
"""
import hashlib
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "briefs" / "2026-09-15-chatgpt-claude-design" / "inventario-export.md"
CLASSES = ("tokens", "referencia", "interno", "incerto")

# Pastas de primeiro nível da estrutura documentada, e o que cada uma vale.
PASTAS_INTERNAS = ("design-system-export", "_ds", "uploads", ".thumbnail")
PASTAS_DE_TOKENS = ("tokens", "guidelines", "reference")
PASTAS_DE_REFERENCIA = ("components", "ui_kits", "templates", "assets", "export")
# `support.js` é o runtime do canvas (`.dc.html`) do Claude Design — o
# irmão do `_ds_bundle.js`: abre o arquivo no navegador, não é design.
NOMES_INTERNOS = (".thumbnail", "thumbnail.html", "support.js")
EXTENSOES_INTERNAS = (".zip",)
NOMES_DE_TOKENS = ("readme.md", "skill.md", "styles.css", "design.md")

# Fora das pastas conhecidas, a extensão decide.
EXTENSOES_DE_REFERENCIA = (
    ".html", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif",
    ".woff2", ".woff", ".ttf", ".otf",
)
EXTENSOES_DE_TEXTO_DE_DESIGN = (".css", ".json", ".md")
PALAVRAS_DE_DESIGN = ("token", "design", "guideline")


def classificar(rel):
    rel = rel.replace("\\", "/").strip("/")
    partes = rel.split("/")
    pastas = partes[:-1]  # toda pasta do caminho: o zip pode ter sido extraído numa subpasta
    nome = partes[-1]
    minusculo = nome.lower()
    extensao = Path(minusculo).suffix

    # Interno vence: um `components/` DENTRO de um export aninhado ou de `_ds/`
    # continua sendo duplicata.
    if any(p in PASTAS_INTERNAS for p in pastas) or nome.startswith("_ds_") or minusculo in NOMES_INTERNOS:
        return "interno"
    if extensao in EXTENSOES_INTERNAS:
        return "interno"  # o zip original, guardado ao lado do que saiu dele
    # Fora do interno, a pasta conhecida MAIS PRÓXIMA do arquivo decide
    # (`assets/telas/x.png` é assets; `ui_kits/pwa/Hoje.jsx` é ui_kits).
    pasta = next((p for p in reversed(pastas) if p in PASTAS_DE_TOKENS or p in PASTAS_DE_REFERENCIA), "")
    if nome.startswith("_adherence") or pasta in PASTAS_DE_TOKENS or minusculo in NOMES_DE_TOKENS:
        return "tokens"
    if pasta in PASTAS_DE_REFERENCIA or extensao in EXTENSOES_DE_REFERENCIA:
        return "referencia"
    if extensao in EXTENSOES_DE_TEXTO_DE_DESIGN and any(p in rel.lower() for p in PALAVRAS_DE_DESIGN):
        return "tokens"
    return "incerto"


def inventariar(raiz):
    raiz = Path(raiz)
    itens = []
    arquivos = sorted((p for p in raiz.rglob("*") if p.is_file()),
                      key=lambda p: p.relative_to(raiz).as_posix())
    for caminho in arquivos:
        rel = caminho.relative_to(raiz).as_posix()
        itens.append({
            "caminho": rel,
            "bytes": caminho.stat().st_size,
            "sha256": hashlib.sha256(caminho.read_bytes()).hexdigest(),
            "classe": classificar(rel),
        })
    return itens


def exigir_tudo_classificado(itens):
    incertos = [i["caminho"] for i in itens if i["classe"] == "incerto"]
    if incertos:
        # SystemExit com texto: o Python imprime a mensagem e encerra com 1,
        # sem traceback. Cada incerto numa linha, para ninguém ler só o primeiro.
        raise SystemExit("sem classe ({}):\n  {}".format(len(incertos), "\n  ".join(incertos)))


def _por_classe(itens):
    contagem = {c: 0 for c in CLASSES}
    for i in itens:
        contagem[i["classe"]] = contagem.get(i["classe"], 0) + 1
    return contagem


def _tabela_por_classe(itens):
    return ["| classe | arquivos |", "|---|---:|"] + [
        "| {} | {} |".format(c, n) for c, n in _por_classe(itens).items()
    ]


def _tabela_por_arquivo(itens, com_sha=True):
    if com_sha:
        return ["| caminho | bytes | sha256 (8) | classe |", "|---|---:|---|---|"] + [
            "| `{}` | {} | `{}` | {} |".format(i["caminho"], i["bytes"], i["sha256"][:8], i["classe"])
            for i in itens
        ]
    return ["| caminho | bytes | classe |", "|---|---:|---|"] + [
        "| `{}` | {} | {} |".format(i["caminho"], i["bytes"], i["classe"]) for i in itens
    ]


def escrever_md(itens, destino, origem):
    destino = Path(destino)
    megabytes = "{:.1f}".format(sum(i["bytes"] for i in itens) / 1e6).replace(".", ",")
    linhas = [
        "# Inventário do export do Claude Design",
        "",
        "Gerado por `scripts/inventariar_export.py` em {} a partir de `{}`. **{}** arquivos, {} MB.".format(
            datetime.now().strftime("%d/%m/%Y %H:%M"), origem, len(itens), megabytes),
        "",
    ] + _tabela_por_classe(itens) + [""] + _tabela_por_arquivo(itens)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main(argv):
    """Devolve o código de saída; `--estrito` com incerto levanta SystemExit."""
    argv = list(argv)
    estrito = "--estrito" in argv
    if estrito:
        argv.remove("--estrito")
    destino = DESTINO
    if "--saida" in argv:
        posicao = argv.index("--saida")
        try:
            destino = Path(argv[posicao + 1])
        except IndexError:
            print("--saida precisa de um caminho", file=sys.stderr)
            return 2
        del argv[posicao:posicao + 2]
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    raiz = Path(argv[0])
    if not raiz.is_dir():
        print("não é uma pasta: {}".format(raiz), file=sys.stderr)
        return 2

    itens = inventariar(raiz)
    if not itens:
        print("inventário vazio: {} não tem nenhum arquivo (zip errado? pasta errada?)".format(raiz.as_posix()),
              file=sys.stderr)
        return 2

    escrever_md(itens, destino, origem=raiz.as_posix())
    print("\n".join(_tabela_por_arquivo(itens, com_sha=False)))
    print()
    print("\n".join(_tabela_por_classe(itens)))
    print()
    print("{} arquivos → {}".format(len(itens), destino))
    if estrito:
        exigir_tudo_classificado(itens)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
