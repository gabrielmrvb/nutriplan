# -*- coding: utf-8 -*-
"""Gera os ícones do PWA a partir do desenho da marca.

    .venv/Scripts/python.exe scripts/make_icons.py

Por que gerar em vez de versionar um PNG pronto: o ícone é derivado das cores
da marca, que já estão no CSS. Quando a paleta muda — e ela mudou — regenerar é
um comando, contra abrir editor de imagem e exportar quatro arquivos na mão.

Escreve PNG sem dependência externa (só `zlib` e `struct` da biblioteca padrão),
porque instalar Pillow para desenhar um retângulo e uma letra não se paga.

Dois formatos, e a diferença entre eles importa:

* **any** — o ícone como ele é, ocupando quase toda a arte. É o que aparece na
  aba do navegador e em sistemas que não recortam.
* **maskable** — o Android recorta o ícone na forma que o fabricante escolher
  (círculo, quadrado arredondado, gota). Só a "zona segura", o círculo central
  com 80% do lado, sobrevive garantidamente. Por isso a versão maskable desenha
  a letra bem menor, com fundo sangrando até a borda: o que for cortado é fundo.
"""
import struct
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "static" / "icons"

#: Grafite do tema escuro e o verde-menta da marca — os mesmos tokens do CSS.
FUNDO = (11, 15, 14)
MARCA = (74, 222, 155)


def png(largura: int, altura: int, pixels) -> bytes:
    """Codifica uma matriz RGB em PNG."""
    linhas = b"".join(
        b"\x00" + b"".join(bytes(pixel) for pixel in linha) for linha in pixels
    )

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        conteudo = tipo + dados
        return (
            struct.pack(">I", len(dados))
            + conteudo
            + struct.pack(">I", zlib.crc32(conteudo) & 0xFFFFFFFF)
        )

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", cabecalho)
        + bloco(b"IDAT", zlib.compress(linhas, 9))
        + bloco(b"IEND", b"")
    )


def desenhar_n(lado: int, escala: float):
    """A letra N, centralizada, ocupando `escala` do lado da arte.

    Desenhada como três formas (haste esquerda, haste direita e a diagonal),
    porque escrever um renderizador de fonte para uma letra só seria trocar um
    problema simples por um caro.
    """
    pixels = [[FUNDO for _ in range(lado)] for _ in range(lado)]

    altura = lado * escala
    largura = altura * 0.78
    esquerda = (lado - largura) / 2
    topo = (lado - altura) / 2
    haste = largura * 0.26

    def dentro_da_diagonal(x, y):
        # A diagonal vai do canto superior esquerdo ao inferior direito da
        # letra; a espessura é medida na horizontal, que é o que faz o traço
        # parecer uniforme sem calcular distância perpendicular.
        progresso = (y - topo) / altura
        centro = esquerda + haste / 2 + progresso * (largura - haste)
        return abs(x - centro) <= haste * 0.62

    for y in range(lado):
        if not (topo <= y <= topo + altura):
            continue
        for x in range(lado):
            if not (esquerda <= x <= esquerda + largura):
                continue
            na_esquerda = x <= esquerda + haste
            na_direita = x >= esquerda + largura - haste
            if na_esquerda or na_direita or dentro_da_diagonal(x, y):
                pixels[y][x] = MARCA
    return pixels


def gerar(nome: str, lado: int, escala: float):
    caminho = DESTINO / nome
    caminho.write_bytes(png(lado, lado, desenhar_n(lado, escala)))
    print(f"  {nome}: {lado}x{lado}, {caminho.stat().st_size} bytes")


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    print("Ícones do PWA:")
    # `any`: a letra ocupa 62% da arte, como um ícone de app comum.
    gerar("icon-192.png", 192, 0.62)
    gerar("icon-512.png", 512, 0.62)
    # `maskable`: 42% deixa margem para qualquer recorte do Android.
    gerar("icon-192-maskable.png", 192, 0.42)
    gerar("icon-512-maskable.png", 512, 0.42)
