"""Desenha o ícone do NutriPlan e o rasteriza sem biblioteca de imagem.

    .venv/Scripts/python.exe scripts/gerar_icones.py

Por que existe um rasterizador escrito à mão aqui: não há Pillow, cairosvg nem
node nesta máquina, e o ícone precisa sair em PNG para o manifesto do PWA. As
únicas dependências são `zlib` e `struct`, que vêm com o Python.

A DECISÃO QUE ORGANIZA O ARQUIVO

A geometria é definida UMA vez, em coordenadas de 0 a 1, e serve às duas
saídas: o SVG é emitido a partir dela, e o PNG é rasterizado a partir dela.

A alternativa seria escrever o SVG à mão e um parser de SVG para gerar o PNG —
e aí eu teria dois desenhos que precisam concordar, mais um parser para manter.
Com uma fonte só, o SVG e o PNG não têm como divergir.

O DESENHO

Anel e "N", em duas metáforas que cabem em duas formas:

  O ANEL é prato e é anilha ao mesmo tempo — comida e treino na mesma silhueta.
  Foi escolhido por ser a forma que SOBREVIVE a 16 pixels: círculo é a figura
  mais reconhecível que existe em tamanho pequeno.

  A DIAGONAL do N tem um vinco no meio, como raio. É a energia, e é sutil de
  propósito: a 16px ela lê como uma diagonal comum, e o vinco só aparece nos
  tamanhos em que há pixel para ele.

Não há folha. Uma folha ocuparia 3 pixels no favicon e viraria ruído — e o
anel já carrega a metáfora de nutrição. Duas formas, duas leituras; três formas
seria uma mancha.
"""
import math
import struct
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "static" / "icons"

# ---------------------------------------------------------------- paleta
FUNDO = (0x0D, 0x0F, 0x12)
MARCA = (0x10, 0xB9, 0x81)

#: O anel é a mesma cor da marca, mais apagado. Cheio, ele disputaria atenção
#: com o "N" e o ícone viraria duas formas brigando.
#:
#: Começou em 40% e não sobrevivia a 16px: um pixel de espessura a 40% de
#: opacidade é um cinza que o olho não separa do fundo.
ANEL_ALFA = 0.55

# ------------------------------------------------------------- geometria
#: Tudo em coordenadas de 0 a 1, para o desenho não depender do tamanho.

QUINA = 0.225          # canto da placa, na proporção do lado

#: A proporção foi MEDIDA, e não escolhida a olho.
#:
#: A primeira versão tinha o "N" ocupando 37% da largura com haste de 7%. Num
#: favicon de 16px isso dá seis pixels de letra e haste de UM — e a medição
#: mostrou o resultado: o perfil de tinta a 16px era ".....++...+....."; três
#: colunas fracas, sem silhueta de N nenhuma.
#:
#: O anel some primeiro. A 40% de opacidade e um pixel de espessura ele vira
#: um cinza indistinguível do fundo. Subiu para 55% e engrossou.
ANEL_EXTERNO = 0.470
ANEL_INTERNO = 0.400

HASTE = 0.105          # espessura das hastes verticais do N
TOPO, BASE = 0.255, 0.745
ESQ, DIR = 0.245, 0.755

#: O vinco da diagonal. Sem ele, a reta de canto a canto passaria em x=0,465 e
#: x=0,535 na meia-altura; o desvio para a esquerda é o que faz a diagonal
#: curvar como raio em vez de descer reta.
VINCO_X = 0.395
VINCO_LARGURA = 0.130


def _n_diagonal():
    """A diagonal do N como polígono, com o vinco no meio."""
    return [
        (ESQ, TOPO),
        (ESQ + HASTE, TOPO),
        (VINCO_X + VINCO_LARGURA, 0.5),
        (DIR, BASE),
        (DIR - HASTE, BASE),
        (VINCO_X, 0.5),
    ]


def _formas():
    """As figuras do ícone, do fundo para a frente.

    Cada uma é `(tipo, dados, cor, alfa)`. A ordem é a de pintura.
    """
    return [
        ("quina", (QUINA,), FUNDO, 1.0),
        ("anel", (ANEL_EXTERNO, ANEL_INTERNO), MARCA, ANEL_ALFA),
        ("retangulo", (ESQ, TOPO, ESQ + HASTE, BASE), MARCA, 1.0),
        ("retangulo", (DIR - HASTE, TOPO, DIR, BASE), MARCA, 1.0),
        ("poligono", _n_diagonal(), MARCA, 1.0),
    ]


# ------------------------------------------------------- testes de dentro

