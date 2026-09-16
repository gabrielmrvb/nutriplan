"""Uma letra, até duas opções completas e intercambiáveis (15/09/2026).

O QUE ESTE MÓDULO FECHA, medido em produção no perfil intermediário, cinco
dias, dois grupos por dia: A1 com 4 exercícios, 13 séries, ~36 minutos e A2
com 4, 13, ~29 — a mesma letra com conteúdos diferentes em dias diferentes,
cada sessão curta, e a nomenclatura dizendo "dois treinos obrigatórios".

`repartir_ocorrencia` já repartia o modelo entre as passagens da letra; o que
faltava era tratar as duas metades como VERSÕES da mesma letra, dar a cada
uma o tamanho de uma sessão, e deixar a pessoa escolher qual faz no dia.

Tudo aqui é função pura sobre os itens do catálogo (`WorkoutTemplateItem`) —
nada lê banco, nada lê relógio. Quem grava é `services.create_routine`;
quem confere se a ficha gravada é a que sairia hoje é `services._prescricao_confere`,
pela MESMA função, porque duas cópias da conta é como as duas nascem
diferentes.

AS REGRAS DE EQUIVALÊNCIA, e cada uma tem teste:

- os mesmos grupos principais nas duas opções;
- os mesmos PADRÕES COMPOSTOS em cada grupo principal (16/09/2026): puxada
  e remada numa opção contra duas puxadas na outra têm o mesmo volume e os
  mesmos minutos, e não são a mesma semana. Os isoladores podem diferir;
- volume por grupo com diferença de no máximo UMA série;
- duração estimada com diferença de no máximo CINCO minutos;
- pelo menos METADE dos exercícios de cada opção não está na outra;
- compatíveis com o nível (o teto semanal é da pessoa) e com o catálogo
  (só exercício ativo, dose do modelo, papel de cada um preservado).

Sem catálogo para duas opções assim, sai UMA — nunca uma alternativa falsa.
"""
import copy
from collections import OrderedDict
from decimal import Decimal

from . import doutrina
from .models import PADROES_COMPOSTOS, segundos_da_sessao

#: Quantas séries DIRETAS uma sessão quer ter, POR NÍVEL E POR TIPO DE DIA —
#: desde 17/09/2026 lidas do `docs/briefs/treino/TREINO.md` (`doutrina`).
#: A faixa antiga (12–15 / 15–18 / 16–20, só por nível) era a causa, junto
#: com o catálogo, de "Peito e tríceps" sair com 13 séries em 36 minutos:
#: uma ficha de academia de dois grupos tem 21–28. Abaixo do piso a opção
#: pede série ao isolador e ao acessório — até QUATRO por exercício, nunca
#: mais —; acima do teto ela não cresce. `PISO_SERIES_COMPLETO` e
#: `TETO_SERIES_COMPLETO` são o intermediário de dois grupos, o padrão de
#: quem chama sem faixa.
PISO_SERIES_COMPLETO, TETO_SERIES_COMPLETO = doutrina.faixa_de_series(doutrina.NIVEL_PADRAO, doutrina.DOIS_GRUPOS)
TETO_SERIES_POR_EXERCICIO = 4


def faixa_de_series(nivel, tipo_de_dia) -> tuple:
    """`(piso, teto)` de séries diretas por sessão, do TREINO.md."""
    return doutrina.faixa_de_series(nivel, tipo_de_dia)

#: A partir de quantos minutos de teto a opção sobe até a faixa. Abaixo
#: disso (a faixa "até 30"), encher os anunciados só tirava os complementares
#: no corte seguinte; a dose fica a do catálogo.
MINUTOS_PARA_PREENCHER = 45

#: Quanto tempo a versão rápida pode levar, em minutos. Derivada da opção
#: escolhida por `escolher_para_o_tempo` — as mesmas cinco camadas do corte
#: por relógio, então os principais ficam e o acessório de menor prioridade
#: sai primeiro. Não é uma terceira ficha.
TETO_RAPIDO_MIN = 40

#: A sessão completa é a FICHA INTEIRA: até 90 minutos. É o teto para quem
#: não tem teto (`duracao_treino` "livre") e para quem nunca respondeu; quem
#: escolheu uma faixa continua com a faixa dela — a escolha não é
#: sobrescrita. Foi 65 entre 15 e 17/09/2026, enquanto o catálogo não
#: sustentava mais que isso; com o catálogo dos 63 e a faixa do TREINO.md, a
#: ficha de dois grupos do intermediário fecha em 60–80 minutos.
TETO_COMPLETO_MIN = 90

