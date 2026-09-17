# -*- coding: utf-8 -*-
"""Compara os tokens que o Claude Design exportou com a direção C (Mesa).

    .venv/Scripts/python.exe scripts/tokens_do_export.py artifacts/claude-design/export
    .venv/Scripts/python.exe scripts/tokens_do_export.py artifacts/claude-design/export --saida difs.md

Imprime um markdown com, para CADA token de cor do `:root` do `app.css`, o
valor que o export propôs (ou "ausente") e o veredito — igual, diferente,
misto —, mais o que o export tem e a direção não ("novos no export"), os
nomes que precisaram ser traduzidos (`--color-brand` → `--brand`), o que foi
ignorado (`--ferro-*`, que é o outro regime) e o que não deu para ler. No
fim vai a tabela só das diferenças, com a coluna `motivo` vazia: é ela que
`proposto-nao-adotado.md` recebe, linha a linha, escrita à mão — a razão é
humana. A spec ganha (spec 15/09/2026, §7).

O que é lido: `.css`, `.json`, `.md` e `.html` de tudo que a triagem da
Task 8 (`scripts/inventariar_export.py`) não classifica como `interno` —
bundle, manifesto, thumbnail, uploads e o export aninhado ficam de fora,
porque repetem ou contradizem o que está na raiz. Só VALOR DE COR entra
(`#hex`, `rgb()`, `hsl()`): raio, espaço e movimento têm régua própria e não
cabem numa comparação de string. JSON é lido nas duas formas do mercado —
plana (`{"--brand": "#..."}`) e W3C/DTCG (`{"color": {"brand": {"$value":
"#..."}}}`, com `value` ou `$value`) — e o que não couber em nenhuma vira
linha de "não lidos" com o nome do arquivo, nunca um traceback.

Cor é comparada normalizada: caixa não conta, `#abc` é `#aabbcc`, e
`rgba(20, 31, 26, .10)` é `rgba(20,31,26,0.1)`. Nome também: `--`, caixa,
`_`/`.` e um prefixo `color-`/`cor-` são removidos antes de casar com a
direção, e todo casamento com grafia diferente é escrito no relatório.

Códigos de saída: 0 comparou; 2 pasta inexistente ou nenhum token lido.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css" / "app.css"

#: `--nome: valor` até `;`, chave, quebra de linha, aspas, crase ou barra
#: de tabela — assim a mesma regex lê CSS, o `<style>` de um HTML e o bloco
#: de código de um `.md` sem engolir a linha seguinte.
DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;{}\n\"'`|]+)")
HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
FUNCAO = re.compile(r"(?:rgba?|hsla?)\(.*\)", re.I)
NUMERO = re.compile(r"-?\d*\.?\d+$")
EXTENSOES = (".css", ".json", ".md", ".html")
PREFIXOS_DE_NOME = ("colors-", "color-", "cores-", "cor-")
MARCA_SEM_SPEC = "(não existe na spec)"


# A triagem é UMA, e mora na Task 8: o que ela chama de `interno` não é
# lido aqui. Dois caminhos de import porque o módulo é chamado de dois
# jeitos — como script (scripts/ é o sys.path[0]) e pela suíte (cwd na raiz).
try:
    from inventariar_export import classificar
except ImportError:
    from scripts.inventariar_export import classificar


@dataclass
class Leitura:
    """O que saiu do export: valores por nome, de onde vieram, o que não deu."""
    encontrados: dict = field(default_factory=dict)   # nome -> {valores como escritos}
    origens: dict = field(default_factory=dict)       # nome -> {caminho relativo}
    nao_lidos: list = field(default_factory=list)     # [(caminho relativo, motivo)]
    arquivos_lidos: int = 0


def e_cor(valor):
    valor = valor.strip()
    return bool(HEX.fullmatch(valor) or FUNCAO.fullmatch(valor))


def normalizar_cor(valor):
    """Duas grafias da mesma cor viram a mesma string; cores diferentes, não."""
    valor = " ".join(valor.split()).lower()  # espaço colapsado, nunca removido: `rgb(20 31 26)` tem três canais
    if HEX.fullmatch(valor):
        digitos = valor[1:]
        if len(digitos) in (3, 4):
            digitos = "".join(d * 2 for d in digitos)
        return "#" + digitos
    if FUNCAO.fullmatch(valor):
        funcao, resto = valor.split("(", 1)
        partes = []
        for parte in resto[:-1].split(","):
            parte = parte.strip()
            partes.append(format(float(parte), "g") if NUMERO.fullmatch(parte) else parte)
        return funcao.strip() + "(" + ",".join(partes) + ")"
    return valor


def normalizar_nome(nome):
    """`--Color-Brand`, `color.brand` e `--brand` casam com o mesmo token."""
    nome = nome.strip().lower().replace("_", "-").replace(".", "-")
    if nome.startswith("--"):
        nome = nome[2:]
    for prefixo in PREFIXOS_DE_NOME:
        if nome.startswith(prefixo) and len(nome) > len(prefixo):
            nome = nome[len(prefixo):]
            break
    return nome


def _nome_json(caminho):
    partes = [p[2:] if p.startswith("--") else p for p in caminho]
    return "--" + "-".join(partes)


def _percorrer_json(no, caminho, pares):
    if isinstance(no, dict):
        for chave in ("$value", "value"):
            if chave in no:
                if isinstance(no[chave], str) and caminho:
                    pares.append((_nome_json(caminho), no[chave]))
                return
        for chave, filho in no.items():
            if str(chave).startswith("$"):
                continue  # $type, $description: metadado do DTCG
            _percorrer_json(filho, caminho + [str(chave)], pares)
    elif isinstance(no, str) and caminho:
        pares.append((_nome_json(caminho), no))


def pares_do_json(texto):
    """(pares, motivo): pares vazios e motivo preenchido quando não deu para ler."""
    try:
        dados = json.loads(texto)
    except ValueError as erro:
        return [], "JSON inválido ({})".format(erro)
    if not isinstance(dados, dict):
        return [], "JSON sem objeto na raiz (forma desconhecida)"
    pares = []
    _percorrer_json(dados, [], pares)
    if not pares:
        return [], "JSON sem par nome/valor reconhecível (forma desconhecida)"
    return pares, None


def ler_export(raiz):
    raiz = Path(raiz)
    leitura = Leitura()
    for caminho in sorted(p for p in raiz.rglob("*") if p.is_file()):
        rel = caminho.relative_to(raiz).as_posix()
        if caminho.suffix.lower() not in EXTENSOES or classificar(rel) == "interno":
            continue
        try:
            texto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError as erro:
            leitura.nao_lidos.append((rel, "não deu para abrir ({})".format(erro.strerror or erro)))
            continue
        if caminho.suffix.lower() == ".json":
            pares, motivo = pares_do_json(texto)
            if motivo:
                leitura.nao_lidos.append((rel, motivo))
                continue
        else:
            pares = DECL.findall(texto)
        leitura.arquivos_lidos += 1
        for nome, valor in pares:
            valor = valor.strip()
            if e_cor(valor):
                leitura.encontrados.setdefault(nome, set()).add(valor)
                leitura.origens.setdefault(nome, set()).add(rel)
    return leitura


def extrair(raiz):
    """Nome da custom property → valores encontrados (a interface da Task 11)."""
    return ler_export(raiz).encontrados


def _spec(css=None):
    """A direção C: as cores Mesa do `:root` do app.css, na ordem do arquivo.

    `--ferro-*` mora no mesmo bloco e fica de fora — é o outro regime, e o
    export que trouxer Ferro é lido com o mesmo filtro (`relatorio`). Os
    comentários saem antes da leitura porque falam de cor em hex.
    """
    css = CSS.read_text(encoding="utf-8") if css is None else css
    bloco = re.sub(r"/\*.*?\*/", "", css, flags=re.S).split(":root {", 1)[1].split("}", 1)[0]
    spec = {}
    for nome, valor in DECL.findall(bloco):
        valor = valor.strip()
        if e_cor(valor) and not nome.startswith("--ferro-"):
            spec[nome] = valor
    return spec


def _balde():
    return {"nomes": set(), "valores": set(), "onde": set()}


def relatorio(leitura, spec):
    """Token a token da direção, mais os novos, o mapeamento e o que ficou."""
    indice = {}
    for nome in spec:
        indice.setdefault(normalizar_nome(nome), nome)
    por_spec, novos, ignorados = {}, {}, []
    for nome in sorted(leitura.encontrados):
        chave = normalizar_nome(nome)
        if chave.startswith("ferro-"):
            ignorados.append(nome)
            continue
        alvo = indice.get(chave)
        balde = por_spec.setdefault(alvo, _balde()) if alvo else novos.setdefault(chave, _balde())
        balde["nomes"].add(nome)
        balde["valores"] |= leitura.encontrados[nome]
        balde["onde"] |= leitura.origens.get(nome, set())

    linhas = []
    for nome, esperado in spec.items():
        balde = por_spec.get(nome)
        valores = sorted(balde["valores"]) if balde else []
        if not balde:
            estado = "ausente"
        else:
            iguais = [v for v in valores if normalizar_cor(v) == normalizar_cor(esperado)]
            estado = "igual" if len(iguais) == len(valores) else ("misto" if iguais else "diferente")
        linhas.append({
            "token": nome, "spec": esperado, "export": valores, "estado": estado,
            "nomes": sorted(balde["nomes"]) if balde else [],
            "onde": sorted(balde["onde"]) if balde else [],
        })
    mapeamento = [(n, linha["token"]) for linha in linhas for n in linha["nomes"] if n != linha["token"]]
    lista_novos = [
        (" / ".join(sorted(b["nomes"])), sorted(b["valores"]), sorted(b["onde"]))
        for _, b in sorted(novos.items())
    ]
    estados = [linha["estado"] for linha in linhas]
    resumo = {
        "iguais": estados.count("igual"),
        "diferentes": estados.count("diferente") + estados.count("misto"),
        "ausentes": estados.count("ausente"),
        "novos": len(lista_novos),
        "tokens_lidos": len(leitura.encontrados),
        "arquivos": leitura.arquivos_lidos,
    }
    return {
        "linhas": linhas, "novos": [(n, v) for n, v, _ in lista_novos], "novos_onde": lista_novos,
        "mapeamento": mapeamento, "ignorados": ignorados, "nao_lidos": list(leitura.nao_lidos), "resumo": resumo,
    }


def comparar(encontrados, spec):
    """Só o que difere, como (token, proposto, spec) — a tabela da Task 11.

    Token da direção com QUALQUER valor divergente no export entra (o
    "misto" também é proposta); token só do export entra com a marca.
    """
    rel = relatorio(Leitura(encontrados=dict(encontrados)), spec)
    difs = [
        (linha["token"], " / ".join(linha["export"]), linha["spec"])
        for linha in rel["linhas"] if linha["estado"] in ("diferente", "misto")
    ]
    difs += [(nome, " / ".join(valores), MARCA_SEM_SPEC) for nome, valores in rel["novos"]]
    return sorted(difs)


def _codigo(valores):
    return " / ".join("`{}`".format(v) for v in valores) if valores else "ausente"


def escrever_md(rel, origem):
    r = rel["resumo"]
    linhas = [
        "# Tokens do export × direção C (Mesa)",
        "",
        "Gerado por `scripts/tokens_do_export.py` em {} a partir de `{}`: {} token(s) lido(s) em {} arquivo(s). "
        "Dos {} tokens de cor da direção — **igual: {}**, **diferente: {}**, **ausente no export: {}**; "
        "**novo no export: {}**. A spec ganha — a coluna `motivo` da última tabela é escrita à mão.".format(
            datetime.now().strftime("%d/%m/%Y %H:%M"), origem, r["tokens_lidos"], r["arquivos"],
            len(rel["linhas"]), r["iguais"], r["diferentes"], r["ausentes"], r["novos"]),
        "",
        "## Token a token (ordem do `:root`)",
        "",
        "| token | direção C | export | estado | onde |", "|---|---|---|---|---|",
    ]
    for linha in rel["linhas"]:
        estado = linha["estado"] if linha["estado"] in ("igual", "ausente") else "**{}**".format(linha["estado"])
        linhas.append("| `{}` | `{}` | {} | {} | {} |".format(
            linha["token"], linha["spec"], _codigo(linha["export"]), estado, ", ".join(linha["onde"])))
    linhas += ["", "## Novos no export (não existem na direção)", ""]
    if rel["novos_onde"]:
        linhas += ["| token | valor | onde |", "|---|---|---|"]
        linhas += ["| `{}` | {} | {} |".format(nome, _codigo(valores), ", ".join(onde)) for nome, valores, onde in rel["novos_onde"]]
    else:
        linhas.append("Nenhum.")
    linhas += ["", "## Nomes traduzidos (grafia do export → token da direção)", ""]
    if rel["mapeamento"]:
        linhas += ["| no export | na direção |", "|---|---|"]
        linhas += ["| `{}` | `{}` |".format(a, b) for a, b in rel["mapeamento"]]
    else:
        linhas.append("Nenhum: todo nome casou como está.")
    linhas += ["", "## Ignorados (`--ferro-*`: o outro regime, fora desta comparação)", ""]
    linhas.append(", ".join("`{}`".format(n) for n in rel["ignorados"]) if rel["ignorados"] else "Nenhum.")
    linhas += ["", "## Não lidos", ""]
    if rel["nao_lidos"]:
        linhas += ["| arquivo | motivo |", "|---|---|"]
        linhas += ["| `{}` | {} |".format(a, m) for a, m in rel["nao_lidos"]]
    else:
        linhas.append("Nenhum: todo arquivo de token, referência ou classe incerta foi lido.")
    linhas += [
        "", "## Só as diferenças (a tabela para `proposto-nao-adotado.md`)", "",
        "| token | proposto pelo Claude Design | spec (direção C) | motivo |", "|---|---|---|---|",
    ]
    difs = [(l["token"], " / ".join(l["export"]), l["spec"]) for l in rel["linhas"] if l["estado"] in ("diferente", "misto")]
    difs += [(nome, " / ".join(valores), MARCA_SEM_SPEC) for nome, valores in rel["novos"]]
    linhas += ["| `{}` | `{}` | `{}` | |".format(*d) for d in sorted(difs)] or ["| — | — | — | nenhuma diferença |"]
    return "\n".join(linhas) + "\n"


def raiz_efetiva(raiz):
    """Quem passa a pasta de cima do zip extraído cai na pasta do export."""
    raiz = Path(raiz)
    aninhada = raiz / "design-system-export"
    if aninhada.is_dir() and not (raiz / "styles.css").exists() and not (raiz / "tokens").is_dir():
        return aninhada
    return raiz


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compara os tokens de cor do export do Claude Design com o :root do app.css.")
    parser.add_argument("pasta", type=Path, help="pasta do export extraído (design-system-export/ ou a de cima)")
    parser.add_argument("--saida", type=Path, help="grava o markdown aqui em vez de imprimir")
    args = parser.parse_args(argv)
    if not args.pasta.is_dir():
        print("pasta não existe: {}".format(args.pasta), file=sys.stderr)
        return 2
    raiz = raiz_efetiva(args.pasta)
    leitura = ler_export(raiz)
    if not leitura.encontrados:
        print("nenhum token lido em {} ({} arquivo(s) de texto percorrido(s))".format(raiz.as_posix(), leitura.arquivos_lidos))
        for rel, motivo in leitura.nao_lidos:
            print("  não lido: {} — {}".format(rel, motivo))
        return 2
    rel = relatorio(leitura, _spec())
    md = escrever_md(rel, origem=raiz.as_posix())
    if args.saida:
        args.saida.write_text(md, encoding="utf-8")
        r = rel["resumo"]
        print("{}: igual {} · diferente {} · ausente {} · novo {} · não lido {} → {}".format(
            raiz.as_posix(), r["iguais"], r["diferentes"], r["ausentes"], r["novos"], len(rel["nao_lidos"]), args.saida))
    else:
        print(md, end="")
    return 0


if __name__ == "__main__":
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")  # o markdown tem × e →; o console do Windows nem sempre
    sys.exit(main())
