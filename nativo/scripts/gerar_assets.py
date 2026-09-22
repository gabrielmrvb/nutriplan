# -*- coding: utf-8 -*-
"""As FONTES dos ícones e splash das lojas, derivadas da arte aprovada.

Lê `assets/nutriplan-icon-source.png` (a mesma arte de que
`scripts/gerar_identidade.ps1` tira os ícones do PWA; as medidas do símbolo
são as de lá: x 335..964, y 299..826, o N com a folha, SEM o wordmark) e
escreve em `nativo/assets/` o que `@capacitor/assets` pede:

    icon-only.png        1024×1024, fundo sólido, para iOS e a loja (sem alfa: a Apple recusa)
    icon-foreground.png  1024×1024, símbolo sobre transparente (adaptive icon do Android)
    icon-background.png  1024×1024, só o fundo (adaptive icon do Android)
    splash.png           2732×2732, símbolo pequeno sobre o chão do Ferro
    splash-dark.png      idem — a marca não muda de cor com o tema (partials/marca.html)

E o ícone do push do Android (`android/app/src/main/res/drawable-*/ic_stat_nutriplan.png`,
24 dp em mdpi…xxxhdpi): a silhueta do símbolo em BRANCO sobre transparente —
a barra de status pinta o ícone com uma cor só, e o ícone do app viraria um
quadrado branco.

Depois: `npm run assets` gera todos os tamanhos nas duas plataformas.

Roda com o Python do repositório:  ../.venv/Scripts/python.exe scripts/gerar_assets.py
"""
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[2]
FONTE = RAIZ / "assets" / "nutriplan-icon-source.png"
SAIDA = RAIZ / "nativo" / "assets"
SIMBOLO = (335, 299, 964, 826)
VERDE_FLORESTA = (7, 37, 24)   # o sólido do maskable (média do fundo da placa)
CHAO_FERRO = (11, 20, 15)      # --ferro-bg / PWA_THEME_COLOR (#0b140f)


def simbolo_recortado():
    """O símbolo com o fundo da placa virando transparência: o fundo é um
    gradiente de verde-escuro, e o que não é fundo (branco do N, verde da
    folha) fica opaco. A máscara é por distância ao verde-floresta."""
    arte = Image.open(FONTE).convert("RGB").crop(SIMBOLO)
    largura, altura = arte.size
    saida = Image.new("RGBA", arte.size)
    fonte = arte.load()
    dest = saida.load()
    fr, fg, fb = VERDE_FLORESTA
    for y in range(altura):
        for x in range(largura):
            r, g, b = fonte[x, y]
            distancia = max(abs(r - fr), abs(g - fg), abs(b - fb))
            # fundo puro (distância pequena) -> transparente; borda -> alfa parcial
            alfa = 0 if distancia < 18 else 255 if distancia > 60 else int((distancia - 18) * 255 / 42)
            dest[x, y] = (r, g, b, alfa)
    return saida


def compor(lado, fracao, fundo, simbolo, com_fundo=True):
    tela = Image.new("RGBA", (lado, lado), fundo + (255,) if com_fundo else (0, 0, 0, 0))
    alvo = int(lado * fracao)
    escala = alvo / max(simbolo.size)
    redimensionado = simbolo.resize((max(1, round(simbolo.width * escala)), max(1, round(simbolo.height * escala))), Image.LANCZOS)
    x = (lado - redimensionado.width) // 2
    y = (lado - redimensionado.height) // 2
    tela.alpha_composite(redimensionado, (x, y))
    return tela


DENSIDADES = {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}


def icone_do_push(simbolo):
    """Silhueta: todo pixel opaco do símbolo vira branco, o alfa fica."""
    branco = Image.new("RGBA", simbolo.size, (255, 255, 255, 0))
    branco.putalpha(simbolo.getchannel("A"))
    res = RAIZ / "nativo" / "android" / "app" / "src" / "main" / "res"
    for densidade, lado in DENSIDADES.items():
        pasta = res / ("drawable-" + densidade)
        pasta.mkdir(parents=True, exist_ok=True)
        compor(lado, 0.9, (0, 0, 0), branco, com_fundo=False).save(pasta / "ic_stat_nutriplan.png")


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    simbolo = simbolo_recortado()
    icone_do_push(simbolo)
    compor(1024, 0.62, VERDE_FLORESTA, simbolo).convert("RGB").save(SAIDA / "icon-only.png")
    compor(1024, 0.55, VERDE_FLORESTA, simbolo, com_fundo=False).save(SAIDA / "icon-foreground.png")
    Image.new("RGB", (1024, 1024), VERDE_FLORESTA).save(SAIDA / "icon-background.png")
    splash = compor(2732, 0.22, CHAO_FERRO, simbolo).convert("RGB")
    splash.save(SAIDA / "splash.png")
    splash.save(SAIDA / "splash-dark.png")
    for nome in ("icon-only", "icon-foreground", "icon-background", "splash", "splash-dark"):
        arquivo = SAIDA / (nome + ".png")
        print("%-20s %s %d KB" % (nome, Image.open(arquivo).size, arquivo.stat().st_size // 1024))


if __name__ == "__main__":
    main()
