"""Como o consumo planejado vira o que se compra no mercado.

A lista dizia "2 kg de Arroz branco cozido", "600 g de Ovo de galinha cozido" e
"450 g de Sardinha em óleo (drenada)". Todos os três números estão CERTOS — são
o que a pessoa vai comer — e nenhum dos três se compra assim. Ninguém pede meio
quilo de ovo cozido na feira, e arroz cozido não existe na prateleira.

A conversão mora aqui, num lugar só, por três motivos:

1. **é testável.** Cada regra é um dado, e o teste percorre a tabela inteira em
   vez de conferir um caso por vez;
2. **não vira condicional no template.** Um `{% if %}` por alimento seria a
   mesma regra escrita em HTML, onde ninguém consegue medi-la;
3. **a identidade é o NOME**, que é a chave estável do catálogo (`Food.name`
   tem índice único e é o que o seed usa). Casar por `id` amarraria a tabela à
   ordem de criação; casar por posição na lista quebraria na primeira
   reordenação.

O QUE ESTE MÓDULO NÃO FAZ: fingir precisão. Fator de cozimento varia com a
água, o tempo e a panela; lata de sardinha varia de marca. Toda conversão
aproximada é MARCADA, e a tela diz isso em uma linha — em vez de imprimir um
número exato que ninguém mediu.
"""
from decimal import Decimal

#: Quanto o alimento CRU rende depois de cozido, em peso.
#:
#: O consumo é registrado cozido porque é assim que se come e assim que a tabela
#: nutricional mede. A compra é crua porque é assim que se vende. O fator é a
#: razão entre os dois, e cada um é o valor usual da literatura de porções —
#: arroz e feijão absorvem ~2,5 vezes o próprio peso em água; macarrão, ~2,4.
#:
#: São aproximações honestas, e por isso tudo que passa por aqui sai marcado
#: como aproximado.
FATOR_CRU = {
    "Arroz branco cozido": (Decimal("2.5"), "Arroz branco (cru)"),
    "Arroz integral cozido": (Decimal("2.5"), "Arroz integral (cru)"),
    "Feijão carioca cozido": (Decimal("2.5"), "Feijão carioca (cru)"),
    "Feijão preto cozido": (Decimal("2.5"), "Feijão preto (cru)"),
    "Lentilha cozida": (Decimal("2.5"), "Lentilha (crua)"),
    "Grão-de-bico cozido": (Decimal("2.5"), "Grão-de-bico (cru)"),
    "Macarrão cozido": (Decimal("2.4"), "Macarrão (cru)"),
    "Cuscuz de milho cozido": (Decimal("2.5"), "Flocão de milho"),
}

#: Alimentos que se compram por UNIDADE, com o peso médio de cada uma.
#:
#: "600 g de ovo" é uma quantidade que ninguém pede. Doze ovos, sim — e uma
#: dúzia é como a caixa é vendida, então o texto diz dúzia quando fecha.
POR_UNIDADE = {
    "Ovo de galinha cozido": (Decimal("50"), "ovo", "ovos"),
    "Ovo de galinha frito": (Decimal("50"), "ovo", "ovos"),
    "Banana prata": (Decimal("90"), "banana", "bananas"),
    "Banana nanica": (Decimal("120"), "banana", "bananas"),
    "Maçã": (Decimal("130"), "maçã", "maçãs"),
    "Laranja": (Decimal("180"), "laranja", "laranjas"),
    "Pão francês": (Decimal("50"), "pão", "pães"),
}

#: Alimentos vendidos em EMBALAGEM fechada, com o conteúdo útil de cada uma.
#:
#: O peso é o que sobra depois de drenar, no caso das conservas: a lista pede
#: sardinha drenada, e é isso que a lata entrega. Comparar com o peso bruto
#: mandaria comprar lata a menos.
EMBALAGEM = {
    "Atum em água (drenado)": (Decimal("120"), "lata", "latas"),
    "Atum em óleo (drenado)": (Decimal("120"), "lata", "latas"),
    "Sardinha em óleo (drenada)": (Decimal("125"), "lata", "latas"),
    "Milho verde em conserva": (Decimal("170"), "lata", "latas"),
    "Pão de forma integral": (Decimal("500"), "pacote", "pacotes"),
    "Pão de forma": (Decimal("500"), "pacote", "pacotes"),
    "Leite integral": (Decimal("1000"), "litro", "litros"),
    "Leite desnatado": (Decimal("1000"), "litro", "litros"),
}


def _plural(quantidade: Decimal, singular: str, plural: str) -> str:
    return singular if quantidade == 1 else plural


def converter(nome: str, quantidade: Decimal, unidade: str):
    """Traduz o consumo planejado para a forma de compra.

    Devolve `(texto, aproximado)`. `texto` é o que vai na lista; `aproximado`
    diz se a conversão envolveu estimativa — e é o que a tela usa para avisar,
    em vez de fingir precisão que não existe.

    Alimento fora das três tabelas sai como entrou: quem se vende por peso
    continua em g ou kg, e é a maioria. A conversão é a exceção, não a regra.
    """
    from .shopping import humanize, round_up

    # 1. cozido -> cru. Vem primeiro porque muda a QUANTIDADE, e as outras
    #    regras (unidade, embalagem) operam sobre o peso que se compra.
    if nome in FATOR_CRU:
        fator, rotulo = FATOR_CRU[nome]
        crua = round_up(quantidade / fator)
        return f"{humanize(crua, unidade)} de {rotulo.lower()}", True

    if nome in POR_UNIDADE:
        peso, singular, plural = POR_UNIDADE[nome]
        unidades = (quantidade / peso).to_integral_value(rounding="ROUND_CEILING")
        if unidades <= 0:
            unidades = Decimal(1)
        # Dúzia só quando fecha exatamente: "1 dúzia e meia" é pior de ler que
        # "18 ovos", e arredondar para a dúzia mandaria comprar o que não
        # precisa.
        if singular == "ovo" and unidades % 12 == 0:
            duzias = unidades / 12
            return (
                f"{int(duzias)} {_plural(duzias, 'dúzia', 'dúzias')} de ovos",
                True,
            )
        return f"{int(unidades)} {_plural(unidades, singular, plural)}", True

    if nome in EMBALAGEM:
        conteudo, singular, plural = EMBALAGEM[nome]
        pacotes = (quantidade / conteudo).to_integral_value(rounding="ROUND_CEILING")
        if pacotes <= 0:
            pacotes = Decimal(1)
        return f"{int(pacotes)} {_plural(pacotes, singular, plural)}", True

    # 2. o resto se compra por peso, e já está na forma certa.
    return humanize(quantidade, unidade), False