#: Diferença máxima entre as opções: uma série por grupo, cinco minutos.
TOLERANCIA_DE_SERIES = 1
TOLERANCIA_DE_MINUTOS = 5

#: Com duas opções, o PENÚLTIMO exercício direto de um grupo só sai da opção
#: quando a semana passa do teto em mais do que esta fração dele. Abaixo
#: disso o excesso fica (teto de aparo, não promessa): tirar a corda de uma
#: opção — e da irmã, que acompanha — para cobrir uma série deixava a semana
#: com UM tríceps distinto. Acima disso é o aparo que o nível pede: o
#: iniciante (teto 12) com o ombro em 21 perde a elevação lateral, como
#: sempre perdeu. Medido POR OCORRÊNCIA da letra: a letra que cai duas ou
#: três vezes soma o mesmo secundário duas ou três vezes, e esse excesso de
#: frequência não se conserta apagando o único isolador do dia — e só quando
#: a própria letra, repetida, já passa do teto no grupo. Um quinto, e não
#: metade: com metade o iniciante ficava com o mesmo volume do intermediário
#: (73 contra 74 séries na semana) e o nível deixava de valer; com um quarto
#: o crucifixo do iniciante (teto 12, peito em 17 com A duas vezes: 2,5 por
#: ocorrência) ficava, e a semana dele fechava em 88% da do intermediário
#: contra os 85% que `test_experiencia` mede desde 10/09/2026.
FRACAO_DE_EXCESSO_QUE_DESTRAVA = Decimal("0.2")

#: Fração mínima de exercícios PRÓPRIOS em cada opção. Meio a meio é o que
#: separa "duas versões" de "a mesma ficha com um exercício trocado".
FRACAO_MINIMA_DISTINTA = Decimal("0.5")


def _por_grupo(itens) -> "OrderedDict":
    grupos = OrderedDict()
    for item in itens:
        grupos.setdefault(item.exercise.muscle_group, []).append(item)
    return grupos


def _partes_por_padrao(lista, n, compartilhados) -> list:
    """Reparte um grupo ANUNCIADO em `n` partes, por padrão composto.

    Cada padrão composto do grupo é um bloco em rodízio próprio — assim cada
    parte recebe uma pressão de peito, uma puxada, uma remada. Bloco com
    menos exercícios que partes vai INTEIRO para todas, como compartilhado:
    é a única forma de as duas opções cobrirem o padrão, e a régua de metade
    própria (`distintas_o_bastante`) decide depois se a letra sai com duas.
    Os isoladores formam um bloco só, em rodízio, e podem diferir entre as
    partes — a régua de equivalência não os compara. O rodízio continua de
    um bloco para o outro (`deslocamento`), para os tamanhos se equilibrarem
    entre blocos e não dentro de cada um.
    """
    blocos = OrderedDict()
    isoladores = []
    for item in lista:
        padrao = getattr(item.exercise, "padrao", "")
        if padrao in PADROES_COMPOSTOS:
            blocos.setdefault(padrao, []).append(item)
        else:
            isoladores.append(item)
    partes = [[] for _ in range(n)]
    deslocamento = 0
    for bloco in list(blocos.values()) + ([isoladores] if isoladores else []):
        if bloco is not isoladores and len(bloco) < n:
            for parte in partes:
                parte.extend(bloco)
            compartilhados.update(item.exercise_id for item in bloco)
            continue
        for i, item in enumerate(bloco):
            partes[(i + deslocamento) % n].append(item)
        deslocamento = (deslocamento + len(bloco)) % n
    return partes


