"""A pergunta que a tela Hoje passou a responder primeiro: e agora?

A tela abria com anel de calorias, saldo energético e barra de macros — cinco
números antes de qualquer ação, e quase todos zerados às sete da manhã. Quem
abre o app de manhã não quer saber que comeu 0 de 2765 kcal; quer saber o que
fazer com o café da manhã.

Este módulo decide UMA ação. Ele não inventa nada: tudo que devolve sai de
`MealSlot`, `MealLog`, `HydrationLog` e do estado de treino que o Treino V3 já
calcula. Quando não há o que fazer, ele diz isso — não preenche o espaço.
"""
from dataclasses import dataclass

from django.urls import reverse


@dataclass
class Acao:
    """A próxima coisa a fazer, e como a tela deve apresentá-la."""

    tipo: str = "vazio"
    rotulo: str = ""
    titulo: str = ""
    detalhe: str = ""
    cta: str = ""
    url: str = ""
    slot: object = None
    horario: object = None
    atrasada: bool = False

    @property
    def existe(self) -> bool:
        return self.tipo != "vazio"


def _pendente(slot) -> bool:
    """Refeição sem marcação nenhuma hoje.

    Pulada e "comi outra coisa" contam como RESOLVIDAS: a pessoa já respondeu
    sobre elas, e insistir seria a tela cobrando uma decisão que já foi tomada.
    """
    log = getattr(slot, "log", None)
    return log is None or log.status == "pending"


def _acao_de_refeicao(slot, rotulo, atrasada) -> Acao:
    """A refeição vira ação, mas o CTA NÃO marca a refeição.

    O botão leva ao cartão dela, e o motivo é o A/B: quase todo slot tem duas
    opções, e um "marcar como comido" aqui teria que escolher uma delas pela
    pessoa. Escolher A porque A é a primeira grava um prato que ela pode não
    ter comido — e `MealLog` é fato consumado, com macros copiados na hora.
    Um toque a mais é barato; registro errado, não.

    O que o cartão entrega é a informação que evita o passeio: qual refeição,
    a que horas, e a meta dela.
    """
    alvo = "%d kcal · %d g de proteína" % (slot.target_kcal, slot.target_protein_g)
    return Acao(
        tipo="refeicao",
        rotulo=rotulo,
        titulo=slot.name,
        detalhe=alvo,
        cta="Ver refeição",
        url="#slot-%d" % slot.pk,
        slot=slot,
        horario=slot.time,
        atrasada=atrasada,
    )


def _acao_de_treino(estado, rotulo, atrasada, continuando=False) -> Acao:
    sessao = estado.sessao
    if continuando:
        detalhe = "%d de %d séries registradas" % (
            estado.series_feitas, estado.total_series
        )
        cta = "Continuar de onde parou"
    else:
        detalhe = "%d exercícios" % estado.total_exercicios
        cta = "Começar treino"
    return Acao(
        tipo="treino",
        rotulo=rotulo,
        titulo=sessao.name,
        detalhe=detalhe,
        cta=cta,
        url=reverse("workouts:now"),
        horario=sessao.start_time,
        atrasada=atrasada,
    )


#: Quantos pontos percentuais atrás do esperado contam como "significativamente
#: atrás". Abaixo disso é ruído: quem bebeu 1 L às 13h de uma meta de 3 L está
#: 13 pontos atrás e vai chegar lá sem ninguém avisar.
ATRASO_DE_HIDRATACAO_PP = 25

#: Abaixo disto não vale tomar a tela. Faltando 200 ml às 20h a pessoa não
#: precisa de um cartão dizendo isso — ela precisa de um copo.
FALTA_MINIMA_PARA_AVISAR_ML = 500


