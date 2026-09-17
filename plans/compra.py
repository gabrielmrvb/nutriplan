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
água, o tempo e a panela; lata de sardinha varia de marca; "1 unidade" de
repolho varia de pé para pé. Toda conversão aproximada é MARCADA, e a tela diz
isso em uma linha — em vez de imprimir um número exato que ninguém mediu.

**Mínimo de venda (avaliação de 16/09/2026, B16).** As tabelas de cru,
encolhimento, unidade e embalagem não bastavam: 33 dos 50 alimentos de receita ativa
saíam soltos em grama ou mililitro ("Repolho 40 g", "Azeite 20 ml", "Café
coado 300 ml", "Couve refogada 250 g"). Nenhum se compra assim — o mercado tem
um piso (a garrafa de azeite não vem em 20 ml) que a conta do cardápio não
conhece. `MINIMO_DE_COMPRA` é esse piso, e `plans/test_lista_compravel.py` é a
régua: todo alimento de receita ativa precisa terminar em ALGUMA das cinco
tabelas, e quem entrar sem forma de compra fica vermelho ali antes de chegar à
tela de alguém.
"""
import re
from decimal import Decimal

#: Quanto o alimento CRU rende depois de cozido, em peso.
#:
#: O consumo é registrado cozido porque é assim que se come e assim que a tabela
#: nutricional mede. A compra é crua porque é assim que se vende. O fator é a
#: razão entre os dois, e cada um é o valor usual da literatura de porções —
#: arroz e feijão absorvem ~2,5 vezes o próprio peso em água; macarrão, ~2,4.
#: `crua = quantidade / fator` — o cru pesa MENOS, porque o grão INCHA na
#: panela (`test_o_fator_de_cada_alimento_e_o_da_tabela` mede isso: fator
#: sempre > 1).
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

#: O mesmo problema que `FATOR_CRU`, ao contrário: carne, frango, peixe e
#: verdura refogada perdem água na panela — o CRU pesa MAIS que o pronto, não
#: menos. Se estivessem na tabela acima, `crua = quantidade / fator` faria
#: "carne moída refogada" encolher ainda mais na conversão para cru — o
#: oposto do que o açougue vende. Por isso é tabela separada, com a fórmula
#: invertida: `crua = quantidade * fator` (600 g refogados × 1,3 = 780 g
#: crus — o caso da avaliação de 16/09/2026, B16). Fica fora de `FATOR_CRU`
#: também para não mexer no invariante que aquela tabela já tinha
#: (`test_o_fator_de_cada_alimento_e_o_da_tabela` espera 2-tupla e um fator
#: de INCHAÇO, não de perda de água).
#:
#: Os números (1,1 a 1,4) são bem mais perto de 1 que os do grão seco, porque
#: a perda aqui é só água de superfície — não amido que incha.
FATOR_DE_ENCOLHIMENTO = {
    "Carne moída (patinho) refogada": (Decimal("1.3"), "Carne moída (patinho) (crua)"),
    "Coxa de frango sem pele cozida": (Decimal("1.35"), "Coxa de frango sem pele (crua)"),
    "Peito de frango grelhado": (Decimal("1.35"), "Peito de frango (cru)"),
    "Filé de tilápia grelhado": (Decimal("1.25"), "Filé de tilápia (cru)"),
    "Couve refogada": (Decimal("1.25"), "Couve (crua)"),
    "Espinafre cozido": (Decimal("1.4"), "Espinafre (cru)"),
    "Abobrinha cozida": (Decimal("1.1"), "Abobrinha (crua)"),
    "Batata doce cozida": (Decimal("1.1"), "Batata doce (crua)"),
    "Batata inglesa cozida": (Decimal("1.1"), "Batata inglesa (crua)"),
    "Brócolis cozido": (Decimal("1.1"), "Brócolis (cru)"),
}

#: Café é o único alimento medido em ML de bebida coada mas vendido em GRAMA de
#: pó — nenhuma das outras tabelas cobre essa troca de eixo (litro de leite é
#: litro de leite; aqui não). Fica fora de `FATOR_CRU` de propósito: aquela
#: tabela guarda um fator de ENCOLHIMENTO de cozimento (sempre entre 1 e 4,
#: conferido por `test_o_fator_de_cada_alimento_e_o_da_tabela`), e este número
#: é um RENDIMENTO — quanto café coado UMA xícara de pó rende —, que é outra
#: grandeza.
#:
#: 15 vem da proporção caseira usual do coado: ~10 g de pó para 150 ml de água
#: (a mesma xícara-padrão que `FoodPortion` usa para este alimento). Não tem
#: fonte mais precisa que isso — pó de marca diferente rende diferente —, e por
#: isso café sai sempre marcado como aproximado, como todo o resto aqui.
CAFE_ML_POR_GRAMA_DE_PO = Decimal("15")

#: Alimentos que se compram por UNIDADE, com o peso médio de cada uma.
#:
#: "600 g de ovo" é uma quantidade que ninguém pede. Doze ovos, sim — e uma
#: dúzia é como a caixa é vendida, então o texto diz dúzia quando fecha.
#:
#: O peso abaixo é um PISO histórico, usado só quando não há `Food` para
#: consultar (ou o alimento não tem porção cadastrada). Quando `converter`
#: recebe o `food`, a porção padrão do catálogo (`FoodPortion.is_default`)
#: VENCE — é o número que a pessoa já vê no cardápio de hoje, e dois pesos
#: diferentes pra mesma banana (90 g aqui, 70 g lá) é o tipo de divergência
#: que corrói confiança no app inteiro, não só na lista de compras.
POR_UNIDADE = {
    "Ovo de galinha cozido": (Decimal("50"), "ovo", "ovos"),
    "Ovo de galinha frito": (Decimal("50"), "ovo", "ovos"),
    "Banana prata": (Decimal("90"), "banana", "bananas"),
    "Banana nanica": (Decimal("120"), "banana", "bananas"),
    "Maçã": (Decimal("130"), "maçã", "maçãs"),
    "Laranja": (Decimal("180"), "laranja", "laranjas"),
    "Pão francês": (Decimal("50"), "pão", "pães"),
    # Hortifrúti vendido por peça — o rótulo é "unidade", não o nome do
    # alimento: "3 tomates" contém a palavra "tomate", que É o nome do
    # alimento, e o rótulo da lista (`shopping__name`) já mostra esse nome ao
    # lado — repeti-lo na quantidade é o MESMO bug que UX P1-03 mediu para
    # "Arroz branco cozido" (`test_lista_nome_e_quantidade.py`).
    # 120 g aqui, 110 g na porção do catálogo ("1 unidade média"): quando
    # `converter` recebe o `food`, a porção VENCE (ver `_porcao_padrao`), e é
    # assim que a lista de compras a lê. Este 120 só responde sem `food`.
    "Tomate": (Decimal("120"), "unidade", "unidades"),
    "Cenoura crua": (Decimal("70"), "unidade", "unidades"),
    # Frios fatiados: a porção do catálogo JÁ é a fatia de servir, e é também
    # como se compra no açougue/frios — 1 fatia = 1 fatia, sem tradução extra.
    "Presunto cozido": (Decimal("15"), "fatia", "fatias"),
    "Queijo prato": (Decimal("20"), "fatia", "fatias"),
    "Queijo muçarela": (Decimal("20"), "fatia", "fatias"),
    "Queijo minas frescal": (Decimal("30"), "fatia", "fatias"),
}

#: Alimentos vendidos em EMBALAGEM fechada, com o conteúdo útil de cada uma.
#:
#: O peso é o que sobra depois de drenar, no caso das conservas: a lista pede
#: sardinha drenada, e é isso que a lata entrega. Comparar com o peso bruto
#: mandaria comprar lata a menos.
EMBALAGEM = {
    "Atum em água (drenado)": (Decimal("120"), "lata", "latas"),
    "Atum em óleo (drenado)": (Decimal("120"), "lata", "latas"),
    # 84 g é o peso DRENADO — o mesmo da `FoodPortion` "1 lata drenada" e o
    # que o nome do alimento diz. Era 125 (a lata cheia, com o óleo): a Home
    # mostrava "2 latas drenadas (168 g)" e a lista comprava um terço a menos.
    "Sardinha em óleo (drenada)": (Decimal("84"), "lata", "latas"),
    "Milho verde em conserva": (Decimal("170"), "lata", "latas"),
    "Pão de forma integral": (Decimal("500"), "pacote", "pacotes"),
    "Pão de forma": (Decimal("500"), "pacote", "pacotes"),
    "Leite integral": (Decimal("1000"), "litro", "litros"),
    "Leite desnatado": (Decimal("1000"), "litro", "litros"),
}

#: A MENOR quantidade que o mercado vende — o azeite não vem em 20 ml, vem em
#: garrafa de 500. Cada linha é `(quantidade, unidade_base, rótulo_singular,
#: rótulo_plural)`.
#:
#: Quando `unidade_base` é a string `"unidade"`, a `quantidade` é só o peso
#: TÍPICO de uma peça (repolho, mamão…) — existe para decidir QUANTAS
#: comprar, nunca aparece no texto: "1 unidade (1000 g)" seria pior que "1
#: unidade", porque o peso de UM repolho é palpite, não medida. Quando
#: `unidade_base` é `"g"`/`"ml"`, ela É o tamanho do pacote/garrafa e aparece
#: entre parênteses, porque aí o número é a informação que falta ("1 unidade
#: (150 g)" diz que é uma cebola média, não uma gigante).
#:
#: Veio da avaliação de 16/09/2026 (B16): a lista pedia "Repolho 40 g",
#: "Alface 60 g", "Azeite 20 ml", "Café coado 300 ml", "Presunto 50 g",
#: "Couve refogada 250 g", "Carne moída refogada 600 g" — seis das 33
#: quantidades que ninguém consegue comprar como estava escrito (a sétima,
#: carne, resolve por `FATOR_CRU`, não por aqui). `converter()` arredonda
#: para CIMA ao múltiplo do mínimo — nunca fraciona, "0,5 garrafa" é tão
#: inútil quanto "20 ml" — e toda conversão que passa por aqui sai marcada
#: como aproximada.
MINIMO_DE_COMPRA = {
    "Azeite de oliva extra virgem": (Decimal("500"), "ml", "garrafa", "garrafas"),
    "Óleo de soja": (Decimal("900"), "ml", "garrafa", "garrafas"),
    "Café coado sem açúcar": (Decimal("250"), "g", "pacote de café", "pacotes de café"),
    "Alface": (Decimal("300"), "unidade", "pé", "pés"),
    "Repolho": (Decimal("1000"), "unidade", "unidade", "unidades"),
    "Couve refogada": (Decimal("300"), "g", "maço", "maços"),
    "Cebola": (Decimal("150"), "g", "unidade", "unidades"),
    "Iogurte natural integral": (Decimal("170"), "g", "pote", "potes"),
    "Requeijão cremoso": (Decimal("200"), "g", "pote", "potes"),
    "Pasta de amendoim integral": (Decimal("500"), "g", "pote", "potes"),
    "Mel": (Decimal("250"), "g", "pote", "potes"),
    "Aveia em flocos": (Decimal("200"), "g", "pacote", "pacotes"),
    "Granola sem açúcar": (Decimal("250"), "g", "pacote", "pacotes"),
    "Azeitona": (Decimal("100"), "g", "vidro", "vidros"),
    "Manteiga": (Decimal("200"), "g", "tablete", "tabletes"),
    "Margarina com sal": (Decimal("500"), "g", "pote", "potes"),
    "Amendoim torrado": (Decimal("500"), "g", "pacote", "pacotes"),
    "Farinha de mandioca torrada": (Decimal("500"), "g", "pacote", "pacotes"),
    "Goma de tapioca hidratada": (Decimal("500"), "g", "pacote", "pacotes"),
    "Proteína de soja texturizada (seca)": (Decimal("400"), "g", "pacote", "pacotes"),
    "Mamão papaia": (Decimal("400"), "unidade", "mamão", "mamões"),
}


def _plural(quantidade: Decimal, singular: str, plural: str) -> str:
    return singular if quantidade == 1 else plural


def _porcao_padrao(food):
    """A porção padrão do catálogo para este alimento, ou `None`.

    Só é chamada quando `food` foi passado — sem ele, a consulta nem existe,
    e as tabelas estáticas deste módulo continuam valendo sozinhas (é o que
    mantém `converter` chamável sem banco, como os testes de
    `SimpleTestCase` sempre fizeram).

    `food.portions.all()`, NUNCA `.filter(is_default=True)`: o `.filter()`
    monta uma queryset nova, e uma queryset nova ignora o cache de
    `prefetch_related` — é o `N+1` que `shopping.weekly_quantities` pagava
    antes de prefetchar `__food__portions`, um SELECT por alimento único de
    `POR_UNIDADE` a cada `shopping_list`. `.all()` é o único caminho que lê o
    cache; a ordenação do model (`-is_default, grams`) já traz a porção
    padrão primeiro quando existe alguma.
    """
    if food is None:
        return None
    for portion in food.portions.all():
        if portion.is_default:
            return portion
    return None


def converter(nome: str, quantidade: Decimal, unidade: str, food=None):
    """Traduz o consumo planejado para a forma de compra.

    Devolve `(texto, aproximado)`. `texto` é o que vai na lista; `aproximado`
    diz se a conversão envolveu estimativa — e é o que a tela usa para avisar,
    em vez de fingir precisão que não existe.

    `food` é opcional: quando vem, a porção padrão do catálogo
    (`FoodPortion.is_default`) vence o peso fixo de `POR_UNIDADE`, do jeito
    que corrigiu a banana (90 g na tabela, 70 g na porção — a porção é o que
    a pessoa já viu no cardápio). Sem `food`, a tabela estática responde
    sozinha, e é assim que os testes puros (`SimpleTestCase`, sem banco)
    continuam funcionando.

    Alimento fora das cinco tabelas sai como entrou: quem se vende por peso
    continua em g ou kg, e é a maioria. A conversão é a exceção, não a regra.
    """
    from .shopping import humanize, round_up

    # Café é medido em ml de bebida coada mas vendido em g de pó — nenhuma
    # tabela cobre essa troca de eixo, então ele tem sua própria conversão
    # antes de qualquer tabela (ver `CAFE_ML_POR_GRAMA_DE_PO`). Depois desta
    # linha `quantidade`/`unidade` já descrevem o PÓ, e `MINIMO_DE_COMPRA`
    # resolve o resto do jeito que resolve qualquer outro alimento em grama.
    if nome == "Café coado sem açúcar":
        quantidade = round_up(quantidade / CAFE_ML_POR_GRAMA_DE_PO)
        unidade = "g"

    # 1. cozido -> cru. Vem primeiro porque muda a QUANTIDADE, e as outras
    #    regras (mínimo, unidade, embalagem) operam sobre o peso que se
    #    compra — não retorna mais aqui: o texto de "cru" só é a resposta
    #    final quando NENHUMA tabela seguinte tem este alimento.
    rotulo_cru = None
    if nome in FATOR_CRU:
        fator, rotulo_cru = FATOR_CRU[nome]
        quantidade = round_up(quantidade / fator)
        # O cru sempre se pesa — mesmo quando o consumo original era em ml
        # (café, acima, é o único caso; os demais já eram g).
        unidade = "g"
    elif nome in FATOR_DE_ENCOLHIMENTO:
        fator, rotulo_cru = FATOR_DE_ENCOLHIMENTO[nome]
        # Fórmula invertida: aqui o cru pesa MAIS, não menos (ver o
        # comentário da tabela).
        quantidade = round_up(quantidade * fator)
        unidade = "g"

    # 2. mínimo de venda — depois do cru (opera sobre o peso que se compra,
    #    não o que se come) e antes de unidade/embalagem (mínimo é mais
    #    específico: cobre alimento que TAMBÉM teria uma forma óbvia em
    #    quilo, mas que o mercado não vende picado assim).
    if nome in MINIMO_DE_COMPRA:
        minimo, unidade_minima, singular, plural = MINIMO_DE_COMPRA[nome]
        passos = (quantidade / minimo).to_integral_value(rounding="ROUND_CEILING")
        if passos <= 0:
            passos = Decimal(1)
        rotulo = _plural(passos, singular, plural)
        if unidade_minima == "unidade":
            return f"{int(passos)} {rotulo}", True
        total = passos * minimo
        return f"{int(passos)} {rotulo} ({humanize(total, unidade_minima)})", True

    if nome in POR_UNIDADE:
        peso, singular, plural = POR_UNIDADE[nome]
        porcao = _porcao_padrao(food)
        if porcao is not None:
            peso = porcao.grams
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

    # 3. cru sem mínimo (arroz, feijão, carne…): o texto final é o estado
    #    do alimento, não o número solto.
    if rotulo_cru is not None:
        # O NOME NÃO SE REPETE. A linha da lista já diz "Arroz branco cozido"
        # no rótulo; a quantidade dizia "1,4 kg de arroz branco (cru)" ao
        # lado, `nowrap`, e quem encolhia era o nome — letra por letra a
        # 320 px (UX P1-03, 14/09/2026). Quando o que se compra é o mesmo
        # alimento, a quantidade fica só com o número e o estado: "1,4 kg
        # (cru)", "600 g (crua)". Quando é OUTRO produto — cuscuz se compra
        # como flocão de milho —, o rótulo inteiro fica, porque aí ele é
        # informação, não repetição.
        raiz = re.sub(
            r"\s+(cozid[oa]|refogad[oa]|grelhad[oa]|desfiad[oa])$",
            "",
            nome,
            flags=re.I,
        )
        if rotulo_cru.lower().startswith(raiz.lower()):
            estado = rotulo_cru[len(raiz):].strip()
            return f"{humanize(quantidade, unidade)} {estado}".strip(), True
        return f"{humanize(quantidade, unidade)} de {rotulo_cru.lower()}", True

    # 4. o resto se compra por peso, e já está na forma certa.
    return humanize(quantidade, unidade), False