def montar_opcoes(itens, n=2, principais=()) -> list:
    """Divide os itens do modelo em `n` opções, e diz quais são compartilhados.

    Devolve `(opcoes, compartilhados)`: `opcoes` é uma lista de listas de itens
    NA ORDEM DO MODELO, `compartilhados` é o conjunto de `exercise_id` que
    aparece em mais de uma opção.

    POR GRUPO MUSCULAR, em rodízio: a opção `k` leva as posições `k`, `k+n`,
    `k+2n`... do grupo — é a mesma repartição de `repartir_ocorrencia`, e a
    razão é a mesma: repartir a lista inteira deixaria uma opção sem peito e a
    outra sem tríceps. Grupo ÍMPAR: a opção que ficou com um a menos recebe o
    último do rodízio da outra como compartilhado, para as duas terem o mesmo
    tamanho (com três tríceps, uma leva mergulho e corda, a outra testa e
    corda). Grupo com menos exercícios que opções: todos compartilham.

    GRUPO ANUNCIADO (`principais`) é repartido por PADRÃO COMPOSTO
    (`_partes_por_padrao`), para cada opção levar uma pressão, uma puxada,
    uma remada — o padrão composto com um exercício só é compartilhado. Sem
    isso a régua de equivalência (mesmos padrões compostos por grupo
    anunciado) reprovava 13 das 16 letras que hoje saem com duas opções: o
    rodízio cego dava o crucifixo a uma e o mergulho à outra.
    """
    opcoes = [[] for _ in range(n)]
    compartilhados = set()
    anunciados = set(principais or ())
    for j, (grupo, lista) in enumerate(_por_grupo(itens).items()):
        if len(lista) < n:
            for k in range(n):
                opcoes[k].extend(lista)
            compartilhados.update(item.exercise_id for item in lista)
            continue
        if grupo in anunciados:
            partes = _partes_por_padrao(lista, n, compartilhados)
        else:
            partes = [lista[k::n] for k in range(n)]
        maior = max(len(parte) for parte in partes)
        for k, parte in enumerate(partes):
            faltam = maior - len(parte)
            if faltam:
                # Os últimos da parte mais cheia, que são os de menor
                # prioridade pela ordem do modelo — e que esta parte ainda
                # não tem (um compartilhado já está nas duas).
                doadora = max(partes, key=len)
                emprestados = [item for item in doadora if item not in parte][-faltam:]
                parte = parte + emprestados
                compartilhados.update(item.exercise_id for item in emprestados)
            # O GRUPO SEGUINTE COMEÇA PELA OUTRA OPÇÃO. O primeiro exercício
            # de cada grupo é o principal (mais séries, composto, descanso
            # maior); dar sempre à opção 1 o primeiro de todo grupo deixava
            # uma opção com três compostos e a outra com um — doze minutos
            # de diferença que nenhuma série equilibra.
            opcoes[(k + j) % n].extend(parte)
    posicao = {id(item): i for i, item in enumerate(itens)}
    return [sorted(op, key=lambda item: posicao[id(item)]) for op in opcoes], compartilhados


def distintas_o_bastante(opcoes, compartilhados) -> bool:
    """Metade ou mais de cada opção é só dela."""
    for op in opcoes:
        if not op:
            return False
        proprios = sum(1 for item in op if item.exercise_id not in compartilhados)
        if Decimal(proprios) / Decimal(len(op)) < FRACAO_MINIMA_DISTINTA:
            return False
    return True


def _minutos(linhas) -> int:
    """`linhas` são `(item, series, grau)`."""
    return round(
        segundos_da_sessao(
            [(series, item.rest_seconds, item.exercise.is_compound) for item, series, _ in linhas]
        )
        / 60
    )


def _cabe(linhas, teto_min) -> bool:
    return teto_min is None or _minutos(linhas) <= teto_min


