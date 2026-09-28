"""Uma letra, UMA lista: a variante única, montada por cota (27/09/2026).

A DECISÃO DO DONO, literal: "Fichas novas com uma variante só"; "letra
repetida faz sempre o mesmo treino — variação é troca por exercício na
linha, escolha da pessoa; sem alternância automática". De 15 a 27/09/2026
cada letra saía com até duas OPÇÕES equivalentes de meio modelo, e a pessoa
alternava; as fichas nascidas nesse período continuam sendo LIDAS
(`TrainingSession.opcoes`/`da_opcao`, `services.variacao_do_dia`) até a
última sumir — o motor só não gera mais nenhuma.

POR QUE COTA, e não "o modelo inteiro" nem "a opção 1 de antes" (medido na
T3, 27/09/2026): o modelo inteiro chega ao relógio com 90 a 130 minutos, e o
relógio — que corta compostos por último — escolhe a ficha: "Peito e
tríceps" com 2 peitos, trapézio, antebraço e core fora da semana. A opção 1
de antes perde o composto principal que o rodízio dava à opção 2 (o stiff de
toda divisão). `variante_unica` escolhe pela cota do `TREINO.md` (tabela A e
"Tipos de dia"): o principal de cada grupo primeiro, todo grupo anunciado
coberto, o resto da cota na ordem do modelo, um exercício de cada
complementar. O relógio volta a ser rede de segurança.

Tudo aqui é função pura sobre os itens do catálogo (`WorkoutTemplateItem`) —
nada lê banco, nada lê relógio. Quem grava é `services.create_routine`;
quem confere se a ficha gravada é a que sairia hoje é `services._prescricao_confere`,
pela MESMA função, porque duas cópias da conta é como as duas nascem
diferentes.
"""
import copy
from collections import Counter
from decimal import Decimal

from . import doutrina
from .models import segundos_da_sessao

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

#: CORPO INTEIRO UMA VEZ POR SEMANA EXIGE 75 MINUTOS (27/09/2026, decisão do
#: dono, literal: "se não couber [em 60 com panturrilha e core em uma
#: série], EXIGIR 75 min" — e NÃO aceitar os dois grupos fora a 60 com
#: aviso). O princípio: quem treina uma vez por semana só tem essa sessão, e
#: os dez grupos do título e do modelo são a semana inteira dele; medido, no
#: piso de série eles dão 62,7 minutos (66,0 com o complementar em duas
#: séries), e a dose do catálogo, 75,3. O gerador monta essa ficha com
#: `max(faixa, 75)` (`services.prescrever_opcoes`), e a ficha e a tela de
#: Treino dizem por quê.
MINUTOS_DO_CORPO_INTEIRO = 75

#: Panturrilha e core são complementares em todo tipo de dia, MESMO quando
#: anunciados ("Pernas completo"): no máximo dois exercícios, e a cota de
#: pequeno não vale para eles (TREINO.md, "Tipos de dia").
COMPLEMENTARES_SEMPRE = frozenset({"calves", "core"})

#: Os pares que dividem UMA cota (TREINO.md, "Tipos de dia"): posterior e
#: glúteo são uma cadeia; antebraço e trapézio dividem o segundo pequeno de
#: "Costas, bíceps, antebraço e trapézio".
JUNTOS = (("hamstrings", "glutes"), ("forearms", "traps"))

#: Quem é GRANDE nos tipos de dia que têm mais de um (ou que não seguem a
#: regra geral). Nos outros — um, dois e três grupos — o grande é o
#: PRIMEIRO anunciado que é grande ("Peito, tríceps e ombro": o ombro é
#: pequeno ali), e quadríceps e posterior dividem a cota dele.
GRANDES_DO_TIPO = {
    doutrina.SUPERIOR: (("chest",), ("back",)),
    doutrina.FULL: (("quads",), ("chest",), ("back",), ("hamstrings", "glutes")),
    doutrina.INFERIOR: (("quads",),),
}
PERNAS = ("quads", "hamstrings")

