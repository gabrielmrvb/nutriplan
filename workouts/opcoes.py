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

from .models import segundos_da_sessao

#: Quantas séries uma sessão completa quer ter, POR NÍVEL. A faixa do brief
#: ("15–18 séries totais por sessão") é a do intermediário; quem está
#: começando pede menos (o brief: "iniciante 4–5 exercícios") e o avançado
#: um pouco mais. A chave é o teto semanal da pessoa (`teto_semanal_de`),
#: que já é a tradução do nível — uma régua, dois usos. Abaixo do piso a
#: opção pede série ao isolador e ao acessório — até QUATRO por exercício,
#: nunca mais —; acima do teto ela não cresce.
FAIXA_POR_TETO_SEMANAL = {12: (12, 15), 20: (15, 18), 24: (16, 20)}
PISO_SERIES_COMPLETO = 15
TETO_SERIES_COMPLETO = 18
TETO_SERIES_POR_EXERCICIO = 4


def faixa_de_series(teto_semanal) -> tuple:
    """`(piso, teto)` de séries por sessão para este teto semanal."""
    return FAIXA_POR_TETO_SEMANAL.get(int(teto_semanal or 20), (PISO_SERIES_COMPLETO, TETO_SERIES_COMPLETO))

#: A partir de quantos minutos de teto a opção sobe até a faixa. Abaixo
#: disso (a faixa "até 30"), encher os anunciados só tirava os complementares
#: no corte seguinte; a dose fica a do catálogo.
MINUTOS_PARA_PREENCHER = 45

#: Quanto tempo a versão rápida pode levar, em minutos. Derivada da opção
#: escolhida por `escolher_para_o_tempo` — as mesmas cinco camadas do corte
#: por relógio, então os principais ficam e o acessório de menor prioridade
#: sai primeiro. Não é uma terceira ficha.
TETO_RAPIDO_MIN = 40

#: A sessão completa mira perto de uma hora. É o teto para quem não tem teto
#: (`duracao_treino` "livre") e para quem nunca respondeu; quem escolheu uma
#: faixa continua com a faixa dela — a escolha não é sobrescrita.
TETO_COMPLETO_MIN = 65

#: Diferença máxima entre as opções: uma série por grupo, cinco minutos.
TOLERANCIA_DE_SERIES = 1
TOLERANCIA_DE_MINUTOS = 5

#: Fração mínima de exercícios PRÓPRIOS em cada opção. Meio a meio é o que
#: separa "duas versões" de "a mesma ficha com um exercício trocado".
FRACAO_MINIMA_DISTINTA = Decimal("0.5")


def _por_grupo(itens) -> "OrderedDict":
    grupos = OrderedDict()
    for item in itens:
        grupos.setdefault(item.exercise.muscle_group, []).append(item)
    return grupos


def montar_opcoes(itens, n=2) -> list:
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
    """
    opcoes = [[] for _ in range(n)]
    compartilhados = set()
    for j, lista in enumerate(_por_grupo(itens).values()):
        if len(lista) < n:
            for k in range(n):
                opcoes[k].extend(lista)
            compartilhados.update(item.exercise_id for item in lista)
            continue
        partes = [lista[k::n] for k in range(n)]
        maior = max(len(parte) for parte in partes)
        for k, parte in enumerate(partes):
            faltam = maior - len(parte)
            if faltam:
                # Os últimos da parte mais cheia, que são os de menor
                # prioridade pela ordem do modelo.
                doadora = max(partes, key=len)
                emprestados = doadora[-faltam:]
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


def preencher_ate_a_faixa(linhas, teto_min, principal, faixa=None) -> list:
    """Sobe a série de isolador e acessório até a sessão chegar ao piso.

    `linhas` são `(item, series, grau)` na ordem da ficha. Uma série por vez,
    do PRIMEIRO isolador/acessório de um grupo ANUNCIADO (o complementar não
    faz um treino de peito e tríceps parecer maior), nunca acima de quatro por
    exercício, nunca acima do teto de séries, nunca além do tempo. O composto
    principal não recebe: ele já tem a dose que o catálogo pede.
    """
    piso, teto_series = faixa or (PISO_SERIES_COMPLETO, TETO_SERIES_COMPLETO)
    linhas = list(linhas)
    total = sum(s for _, s, _ in linhas)
    if total >= piso:
        return linhas
    anunciados = set(principal or ())
    mudou = True
    while total < piso and mudou:
        mudou = False
        # Em RODÍZIO: uma série por exercício por volta, do acessório para o
        # isolador — para nenhum isolador chegar a quatro enquanto outro
        # continua em três.
        elegiveis = [
            i for i, (item, series, grau) in enumerate(linhas)
            if grau < 2 and series < TETO_SERIES_POR_EXERCICIO
            and (not anunciados or item.exercise.muscle_group in anunciados)
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
            if total >= piso:
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


def _ceder(op, grupo, dose_do_catalogo):
    """Uma concessão no grupo, nesta ordem: a série que o preenchimento
    acrescentou volta ao catálogo; um isolador desce ao piso de duas; só então
    um exercício sai — o de menor grau (isolador antes de acessório), nunca o
    último exercício direto do grupo na opção, nunca o composto principal. Devolve `(exercise_id, séries_agora)` — `None` em
    `séries_agora` quando o exercício saiu — ou `None` quando não há o que
    ceder."""
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
    if len(diretos) <= 1:
        return None
    grau_minimo = min(op[i][2] for i in podem)
    i = [i for i in podem if op[i][2] == grau_minimo][-1]
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
    limite = Decimal(teto)
    for _ in range(200):
        pior_caso = volume_semanal_pior_caso(por_letra, ocorrencias)
        pendentes = sorted(
            (g for g, v in pior_caso.items() if v > limite),
            key=lambda g: (pior_caso[g], g),
            reverse=True,
        )
        cedeu = False
        for grupo in pendentes:
            candidatas = []
            for label, opcoes in por_letra.items():
                for k, op in enumerate(opcoes):
                    vol = _volume(op).get(grupo, Decimal(0)) * ocorrencias.get(label, 1)
                    if vol:
                        candidatas.append((vol, label, k))
            candidatas.sort(key=lambda c: c[0], reverse=True)
            for _vol, label, k in candidatas:
                op = por_letra[label][k]
                concessao = _ceder(op, grupo, dose_do_catalogo)
                if concessao is None:
                    continue
                cedeu = True
                exercise_id, series_agora = concessao
                agora = _volume(op).get(grupo, Decimal(0))
                for outra in por_letra[label]:
                    if outra is op:
                        continue
                    _espelhar(outra, grupo, exercise_id, series_agora)
                    if _volume(outra).get(grupo, Decimal(0)) - agora > TOLERANCIA_DE_SERIES:
                        _ceder(outra, grupo, dose_do_catalogo)
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


def equivalentes(opcoes, principais) -> bool:
    """As opções da letra são intercambiáveis pelas cinco réguas?"""
    if len(opcoes) < 2:
        return True
    anunciados = set(principais or ())
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

