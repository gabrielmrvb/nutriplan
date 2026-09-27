"""Distância escrita de um jeito só (QA de 27/09/2026, M2).

Até duas casas, sem zero à direita, com vírgula decimal: 5,2 · 5,23 · 10. A
mesma corrida aparecia como "5,20 km" na lista (o filtro `km` da corrida) e
"5,2 km" na Home (`floatformat:1`, que ainda cortava "5,23" para "5,2").

A CARGA vai usar a mesma função (M1: "40×6" ao lado de "42,50×6"), mas os
testes que cobram "62,50" moram em `workouts/`, onde a missão-mãe está
trabalhando — fica para a parte 2, registrada no ledger.

Registrado como biblioteca EMBUTIDA (`TEMPLATES["OPTIONS"]["builtins"]`): o
filtro existe em todo template sem `{% load %}`. `config/test_numeros.py`
varre `templates/` atrás do formato antigo.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()


def decimal_curto(valor, casas=2) -> str:
    numero = Decimal(str(valor)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    texto = format(numero, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return "0" if texto in ("-0", "") else texto.replace(".", ",")


@register.filter
def distancia(metros):
    """Metros para quilômetros: `5230` vira "5,23"."""
    try:
        return decimal_curto(Decimal(str(metros)) / 1000)
    except (InvalidOperation, TypeError, ValueError):
        return "—"