#: LETRA REPETIDA SEGUE A TABELA A. O CONTRATO SEMANAL VALE SÓ PARA A LETRA
#: TREINADA UMA VEZ POR SEMANA (28/09/2026, decisão do dono; a de 27/09 dizia
#: "3 de tríceps quando a letra é 1× por semana"). Na letra que cai UMA vez,
#: o contrato semanal de variedade (4/4/3/3: exercícios distintos por
#: semana, do intermediário para cima) vence a tabela A na cota de
#: exercícios. O princípio: o teto por sessão da tabela A existe para a letra
#: que REPETE, cuja dose se soma na semana; a letra que cai uma vez tem de
#: carregar a dose da semana inteira. É o que dá três tríceps a "Peito,
#: tríceps e ombro" e três bíceps a "Costas, bíceps, antebraço e trapézio" no
#: ABC de três dias (a tabela A diz dois); no ABC de quatro a sete dias,
#: onde essas letras repetem, a semana tem dois. Não vale para os tipos de um
#: e dois dias (superior, inferior, corpo inteiro), onde o contrato não é
#: cobrado.
CONTRATO_DE_VARIEDADE = {"chest": 4, "back": 4, "triceps": 3, "biceps": 3}
TIPOS_DO_CONTRATO = frozenset({doutrina.UM_GRUPO, doutrina.DOIS_GRUPOS, doutrina.TRES_GRUPOS})


def _blocos(grupos, juntos=JUNTOS) -> list:
    """Os grupos em blocos de cota, na ordem dada: o par de `juntos` vira um
    bloco só (com os membros que estão em `grupos`)."""
    blocos = []
    for grupo in grupos:
        par = next((p for p in juntos if grupo in p), (grupo,))
        bloco = tuple(g for g in par if g in grupos)
        if bloco not in blocos:
            blocos.append(bloco)
    return blocos


def _grandes(anunciados, tipo) -> list:
    """Os blocos que recebem a cota do GRANDE (TREINO.md, "Tipos de dia")."""
    if tipo is None:
        return []
    if tipo in GRANDES_DO_TIPO:
        grandes = [tuple(g for g in bloco if g in anunciados) for bloco in GRANDES_DO_TIPO[tipo]]
    elif "quads" in anunciados and "hamstrings" in anunciados:
        grandes = [tuple(g for g in PERNAS if g in anunciados)]
    else:
        primeiro = next((g for g in anunciados if g in doutrina.GRANDES), None)
        grandes = [] if primeiro is None else [b for b in _blocos(anunciados) if primeiro in b]
    return [bloco for bloco in grandes if bloco]


def cotas(principais, tipo, nivel, vezes=1) -> list:
    """`[(grupos, quantos)]`: quantos exercícios cada grupo ANUNCIADO recebe
    na variante da letra — `exercicios_grande`/`exercicios_pequeno` da tabela
    A do TREINO.md, repartidos como a seção "Tipos de dia" manda.

    TODO GRUPO DO TÍTULO TEM PELO MENOS UM EXERCÍCIO (decisão do dono,
    27/09/2026): o título promete cada um, e um bloco nunca fica menor que
    o número de grupos anunciados nele. Nas pernas de dois e três grupos o
    glúteo anunciado tem a vaga DELE, fora da cota do grande de quadríceps e
    posterior — antes ele comia uma das quatro, e "Pernas e ombros" saía com
    UM posterior (média do ciclo 6,7 contra o piso de 10). É também o que dá
    DOIS exercícios à cadeia posterior do "Corpo inteiro" (um grande, dois
    anunciados: stiff e elevação pélvica) e um ao trapézio de "Ombros" (cota
    0 de pequeno). Letra repetida segue a tabela A; o contrato semanal de
    variedade (`CONTRATO_DE_VARIEDADE`) vale só para a letra treinada uma
    vez por semana (`vezes == 1`, 28/09/2026). `tipo=None` é o `abcd D`
    ("Complementares"), fora do contrato: todo grupo com o máximo do
    complementar, dois.
    """
    anunciados = list(principais or ())
    if tipo is None:
        return [(bloco, max(2, len(bloco))) for bloco in _blocos(anunciados, juntos=JUNTOS[:1])]
    grande, pequeno = doutrina.exercicios_por_grupo(nivel, tipo)
    grandes = _grandes(anunciados, tipo)
    dentro = {g for bloco in grandes for g in bloco}
    fora = [g for g in anunciados if g not in dentro]
    # O glúteo que ficou fora do grande das pernas: a vaga dele, uma.
    proprios = [((g,), 1) for g in fora if g == "glutes" and "hamstrings" in dentro]
    pequenos = _blocos([g for g in fora if not any(g in b for b, _ in proprios)])
    resultado = [(bloco, grande) for bloco in grandes] + proprios + [
        (bloco, min(pequeno, 2) if set(bloco) <= COMPLEMENTARES_SEMPRE else pequeno)
        for bloco in pequenos
    ]
    contrato = (
        CONTRATO_DE_VARIEDADE
        if vezes == 1 and tipo in TIPOS_DO_CONTRATO and nivel != "iniciante" else {}
    )
    return [
        (bloco, max(n, len(bloco), *(contrato.get(g, 0) for g in bloco)))
        for bloco, n in resultado
    ]


