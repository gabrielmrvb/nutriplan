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
