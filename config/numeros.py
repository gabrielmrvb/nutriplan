"""Distância escrita de um jeito só (QA de 27/09/2026, M2).

Até duas casas, sem zero à direita, com vírgula decimal: 5,2 · 5,23 · 10. A
mesma corrida aparecia como "5,20 km" na lista (o filtro `km` da corrida) e
"5,2 km" na Home (`floatformat:1`, que ainda cortava "5,23" para "5,2").

A CARGA usa a mesma função desde a parte 2 (item 5, 28/09/2026): o filtro
`carga` substitui o `floatformat:'-2'` ad hoc espalhado por
`templates/workouts/`, que mantinha o zero à direita ("62,50" em vez de
"62,5"). `config/test_numeros.py` varre `templates/workouts/` atrás do
formato antigo, no mesmo molde da varredura de `|distancia`.

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


@register.filter
def carga(peso):
    """Carga em kg, sem zero à direita: `Decimal('62.50')` vira "62,5"."""
    try:
        return decimal_curto(peso)
    except (InvalidOperation, TypeError, ValueError):
        return "—"
