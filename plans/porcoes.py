# -*- coding: utf-8 -*-
"""A medida caseira de uma quantidade: "7,5 colheres de sopa" para 116 g de aveia.

`FoodPortion` existia desde a primeira versão do catálogo (79 dos 102
alimentos, 85 porções) e nunca era lida fora do seed — a Home mostrava
"Aveia 116 g" (avaliação de 16/09, B15) em vez de "7,5 colheres de sopa",
que é o que uma pessoa de fato mede na cozinha.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

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
    if n == MEIO:
        # "½ xícara", não "0,5 xícaras" (QA local da Fase 3, 17/09/2026). O
        # glifo evita a concordância de gênero de "meio/meia", que o catálogo
        # não sabe; o singular é o que se diz para uma fração de UMA unidade.
        # Só o meio exato: 1,5 e acima seguem com vírgula e no plural.
        return "½", porcao.singular
    rotulo = porcao.singular if n == 1 else porcao.plural
    return _formatar(n), rotulo


#: O que sobra do nome do alimento quando ele vira item de uma linha só.
#:
#: O catálogo nomeia o alimento pelo que ele É na tabela nutricional — "Peito
#: de frango grelhado", "Ovo de galinha cozido", "Atum em água (drenado)" —
#: porque 100 g de frango cru e 100 g de frango grelhado não têm a mesma
#: caloria, e a tabela precisa dizer qual. A LINHA DO CARD tem outra pergunta:
#: "do que é feito?". Ali "grelhado" é ruído, e ruído vezes cinco ingredientes
#: estoura a linha num celular.
#:
#: A lista é FECHADA e escrita à mão, de propósito. Uma regra ("tire o último
#: adjetivo") transformaria "Pão de forma integral" em "Pão de forma" —
#: aceitável — e "Leite desnatado" em "Leite", que é outro alimento com outra
#: caloria. Cada corte aqui foi lido no catálogo antes de entrar.
PREPARO_NO_NOME = (
    " grelhado", " grelhada", " cozido", " cozida", " refogado", " refogada",
    " torrado", " torrada", " assado", " assada", " em flocos", " sem pele",
    " hidratada", " hidratado", " texturizada (seca)", " (drenado)",
    " (drenada)", " (patinho)", " coado sem açúcar", " extra virgem",
)


def nome_curto(nome: str) -> str:
    """O nome do alimento sem o preparo, para caber numa linha.

    "Peito de frango grelhado" → "peito de frango"; "Ovo de galinha cozido" →
    "ovo de galinha". O que NÃO sai é o que muda o alimento: "Leite desnatado"
    e "Arroz integral" continuam inteiros, porque leite e leite desnatado são
    linhas diferentes da tabela.

    Devolve em minúscula: a linha é uma enumeração ("2 ovos · 1 pão francês"),
    e nome próprio no meio de uma lista lê como título.
    """
    curto = nome
    for sufixo in PREPARO_NO_NOME:
        if curto.lower().endswith(sufixo):
            curto = curto[: -len(sufixo)]
            break
    return curto.strip().lower()


#: Abreviações da medida caseira, e só as que não cabem por extenso.
#:
#: "4 colheres de servir de arroz branco" tem 37 caracteres; a linha do card
#: tem três ou quatro itens. Abreviar "colher" é o que o mercado, a receita e
#: a embalagem já fazem — e as outras medidas ("fatia", "xícara", "unidade",
#: "concha") são curtas e ficam por extenso, porque abreviação que ninguém
#: usa custa uma tradução na cabeça de quem lê.
MEDIDA_ABREVIADA = {
    "colher de sopa": "col. de sopa",
    "colheres de sopa": "col. de sopa",
    "colher de servir": "col. de servir",
    "colheres de servir": "col. de servir",
    "colher de chá": "col. de chá",
    "colheres de chá": "col. de chá",
}


def item_em_uma_linha(quantidade_g, unidade, nome_do_alimento, caseira) -> str:
    """Um ingrediente como a pessoa o diria: "2 ovos", "150 g de frango".

    Com medida caseira, ela vem na frente e a grama some — quem monta o prato
    mede com a colher que tem, não com a balança. Sem medida caseira (o
    alimento não tem porção cadastrada, ou a quantidade é menos de meia), o
    número em grama é a verdade disponível, e dizê-lo é melhor que arredondar
    para uma colher que não existe.
    """
    curto = nome_curto(nome_do_alimento)
    if caseira:
        numero, rotulo = caseira
        rotulo = MEDIDA_ABREVIADA.get(rotulo, rotulo)
        if _a_medida_ja_nomeia(rotulo, curto):
            # "4 ovos médios", e não "4 ovos médios de ovo de galinha".
            return "%s %s" % (numero, rotulo)
        return "%s %s de %s" % (numero, rotulo, curto)
    return "%s %s de %s" % (_formatar(Decimal(quantidade_g)), unidade, curto)


def _a_medida_ja_nomeia(rotulo: str, alimento_curto: str) -> bool:
    """A medida caseira já diz qual é o alimento?

    Muitas porções do catálogo são o próprio alimento contado — "ovo médio",
    "banana média", "pão francês" —, e nessas a fórmula genérica devolvia "4
    ovos médios DE OVO DE GALINHA". A régua é o radical da primeira palavra
    da medida: se ele aparece como palavra inteira no nome curto do alimento,
    a medida já nomeia, e repetir só gasta linha.

    Radical e não a palavra: a medida vem no plural quando a quantidade é
    maior que um ("ovos"), e o nome do alimento está no singular ("ovo de
    galinha"). Cortar o "s"/"es" final resolve os dois casos do catálogo, e é
    tudo o que esta função promete — ela decide LAYOUT, não conteúdo: errar
    para o lado de repetir devolve a frase longa, que continua verdadeira.
    """
    primeira = rotulo.split()[0].lower()
    radical = primeira[:-2] if primeira.endswith("es") else primeira.rstrip("s")
    if len(radical) < 3:
        return False
    return any(
        palavra == radical or palavra.rstrip("s") == radical
        for palavra in alimento_curto.lower().split()
    )


#: As três porções que a tela oferece: meia, inteira e uma e meia.
#:
#: Três e não um campo livre, porque a pergunta é "comi menos/mais do que a
#: receita rende?" e não "quantos gramas de arroz eu pus?" — quem quer o grama
#: exato tem "Comi outra coisa", que soma alimento a alimento. Meia e uma e
#: meia são as duas respostas que uma pessoa dá sem pesar nada.
PORCOES = (Decimal("0.5"), Decimal("1"), Decimal("1.5"))

#: Como cada uma se escreve. "½" e não "0,5" pelo mesmo motivo da medida
#: caseira: é o glifo que uma receita usa.
PORCAO_ESCRITA = {Decimal("0.5"): "½", Decimal("1"): "1", Decimal("1.5"): "1½"}


def porcao_valida(texto) -> Decimal:
    """A porção pedida, ou 1 quando o pedido não é uma das três.

    LISTA FECHADA, e a razão é a mesma do `de=` da água: este valor multiplica
    caloria gravada no histórico. Um `porcao=99` vindo de um POST forjado
    escreveria um dia de 280.000 kcal — e a tela de Progresso, a ofensiva e as
    conquistas leem esse número. Cair em 1 é o comportamento certo para lixo:
    registra a refeição como a receita rende, que é o que a tela oferecia
    antes de a porção existir.
    """
    try:
        pedida = Decimal(str(texto))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("1")
    return pedida if pedida in PORCOES else Decimal("1")


#: Os verbos que abrem um passo de receita, no imperativo.
#:
#: Lista FECHADA, lida das 54 instruções do catálogo. A alternativa era cortar
#: em toda vírgula e em todo " e ", e isso parte a frase no lugar errado:
#: "sirva com o ovo cozido E o tomate" viraria dois passos, e o segundo não
#: teria verbo. Cortar ANTES de um verbo é o que separa ação de complemento.
VERBOS_DE_PREPARO = (
    "hidrate", "leve", "sirva", "refogue", "cozinhe", "bata", "misture",
    "asse", "grelhe", "tempere", "corte", "amasse", "junte", "acrescente",
    "coloque", "doure", "frite", "escorra", "reserve", "recheie", "monte",
    "aqueça", "deixe", "passe", "regue", "salpique", "espalhe", "fatie",
    "descasque", "adicione", "abra", "unte", "polvilhe", "bata", "tempere",
    "sele", "cubra", "finalize", "complete", "prepare",
)


def passos_do_preparo(instrucoes: str) -> list:
    """O modo de preparo em passos numerados.

    O catálogo guarda uma frase corrida ("Hidrate o cuscuz, leve à cuscuzeira
    e sirva com o ovo cozido e o tomate, regados com o azeite"), porque é
    assim que uma receita simples se escreve. Na cozinha, com uma mão ocupada,
    é uma lista que se lê — e cada vírgula ali é um passo.

    O corte é por ponto-final e por ", e " / " e depois ": as três marcas que
    separam AÇÕES nessas frases. Vírgula solta não serve ("com o ovo cozido e
    o tomate, regados com o azeite" é um passo só, e cortar ali daria dois
    passos sem verbo). Quando nenhuma marca aparece, a frase inteira é um
    passo — que é a verdade, e melhor que inventar dois.
    """
    import re

    texto = (instrucoes or "").strip()
    if not texto:
        return []
    verbos = "|".join(VERBOS_DE_PREPARO)
    # Corta no ponto-final, e antes de um verbo de preparo que venha depois de
    # vírgula ou de " e ". O `(?=...)` guarda o verbo no passo seguinte.
    partes = re.split(
        r"\.\s+|(?:,\s*|\s+e\s+|\s*;\s*)(?=(?:%s)\b)" % verbos,
        texto,
        flags=re.IGNORECASE,
    )
    return [p.strip(" .,;").capitalize() for p in partes if p.strip(" .,;")]