def atraso_de_hidratacao(*, slots, meta_agua, bebido, agora) -> float:
    """Pontos percentuais atrás do esperado PARA A HORA. Zero se não dá para saber.

    A ideia é simples e é a única que não inventa horário: a janela de consumo
    do dia é a do próprio plano — da primeira refeição à última. Antes da
    primeira, não se espera nada; depois da última, espera-se a meta inteira;
    no meio, proporcional.

    Usar o plano em vez de "7h às 22h" importa porque o plano é de quem usa:
    quem come às 5h30 e às 19h tem outra janela, e um horário escrito à mão
    aqui estaria errado para essa pessoa todos os dias.

    Devolve pontos percentuais e não uma fração porque é assim que a regra é
    lida em voz alta: "trinta pontos atrás do esperado".
    """
    if not meta_agua or not slots:
        return 0.0

    horarios = [s.time for s in slots if s.time is not None]
    if len(horarios) < 2:
        return 0.0

    inicio, fim = min(horarios), max(horarios)
    if fim <= inicio:
        return 0.0

    def em_minutos(t):
        return t.hour * 60 + t.minute

    agora_min = em_minutos(agora.time())
    inicio_min, fim_min = em_minutos(inicio), em_minutos(fim)

    if agora_min <= inicio_min:
        esperado = 0.0
    elif agora_min >= fim_min:
        esperado = 1.0
    else:
        esperado = (agora_min - inicio_min) / (fim_min - inicio_min)

    real = min(bebido / meta_agua, 1.0)
    return (esperado - real) * 100


def proxima_acao(*, slots, treino, meta_agua, bebido, agora) -> Acao:
    """A ação mais útil neste instante.

    A ordem não é uma lista de prioridades escrita à mão — são três perguntas,
    nesta ordem:

    1. **Tem algo EM ANDAMENTO?** Treino começado e não terminado ganha de
       tudo. Estado vence agenda: quem está entre séries não quer ser mandado
       para o lanche da tarde porque deu quinze horas.

    2. **O que está acontecendo AGORA?** Entre o que já venceu, ganha o de
       horário MAIS RECENTE — não o mais atrasado. Às 20h, com almoço e jantar
       pendentes, "agora" é o jantar; o almoço das 12h não é uma coisa a fazer
       agora, é uma pendência, e ela continua visível na lista logo abaixo.

    3. **O que vem a seguir?** Sem nada vencido, mostra o próximo com o rótulo
       trocado, para a tela não fingir urgência às seis da manhã.

    Sem refeição e sem treino, sobra a água — e ela só aparece quando falta
    mesmo. Com tudo resolvido, a ação é vazia e a tela diz isso em vez de
    inventar uma tarefa.
    """
    hora = agora.time()

    # 1. em andamento
    if treino is not None and treino.tem_treino and not treino.concluido:
        if treino.comecou:
            return _acao_de_treino(treino, "AGORA", atrasada=False, continuando=True)

    vencidos, futuros = [], []
    for slot in slots:
        if not _pendente(slot):
            continue
        destino = vencidos if slot.time <= hora else futuros
        destino.append((slot.time, "refeicao", slot))

    if treino is not None and treino.tem_treino and not treino.concluido:
        inicio = treino.sessao.start_time
        if inicio is not None:
            destino = vencidos if inicio <= hora else futuros
            destino.append((inicio, "treino", treino))

    # 2. o que está acontecendo agora: entre os vencidos, o mais recente
    if vencidos:
        vencidos.sort(key=lambda item: item[0])
        _, tipo, alvo = vencidos[-1]
        if tipo == "treino":
            return _acao_de_treino(alvo, "AGORA", atrasada=True)
        return _acao_de_refeicao(alvo, "AGORA", atrasada=True)

    # 2-B. água muito atrás do esperado PARA A HORA.
    #
    # Entra aqui e não antes, e o lugar é a decisão inteira. Não passa na
    # frente de treino em andamento — ninguém entre séries quer ser mandado
    # beber água. Não passa na frente de refeição vencida — aquilo tem hora
    # marcada e passa; sede não.
    #
    # O que ela ocupa é o slot do "A SEGUIR", que por definição significa que
    # nada é urgente agora. Se nada venceu e a pessoa está trinta pontos atrás
    # do esperado, beber água É a coisa útil deste instante — e mostrar a
    # próxima refeição daqui a três horas, não.
    #
    # De manhã o esperado é baixo e o atraso não alcança o limiar. E beber
    # DESLIGA O CARTÃO NA HORA: o atraso cai abaixo do limiar no mesmo instante,
    # medido às 11h com 0 ml, às 15h com 1.000 e às 19h com 2.000.
    #
    # O que ele NÃO faz é ficar desligado, e isto está escrito porque a primeira
    # versão deste comentário afirmava que sim — "ela não domina o dia porque
    # ceder a ela a desliga". Meia verdade. `esperado` cresce com o relógio mais
    # depressa do que 500 ml movem `real`, então quem continua atrás vê o cartão
    # de novo umas duas horas depois. Simulado numa janela de 7h às 20h com meta
    # de 3 L, bebendo 500 toda vez que ele pede: aparece às 10:30, 12:30, 15:00,
    # 17:00 e 19:00 — cinco vezes, e a pessoa fecha o dia com 2.500 ml.
    #
    # Cinco lembretes espaçados de duas horas é cadência, não wallpaper. Já
    # quem não bebe NADA vê o cartão sem interrupção das 10:30 em diante, e isso
    # é honesto e não é novidade: sem nada vencido e sem treino, o ramo 4 já
    # mostrava água o resto do dia antes desta regra existir. A diferença é que
    # agora ele aparece enquanto ainda dá tempo de fazer algo a respeito.
    if meta_agua and bebido < meta_agua:
        faltam = meta_agua - bebido
        atraso = atraso_de_hidratacao(
            slots=slots, meta_agua=meta_agua, bebido=bebido, agora=agora
        )
        if atraso >= ATRASO_DE_HIDRATACAO_PP and faltam >= FALTA_MINIMA_PARA_AVISAR_ML:
            return Acao(
                tipo="agua",
                rotulo="HIDRATAÇÃO",
                titulo="Faltam %d ml" % faltam,
                detalhe="%d de %d ml hoje" % (bebido, meta_agua),
                cta="Registrar 500 ml",
                url="#hidratacao",
            )

    # 3. o que vem a seguir: o mais próximo no futuro
    if futuros:
        futuros.sort(key=lambda item: item[0])
        _, tipo, alvo = futuros[0]
        if tipo == "treino":
            return _acao_de_treino(alvo, "A SEGUIR", atrasada=False)
        return _acao_de_refeicao(alvo, "A SEGUIR", atrasada=False)

    # 4. água, e só quando falta
    if meta_agua and bebido < meta_agua:
        faltam = meta_agua - bebido
        return Acao(
            tipo="agua",
            rotulo="HIDRATAÇÃO",
            titulo="Faltam %d ml" % faltam,
            detalhe="%d de %d ml hoje" % (bebido, meta_agua),
            cta="Registrar 500 ml",
            url="#hidratacao",
        )

    # 5. nada pendente. A tela diz isso em vez de preencher o espaço.
    return Acao(tipo="vazio")


