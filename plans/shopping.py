"""Lista de compras da semana, montada a partir do cardápio.

Duas decisões moldam tudo aqui:

1. **A lista é organizada por corredor de supermercado, não por refeição nem
   por macro.** Quem está no mercado anda por corredor. Uma lista que manda
   voltar ao hortifrúti três vezes porque separou "café da manhã" de "almoço"
   é uma lista que a pessoa abandona no meio.

2. **Quantidade é somada e arredondada para cima, para embalagem.** Ninguém
   compra 847 g de arroz. A conta exata serve ao gerador de cardápio; a lista
   de compras serve a quem empurra o carrinho, e para essa pessoa "1 kg" é uma
   informação melhor que "847 g".
"""
from decimal import Decimal

from catalog.models import Aisle

from .models import MealOption

#: Quantos dias a lista cobre. O cardápio é o mesmo todo dia (a meta é única),
#: então a semana é o cardápio vezes sete.
DAYS = 7

#: Ordem em que a lista aparece — a ordem em que se anda num mercado comum:
#: entra pelo hortifrúti, passa pelo açougue e pela geladeira, pega o pão e
#: fecha na mercearia.
AISLE_ORDER = [
    Aisle.PRODUCE,
    Aisle.BUTCHER,
    Aisle.DAIRY,
    Aisle.BAKERY,
    Aisle.GROCERY,
]

#: Acima disso a quantidade é anunciada em quilos: "1,2 kg" cabe na cabeça,
#: "1200 g" faz a pessoa converter no meio do corredor.
KILO_THRESHOLD = Decimal("1000")

#: Degraus de arredondamento. A ideia não é precisão, é a menor quantidade que
#: dá para comprar sem ficar contabilizando grama.
ROUNDING = [
    (Decimal("100"), Decimal("10")),
    (Decimal("1000"), Decimal("50")),
    (Decimal("100000"), Decimal("100")),
]


def round_up(quantity: Decimal) -> Decimal:
    """Arredonda para cima até o degrau de compra mais próximo."""
    for limite, passo in ROUNDING:
        if quantity <= limite:
            return (quantity / passo).to_integral_value(rounding="ROUND_CEILING") * passo
    return quantity


def humanize(quantity: Decimal, unit: str) -> str:
    """A quantidade do jeito que se fala na fila do caixa."""
    if unit == "ml" and quantity >= KILO_THRESHOLD:
        litros = (quantity / Decimal("1000")).normalize()
        return f"{litros} L".replace(".", ",")
    if unit == "g" and quantity >= KILO_THRESHOLD:
        quilos = (quantity / Decimal("1000")).normalize()
        return f"{quilos} kg".replace(".", ",")
    return f"{quantity.to_integral_value()} {unit}"


def weekly_quantities(plan, label=None) -> dict:
    """Quanto de cada alimento o cardápio da semana consome.

    `label` escolhe entre seguir a Opção A ou a B de cada refeição. Sem ele, a
    lista assume a A — é a que a tela apresenta primeiro e a que o total do dia
    já usa como referência.
    """
    options = (
        MealOption.objects.filter(slot__plan=plan)
        .select_related("template", "slot")
        .prefetch_related("template__items__food")
        .order_by("slot__order", "label")
    )

    escolhidas = {}
    for option in options:
        # Uma opção por horário: a primeira do rótulo pedido, ou a primeira que
        # existir quando aquele horário não tem a opção B.
        atual = escolhidas.get(option.slot_id)
        if atual is None or (label and option.label == label and atual.label != label):
            escolhidas[option.slot_id] = option

    totais = {}
    for option in escolhidas.values():
        for item in option.template.items.all():
            quantidade = item.scaled_quantity(option.scale_factor) * DAYS
            entrada = totais.setdefault(
                item.food,
                {"food": item.food, "quantity": Decimal("0"), "recipes": set()},
            )
            entrada["quantity"] += quantidade
            entrada["recipes"].add(option.template.name)
    return totais


def shopping_list(plan, label=None) -> list:
    """A lista pronta para a tela: corredores, com os itens de cada um."""
    totais = weekly_quantities(plan, label=label)

    por_corredor = {}
    for entrada in totais.values():
        food = entrada["food"]
        bruto = entrada["quantity"]
        arredondado = round_up(bruto)
        por_corredor.setdefault(food.aisle, []).append(
            {
                "food": food,
                "quantity": arredondado,
                "display": humanize(arredondado, food.base_unit),
                "recipes": sorted(entrada["recipes"]),
            }
        )

    lista = []
    for aisle in AISLE_ORDER:
        itens = por_corredor.get(aisle)
        if not itens:
            continue
        itens.sort(key=lambda linha: linha["food"].name.lower())
        lista.append(
            {
                "aisle": aisle,
                "name": Aisle(aisle).label,
                "items": itens,
                "count": len(itens),
            }
        )
    return lista