def _degrau(item) -> int:
    """O degrau da escada do peso do corpo (`Exercise.progressao`); sem
    escada, o 3 — "a versão padrão do movimento" (TREINO.md, "O degrau do
    iniciante") —, para o crucifixo da academia não passar na frente da
    flexão só por não ter escada."""
    return (getattr(item.exercise, "progressao", None) or {}).get("nivel", 3)


def variante_unica(itens, principais, tipo, nivel, vezes=1) -> list:
    """A lista da letra: UMA, a mesma em toda ocorrência da semana.

    `itens` são os do modelo, na ordem dele (com o perfil de equipamento e o
    degrau do iniciante já aplicados); devolve os escolhidos na MESMA ordem —
    `prioridades_da_sessao` lê a ordem da ficha para o grau. Por bloco de
    `cotas`, e depois um exercício de cada grupo do modelo que não está em
    bloco nenhum (o complementar: trapézio e antebraço de "Costas e
    bíceps", panturrilha e core de "Pernas e ombros"), nesta ordem:

    1. o composto PRINCIPAL de cada grupo do bloco (`prioridades_da_sessao`
       sobre o modelo inteiro): o stiff não se perde para uma "outra opção",
       nem a remada alta, que é o principal do trapézio;
    2. um de cada grupo anunciado do bloco ainda sem exercício — a elevação
       pélvica do glúteo anunciado;
    3. o resto da cota, do grupo MENOS servido, e no empate a ordem do
       modelo — que, dentro de cada grupo, desce por importância. Com duas
       regras de desempate (aprovadas pelo dono em 27/09/2026):

       - PADRÃO NOVO PRIMEIRO: ao completar a cota de um grupo, um padrão
         de movimento que o grupo ainda não tem (`Exercise.padrao`) vem
         antes de repetir um que ele já tem. O princípio: com uma lista só
         por letra, a variedade que as duas opções davam alternando tem de
         caber DENTRO da lista — três de ombro são desenvolvimento,
         elevação e deltoide posterior (três porções), não dois
         desenvolvimentos; o quadríceps que já tem agachamento ganha a
         extensão de joelho. O modelo lista dois de cada padrão composto
         porque cada antiga opção precisava de um, e esse segundo não é
         variedade — por isso, esgotados os padrões novos, repetir um
         padrão de isolamento vem antes do segundo composto do mesmo
         padrão (o terceiro tríceps é a testa, não o supino fechado). A
         exceção é o grande de UM grupo só (peito, costas, o
         ombro de "Ombros", o quadríceps do "Inferior"): ali os primeiros
         itens do modelo JÁ são a ficha de academia curada — supino reto,
         inclinado, flexão, crucifixo; barra, remada, puxada, remada — e o
         grande é composto antes de isolador (tabela C: "isoladores no
         máximo metade dos exercícios dele");
       - DEGRAU MAIS FÁCIL PARA O INICIANTE: entre exercícios do mesmo
         grupo, o degrau mais baixo da escada do peso do corpo
         (`Exercise.progressao`) vem antes. O princípio é o do TREINO.md, "O
         degrau do iniciante": quem está começando faz os MESMOS movimentos
         a partir do degrau em que consegue fazer; sem escada, conta como o
         degrau 3, a versão padrão do movimento.

    Não olha o relógio: a cota é a da sessão, e a mesma lista vale com e sem
    teto de tempo (`teto=None` é a referência da nota de tempo). Quem cabe no
    tempo é a cadeia de depois — preenchimento, teto semanal, relógio.
    """
    from .services import PRINCIPAL, prioridades_da_sessao

    posicao = {id(item): i for i, item in enumerate(itens)}
    graus = {id(item): grau for item, grau in zip(itens, prioridades_da_sessao(itens))}
    blocos = cotas(principais, tipo, nivel, vezes)
    em_bloco = {g for bloco, _ in blocos for g in bloco}
    for item in itens:
        grupo = item.exercise.muscle_group
        if grupo not in em_bloco:
            em_bloco.add(grupo)
            blocos.append(((grupo,), 1))
    # O grande de UM grupo só (peito, costas): os primeiros itens do modelo
    # são a ficha curada e ficam; nos outros blocos o padrão novo vem antes.
    na_ordem_do_modelo = [b for b in _grandes(list(principais or ()), tipo) if len(b) == 1]
    iniciante = nivel == "iniciante"
    escolhidos = []
    for bloco, n in blocos:
        candidatos = [item for item in itens if item.exercise.muscle_group in bloco]
        cota = [item for item in candidatos if graus[id(item)] == PRINCIPAL][:n]
        for grupo in bloco:
            if len(cota) < n and all(item.exercise.muscle_group != grupo for item in cota):
                cota += [item for item in candidatos if item.exercise.muscle_group == grupo][:1]
        padrao_novo_primeiro = bloco not in na_ordem_do_modelo
        while len(cota) < n:
            ja = {id(item) for item in cota}
            resto = [item for item in candidatos if id(item) not in ja]
            if not resto:
                break
            servidos = Counter(item.exercise.muscle_group for item in cota)
            padroes = {(item.exercise.muscle_group, item.exercise.padrao) for item in cota}
            cota.append(min(resto, key=lambda item: (
                servidos[item.exercise.muscle_group],
                padrao_novo_primeiro and (item.exercise.muscle_group, item.exercise.padrao) in padroes,
                # Esgotados os padrões novos, o SEGUNDO composto de um padrão
                # que o grupo já tem vem por último: ele existe no modelo
                # porque cada antiga opção precisava de um.
                padrao_novo_primeiro and (item.exercise.muscle_group, item.exercise.padrao) in padroes
                and item.exercise.is_compound,
                _degrau(item) if iniciante else 0,
                posicao[id(item)],
            )))
        escolhidos += cota
    return sorted(escolhidos, key=lambda item: posicao[id(item)])


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
    # Em RODÍZIO, uma série por vez: primeiro pelos GRUPOS anunciados — o
    # que recebeu menos série de sobra vem antes (decisão do dono,
    # 27/09/2026: com a lista única o peito recebia as sobras antes do
    # tríceps e passava do teto da média do ciclo) —, e dentro do grupo do
    # acessório para o isolador, do que tem menos série, para nenhum
    # isolador chegar a quatro enquanto outro continua em três.
    acrescidas = Counter()
    while total < teto_series:
        elegiveis = sorted(
            (
                i for i, (item, series, grau) in enumerate(linhas)
                if grau < 2 and series < teto_ex and anunciado(item)
            ),
            key=lambda i: (acrescidas[linhas[i][0].exercise.muscle_group], -linhas[i][2], linhas[i][1], i),
        )
        for i in elegiveis:
            item, series, grau = linhas[i]
            tentativa = list(linhas)
            tentativa[i] = (item, series + 1, grau)
            if not _cabe(tentativa, teto_min):
                continue
            linhas = tentativa
            acrescidas[item.exercise.muscle_group] += 1
            total += 1
            break
        else:
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