def preencher_ate_a_faixa(linhas, teto_min, principal, faixa=None, por_exercicio=None) -> list:
    """Leva a sessão à faixa de séries diretas dos grupos anunciados: sobe a
    série de isolador e acessório até o TOPO dela — e, quando a dose do
    catálogo já passa do topo, desce até ele.

    `linhas` são `(item, series, grau)` na ordem da ficha. Uma série por vez,
    do PRIMEIRO isolador/acessório de um grupo ANUNCIADO (o complementar não
    faz um treino de peito e tríceps parecer maior, e não entra na conta),
    nunca acima do teto por exercício do NÍVEL, nunca acima do teto de
    séries, nunca além do tempo. O composto principal não recebe: ele já tem
    a dose que o catálogo pede.

    ATÉ O TOPO, e não até o piso (17/09/2026): a ficha padrão de academia é
    3 a 4 séries por exercício, e parar no piso (21, para dois grupos)
    deixava "Peito e tríceps" em 22 séries e 54 minutos com o catálogo
    inteiro. O que segura é o relógio (`teto_min`), o teto semanal da
    frequência (`aparar_opcoes`, depois) e o teto por exercício.

    `por_exercicio` é `(piso, teto)` de séries por exercício do nível
    (TREINO.md, tabela A): o iniciante faz 2 a 3, e o modelo é o MESMO dos
    outros níveis — o supino de quatro do catálogo vira três para ele, e
    "Peito, tríceps e ombro" com oito exercícios desce a 18 séries baixando
    isolador e acessório a duas antes de subir de volta até o topo. Sem o
    argumento vale o intermediário (3 a 4).
    """
    piso, teto_series = faixa or (PISO_SERIES_COMPLETO, TETO_SERIES_COMPLETO)
    piso_ex, teto_ex = por_exercicio or doutrina.series_por_exercicio(doutrina.NIVEL_PADRAO)
    anunciados = set(principal or ())

    def anunciado(item):
        return not anunciados or item.exercise.muscle_group in anunciados

    # O teto por exercício do nível vale para todo anunciado, principal
    # incluído: quatro séries de supino não são dose de iniciante.
    linhas = [
        (item, min(series, teto_ex) if anunciado(item) else series, grau)
        for item, series, grau in linhas
    ]

    def diretas_anunciadas():
        return sum(s for item, s, _ in linhas if anunciado(item))

    total = diretas_anunciadas()
    # Acima do topo, desce: uma série por vez, do isolador para o acessório,
    # do mais cheio para o mais vazio, nunca abaixo do piso do nível e nunca
    # do principal. Sobrando excesso depois disso, fica — o teto semanal e o
    # relógio ainda passam por aqui.
    while total > teto_series:
        cedem = [
            i for i, (item, series, grau) in enumerate(linhas)
            if grau < 2 and series > piso_ex and anunciado(item)
        ]
        if not cedem:
            break
        cedem.sort(key=lambda i: (linhas[i][2], -linhas[i][1], -i))
        i = cedem[0]
        item, series, grau = linhas[i]
        linhas[i] = (item, series - 1, grau)
        total -= 1
    if total >= teto_series:
        return linhas
    mudou = True
    while total < teto_series and mudou:
        mudou = False
        # Em RODÍZIO: uma série por exercício por volta, do acessório para o
        # isolador — para nenhum isolador chegar a quatro enquanto outro
        # continua em três.
        elegiveis = [
            i for i, (item, series, grau) in enumerate(linhas)
            if grau < 2 and series < teto_ex and anunciado(item)
        ]
        elegiveis.sort(key=lambda i: (-linhas[i][2], linhas[i][1], i))
        for i in elegiveis:
            item, series, grau = linhas[i]
            tentativa = list(linhas)
            tentativa[i] = (item, series + 1, grau)
            if total + 1 > teto_series or not _cabe(tentativa, teto_min):
                continue
            linhas = tentativa
            total += 1
            mudou = True
            if total >= teto_series:
                break
    return linhas


def _volume(linhas) -> dict:
    """Séries efetivas por grupo: direta vale 1, secundária vale meia."""
    from .services import volume_efetivo

    return volume_efetivo(
        [
            (item.exercise.muscle_group, tuple(item.exercise.secondary_muscles or ()), Decimal(series))
            for item, series, _ in linhas
        ]
    )


def volume_semanal_pior_caso(por_letra, ocorrencias) -> dict:
    """Por grupo, o MAIOR volume que a semana pode ter: cada ocorrência da
    letra faz a opção mais pesada naquele grupo.

    É a conta que faz "repetir sempre a preferida" caber no teto — e que NÃO
    soma as duas opções, porque ninguém faz os dois treinos no mesmo dia.
    """
    total = {}
    for label, opcoes in por_letra.items():
        volumes = [_volume(op) for op in opcoes]
        grupos = set().union(*(v.keys() for v in volumes)) if volumes else set()
        for grupo in grupos:
            pior = max(v.get(grupo, Decimal(0)) for v in volumes)
            total[grupo] = total.get(grupo, Decimal(0)) + pior * ocorrencias.get(label, 1)
    return total


def _pior_caso_direto(por_letra, ocorrencias) -> dict:
    """Como `volume_semanal_pior_caso`, sobre séries DIRETAS."""
    total = {}
    for label, opcoes in por_letra.items():
        volumes = [_volume_direto(op) for op in opcoes]
        grupos = set().union(*(v.keys() for v in volumes)) if volumes else set()
        for grupo in grupos:
            pior = max(v.get(grupo, 0) for v in volumes)
            total[grupo] = total.get(grupo, 0) + pior * ocorrencias.get(label, 1)
    return total


