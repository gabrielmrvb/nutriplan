"""O rodízio diário do cardápio: quais opções do repertório aparecem hoje.

O problema que este módulo resolve: cada `MealSlot` guarda um repertório
PERSISTENTE de opções (quatro, no cardápio V2), e a tela mostra duas. Quais
duas é função do dia — e precisa ser a MESMA resposta em toda parte.

Uma regra, vários consumidores. A tela Hoje, o total do cardápio e a lista de
compras chamam daqui. Reimplementar a escolha em qualquer um deles criaria
duas respostas para "o que eu como hoje", e elas divergiriam na primeira
mudança — foi exatamente o que aconteceu com "quem é a vez" antes de
`agora.marcar_refeicoes` passar a LER a decisão em vez de refazê-la.

O que este módulo NÃO faz, e de propósito:

*   não cria, apaga nem reordena `MealOption`. Opção é objeto persistente; o
    rodízio é uma projeção de leitura sobre o que já existe. Recriar opções por
    dia arrancaria a identidade que o histórico e a fila offline usam;
*   não usa `random`. Nem `random.seed()`, que é estado global e contaminaria
    qualquer outro sorteio do processo, nem `hash()`, que o Python randomiza
    por processo (`PYTHONHASHSEED`) — dois workers do mesmo servidor
    responderiam cardápios diferentes no mesmo dia;
*   não olha para `plan.pk`. Ver `_deslocamento`.
"""

from __future__ import annotations

import hashlib
from itertools import combinations

from django.utils import timezone

from .models import OptionLabel

#: Quantas opções a tela mostra por refeição, por dia.
#:
#: Sai de `OptionLabel` porque é a mesma coisa dita duas vezes: os rótulos são
#: a apresentação das opções projetadas, e mostrar três com dois rótulos
#: disponíveis é um estado impossível que não precisa existir.
POR_DIA = len(OptionLabel.values)


def _ordenar_pares(pares: list) -> list:
    """Ordena os pares para que dias seguidos repitam o mínimo possível.

    Ciclar os pares em ordem lexicográfica cumpriria o determinismo e falharia
    no PRODUTO. Com quatro opções, `combinations` devolve
    `(0,1) (0,2) (0,3) (1,2) (1,3) (2,3)`: a opção 0 apareceria três dias
    seguidos, e "pouca variedade" é justamente a queixa que o cardápio V2
    existe para resolver.

    A ordenação gulosa começa no primeiro par e sempre escolhe, entre os que
    sobraram, o de menor sobreposição com o anterior — desempatando pelo par em
    si, para não depender de ordem de conjunto. Com quatro opções ela encontra
    sozinha o emparelhamento round-robin `(0,1) (2,3) (0,2) (1,3) (0,3) (1,2)`:
    nenhum dia repete os DOIS pratos do dia anterior, e nenhuma opção aparece
    três dias seguidos.
    """
    restantes = sorted(pares)
    ordenados = [restantes.pop(0)]
    while restantes:
        anterior = set(ordenados[-1])
        proximo = min(restantes, key=lambda par: (len(anterior & set(par)), par))
        restantes.remove(proximo)
        ordenados.append(proximo)
    return ordenados


def _deslocamento(user_pk: int, slot_order: int) -> int:
    """De onde este slot, desta pessoa, começa a percorrer o ciclo de pares.

    É o que tira os horários de fase entre si: sem ele, café e almoço
    avançariam em bloco e o dia inteiro trocaria junto, o que faz o cardápio
    parecer dois cardápios alternando em vez de variar.

    `sha256` e não `hash()`: precisa valer entre processos, entre reinícios e
    entre máquinas. A pessoa que abre o app no celular e no computador no mesmo
    dia tem que ver a mesma comida.

    Repare no que NÃO entra aqui: `plan.pk`. O `NutritionPlan` é retrato, e
    nasce um novo sempre que a entrada muda — pesagem nova, recalibração,
    ajuste de altura. Semear pelo pk faria o almoço trocar porque a pessoa
    subiu na balança, e não porque o dia virou.
    """
    semente = "%d:%d" % (user_pk, slot_order)
    return int.from_bytes(hashlib.sha256(semente.encode("utf-8")).digest()[:8], "big")


