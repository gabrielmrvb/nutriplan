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
* só entram substitutos da mesma classe E do mesmo PAPEL no prato;
* a quantidade é calculada para igualar **esse** macro;
* o resultado é descartado quando as calorias fogem demais, porque igualar
  proteína estourando o dia em gordura também não serve;
* e é descartado também quando algum macro SECUNDÁRIO se desloca demais.

O papel no prato entrou depois, e por um motivo constrangedor: casar macro e
caloria fazia o app oferecer 467 g de cebola no lugar de 150 g de arroz, e
240 g de cenoura no lugar de uma banana. A conta fechava e a refeição virava
outra coisa. Cebola e arroz dividem o corredor "hortifrúti" no mercado, mas
não dividem função nenhuma no prato.

O critério das calorias nasceu de uma auditoria da base: igualar o macro dominante e
a caloria total deixava passar trocas que reescreviam o resto da refeição. A
pior delas oferecia proteína de soja no lugar de patinho grelhado — proteína
igual, calorias 11% acima, e o carboidrato do prato saindo de 0 g para 30 g.
Metade das trocas do catálogo tinha algum macro mais de 50% fora do original.
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

#: Quanto um macro que NÃO é o dominante pode se deslocar, em gramas.
#:
#: Em gramas e não em porcentagem porque o denominador costuma ser zero: carne
#: não tem carboidrato, e "de 0 g para 30 g" não tem porcentagem que descreva.
#:
#: Oito gramas saiu de medição, não de opinião. Rodando o catálogo inteiro com
#: vários limites, o desvio mediano já era de 1,9 g — os absurdos eram uma
#: cauda curta. Cortar em 8 g derruba o pior caso de 43 g para 8 g e custa 8
#: das 184 trocas possíveis, com um único alimento ficando sem alternativa.
#: Limites mais apertados que isso passam a cobrar cobertura sem ganhar
#: fidelidade proporcional.
MAX_SECONDARY_DRIFT_G = Decimal("8")

#: Quantidade mínima e máxima que faz sentido servir. Fora disso a troca deixa
#: de ser comida: 8 g de arroz não alimenta, 900 g de abobrinha não cabe.
MIN_GRAMS = Decimal("10")
MAX_GRAMS = Decimal("600")

#: Quantas porções padrão a troca pode pedir, no máximo.
#:
#: Um teto em gramas é cego ao alimento: 400 g de arroz é um prato grande,
#: 400 g de clara de ovo são treze claras. E foi exatamente isso que o app
#: ofereceu no lugar de um filé de frango — 423 g, dentro do teto de 600 e
#: completamente fora da realidade de quem vai cozinhar.
#:
#: Quatro porções é o limite do que ainda parece uma refeição: quatro colheres
#: de azeite, quatro escumadeiras de arroz, quatro ovos. Acima disso a pessoa
#: lê a sugestão e fecha o app.
MAX_PORTIONS = Decimal("4")

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


def _porcoes_demais(food, grams: Decimal) -> bool:
    """A quantidade pedida cabe num prato?

    Medida em porções padrão do próprio alimento, que é o que traduz gramas em
    algo que a pessoa reconhece: "1 escumadeira", "1 colher de sopa", "1 clara".
    Alimento sem porção cadastrada passa — não dá para julgar o que não foi
    declarado, e recusar por falta de dado esconderia trocas boas.
    """
    porcao = food.portions.filter(is_default=True).first()
    if porcao is None or porcao.grams <= 0:
        return False
    return grams > porcao.grams * MAX_PORTIONS


def substitutes_for(food, grams, limit=MAX_RESULTS) -> list:
    """Alternativas equivalentes a `grams` de `food`, da mais parecida à menos.

    A ordenação é pela diferença calórica: entre dois substitutos que entregam
    a mesma proteína, ganha o que mexe menos no resto do dia.
    """
    grams = Decimal(str(grams))
    macro = dominant_macro(food)
    referencia = food.macros_for(grams)

    candidatos = []
    for outro in Food.objects.filter(is_active=True, role=food.role).exclude(pk=food.pk):
        if dominant_macro(outro) != macro:
            continue
        quantidade = _equivalent_grams(food, outro, grams, macro)
        if quantidade is None or not (MIN_GRAMS <= quantidade <= MAX_GRAMS):
            continue
        if _porcoes_demais(outro, quantidade):
            continue

        macros = outro.macros_for(quantidade)

        # Os macros que não são o dominante não podem passear: é o que impede
        # a troca de acertar a proteína e reescrever o resto do prato.
        if macro != "mixed":
            secundarios = [m for m in KCAL_PER_G if m != macro]
            if any(
                abs(macros[m] - referencia[m]) > MAX_SECONDARY_DRIFT_G
                for m in secundarios
            ):
                continue

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