def _ceder(op, grupo, dose_do_catalogo, minimo_diretos=1):
    """Uma concessão no grupo, nesta ordem: a série que o preenchimento
    acrescentou volta ao catálogo; um isolador desce ao piso de duas; um
    composto ACESSÓRIO desce ao piso de três (`PISO_COMPOSTO`); só então um
    exercício sai — o de menor grau (isolador antes de acessório), nunca o
    último exercício direto do grupo na lista, nunca o composto principal.
    Devolve `(exercise_id, séries_agora)` — `None` em `séries_agora` quando o
    exercício saiu — ou `None` quando não há o que ceder.

    SÉRIE ANTES DE EXERCÍCIO, e o degrau do acessório entrou em 27/09/2026
    com a variante única: a letra que cai três vezes (abc2 a 7 dias) repete
    a MESMA lista três vezes, e o TREINO.md manda o peito ficar em "4
    exercícios a 3 séries" — "a sessão NÃO perde o quarto exercício para
    caber". Até ali três opções de um terço cada davam a variedade que o
    teto tirava de uma lista cheia.

    `minimo_diretos` é quantos exercícios diretos do grupo a lista precisa
    manter para um poder sair (1: a trava de sempre). O que sobra é teto de
    aparo, não promessa — inclusive uma série DIRETA acima dele.

    Até 27/09/2026 havia aqui a régua do PENÚLTIMO direto das duas opções
    (`FRACAO_DE_EXCESSO_QUE_DESTRAVA`): com uma variante só, não há irmã a
    acompanhar e a trava é a de sempre.
    """
    from .services import PISO_COMPOSTO

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
    for grau_que_desce, piso in ((0, 2), (1, PISO_COMPOSTO)):
        acima = [i for i in podem if op[i][2] == grau_que_desce and op[i][1] > piso]
        if acima:
            i = acima[-1]
            item, series, grau = op[i]
            op[i] = (item, series - 1, grau)
            return (item.exercise_id, series - 1)
    if len(diretos) <= minimo_diretos:
        return None
    grau_minimo = min(op[i][2] for i in podem)
    i = [i for i in podem if op[i][2] == grau_minimo][-1]
    saiu = op[i][0].exercise_id
    del op[i]
    return (saiu, None)


