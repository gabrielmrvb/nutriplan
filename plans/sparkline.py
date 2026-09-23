"""A linha fina de uma série de números — e a régua de quando ela pode existir.

POR QUE UM MÓDULO, E POR QUE PURO
---------------------------------
Dois cartões da Home desenham uma: a quilometragem das últimas semanas e a
curva do peso. O desenho é o mesmo e a REGRA é a mesma — e a regra é de
produto, não de estilo: **gráfico não é enfeite**. Com um ponto, ou dois, uma
linha não mostra tendência nenhuma; ela só desenha algo onde não há nada a
ver. `MINIMO_DE_PONTOS` é onde essa decisão mora, e é o que o cartão pergunta
antes de emitir o `<svg>`.

Nada aqui abre consulta nem olha o relógio: recebe uma lista de números e
devolve coordenadas. É o que permite provar a régua sem banco — inclusive o
caso que enganaria uma versão ingênua, a série CHATA (todos os valores
iguais), em que a normalização dividiria por zero.
"""
from dataclasses import dataclass

#: Abaixo disto não há linha. Três é o primeiro número em que existe
#: "tendência": dois pontos são sempre uma reta, e uma reta não informa se o
#: peso está caindo ou se aquelas foram as duas únicas vezes em que alguém se
#: pesou.
MINIMO_DE_PONTOS = 3

#: O sistema de coordenadas do `<svg>`. A PROPORÇÃO é a decisão aqui: 5 para
#: 1. O `viewBox` manda na altura renderizada (a largura vem do CSS e a altura
#: sai da proporção), e a 100×32 a linha do cartão de Progresso saía com 114px
#: de altura a 390px — mais alta que o número que ela acompanha. A margem
#: vertical existe para o círculo da ponta não sair cortado pela metade: ele
#: tem raio 3 e o traço da linha tem 2.
LARGURA = 120
ALTURA = 24
MARGEM = 4


@dataclass
class Linha:
    """A linha pronta para o template: pontos, a ponta e os extremos.

    AS COORDENADAS SÃO TEXTO, e isso não é detalhe de estilo. O projeto é
    pt-BR com `USE_L10N`: um `float` no template sai com VÍRGULA decimal, e
    `cx="100,0"` é um valor inválido que o SVG descarta em silêncio — o
    círculo da ponta ia para a origem do `viewBox`, no canto esquerdo, longe
    da linha (visto na captura da rodada 1). O `points` do `<polyline>` nunca
    teve o problema porque já era uma string montada aqui.
    """

    pontos: str
    fim_x: str
    fim_y: str
    minimo: float
    maximo: float

    @property
    def largura(self) -> int:
        return LARGURA

    @property
    def altura(self) -> int:
        return ALTURA


def desenhar(valores) -> Linha:
    """As coordenadas de uma série, ou `None` quando ela é curta demais.

    `None` e não uma linha vazia: o template pergunta `{% if %}`, e um objeto
    que existe mas não desenha nada é a forma mais fácil de acabar com um
    retângulo vazio na tela — exatamente o buraco que a auditoria de 22/09
    aponta em cartão sem dado.
    """
    valores = [float(v) for v in valores]
    if len(valores) < MINIMO_DE_PONTOS:
        return None

    menor, maior = min(valores), max(valores)
    # Série CHATA: seis pesagens no mesmo peso são um dado legítimo, e
    # `(v - menor) / 0` não é. Ela desenha no meio da caixa, que é a verdade
    # do que aconteceu — nada subiu e nada desceu.
    amplitude = (maior - menor) or 1.0
    achatada = maior == menor

    util = ALTURA - 2 * MARGEM
    passo = LARGURA / (len(valores) - 1)
    pares = []
    for indice, valor in enumerate(valores):
        x = round(indice * passo, 2)
        if achatada:
            y = round(ALTURA / 2, 2)
        else:
            # y cresce para baixo no SVG: o MAIOR valor tem de ficar no topo.
            y = round(MARGEM + util - (valor - menor) / amplitude * util, 2)
        pares.append((x, y))

    return Linha(
        pontos=" ".join("%s,%s" % par for par in pares),
        fim_x="%s" % pares[-1][0],
        fim_y="%s" % pares[-1][1],
        minimo=menor, maximo=maior,
    )