def marcar_refeicoes(slots, acao, agora) -> None:
    """Escreve `slot.marcador` para a lista concordar com o topo.

    O cartão de cima dizia "AGORA · Lanche da manhã" e, na lista, o lanche das
    11h e o café das 7h30 ficavam idênticos: nada indicava qual deles o topo
    apontava, nem que o café continuava em aberto. Documentado em captura, com
    os dois cartões lado a lado.

    A marca "agora" NÃO é recalculada aqui — ela é a identidade do slot que
    `proxima_acao` já escolheu. Reimplementar "quem é o atual" no template ou
    numa segunda função daria duas respostas para a mesma pergunta, e elas
    divergiriam na primeira mudança de regra.

    Quando a ação é treino, nenhuma refeição recebe "agora": o topo não está
    falando de comida, e uma refeição fingindo ser a vez seria a lista
    contradizendo a tela inteira. As vencidas continuam marcadas como
    pendentes, porque elas continuam em aberto.
    """
    # `atrasada` e não o rótulo: ele é texto de tela, e a pergunta aqui é de
    # domínio — a refeição já venceu?
    #
    # Sem esse filtro, uma refeição das 23h escolhida como "A SEGUIR" ganharia
    # o selo "Agora" às onze da manhã: o cartão do topo diria uma coisa e a
    # lista, outra. Refeição futura não recebe selo nenhum.
    e_a_vez = acao.tipo == "refeicao" and acao.atrasada
    alvo = acao.slot if e_a_vez else None
    hora = agora.time()
    for slot in slots:
        if alvo is not None and slot.pk == alvo.pk:
            slot.marcador = "agora"
        elif _pendente(slot) and slot.time <= hora:
            slot.marcador = "pendente"
        else:
            # Futura, ou já resolvida — comida, pulada e "comi outra coisa"
            # não voltam a cobrar nada.
            slot.marcador = ""