def _ceder(op, grupo, dose_do_catalogo, minimo_diretos=1, excesso=None):
    """Uma concessão no grupo, nesta ordem: a série que o preenchimento
    acrescentou volta ao catálogo; um isolador desce ao piso de duas; só então
    um exercício sai — o de menor grau (isolador antes de acessório), nunca o
    último exercício direto do grupo na opção, nunca o composto principal.
    Devolve `(exercise_id, séries_agora)` — `None` em `séries_agora` quando o
    exercício saiu — ou `None` quando não há o que ceder.

    `minimo_diretos` é quantos exercícios diretos do grupo a opção precisa
    manter para um poder sair (1: a trava de sempre). `excesso` só é
    informado quando a letra tem duas opções ou mais, e diz se o excesso da
    semana é GRANDE (`FRACAO_DE_EXCESSO_QUE_DESTRAVA`): com excesso pequeno
    o PENÚLTIMO direto não sai. Uma opção que perde o penúltimo direto fica
    só com o composto — compartilhado quando é único —, a irmã acompanha e
    a letra termina com o mesmo tríceps nas duas versões; pagar quatro
    séries para cobrir uma não é aparo, é amputação (medido no abc2 de seis
    dias, 16/09/2026: corda e testa saíam por UM excesso de uma série; a 7
    dias, com A três vezes, o peito fica 21 direto contra 20 e a flexão de
    braço ficaria de fora da semana por uma série). Com excesso grande — o
    iniciante, teto 12, com o ombro em 21 —, a remoção é o aparo que o
    nível pede, e acontece. O que sobra é teto de aparo, não promessa —
    inclusive uma série DIRETA acima dele.
    """
    diretos = [i for i, (item, _, _) in enumerate(op) if item.exercise.muscle_group == grupo]
    podem = [i for i in diretos if op[i][2] < 2]
    if not podem:
        return None
    acrescidos = [i for i in podem if op[i][1] > dose_do_catalogo(op[i][0])]
    if acrescidos:
        i = acrescidos[-1]
        item, series, grau = op[i]
        op[i] = (item, series - 1, grau)
        return (item.exercise_id, series - 1)
    isoladores = [i for i in podem if op[i][2] == 0 and op[i][1] > 2]
    if isoladores:
        i = isoladores[-1]
        item, series, grau = op[i]
        op[i] = (item, series - 1, grau)
        return (item.exercise_id, series - 1)
    if len(diretos) <= minimo_diretos:
        return None
    grau_minimo = min(op[i][2] for i in podem)
    i = [i for i in podem if op[i][2] == grau_minimo][-1]
    if len(diretos) == 2 and excesso is not None and not excesso:
        return None
    saiu = op[i][0].exercise_id
    del op[i]
    return (saiu, None)


def _espelhar(outra, grupo, exercise_id, series_agora) -> None:
    """A concessão num exercício COMPARTILHADO vale para a irmã também.

    O crucifixo entra nas três opções de uma letra que cai três vezes; se
    o teto o tira de uma e o deixa nas outras, as opções deixam de ser
    equivalentes por causa de um exercício que era o mesmo. A irmã segue:
    reduz ao mesmo número, ou remove — nunca o último direto do grupo dela.
    """
    for i, (item, series, grau) in enumerate(outra):
        if item.exercise_id != exercise_id:
            continue
        if grau >= 2:
            # Na irmã ele é o composto PRINCIPAL do grupo (o rodízio pode
            # dar a mesma elevação pélvica como acessório numa opção e como
            # principal na outra). Principal nunca cede — nem por espelho.
            return
        if series_agora is None:
            diretos = [j for j, (o, _, _) in enumerate(outra) if o.exercise.muscle_group == grupo]
            if len(diretos) > 1:
                del outra[i]
        elif series > series_agora:
            piso = 3 if grau >= 1 else 2
            outra[i] = (item, max(series_agora, piso), grau)
        return


def _limites(teto, grupos) -> dict:
    """O teto de cada grupo: um número para todos (a chamada antiga) ou um
    dicionário grupo → teto — o da FREQUÊNCIA do grupo na semana, desde
    17/09/2026 (`doutrina.teto_semanal`)."""
    if isinstance(teto, dict):
        padrao = Decimal(teto.get("*", 10_000))
        return {g: Decimal(teto.get(g, padrao)) for g in grupos}
    return {g: Decimal(teto) for g in grupos}


