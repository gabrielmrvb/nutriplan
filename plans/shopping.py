"""Lista de compras da semana, montada a partir do cardápio.

Três decisões moldam tudo aqui:

1. **A lista é organizada por corredor de supermercado, não por refeição nem
   por macro.** Quem está no mercado anda por corredor. Uma lista que manda
   voltar ao hortifrúti três vezes porque separou "café da manhã" de "almoço"
   é uma lista que a pessoa abandona no meio.

2. **Quantidade é somada e arredondada para cima, para embalagem.** Ninguém
   compra 847 g de arroz. A conta exata serve ao gerador de cardápio; a lista
   de compras serve a quem empurra o carrinho, e para essa pessoa "1 kg" é uma
   informação melhor que "847 g".

3. **Uma alternativa por refeição por dia, e não as duas.** Quem tem frango ou
   ovo no almoço vai comer um dos dois. Somar as alternativas encheria a lista
   de comida que ninguém cozinha, e lista inflada é lista em que a pessoa para
   de confiar. O rótulo pedido (`?opcao=A` ou `B`) escolhe qual seguir.

   A regra é a mesma desde a primeira versão. O que o cardápio V2 mudou foi
   apenas de onde a alternativa sai: a semana passou a ser projetada dia a dia,
   pela MESMA função que a tela Hoje usa, em vez de um dia multiplicado por
   sete.
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from catalog.models import Aisle

from . import rodizio

#: Quantos dias a lista cobre.
#:
#: Já foi um multiplicador — o cardápio era o mesmo todo dia, então a semana
#: era um dia vezes sete. Com o rodízio do cardápio V2 isso deixou de valer: a
#: semana é percorrida data a data, e este número diz quantas datas.
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


def dias_da_semana(inicio=None) -> list:
    """As sete datas LOCAIS que a lista cobre, a partir de hoje.

    `timezone.localdate()`, nunca `date.today()`: o servidor roda em UTC e, das
    21h à meia-noite de Brasília, `date.today()` já está no dia seguinte. A
    lista compraria a semana errada por três horas todo dia.
    """
    inicio = inicio or timezone.localdate()
    return [inicio + timedelta(days=i) for i in range(DAYS)]


def weekly_quantities(plan, label=None, inicio=None) -> dict:
    """Quanto de cada alimento o cardápio da semana consome.

    A REGRA DE PRODUTO NÃO MUDOU: uma opção por refeição por dia. Quem tem
    frango ou ovo no almoço vai comer um dos dois, não os dois — somar as
    alternativas encheria a lista de comida que ninguém vai cozinhar, e o
    primeiro efeito de uma lista inflada é a pessoa parar de confiar nela.

    `label` escolhe qual das alternativas seguir. Sem ele, a lista assume a A —
    é a que a tela apresenta primeiro e a que o total do dia usa como
    referência.

    O QUE MUDOU é de onde sai essa opção. Antes o cardápio era o mesmo todo
    dia, então bastava pegar a opção A do horário e multiplicar por sete. Com o
    rodízio do cardápio V2, a opção A de segunda pode ser outra receita que a
    de terça — multiplicar uma delas por sete compraria uma semana que não vai
    acontecer.

    Agora a semana é percorrida dia a dia, projetando cada data com a MESMA
    função que a tela Hoje usa (`rodizio.opcoes_do_dia`). Uma regra de
    projeção, vários consumidores: uma segunda implementação aqui divergiria da
    tela na primeira mudança, e a pessoa compraria uma coisa e cozinharia
    outra.
    """
    slots = list(
        plan.slots.prefetch_related("options__template__items__food").order_by("order")
    )

    totais = {}
    for dia in dias_da_semana(inicio):
        for slot in slots:
            projetadas = rodizio.opcoes_do_dia(slot, plan.user_id, dia)
            if not projetadas:
                continue
            # A do rótulo pedido, ou a primeira quando aquele dia projetou só
            # uma — que é o caso de um horário com repertório de tamanho um.
            escolhida = next(
                (opcao for opcao in projetadas if opcao.rotulo == label), projetadas[0]
            )
            for item in escolhida.template.items.all():
                quantidade = item.scaled_quantity(escolhida.scale_factor)
                entrada = totais.setdefault(
                    item.food,
                    {"food": item.food, "quantity": Decimal("0"), "recipes": set()},
                )
                entrada["quantity"] += quantidade
                entrada["recipes"].add(escolhida.template.name)
    return totais


def shopping_list(plan, label=None, inicio=None) -> list:
    """A lista pronta para a tela: corredores, com os itens de cada um."""
    totais = weekly_quantities(plan, label=label, inicio=inicio)

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