def _dentro_quina(x, y, r):
    """Quadrado de cantos arredondados, em coordenadas de 0 a 1."""
    if r <= 0:
        return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
    cx = min(max(x, r), 1 - r)
    cy = min(max(y, r), 1 - r)
    if x == cx or y == cy:
        return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _dentro_anel(x, y, externo, interno):
    d2 = (x - 0.5) ** 2 + (y - 0.5) ** 2
    return interno * interno <= d2 <= externo * externo


def _dentro_retangulo(x, y, x0, y0, x1, y1):
    return x0 <= x <= x1 and y0 <= y <= y1


def _dentro_poligono(x, y, pontos):
    """Regra do cruzamento — o algoritmo do raio horizontal."""
    dentro = False
    n = len(pontos)
    j = n - 1
    for i in range(n):
        xi, yi = pontos[i]
        xj, yj = pontos[j]
        if (yi > y) != (yj > y):
            corte = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < corte:
                dentro = not dentro
        j = i
    return dentro


def _pertence(forma, x, y):
    tipo, dados = forma[0], forma[1]
    if tipo == "quina":
        return _dentro_quina(x, y, *dados)
    if tipo == "anel":
        return _dentro_anel(x, y, *dados)
    if tipo == "retangulo":
        return _dentro_retangulo(x, y, *dados)
    return _dentro_poligono(x, y, dados)


# ------------------------------------------------------------ rasterizar

def rasterizar(lado, formas, amostras=4, escala=1.0):
    """Devolve os bytes RGBA da imagem, com anti-serrilhado por supersampling.

    `amostras` é a raiz: 4 significa 16 pontos por pixel. É o que transforma a
    borda do círculo de uma escada em uma transição — sem isso o anel fica
    visivelmente serrilhado já a 192px.

    `escala` encolhe o DESENHO dentro da tela, sem mexer no fundo: é o que
    produz a variante `maskable`, que precisa de margem porque o Android
    recorta o ícone no formato que o fabricante escolher.
    """
    passo = 1.0 / (lado * amostras)
    meio = passo / 2
    peso = 1.0 / (amostras * amostras)
    linhas = bytearray()

    for py in range(lado):
        linha = bytearray()
        for px in range(lado):
            r = g = b = a = 0.0
            for sy in range(amostras):
                y = (py * amostras + sy) * passo + meio
                for sx in range(amostras):
                    x = (px * amostras + sx) * passo + meio

                    # Cada amostra é composta de trás para frente.
                    cr = cg = cb = ca = 0.0
                    for indice, forma in enumerate(formas):
                        # O fundo ocupa a tela toda; o desenho encolhe dentro
                        # dela quando `escala` é menor que 1.
                        if indice == 0:
                            ax, ay = x, y
                        else:
                            ax = (x - 0.5) / escala + 0.5
                            ay = (y - 0.5) / escala + 0.5
                            if not (0.0 <= ax <= 1.0 and 0.0 <= ay <= 1.0):
                                continue

                        if not _pertence(forma, ax, ay):
                            continue

                        cor, alfa = forma[2], forma[3]
                        cr = cor[0] * alfa + cr * (1 - alfa)
                        cg = cor[1] * alfa + cg * (1 - alfa)
                        cb = cor[2] * alfa + cb * (1 - alfa)
                        ca = alfa + ca * (1 - alfa)

                    r += cr * peso
                    g += cg * peso
                    b += cb * peso
                    a += ca * peso

            linha += bytes(
                (
                    int(round(min(255, max(0, r)))),
                    int(round(min(255, max(0, g)))),
                    int(round(min(255, max(0, b)))),
                    int(round(min(255, max(0, a * 255)))),
                )
            )
        # Byte de filtro 0 (nenhum) na frente de cada linha: o PNG permite
        # cinco filtros por linha, e o ganho de compressão num desenho chapado
        # como este não paga a complexidade.
        linhas += b"\x00" + linha

    return bytes(linhas)


# ----------------------------------------------------------------- PNG

def _bloco(tipo, dados):
    """Um chunk de PNG: tamanho, tipo, dados e CRC do par tipo+dados."""
    return (
        struct.pack(">I", len(dados))
        + tipo
        + dados
        + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    )


def escrever_png(caminho, lado, pixels):
    cabecalho = struct.pack(
        ">IIBBBBB",
        lado,
        lado,
        8,      # bits por canal
        6,      # cor 6 = RGBA
        0,      # compressão padrão
        0,      # filtro padrão
        0,      # sem entrelaçamento
    )
    conteudo = (
        b"\x89PNG\r\n\x1a\n"
        + _bloco(b"IHDR", cabecalho)
        + _bloco(b"IDAT", zlib.compress(pixels, 9))
        + _bloco(b"IEND", b"")
    )
    caminho.write_bytes(conteudo)
    return len(conteudo)


