# -*- coding: utf-8 -*-
"""Contraste WCAG de todo par texto/fundo e gráfico/fundo da direção C, medido
no CSS REAL (não na spec), Mesa e Ferro.

    .venv/Scripts/python.exe scripts/qa/auditar_contraste.py > scratchpad/shots-design/contraste.md

Par que reprova NÃO é corrigido aqui: vira item de BACKLOG com a correção
proposta — cor é decisão de direção. O script só MEDE, e para cada reprovado
calcula o hex vizinho mais próximo que passaria (afastando o primeiro plano
do fundo em luminância, 2% por passo, matiz preservado) e diz quantas regras
do `app.css` aquele token pinta — o raio da mudança, para quem decidir.

Ele reusa `_tokens` e `_contraste` de `config/tests.py` em vez de copiá-los:
é a MESMA régua da suíte, e a suíte é quem prova. `_tokens` resolve o `var()`
dos blocos-gatilho do Ferro contra o `:root`, onde os `--ferro-*` moram.

O que a suíte já guarda (para não confundir auditoria com regressão):
`ContrastTests` mede os três tons de texto sobre as quatro superfícies e
sobre os fundos tingidos, mais `PARES_MEDIDOS`; `PillContrastTests` mede o
texto sobre a própria tinta a 12%; a paleta dos dias mede `--on-brand` sobre
cada `--dia-*`, a cor sobre a tinta a 22% e sobre `--surface`. Esta auditoria
é o produto cartesiano — o que fica ENTRE esses testes.
"""
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from config.tests import _contraste, _luminancia, _tokens  # noqa: E402

#: Os dois regimes de luz e o texto que abre cada bloco no `app.css`. O do
#: Ferro é o mesmo que `ContrastTests` usa — o bloco `@media
#: (prefers-color-scheme: dark)`; `body.modo-foco` resolve para a MESMA
#: paleta e `test_modo_foco_is_the_dark_palette` é quem prova, então medir
#: um basta.
TEMAS = (("Mesa", ":root {"), ("Ferro", "prefers-color-scheme: dark) {" + chr(10) + "  :root {"))

#: Texto pequeno (AA, 1.4.3): 4,5:1. `--brand-strong` entrou porque o CSS o
#: pinta como TEXTO — `a:hover`, `.hoje__etiqueta` sobre `--surface-focus`,
#: `.series__item--feita` e `.descanso__relogio` sobre `--brand-soft`.
TEXTOS = ("--text", "--text-dim", "--text-mute", "--brand", "--brand-strong", "--agua-texto", "--brasa", "--terra", "--danger")
#: Todo fundo que recebe texto. `--canvas-topo` é o topo do gradiente do
#: `body`, onde a marca e o link do cabeçalho pousam — já ficou ilegível uma
#: vez, quando era um hex escrito à mão.
FUNDOS = ("--bg", "--surface", "--surface-2", "--surface-3", "--surface-focus", "--canvas-topo", "--brand-soft", "--terra-soft", "--danger-soft")
#: Objeto gráfico (1.4.11): 3:1. Arco do anel, coluna do gráfico, ponto do
#: ícone, filete do cartão do dia.
GRAFICOS = ("--folha", "--agua", "--brasa", "--terra", "--chama", "--carb", "--fat", "--dia-a", "--dia-b", "--dia-c", "--dia-d", "--dia-e")
SUPERFICIES = ("--bg", "--surface", "--surface-2", "--surface-3")
#: Pares que o CSS pinta e que não caem no produto cartesiano acima: texto
#: sobre a marca (botão primário, aba ativa) e sobre o hover dele; a folha
#: como borda de "feito" sobre o chip tonal; o texto do selo do dia.
ESPECIAIS = (
    ("--on-brand", "--brand", 4.5),
    ("--on-brand", "--brand-strong", 4.5),
    ("--folha", "--brand-soft", 3.0),
    ("--on-brand", "--dia-a", 4.5),
    ("--on-brand", "--dia-b", 4.5),
    ("--on-brand", "--dia-c", 4.5),
    ("--on-brand", "--dia-d", 4.5),
    ("--on-brand", "--dia-e", 4.5),
)
MINIMO_TEXTO, MINIMO_GRAFICO = 4.5, 3.0
#: "Passa raspando": até este tanto acima do mínimo, o par entra na segunda
#: tabela. É a folga que `--folha` sobre `--surface-3` tem hoje (0,03), e a
#: que o comentário do token diz não ser folga para gastar.
FOLGA_CURTA = 0.3
PASSO = 0.02