def aparar_opcoes(por_letra, ocorrencias, teto, dose_do_catalogo) -> dict:
    """Faz o pior caso da semana caber no teto por grupo, cedendo por opção.

    As TRÊS TRAVAS de `aparar_volume_semanal` valem aqui, e pela mesma razão:
    só cede quem treina o grupo DIRETAMENTE; nunca o último exercício direto
    do grupo NA OPÇÃO; e cede a opção que está puxando o máximo. A ordem de
    concessão é a de `_ceder`: série acrescentada, série de isolador até o
    piso, e só então o isolador inteiro. Composto principal nunca cede — se o
    excesso só puder ser resolvido nele, o excesso fica (teto de aparo, não
    promessa).

    E A IRMÃ ACOMPANHA: quando uma opção cede num grupo e a outra fica mais
    de uma série acima dela, a outra cede também. As duas nascem parecidas e
    precisam terminar equivalentes — cortar só uma delas era o que fazia a
    letra perder a segunda opção.
    """
    por_letra = {label: [list(op) for op in opcoes] for label, opcoes in por_letra.items()}
    for _ in range(200):
        pior_caso = volume_semanal_pior_caso(por_letra, ocorrencias)
        limites = _limites(teto, pior_caso)
        pendentes = sorted(
            (g for g, v in pior_caso.items() if v > limites[g]),
            key=lambda g: (pior_caso[g], g),
            reverse=True,
        )
        cedeu = False
        for grupo in pendentes:
            limite = limites[grupo]
            candidatas = []
            for label, opcoes in por_letra.items():
                for k, op in enumerate(opcoes):
                    vol = _volume(op).get(grupo, Decimal(0)) * ocorrencias.get(label, 1)
                    if vol:
                        candidatas.append((vol, label, k))
            candidatas.sort(key=lambda c: c[0], reverse=True)
            for _vol, label, k in candidatas:
                # A CONCESSÃO É ENSAIADA NUMA CÓPIA, e só vale se a letra
                # continuar equivalente no grupo. A irmã acompanha pelo
                # volume DIRETO, que é a régua de equivalência — e não pelo
                # efetivo, que é a régua do teto; os dois divergem quando
                # uma opção carrega mais secundário (flexão de braço, três).
                # Quando nem assim a diferença cabe em uma série — a
                # concessão tiraria o último isolador de uma opção e a irmã
                # não tem o que ceder —, a concessão NÃO acontece e o
                # excesso fica: teto de aparo, não promessa, exatamente como
                # o excesso que só um composto principal resolveria. Medido
                # em 16/09/2026 no abc2 de seis dias: cortar a corda de uma
                # opção deixava tríceps 3 contra 6 e a letra perdia a
                # segunda opção; seguir a irmã até o fim deixava as duas só
                # com o mergulho. Ficar uma série efetiva acima do teto é
                # o menor dos três preços — e é por isso que o penúltimo
                # direto só sai quando o excesso vale metade das séries dele
                # (`_ceder`, `excesso`).
                tentativa = [list(o) for o in por_letra[label]]
                excesso = None
                if len(tentativa) > 1:
                    # O penúltimo direto só sai com excesso GRANDE: mais de um
                    # quinto do teto POR OCORRÊNCIA da letra
                    # (`FRACAO_DE_EXCESSO_QUE_DESTRAVA`). Por ocorrência,
                    # porque a letra que cai duas ou três vezes soma o mesmo
                    # secundário duas ou três vezes — excesso de frequência,
                    # que apagar o único isolador do dia não conserta.
                    # E só se a PRÓPRIA letra, repetida, já passa do teto
                    # no grupo: o ombro de "Pernas e ombros" não paga o
                    # secundário dos pressões de "Peito e tríceps".
                    por_ocorrencia = (pior_caso[grupo] - limite) / Decimal(ocorrencias.get(label, 1))
                    proprio = max(_volume(o).get(grupo, Decimal(0)) for o in tentativa) * ocorrencias.get(label, 1)
                    excesso = (
                        por_ocorrencia > limite * FRACAO_DE_EXCESSO_QUE_DESTRAVA
                        and proprio > limite
                    )
                op = tentativa[k]
                concessao = _ceder(op, grupo, dose_do_catalogo, excesso=excesso)
                if concessao is None:
                    continue
                exercise_id, series_agora = concessao
                for outra in tentativa:
                    if outra is op:
                        continue
                    _espelhar(outra, grupo, exercise_id, series_agora)
                    for _ in range(TETO_SERIES_POR_EXERCICIO):
                        diferenca = (
                            _volume_direto(outra).get(grupo, 0) - _volume_direto(op).get(grupo, 0)
                        )
                        if diferenca <= TOLERANCIA_DE_SERIES:
                            break
                        # A irmã acompanha com a MESMA régua: se seguir
                        # exigiria dela o penúltimo direto por um excesso
                        # pequeno, ela não segue — e a concessão inteira é
                        # descartada logo abaixo.
                        if _ceder(outra, grupo, dose_do_catalogo, excesso=excesso) is None:
                            break
                diretos = [_volume_direto(o).get(grupo, 0) for o in tentativa]
                if len(tentativa) > 1 and max(diretos) - min(diretos) > TOLERANCIA_DE_SERIES:
                    continue
                por_letra[label] = tentativa
                cedeu = True
                break
            if cedeu:
                break
        if not cedeu:
            return por_letra
    return por_letra


def _volume_direto(linhas) -> dict:
    """Séries DIRETAS por grupo. É a régua de equivalência: o secundário
    entra no teto semanal (meia série), mas comparar opções por ele faria a
    flexão de braço — três secundários — desequilibrar ombro e core."""
    volume = {}
    for item, series, _ in linhas:
        volume[item.exercise.muscle_group] = volume.get(item.exercise.muscle_group, 0) + series
    return volume