def indices_do_dia(total: int, user_pk: int, slot_order: int, dia) -> tuple:
    """Quais posições do repertório aparecem neste dia, em ordem crescente.

    `total` é o tamanho do repertório do slot. A resposta tem `POR_DIA` itens
    quando há repertório para isso, e menos quando não há — ver os fallbacks
    logo abaixo, que existem porque produção já tem planos com duas opções e
    eles não podem esperar por uma regeneração para continuar funcionando.
    """
    if total <= 0:
        return ()
    if total <= POR_DIA:
        # Duas opções (o cardápio V1) devolvem as duas; uma devolve a única.
        # Não há o que rodar, e forçar um ciclo aqui só criaria um caminho a
        # mais para dar errado.
        return tuple(range(total))

    pares = _ordenar_pares(list(combinations(range(total), POR_DIA)))
    # O dia AVANÇA o ciclo em um passo. É isso que garante que dias
    # consecutivos caiam em pares vizinhos — que a ordenação gulosa já
    # escolheu para serem diferentes entre si — em vez de saltarem ao acaso e
    # poderem repetir a mesma dupla dois dias seguidos.
    posicao = (_deslocamento(user_pk, slot_order) + dia.toordinal()) % len(pares)
    return pares[posicao]


def opcoes_do_dia(slot, user_pk: int, dia=None) -> list:
    """As opções projetadas para este slot neste dia, já rotuladas.

    Lê `slot.options.all()` de propósito, para aproveitar o
    `prefetch_related` que a view já faz: sem isso a projeção custaria uma
    consulta por horário, e a tela Hoje tem cinco.

    O rótulo A/B é ATRIBUÍDO AQUI, pela posição na projeção, e não lido de um
    campo. É a diferença que o cardápio V2 introduz: "A" quer dizer "a
    primeira opção de hoje", e amanhã pode ser outra receita. A identidade
    persistente — a que o histórico guarda e a fila offline reenvia — é o
    `rank`, que não muda.
    """
    dia = dia or timezone.localdate()
    opcoes = list(slot.options.all())
    if not opcoes:
        return []

    # Ordena por `rank` em Python, e não com `order_by`, porque `order_by`
    # numa relação já pré-carregada dispara uma consulta nova e desmonta o
    # prefetch. O model já ordena por rank; isto é cinto e suspensório para o
    # caso de a lista chegar de outro caminho.
    opcoes.sort(key=lambda opcao: opcao.rank)
    posicoes = {opcao.rank: opcao for opcao in opcoes}

    indices = indices_do_dia(len(opcoes), user_pk, slot.order, dia)
    escolhidas = []
    for rotulo, indice in zip(OptionLabel.values, indices):
        # O repertório pode ter buracos de rank — um plano antigo com rank 0 e
        # 2, por exemplo. `indices_do_dia` trabalha em POSIÇÕES, então a
        # tradução para o objeto é pela posição na lista ordenada, com o
        # dicionário por rank servindo só quando a posição bate com o rank.
        opcao = posicoes.get(indice) if indice in posicoes else opcoes[indice]
        opcao.rotulo = rotulo
        escolhidas.append(opcao)
    return escolhidas


def projetar(slots, user_pk: int, dia=None) -> None:
    """Pendura `opcoes_do_dia` em cada slot da lista, no lugar.

    Existe para que a tela não chame a projeção dentro do template: template
    que chama função com argumento acaba virando lógica de negócio em HTML, e
    aqui o argumento é justamente a data, que é onde os erros de fuso moram.
    """
    dia = dia or timezone.localdate()
    for slot in slots:
        slot.opcoes_do_dia = opcoes_do_dia(slot, user_pk, dia)