def escrever_ico(caminho, tamanhos_e_pngs):
    """Um .ico com PNGs embutidos.

    O formato aceita PNG desde o Vista, e é o que evita converter o desenho
    para bitmap com máscara — que é a parte do ICO que dá errado.
    """
    n = len(tamanhos_e_pngs)
    cabecalho = struct.pack("<HHH", 0, 1, n)
    entradas = b""
    corpo = b""
    deslocamento = 6 + 16 * n
    for lado, dados in tamanhos_e_pngs:
        entradas += struct.pack(
            "<BBBBHHII",
            0 if lado >= 256 else lado,
            0 if lado >= 256 else lado,
            0,          # cores da paleta: 0 = sem paleta
            0,          # reservado
            1,          # planos
            32,         # bits por pixel
            len(dados),
            deslocamento,
        )
        corpo += dados
        deslocamento += len(dados)
    caminho.write_bytes(cabecalho + entradas + corpo)
    return len(cabecalho + entradas + corpo)


# ----------------------------------------------------------------- SVG

def _svg_caminho_poligono(pontos, lado):
    partes = [f"M{pontos[0][0] * lado:.2f} {pontos[0][1] * lado:.2f}"]
    for x, y in pontos[1:]:
        partes.append(f"L{x * lado:.2f} {y * lado:.2f}")
    partes.append("Z")
    return "".join(partes)


def escrever_svg(caminho, lado=64):
    """O mesmo desenho, em vetor.

    Sai da MESMA geometria que o PNG. Escrito à mão, ele começaria a divergir
    do PNG na primeira vez que alguém ajustasse um número num só dos dois.
    """
    r = QUINA * lado
    cor = f"#{MARCA[0]:02x}{MARCA[1]:02x}{MARCA[2]:02x}"
    fundo = f"#{FUNDO[0]:02x}{FUNDO[1]:02x}{FUNDO[2]:02x}"
    meio = lado / 2

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lado} {lado}"
     width="{lado}" height="{lado}" role="img" aria-label="NutriPlan">
  <title>NutriPlan</title>
  <rect width="{lado}" height="{lado}" rx="{r:.2f}" fill="{fundo}"/>
  <circle cx="{meio:.2f}" cy="{meio:.2f}"
          r="{(ANEL_EXTERNO + ANEL_INTERNO) / 2 * lado:.2f}"
          fill="none" stroke="{cor}"
          stroke-width="{(ANEL_EXTERNO - ANEL_INTERNO) * lado:.2f}"
          opacity="{ANEL_ALFA}"/>
  <rect x="{ESQ * lado:.2f}" y="{TOPO * lado:.2f}"
        width="{HASTE * lado:.2f}" height="{(BASE - TOPO) * lado:.2f}" fill="{cor}"/>
  <rect x="{(DIR - HASTE) * lado:.2f}" y="{TOPO * lado:.2f}"
        width="{HASTE * lado:.2f}" height="{(BASE - TOPO) * lado:.2f}" fill="{cor}"/>
  <path d="{_svg_caminho_poligono(_n_diagonal(), lado)}" fill="{cor}"/>
</svg>
"""
    caminho.write_text(svg, encoding="utf-8")
    return len(svg)


# ---------------------------------------------------------------- roteiro

def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    formas = _formas()

    tamanho_svg = escrever_svg(DESTINO / "favicon.svg")
    print(f"  favicon.svg              {tamanho_svg:>6} B")

    # `maskable` com 78% do desenho: o Android recorta num círculo que deixa
    # cerca de 80% do lado visível, e a margem é o que impede a letra de sair
    # cortada em metade dos aparelhos.
    saidas = [
        ("icon-192.png", 192, 1.0),
        ("icon-512.png", 512, 1.0),
        ("icon-192-maskable.png", 192, 0.78),
        ("icon-512-maskable.png", 512, 0.78),
    ]
    for nome, lado, escala in saidas:
        pixels = rasterizar(lado, formas, amostras=4, escala=escala)
        n = escrever_png(DESTINO / nome, lado, pixels)
        print(f"  {nome:<24} {n:>6} B")

    # O favicon clássico, para o que não entende SVG.
    pequenos = []
    for lado in (16, 32, 48):
        pixels = rasterizar(lado, formas, amostras=8, escala=1.0)
        caminho = DESTINO / f"_tmp-{lado}.png"
        escrever_png(caminho, lado, pixels)
        pequenos.append((lado, caminho.read_bytes()))
        caminho.unlink()
    n = escrever_ico(DESTINO / "favicon.ico", pequenos)
    print(f"  favicon.ico              {n:>6} B  (16, 32, 48)")


if __name__ == "__main__":
    main()