def _padroes_compostos(linhas, grupo) -> frozenset:
    """Os padrões COMPOSTOS que a opção cobre num grupo."""
    return frozenset(
        getattr(item.exercise, "padrao", "")
        for item, _, _ in linhas
        if item.exercise.muscle_group == grupo
        and getattr(item.exercise, "padrao", "") in PADROES_COMPOSTOS
    )


def equivalentes(opcoes, principais) -> bool:
    """As opções da letra são intercambiáveis pelas seis réguas?"""
    if len(opcoes) < 2:
        return True
    anunciados = set(principais or ())
    # OS MESMOS PADRÕES COMPOSTOS em cada grupo anunciado. Três supinos
    # contra três crucifixos passavam nas réguas de volume e de minutos; a
    # semana sem remada horizontal também. Isolador pode diferir.
    for grupo in anunciados:
        cobertos = {_padroes_compostos(op, grupo) for op in opcoes}
        if len(cobertos) > 1:
            return False
    volumes = [_volume_direto(op) for op in opcoes]
    minutos = [_minutos(op) for op in opcoes]
    grupos = set().union(*(v.keys() for v in volumes))
    for grupo in grupos:
        valores = [v.get(grupo, 0) for v in volumes]
        if max(valores) - min(valores) > TOLERANCIA_DE_SERIES:
            return False
    if max(minutos) - min(minutos) > TOLERANCIA_DE_MINUTOS:
        return False
    for op in opcoes:
        presentes = {item.exercise.muscle_group for item, _, _ in op}
        if not anunciados <= presentes:
            return False
    return True


def _pode_receber(op, i, teto_min, limite_series=TETO_SERIES_COMPLETO) -> bool:
    item, series, grau = op[i]
    if grau >= 2 or series >= TETO_SERIES_POR_EXERCICIO:
        return False
    if sum(s for _, s, _ in op) + 1 > limite_series:
        return False
    tentativa = list(op)
    tentativa[i] = (item, series + 1, grau)
    return _cabe(tentativa, teto_min)


def equilibrar(opcoes, principais, teto_min, dar=True, teto_series=TETO_SERIES_COMPLETO) -> list:
    """Aproxima as opções quando a régua de volume ou de tempo estourou.

    PRIMEIRO DÁ, DEPOIS TIRA. A opção mais leve num grupo (ou mais curta)
    recebe uma série num isolador/acessório — até quatro por exercício,
    dentro do teto de séries e do tempo. Só quando não há onde receber é que
    a mais pesada cede, nunca abaixo do piso do degrau. Tirar primeiro era o
    que deixava as duas opções com o tríceps em duas séries: uma tinha três
    compostos (aquecimento de aproximação em cada um) e a outra um, e a régua
    dos cinco minutos cobrava a diferença em série.

    Poucas rodadas: as opções nascem parecidas. O teto semanal é conferido
    de novo depois (`aparar_opcoes`), porque dar série pode estourá-lo — e
    aí esta função roda mais uma vez com `dar=False`, só tirando, para o
    que o teto cortou de uma opção não deixar a outra sozinha na frente.
    """
    opcoes = [list(op) for op in opcoes]
    for _ in range(12):
        if equivalentes(opcoes, principais):
            return opcoes
        volumes = [_volume_direto(op) for op in opcoes]
        minutos = [_minutos(op) for op in opcoes]
        leve = pesada = None
        grupo_alvo = None
        grupos = set().union(*(v.keys() for v in volumes))
        for grupo in sorted(grupos):
            valores = [v.get(grupo, 0) for v in volumes]
            if max(valores) - min(valores) > TOLERANCIA_DE_SERIES:
                leve, pesada, grupo_alvo = valores.index(min(valores)), valores.index(max(valores)), grupo
                break
        if leve is None and max(minutos) - min(minutos) > TOLERANCIA_DE_MINUTOS:
            leve, pesada = minutos.index(min(minutos)), minutos.index(max(minutos))
        if leve is None:
            return opcoes
        # Dar: o primeiro isolador/acessório da opção leve (no grupo, se há
        # grupo). O limite é o total da opção pesada: a leve pode alcançá-la,
        # nunca passá-la — e nunca menos que o teto da faixa.
        op = opcoes[leve]
        limite = max(teto_series, sum(s for _, s, _ in opcoes[pesada]))
        recebem = [
            i for i, (item, series, grau) in enumerate(op)
            if (grupo_alvo is None or item.exercise.muscle_group == grupo_alvo)
            and _pode_receber(op, i, teto_min, limite)
        ]
        recebem.sort(key=lambda i: (-op[i][2], op[i][1], i))
        if recebem and dar:
            i = recebem[0]
            item, series, grau = op[i]
            op[i] = (item, series + 1, grau)
            continue
        # Tirar: o último isolador/acessório da opção pesada, até o piso.
        op = opcoes[pesada]
        cedem = [
            i for i, (item, series, grau) in enumerate(op)
            if grau < 2 and (grupo_alvo is None or item.exercise.muscle_group == grupo_alvo)
            and series > (3 if grau >= 1 else 2)
        ]
        if not cedem:
            return opcoes
        i = cedem[-1]
        item, series, grau = op[i]
        op[i] = (item, series - 1, grau)
    return opcoes


