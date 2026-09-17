# -*- coding: utf-8 -*-
"""Pontos de uma polilinha SVG a partir de uma lista de valores.

Apresentação, não cálculo: nenhum número novo nasce aqui — é a generalização
de `plans.views._curva_de_peso` para qualquer série de valores (a carga
máxima por sessão de um exercício, hoje), com as mesmas três decisões:
escala do próprio período (zero-based esconderia a variação), piso para a
faixa estreita não virar montanha, e nada com menos de dois pontos.
"""


def curva(valores, largura=300, altura=64, piso=0.4):
    """`valores` do mais ANTIGO ao mais NOVO. Devolve None com menos de dois.

    `"final"` é o ÚLTIMO valor da lista — não o maior da série —, porque é
    isso que o rótulo acessível e o ponto em destaque (`"ultimo"`) precisam
    mostrar: onde a pessoa está agora, não o recorde do período.
    """
    pontos = [float(v) for v in valores if v is not None]
    if len(pontos) < 2:
        return None
    menor, maior = min(pontos), max(pontos)
    faixa = max(maior - menor, piso)
    passo = largura / (len(pontos) - 1)
    coords = []
    for i, valor in enumerate(pontos):
        x = i * passo
        # y invertido: em SVG a origem é em cima, e valor maior tem de subir.
        y = altura - (valor - menor) / faixa * altura
        coords.append((round(x, 1), round(y, 1)))
    return {
        "largura": largura,
        "altura": altura,
        "pontos": " ".join("%g,%g" % c for c in coords),
        "ultimo": coords[-1],
        "primeiro": pontos[0],
        "final": pontos[-1],
    }
