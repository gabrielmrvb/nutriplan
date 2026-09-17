# -*- coding: utf-8 -*-
"""A medida caseira de uma quantidade: "7,5 colheres de sopa" para 116 g de aveia.

`FoodPortion` existia desde a primeira versão do catálogo (79 dos 102
alimentos, 85 porções) e nunca era lida fora do seed — a Home mostrava
"Aveia 116 g" (avaliação de 16/09, B15) em vez de "7,5 colheres de sopa",
que é o que uma pessoa de fato mede na cozinha.
"""
from decimal import Decimal, ROUND_HALF_UP

MEIO = Decimal("0.5")


def _formatar(n):
    # `Decimal.normalize()` some dígitos à direita, mas também troca para
    # notação científica quando isso encurta a representação — 150 g numa
    # colher de 15 g dava n = Decimal("10.0"), e normalize() virava "1E+1":
    # "1E+1 colheres de sopa (150 g)" na tela. n é sempre múltiplo de 0,5,
    # então basta decidir entre uma ou uma casa decimal.
    inteiro = n == n.to_integral_value()
    texto = str(n.quantize(Decimal("1") if inteiro else Decimal("0.1")))
    return texto.replace(".", ",")


def medida_caseira(quantidade_g, porcao):
    """`("7,5", "colheres de sopa")`, ou None quando não dá meia porção.

    Arredonda a MEIO pelo ROUND_HALF_UP do app (`plans/tracking.py`): 3,25
    porções viram 3,5, e 7,73 viram 7,5 — é o que uma colher consegue medir.
    Abaixo de meia porção a medida mentiria mais que a grama.

    O corte de meia porção é testado ANTES de arredondar, e não depois: 5 g
    de uma porção de 15 g são 0,333 porção, e arredondar primeiro (para o
    degrau de 0,5 mais próximo) levava esse valor a "0,5 colheres de sopa" —
    o teste com a fração real (1/3 de porção) pegou isso.
    """
    if porcao is None or not porcao.grams or not porcao.singular:
        return None
    razao = Decimal(quantidade_g) / Decimal(porcao.grams)
    if razao < MEIO:
        return None
    n = (razao / MEIO).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * MEIO
    rotulo = porcao.singular if n == 1 else porcao.plural
    return _formatar(n), rotulo
