"""Troca de um alimento por outro equivalente.

A pergunta que isto responde é a mais comum de quem segue dieta: "acabou o
frango, posso comer o quê no lugar?". A resposta útil não é "carne moída" — é
**quantos gramas** de carne moída, porque é a quantidade que mantém a refeição
equivalente.

O critério é o macro dominante do alimento, e não a caloria total. Trocar 150 g
de arroz (carboidrato) por uma quantidade isocalórica de azeite fecha a conta
das calorias e destrói a refeição: some o carboidrato do prato e triplica a
gordura. Então:

* o alimento é classificado pelo macro que domina as calorias dele;
* só entram substitutos da mesma classe;
* a quantidade é calculada para igualar **esse** macro;
* e o resultado é descartado quando as calorias fogem demais, porque igualar
  proteína estourando o dia em gordura também não serve.
"""
from decimal import Decimal

from catalog.models import Food

#: Quanto do total de calorias um macro precisa concentrar para ser "o" macro
#: do alimento. Abaixo disso o alimento é misto (ovo, leite) e vira classe
#: própria — trocar leite por óleo porque os dois têm gordura seria absurdo.
DOMINANCE = Decimal("0.45")

#: Limite de quanto as calorias podem escorregar depois de igualar o macro.
#: Trinta e cinco por cento é folgado de propósito: a substituição existe para
#: destravar quem está sem o alimento, não para produzir o clone perfeito.
KCAL_TOLERANCE = Decimal("0.35")

#: Quantidade mínima e máxima que faz sentido servir. Fora disso a troca deixa
#: de ser comida: 8 g de arroz não alimenta, 900 g de abobrinha não cabe.
MIN_GRAMS = Decimal("10")
MAX_GRAMS = Decimal("600")

#: Quantas alternativas mostrar. Três é o número que cabe na tela e que a
#: pessoa consegue comparar de pé na cozinha.
MAX_RESULTS = 3

KCAL_PER_G = {"protein_g": Decimal("4"), "carb_g": Decimal("4"), "fat_g": Decimal("9")}

MACRO_LABEL = {
    "protein_g": "proteína",
    "carb_g": "carboidrato",
    "fat_g": "gordura",
    "mixed": "misto",
}


def dominant_macro(food) -> str:
    """Qual macro manda nas calorias deste alimento, ou "mixed"."""
    total = sum(getattr(food, macro) * fator for macro, fator in KCAL_PER_G.items())
    if total <= 0:
        return "mixed"
    for macro, fator in KCAL_PER_G.items():
        if getattr(food, macro) * fator / total >= DOMINANCE:
            return macro
    return "mixed"


def _equivalent_grams(origin, target, grams: Decimal, macro: str):
    """Quantos gramas do substituto entregam o mesmo tanto do macro dominante.

    Para alimento misto o critério vira a caloria: é o único denominador comum
    entre ovo, leite e iogurte.
    """
    if macro == "mixed":
        base_origem, base_alvo = origin.kcal, target.kcal
    else:
        base_origem, base_alvo = getattr(origin, macro), getattr(target, macro)
    if base_alvo <= 0:
        return None
    return (grams * base_origem / base_alvo).quantize(Decimal("1"))


def substitutes_for(food, grams, limit=MAX_RESULTS) -> list:
    """Alternativas equivalentes a `grams` de `food`, da mais parecida à menos.

    A ordenação é pela diferença calórica: entre dois substitutos que entregam
    a mesma proteína, ganha o que mexe menos no resto do dia.
    """
    grams = Decimal(str(grams))
    macro = dominant_macro(food)
    referencia = food.macros_for(grams)

    candidatos = []
    for outro in Food.objects.filter(is_active=True).exclude(pk=food.pk):
        if dominant_macro(outro) != macro:
            continue
        quantidade = _equivalent_grams(food, outro, grams, macro)
        if quantidade is None or not (MIN_GRAMS <= quantidade <= MAX_GRAMS):
            continue

        macros = outro.macros_for(quantidade)
        alvo_kcal = referencia["kcal"]
        if alvo_kcal > 0:
            desvio = abs(macros["kcal"] - alvo_kcal) / alvo_kcal
            if desvio > KCAL_TOLERANCE:
                continue
        else:
            desvio = Decimal("0")

        candidatos.append(
            {
                "food": outro,
                "quantity": quantidade,
                "unit": outro.base_unit,
                "kcal": macros["kcal"].quantize(Decimal("1")),
                "protein_g": macros["protein_g"].quantize(Decimal("1")),
                "carb_g": macros["carb_g"].quantize(Decimal("1")),
                "fat_g": macros["fat_g"].quantize(Decimal("1")),
                "kcal_gap": desvio,
            }
        )

    candidatos.sort(key=lambda linha: (linha["kcal_gap"], linha["food"].name))
    return candidatos[:limit]


def swap_summary(food, grams) -> dict:
    """O que a tela precisa para montar o modal de troca."""
    grams = Decimal(str(grams))
    macro = dominant_macro(food)
    macros = food.macros_for(grams)
    return {
        "food": food,
        "quantity": grams.quantize(Decimal("1")),
        "unit": food.base_unit,
        "macro": macro,
        "macro_label": MACRO_LABEL[macro],
        "kcal": macros["kcal"].quantize(Decimal("1")),
        "protein_g": macros["protein_g"].quantize(Decimal("1")),
        "options": substitutes_for(food, grams),
    }
