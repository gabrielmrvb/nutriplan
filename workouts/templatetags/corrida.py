# -*- coding: utf-8 -*-
"""Como a corrida se escreve na tela.

A tela de corridas já tinha um vocabulário — o painel ao vivo diz "0,00 km",
"00:00 em movimento" e "— min/km" — e o histórico logo abaixo escrevia
"5230 m" e "1523 s em movimento". Os mesmos três números, duas linguagens, na
mesma página. E `Corrida.pace_s_km` existia, documentado, lido por nenhum
template: quem terminou a corrida via o pace ao vivo e nunca mais.

Os nomes espelham `static/js/corrida.js` de propósito: `relogio` lá, `relogio`
aqui. Não há como o servidor reaproveitar aquele arquivo, mas há como manter os
dois dizendo a mesma coisa com o mesmo nome.
"""
from django import template

register = template.Library()


@register.filter
def relogio(segundos):
    """Segundos para `mm:ss`, ou `h:mm:ss` quando passa da hora.

    `1523` vira `25:23`. A maratona vira `2:01:39` e não `121:39` — a versão
    que só fazia minutos ficava ilegível exatamente na corrida longa, que é
    quando a pessoa mais quer ler o número.
    """
    try:
        total = int(segundos)
    except (TypeError, ValueError):
        return "—"
    if total < 0:
        return "—"
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return "%d:%02d:%02d" % (horas, minutos, segs)
    return "%02d:%02d" % (minutos, segs)


@register.filter
def km(metros):
    """Metros para quilômetros com VÍRGULA decimal, que é o que o app usa.

    `floatformat:2` sozinho respeita a localização, mas o valor continua em
    metros: o histórico dizia "5230 m", e ninguém conta a própria corrida em
    metros.
    """
    try:
        valor = int(metros)
    except (TypeError, ValueError):
        return "—"
    return ("%.2f" % (valor / 1000)).replace(".", ",")


@register.filter
def pace(corrida):
    """`min/km` a partir de `Corrida.pace_s_km`, ou travessão quando não há.

    Recebe a CORRIDA e não o pace já calculado: a propriedade devolve `None`
    para distância ou duração zero, e é ela que sabe disso. Refazer a divisão
    aqui seria a terceira cópia da mesma conta.

    E QUEM TEVE LACUNA NÃO RECEBE PACE. Quando a tela apaga, `corrida.js` para
    de receber posição mas o relógio continua correndo — o `visibilitychange`
    marca `teveLacuna` justamente porque o app SABE que aquele trecho não foi
    medido. O tempo fica inteiro e a distância fica curta, então o pace derivado
    dos dois é rápido demais, e errado por construção.

    Distância e duração continuam aparecendo: são medições reais, ainda que
    incompletas, e a etiqueta "com trecho não registrado" já está na mesma
    linha dizendo isso. O pace não é medição, é divisão — e aqui vale a regra
    que este projeto já aplica ao cardápio: número inventado no histórico é
    pior que buraco no histórico, porque o buraco a pessoa vê.
    """
    if getattr(corrida, "teve_lacuna", False):
        return "—"
    segundos = getattr(corrida, "pace_s_km", None)
    if not segundos:
        return "—"
    return relogio(round(segundos))