def _limites(teto, grupos) -> dict:
    """O teto de cada grupo: um número para todos (a chamada antiga) ou um
    dicionário grupo → teto — o da FREQUÊNCIA do grupo na semana, desde
    17/09/2026 (`doutrina.teto_semanal`)."""
    if isinstance(teto, dict):
        padrao = Decimal(teto.get("*", 10_000))
        return {g: Decimal(teto.get(g, padrao)) for g in grupos}
    return {g: Decimal(teto) for g in grupos}


def aparar_opcoes(por_letra, ocorrencias, teto, dose_do_catalogo) -> dict:
    """Faz o pior caso da semana caber no teto por grupo.

    `por_letra` é `{letra: [lista_de_linhas]}` — desde 27/09/2026 a lista
    externa tem UM elemento por letra, a variante única; a forma é a de
    `volume_semanal_pior_caso`, que também lê as fichas antigas com duas
    opções. As TRÊS TRAVAS de `aparar_volume_semanal` valem aqui, e pela
    mesma razão: só cede quem treina o grupo DIRETAMENTE; nunca o último
    exercício direto do grupo; e cede a letra que está puxando o máximo. A
    ordem de concessão é a de `_ceder`: série acrescentada, série de
    isolador até o piso, e só então o isolador inteiro. Composto principal
    nunca cede — se o excesso só puder ser resolvido nele, o excesso fica
    (teto de aparo, não promessa).
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
            candidatas = []
            for label, opcoes in por_letra.items():
                for op in opcoes:
                    vol = _volume(op).get(grupo, Decimal(0)) * ocorrencias.get(label, 1)
                    if vol:
                        candidatas.append((vol, op))
            candidatas.sort(key=lambda c: c[0], reverse=True)
            cedeu = any(_ceder(op, grupo, dose_do_catalogo) is not None for _vol, op in candidatas)
            if cedeu:
                break
        if not cedeu:
            return por_letra
    return por_letra


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

    É `services.realocar_complementares_orfaos` sobre `{letra: [lista]}`: um
    grupo que não sobrou em letra nenhuma (a prancha, a panturrilha, em "até
    30 min") entra na letra de MAIOR FOLGA. Desde 27/09/2026 a letra tem uma
    lista só (a variante única); o laço "em todas as opções da letra" ficou
    da forma de antes e roda uma vez. `_encaixar` faz o que sempre fez: reduz
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