def versao_rapida(linhas, principais, teto_min=TETO_RAPIDO_MIN) -> tuple:
    """A opção escolhida em ~40 minutos: `(ficam, removidos)`.

    `linhas` são `(item, series, grau)`; `ficam` são `(item, series_finais)`
    na ordem da ficha, `removidos` os itens que saíram. Passa por
    `escolher_para_o_tempo`, então principais e compostos ficam, a série cai
    do degrau mais baixo primeiro, e o complementar sai antes do anunciado.
    """
    from .services import escolher_para_o_tempo

    if not linhas:
        return [], []
    ficam = escolher_para_o_tempo(
        [(item.exercise.muscle_group, series, item.rest_seconds, grau) for item, series, grau in linhas],
        teto_min,
        principais=list(principais or ()),
    )
    indices = {i for i, _ in ficam}
    return (
        [(linhas[i][0], series) for i, series in ficam],
        [linhas[i][0] for i in range(len(linhas)) if i not in indices],
    )


def realocar_orfaos_nas_opcoes(semana, descartados, principais_de, teto_min) -> None:
    """O complementar que o relógio tirou de TODAS as opções procura outra letra.

    É `services.realocar_complementares_orfaos` lida por opção: um grupo que
    não sobrou em nenhuma opção de nenhuma letra (a prancha, a panturrilha,
    em "até 30 min") entra na letra de MAIOR FOLGA — em TODAS as opções dela,
    porque as opções de uma letra têm de continuar equivalentes; se não cabe
    em todas, não entra em nenhuma. `_encaixar` faz o que sempre fez: reduz
    série de isolador/acessório para abrir espaço, nunca do principal, nunca
    abaixo do piso, nunca acima do teto. O teto semanal é conferido depois
    por quem chama. Muda `semana` no lugar.
    """
    from .services import _encaixar, _teto_em_segundos

    if teto_min is None:
        return
    limite = _teto_em_segundos(teto_min)
    presentes = {
        item.exercise.muscle_group
        for opcoes in semana.values() for op in opcoes for item, _, _ in op
    }
    orfaos = {}
    for label, por_opcao in descartados.items():
        anunciados = set(principais_de.get(label) or ())
        for linhas in por_opcao:
            for item, series, grau in linhas:
                grupo = item.exercise.muscle_group
                if grupo in presentes or grupo in anunciados:
                    continue
                if all(i.exercise_id != item.exercise_id for i, _, _ in orfaos.get(grupo, [])):
                    orfaos.setdefault(grupo, []).append((item, series, grau))

    def folga(opcoes):
        return min(
            limite - segundos_da_sessao(
                [(s, i.rest_seconds, i.exercise.is_compound) for i, s, _ in op]
            )
            for op in opcoes
        )

    for grupo in sorted(orfaos):
        candidatos = sorted(orfaos[grupo], key=lambda t: t[1] * (t[0].rest_seconds + 40))
        for label in sorted(semana, key=lambda l: folga(semana[l]), reverse=True):
            opcoes = semana[label]
            if any(i.exercise.muscle_group == grupo for op in opcoes for i, _, _ in op):
                continue
            entrou = False
            for item, series, grau in candidatos:
                encaixes = [_encaixar(op, item, series, grau, limite) for op in opcoes]
                if any(e is None for e in encaixes):
                    continue
                for op, encaixe in zip(opcoes, encaixes):
                    ordem = max([i.order for i, _, _ in op] or [0]) + 1
                    op[:] = []
                    for linha_item, linha_series, linha_grau in encaixe:
                        if linha_item.exercise_id == item.exercise_id and linha_item is item:
                            copia = copy.copy(item)
                            copia.order = ordem
                            op.append((copia, linha_series, linha_grau))
                        else:
                            op.append((linha_item, linha_series, linha_grau))
                entrou = True
                break
            if entrou:
                break