def sanidade():
    """Se a régua não é a que pensamos, nada abaixo vale — para aqui."""
    provas = (("#000000", "#ffffff", 21.0), ("#777777", "#ffffff", 4.48))
    linhas = []
    for cor, fundo, esperado in provas:
        medido = _contraste(cor, fundo)
        ok = abs(medido - esperado) <= 0.01
        linhas.append(f"- `_contraste({cor}, {fundo})` = {medido:.4f} (esperado {esperado}) {'ok' if ok else '**FALHOU**'}")
        if not ok:
            print("\n".join(linhas))
            sys.exit(2)
    return linhas


def _mistura(hexa, alvo, pct):
    a = [int(hexa.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    b = [int(alvo.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join("%02x" % round(a[i] * (1 - pct) + b[i] * pct) for i in range(3))


def propor(cor, fundos_e_minimos):
    """O vizinho mais próximo de `cor` que passa em TODOS os pares dados.

    Afasta a cor do fundo em luminância — clareia a que já é mais clara que
    o fundo (Ferro), escurece a que é mais escura (Mesa) —, misturando com
    branco ou preto em passos de 2%. Misturar com preto ou branco em sRGB
    não gira o matiz: o token continua sendo o mesmo verde, o mesmo âmbar.
    Devolve (hex, percentual) ou None quando nem 100% resolve.
    """
    fundo_ref = fundos_e_minimos[0][0]
    alvo = "#ffffff" if _luminancia(cor) > _luminancia(fundo_ref) else "#000000"
    for passo in range(1, int(1 / PASSO) + 1):
        candidato = _mistura(cor, alvo, passo * PASSO)
        if all(_contraste(candidato, fundo) >= minimo for fundo, minimo in fundos_e_minimos):
            return candidato, round(passo * PASSO * 100)
    return None


def pares_do_tema(tokens):
    pares = [(a, b, MINIMO_TEXTO) for a in TEXTOS for b in FUNDOS]
    pares += [(a, b, MINIMO_GRAFICO) for a in GRAFICOS for b in SUPERFICIES]
    pares += list(ESPECIAIS)
    return [(a, b, m) for a, b, m in pares if a in tokens and b in tokens]


def auditar(css):
    medidas = []  # (tema, cor, hex_cor, fundo, hex_fundo, razao, minimo)
    for tema, escopo in TEMAS:
        tokens = _tokens(css, escopo)
        for cor, fundo, minimo in pares_do_tema(tokens):
            razao = _contraste(tokens[cor], tokens[fundo])
            medidas.append((tema, cor, tokens[cor], fundo, tokens[fundo], razao, minimo))
    ordem = {tema: i for i, (tema, _) in enumerate(TEMAS)}
    medidas.sort(key=lambda m: (ordem[m[0]], m[5]))
    return medidas


def linha(m):
    tema, cor, hc, fundo, hf, razao, minimo = m
    veredito = "ok" if razao >= minimo else "**REPROVA**"
    return f"| {tema} | `{cor}` {hc} | `{fundo}` {hf} | {razao:.2f} | {minimo} | {veredito} |"


def raio(css, token):
    """Quantas regras do `app.css` leem o token — o tamanho da mudança."""
    return len(re.findall(r"var\(" + re.escape(token) + r"\)", css))


def ausentes(css):
    """Tokens das listas que o `:root` não declara como hex — para a
    auditoria dizer o que NÃO mediu em vez de pular em silêncio."""
    tokens = _tokens(css, ":root {")
    pedidos = set(TEXTOS) | set(FUNDOS) | set(GRAFICOS) | set(SUPERFICIES) | {a for a, _, _ in ESPECIAIS} | {b for _, b, _ in ESPECIAIS}
    return sorted(pedidos - set(tokens))


def relatorio(css):
    saida = []
    saida.append("# Contraste WCAG dos tokens da direção C, no CSS real")
    saida.append("")
    saida.append("Sanidade da régua (`config.tests._contraste`):")
    saida.extend(sanidade())
    faltando = ausentes(css)
    if faltando:
        saida.append("")
        saida.append("Tokens pedidos que o `:root` não declara como hex (não medidos): " + ", ".join(f"`{t}`" for t in faltando))
    tokens_ferro = _tokens(css, TEMAS[1][1])
    saida.append("")
    saida.append(f"Âncora do Ferro: `{TEMAS[1][1]!r}` — resolve `--bg` para `{tokens_ferro.get('--bg')}`, `--text` para `{tokens_ferro.get('--text')}`.")

    medidas = auditar(css)
    reprovados = [m for m in medidas if m[5] < m[6]]
    raspando = [m for m in medidas if m[6] <= m[5] < m[6] + FOLGA_CURTA]

    saida.append("")
    saida.append("## Todos os pares, por tema e razão crescente")
    saida.append("")
    saida.append("| tema | texto/gráfico | fundo | razão | mínimo | veredito |")
    saida.append("|---|---|---|---:|---:|---|")
    saida.extend(linha(m) for m in medidas)

    saida.append("")
    for tema, _ in TEMAS:
        do_tema = [m for m in medidas if m[0] == tema]
        rep = [m for m in do_tema if m[5] < m[6]]
        saida.append(f"**{tema}: {len(do_tema)} pares, {len(rep)} reprovados.**")
    saida.append("")
    saida.append(f"**{len(medidas)} pares, {len(reprovados)} reprovados.**")

    saida.append("")
    saida.append("## Reprovados, com a correção PROPOSTA (não aplicada)")
    saida.append("")
    if not reprovados:
        saida.append("Nenhum.")
    for tema, cor, hc, fundo, hf, razao, minimo in reprovados:
        proposta = propor(hc, [(hf, minimo)])
        if proposta:
            hex_novo, pct = proposta
            nova = _contraste(hex_novo, hf)
            texto = f"proposta: `{cor}` → `{hex_novo}` ({pct}% para {'o branco' if _luminancia(hc) > _luminancia(hf) else 'o preto'}), daria {nova:.2f}"
        else:
            texto = "proposta: nenhum vizinho por mistura resolve — o FUNDO é que teria de mudar"
        saida.append(f"- {tema}: `{cor}` {hc} sobre `{fundo}` {hf} = {razao:.2f} (mínimo {minimo}); {texto}; `{cor}` pinta {raio(css, cor)} regra(s) do `app.css`")

    # Um hex por TOKEN que fecha todos os pares reprovados dele no tema —
    # é isso que o dono aplicaria de fato, não um valor por par.
    por_token = {}
    for tema, cor, hc, fundo, hf, razao, minimo in reprovados:
        por_token.setdefault((tema, cor, hc), []).append((hf, minimo, fundo))
    if por_token:
        saida.append("")
        saida.append("Um valor por token, fechando todos os pares reprovados dele:")
        for (tema, cor, hc), lista in por_token.items():
            proposta = propor(hc, [(hf, minimo) for hf, minimo, _ in lista])
            fundos = ", ".join(f"`{f}`" for _, _, f in lista)
            if proposta:
                hex_novo, pct = proposta
                pior = min(_contraste(hex_novo, hf) for hf, _, _ in lista)
                saida.append(f"- {tema}: `{cor}` {hc} → `{hex_novo}` ({pct}%) fecha {len(lista)} par(es) ({fundos}); pior caso passa a {pior:.2f}")
            else:
                saida.append(f"- {tema}: `{cor}` {hc} — nenhuma mistura fecha {fundos}")

    saida.append("")
    saida.append(f"## Pares que passam com folga < {FOLGA_CURTA:.1f} (raspando)")
    saida.append("")
    if not raspando:
        saida.append("Nenhum.")
    else:
        saida.append("| tema | texto/gráfico | fundo | razão | mínimo | folga |")
        saida.append("|---|---|---|---:|---:|---:|")
        for tema, cor, hc, fundo, hf, razao, minimo in raspando:
            saida.append(f"| {tema} | `{cor}` {hc} | `{fundo}` {hf} | {razao:.2f} | {minimo} | {razao - minimo:.2f} |")
    return "\n".join(saida)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
    print(relatorio(css))
