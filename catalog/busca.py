# -*- coding: utf-8 -*-
"""Achar alimento por nome, do jeito que a pessoa digita.

ISTO EXISTE PORQUE O NOME DIGITADO NÃO CASAVA (achado das personas,
21/09/2026): "comi outra coisa" comparava o que a pessoa escreveu com
`Food.name` exato, sem acento e sem maiúscula, mas TAMBÉM sem tolerância a
acento — quem escrevia "feijao", "acai" ou "pao" não casava com "Feijão",
"Açaí" e "Pão", e a refeição entrava com ZERO caloria. No teclado do
celular o acento é justamente o que ninguém digita.

A NORMALIZAÇÃO É UMA SÓ, e mora aqui: `normalizar`. Ela é usada em quatro
lugares que TÊM de concordar — a coluna `Food.busca` (gravada pelos dois
seeds e pela migration), a busca da tela, o casamento do que foi digitado, e
o teste que varre o catálogo. Duas normalizações diferentes seriam a mesma
palavra achando coisas diferentes em telas diferentes.

POR QUE UMA COLUNA E NÃO `unaccent` DO POSTGRES: a extensão precisa de
`CREATE EXTENSION`, que exige privilégio que o role do app não tem no Neon —
e a migration que a criasse falharia no build, não no teste. A coluna é
determinística, é indexável, e o teste de varredura prova que ela não
diverge do nome.
"""
import unicodedata

from django.db.models import Case, IntegerField, Q, When

#: Menos de duas letras não é busca, é a primeira tecla.
#:
#: Com UMA letra, "a" devolveria as primeiras oito de mais de trezentas
#: linhas — uma lista que não responde ao que a pessoa está escrevendo, e que
#: pisca a cada tecla no meio do formulário. É o mínimo que o item 3 da missão
#: pede, e o número está aqui para o servidor e a tela lerem o mesmo.
MINIMO_DE_LETRAS = 2

#: Quantas sugestões cabem sem virar uma segunda tela.
#:
#: Oito é o teto do item 3 da missão. A 390 px, oito linhas de 44 px são 352
#: px — a lista cabe acima do teclado sem cobrir o campo que a pessoa está
#: digitando.
MAXIMO_DE_SUGESTOES = 8


def normalizar(texto) -> str:
    """Minúscula, sem acento, sem espaço sobrando.

    `NFD` separa a letra do acento e `Mn` ("mark, nonspacing") é a categoria
    do acento separado: o que sobra é a letra nua. `casefold` e não `lower`
    porque ele fecha casos que `lower` não fecha (o "ß" do alemão vira "ss");
    não há nome de alimento assim no catálogo, mas a função é a fonte única e
    não custa nada estar certa.
    """
    texto = " ".join((texto or "").split())
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).casefold()


def sugerir(termo, limite=MAXIMO_DE_SUGESTOES):
    """Os alimentos que casam com `termo`, os que COMEÇAM com ele primeiro.

    Devolve `QuerySet` de `Food`, já cortado no limite — UMA consulta, com a
    ordem e o corte feitos pelo banco.

    A ordem é o que faz a lista útil: "carne" casa com 66 linhas da TACO, e
    "Carne, bovina, acém..." interessa mais que "Sopa de carne com legumes".
    O prefixo vem primeiro porque é o que a pessoa está escrevendo; o
    "contém" fica porque a TACO escreve o nome INVERTIDO ("Queijo,
    requeijão, cremoso"), e quem digita "requeijao" não acharia nada com
    prefixo só.
    """
    from catalog.models import Food

    termo = normalizar(termo)
    if len(termo) < MINIMO_DE_LETRAS:
        return Food.objects.none()
    return (
        Food.objects.filter(is_active=True)
        .filter(Q(busca__startswith=termo) | Q(busca__contains=termo))
        .annotate(
            # O flag de prefixo é calculado pelo BANCO para que o `[:limite]`
            # também seja dele: ordenar em Python exigiria trazer as 66 linhas
            # de "carne" para escolher oito.
            prefixo=Case(
                When(busca__startswith=termo, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("prefixo", "busca")[:limite]
    )


def por_nome_digitado(nomes):
    """`{normalizado: Food}` para os nomes que a pessoa escreveu.

    Uma consulta, e só o que foi pedido. A versão anterior carregava o
    catálogo INTEIRO em memória para comparar em Python — dava para os 102
    alimentos curados e passou a dar 685 com a TACO, em todo registro de
    "comi outra coisa".
    """
    from catalog.models import Food

    chaves = {normalizar(nome) for nome in nomes if normalizar(nome)}
    if not chaves:
        return {}
    # O CURADO GANHA DO IMPORTADO quando os dois normalizam para a mesma
    # chave: "Banana prata" (com porção, corredor de mercado e papel no prato)
    # vale mais que a linha crua da tabela. `source` ordena "manual" antes de
    # "taco", e o `setdefault` faz o primeiro vencer.
    achados = {}
    for food in Food.objects.filter(is_active=True, busca__in=chaves).order_by(
        "source", "name"
    ):
        achados.setdefault(food.busca, food)
    return achados
