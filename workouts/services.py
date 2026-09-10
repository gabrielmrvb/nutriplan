"""Monta a rotina de treino da semana a partir dos dias que a pessoa informou.

Duas decisões concentram a inteligência daqui, e as duas são de treinamento,
não de programação:

1. **A divisão vem da frequência, não do gosto.** Dividir o corpo em quatro
   dias para quem treina duas vezes por semana significa cada músculo ser
   treinado a cada duas semanas — a pior forma de organizar treino que existe.
   A regra é: quanto menos dias, mais cada sessão precisa cobrir.

2. **Acima de quatro dias a divisão não cresce, ela repete.** Quem treina cinco
   ou seis vezes roda o ABC de novo (A, B, C, A, B, ...). Inventar um quinto e
   um sexto dia de "braço" e "ombro" preenche a semana e não adiciona estímulo;
   repetir o ciclo dá a cada grupo muscular duas sessões na semana, que é o que
   a literatura mostra render mais que uma.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import (
    TETO_POR_DURACAO,
    TETO_POR_EXPERIENCIA,
    DuracaoTreino,
    Experiencia,
    SplitPreference,
)

from .models import (
    SEGUNDOS_ENTRE_EXERCICIOS,
    SEGUNDOS_POR_SERIE,
    ExerciseLog,
    MuscleGroup,
    SessionExercise,
    Split,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplate,
    segundos_da_sessao,
)


class NoTrainingDays(Exception):
    """A pessoa não marcou nenhum dia de treino — não há rotina a montar."""


#: Divisão escolhida por quantidade de dias na semana. Cinco dias ou mais
#: caem no ABC e o ciclo se repete ao longo da semana.
# De três dias em diante, sempre ABC.
#
# O ciclo se repete para preencher a semana: cinco dias viram A, B, C, A, B, e
# seis viram A, B, C, A, B, C. Isso dá de uma a duas sessões por grupo na
# semana — mais que qualquer divisão de quatro ou cinco letras entrega, porque
# lá cada grupo aparece uma vez só.
#
# ABCD e ABCDE existiram aqui e foram retirados. O motivo declarado é o
# clássico por sinergia: peito e costas são antagonistas e não dividem o dia,
# empurrar fica junto de empurrar, puxar junto de puxar.
#
# O preço dessa escolha está medido, e é alto: quatro dias viram A-B-C-A e o
# peito sai com 28 séries na semana, contra as 10 a 20 que a própria tela de
# volume usa como régua. Sete dias chegam a 42. O que existe hoje contra isso
# é a nota da ficha, que passou a dizer quais dias repetem — ver
# `nota_da_divisao`. Baixar as séries da sessão repetida resolveria de vez, e
# é prescrição de treino: não entra aqui sem decisão de produto.
SPLIT_BY_FREQUENCY = {
    1: Split.FULL,
    2: Split.AB,
    3: Split.ABC,
    4: Split.ABC,
    5: Split.ABC,
    6: Split.ABC,
    7: Split.ABC,
}
DEFAULT_SPLIT = Split.ABC

SPLIT_NOTE = {
    Split.FULL: (
        "Com um treino por semana, o corpo inteiro entra na mesma sessão — é o que "
        "dá algum estímulo a cada grupo muscular. Se conseguir abrir um segundo dia, "
        "o resultado muda de patamar."
    ),
    Split.AB: (
        "Dois treinos por semana: superior e inferior. Cada grupo muscular é treinado "
        "uma vez, então priorize os exercícios do começo da ficha — são eles que "
        "carregam o resultado."
    ),
    Split.ABC: (
        "A divisão clássica por sinergia: empurrar num dia, puxar no outro, "
        "pernas no terceiro. Peito e costas nunca caem no mesmo treino — são "
        "antagonistas, e treinar um cansa o outro pela metade."
    ),
    Split.ABCDE: (
        "Cinco treinos: o ciclo de quatro mais um dia para o que sobra de fora "
        "dele. Somando as séries da semana no ABCD, posterior de coxa e "
        "panturrilha ficam bem abaixo da faixa em que o ganho aparece — o "
        "quinto dia existe para fechar essa conta, não para adicionar treino "
        "por adicionar."
    ),
    Split.ABC2: (
        "Dois grupos principais por dia: peito e tríceps, costas e bíceps, "
        "pernas e ombros. Trapézio e antebraço treinam junto das costas, e "
        "panturrilha, glúteo e abdômen junto das pernas — eles se revezam "
        "entre as passagens da semana em vez de aparecer todo dia, que é como "
        "cabem sem esticar a sessão."
    ),
    Split.ABCD: (
        "Quatro treinos, um foco por dia: peito e tríceps, costas e bíceps, ombro e "
        "perna, e um dia para trapézio, antebraço e core. Volume por sessão é menor, "
        "então dá para puxar mais carga em cada exercício sem estender o treino. O "
        "dia dos complementares fica longe do de costas de propósito — trapézio e "
        "antebraço trabalham junto no puxe, e chegar neles cansado tira do treino "
        "de costas justamente a pegada que ele precisa."
    ),
}


#: (preferência, dias mínimos) -> divisão.
#:
#: A frequência continua mandando, e a preferência escolhe DENTRO do que ela
#: comporta. Não é diplomacia entre dois campos: uma divisão de cinco dias com
#: duas sessões por semana deixa três quintos do corpo sem treinar nenhuma vez,
#: porque as últimas letras nunca chegam. A preferência não cria dias.
#:
#: Lido por linha — cada uma desce para a divisão mais próxima que cabe:
#:   UM     cinco dias viram peito / costas / pernas / ombros / braços; com
#:          quatro cai no ABCD, com três no ABC, e assim por diante.
#:   DOIS   três dias: peito+tríceps, costas+bíceps e pernas+ombros. Os
#:          complementares moram DENTRO desses três dias — trapézio e antebraço
#:          junto das costas, panturrilha, glúteo e core junto das pernas — e
#:          se distribuem entre as passagens da letra na semana.
#:   TRES   o ABC de sempre: empurrar, puxar e pernas, em três dias.
SPLIT_BY_PREFERENCE = {
    SplitPreference.UM: (
        (5, Split.ABCDE), (4, Split.ABCD), (3, Split.ABC), (2, Split.AB), (1, Split.FULL),
    ),
    # DOIS GRUPOS POR DIA É ABC, E NÃO ABCD — mudou em 10/09/2026.
    #
    # A escala pedia quatro dias e entregava ABCD, cujo quarto dia se chama
    # "Complementares". Quem pediu DOIS grupos por dia recebia um dia de
    # trapézio, antebraço, panturrilha e core — que não são dois grupos
    # principais, são o resto. E quem treinava cinco dias recebia A-B-C-D-A,
    # com o dia D no meio da semana sem ter pedido nada parecido.
    #
    # Agora a preferência pede TRÊS dias e entrega A-B-C, repetindo a partir
    # do quarto: A-B-C-A, A-B-C-A-B, A-B-C-A-B-C, A-B-C-A-B-C-A. Os
    # complementares não sumiram — foram para dentro de B e de C, e
    # `repartir_ocorrencia` os distribui entre B1/B2 e C1/C2 em vez de
    # repeti-los toda sessão.
    SplitPreference.DOIS: (
        (3, Split.ABC2), (2, Split.AB), (1, Split.FULL),
    ),
    SplitPreference.TRES: ((3, Split.ABC), (2, Split.AB), (1, Split.FULL)),
}


def _preferencia_de(user) -> str:
    """A preferência de divisão desta pessoa, ou nada.

    `getattr` em vez de `user.profile` porque a ficha pode ser montada num
    caminho em que o perfil ainda não existe — e ali a ausência de preferência
    é a resposta certa, não um erro: `split_for` cai na tabela por frequência,
    que é o que o app fazia antes da pergunta existir.
    """
    profile = getattr(user, "profile", None)
    return getattr(profile, "split_preference", None)


def split_for(days_per_week: int, preference: str = None) -> str:
    """A divisão que faz sentido para essa frequência e essa preferência.

    Sem preferência, cai na tabela por frequência — é o caminho de quem tem
    plano anterior à pergunta existir, e devolve exatamente o que devolvia.
    """
    if not preference:
        return SPLIT_BY_FREQUENCY.get(days_per_week, DEFAULT_SPLIT)

    escala = SPLIT_BY_PREFERENCE.get(preference)
    if escala is None:
        return SPLIT_BY_FREQUENCY.get(days_per_week, DEFAULT_SPLIT)

    for minimo, divisao in escala:
        if days_per_week >= minimo:
            return divisao
    # Zero dias de treino não é uma frequência — é ausência dela. Quem chega
    # aqui não tem ficha para montar, e o corpo inteiro é a resposta menos
    # errada se alguém montar mesmo assim.
    return Split.FULL


def _divisao_cheia(preferencia):
    """Quantos dias esta preferência PEDE, e que divisão ela produz então.

    É o primeiro degrau da escala em `SPLIT_BY_PREFERENCE` — a divisão que
    aquela preferência entrega quando a semana comporta. Lido da própria tabela
    e não escrito à mão: no dia em que a tabela mudar, a explicação acompanha.
    """
    escala = SPLIT_BY_PREFERENCE.get(preferencia)
    if not escala:
        return None, 0
    minimo, divisao = escala[0]
    return divisao, minimo


#: O nome que a pessoa escolheu, para a explicação falar a língua da pergunta.
ROTULO_DA_PREFERENCIA = {
    SplitPreference.UM: "1 grupo por dia",
    SplitPreference.DOIS: "2 grupos por dia",
    SplitPreference.TRES: "3 grupos por dia",
}


def divisao_explicada(user, dias=None) -> dict:
    """O que a pessoa pediu, o que foi aplicado, e por quê — quando divergem.

    O DEFEITO QUE ISTO FECHA. `split_for` cruza preferência com frequência e a
    frequência manda: quem pede "1 grupo por dia" e treina duas vezes recebe AB,
    porque uma divisão de cinco dias com duas sessões deixaria três quintos do
    corpo sem treinar nenhuma vez. A regra está certa. O que estava errado é que
    ninguém era avisado: a tela mostrava AB e o perfil continuava dizendo
    "1 grupo por dia", como se a escolha tivesse sido respeitada.

    Pior: abaixo de quatro dias `preferencia_muda_a_divisao` responde False e o
    onboarding nem PERGUNTA — a preferência gravada fica lá, inerte, e a pessoa
    não tem como saber que ela não vale para a frequência dela.

    Devolve sempre as três informações. `cedeu` é o que a tela usa para decidir
    se explica; sem divergência não há o que explicar, e escrever "sua
    preferência foi respeitada" seria ocupar espaço para informar ausência.
    """
    preferencia = _preferencia_de(user)
    dias = user.training_days.count() if dias is None else dias
    aplicada = split_for(dias, preferencia)

    cheia, minimo = _divisao_cheia(preferencia)
    cedeu = bool(preferencia) and cheia is not None and aplicada != cheia

    return {
        "preferencia": preferencia,
        "rotulo": ROTULO_DA_PREFERENCIA.get(preferencia, ""),
        "aplicada": aplicada,
        "aplicada_rotulo": dict(Split.choices).get(aplicada, aplicada),
        "pedida": cheia,
        "pedida_rotulo": dict(Split.choices).get(cheia, cheia),
        "dias": dias,
        "dias_necessarios": minimo,
        "cedeu": cedeu,
        "motivo": (
            "Você escolheu %s, que precisa de %d dias de treino por semana. "
            "Com %d, o app aplicou %s — uma divisão maior deixaria parte do "
            "corpo sem treinar nenhuma vez."
            % (
                ROTULO_DA_PREFERENCIA.get(preferencia, "sua divisão"),
                minimo,
                dias,
                dict(Split.choices).get(aplicada, aplicada),
            )
            if cedeu
            else ""
        ),
    }


def preferencia_muda_a_divisao(dias_por_semana: int) -> bool:
    """A pergunta de divisão altera alguma coisa nessa frequência?

    NÃO é uma regra escrita à mão — é lida da própria `SPLIT_BY_PREFERENCE`,
    rodando `split_for` para cada preferência e vendo se sobra mais de uma
    resposta. O dia em que a tabela mudar, o onboarding acompanha sozinho.

    Hoje isso responde `False` para 0, 1, 2 e 3 dias e `True` de 4 em diante:
    quem treina três vezes recebe ABC pelas três preferências, porque a
    divisão não pode inventar dias que a semana não tem. Perguntar ali é pedir
    uma escolha que o app vai ignorar — e o onboarding fica um passo mais
    longo em troca de nada.
    """
    respostas = {split_for(dias_por_semana, p) for p in SPLIT_BY_PREFERENCE}
    return len(respostas) > 1


def templates_for(split: str) -> list:
    """Os dias da divisão, em ordem, já com os exercícios pré-carregados."""
    return list(
        WorkoutTemplate.objects.filter(split=split, is_active=True)
        .order_by("order")
        .prefetch_related("items__exercise")
    )


def build_sessions(plan, training_days, templates) -> list:
    """Casa cada dia de treino da pessoa com um dia da divisão, em ordem.

    O `%` é o que faz a divisão repetir quando a pessoa treina mais dias do que
    a divisão tem letras: cinco dias num ABC viram A, B, C, A, B.
    """
    sessions = []
    for index, day in enumerate(training_days):
        template = templates[index % len(templates)]
        sessions.append(
            TrainingSession(
                plan=plan,
                weekday=day.weekday,
                label=template.label,
                name=template.name,
                focus=template.focus,
                main_groups=list(template.main_groups or ()),
                start_time=day.start_time,
                duration_min=day.duration_min,
                order=index,
            )
        )
    return sessions


#: A DOSE DO CATÁLOGO É POR SESSÃO, e esta linha é a correção de 08/09/2026.
#:
#: Ela já foi lida como orçamento SEMANAL, repartido entre as ocorrências da
#: letra: com cinco dias em ABC a letra A cai duas vezes, e as quatro séries de
#: Supino reto viravam `[2, 2]`. Medido no perfil de referência da missão — 27
#: anos, 102 kg, 1,85 m, segunda a sexta, 90 minutos por sessão — o Supino saía
#: com DUAS séries na segunda e DUAS na quinta, em sessões de 21 a 26 minutos
#: para quem informou noventa.
#:
#: O que fecha o diagnóstico é o tempo: sobravam mais de sessenta minutos, então
#: o corte por relógio nem chegou a ser acionado. A redução vinha só da divisão
#: do volume — exatamente o que um exercício principal não pode sofrer sem razão
#: calculada.
#:
#: O problema que a repartição resolvia continua real: repetir a letra multiplica
#: o volume semanal, e o dia A duas vezes daria 26 séries de peito. Quem resolve
#: isso agora é `TETO_SEMANAL_POR_GRUPO`, e o preço é pago pelo ISOLADOR — não
#: pelo composto.

#: Séries efetivas por grupo muscular por semana, contando participação
#: secundária pela metade.
#:
#: Vinte é o topo da faixa que a literatura de hipertrofia trata como
#: produtiva para um grupo grande; abaixo de dez o estímulo fica magro. O número
#: é um TETO, não uma meta: ficha que já cabe embaixo dele não é tocada.
TETO_SEMANAL_POR_GRUPO = 20

#: Quanto uma série conta para um músculo que ela usa de forma SECUNDÁRIA.
#:
#: Meia série, e é regra explícita justamente porque a missão proíbe o
#: contrário: "não conte uma série de tríceps no supino como se fosse idêntica a
#: uma série direta de tríceps". Um número escrito num lugar só é auditável;
#: espalhar a intuição por condicionais não é.
PESO_SECUNDARIO = Decimal("0.5")

#: Abaixo disto um exercício composto deixa de ser treino e vira aquecimento.
#:
#: Três é o piso; o catálogo pede quatro nos principais e é isso que a pessoa
#: recebe. Duas séries num composto principal só podem existir por decisão
#: explícita — nunca como sobra de uma conta.
PISO_COMPOSTO = 3


def dose_da_sessao(item) -> int:
    """Quantas séries deste item a pessoa faz NA SESSÃO.

    É o número do catálogo, sem repartir. A função existe para que o lugar
    onde essa decisão mora tenha nome — e para que mudá-la seja uma edição, e
    não uma arqueologia.
    """
    return item.sets


#: Os três degraus de prioridade, do que cede primeiro ao que cede por último.
ISOLADOR, ACESSORIO, PRINCIPAL = 0, 1, 2

#: A partir de quantas séries um composto é PRINCIPAL no catálogo.
#:
#: Quatro, e o número não foi escolhido aqui: é o que o catálogo já usa para
#: dizer isso. Medido nos 111 itens dos 15 modelos — todo composto que a missão
#: chama de principal pede QUATRO séries (supino reto, agachamento, leg press,
#: stiff, remada curvada, puxada frente), e todo composto acessório pede TRÊS
#: (supino inclinado, desenvolvimento, mergulho, flexão de braço). A informação
#: já estava escrita; faltava lê-la.
SERIES_DE_PRINCIPAL = 4


def prioridades_da_sessao(itens) -> list:
    """Quem cede primeiro quando falta tempo ou estoura o volume semanal.

    Recebe os itens NA ORDEM DA FICHA e devolve um degrau por item. Menor sai
    antes: isolador, depois composto acessório, e o composto principal por
    último. É a ordem que a missão escreve — "é preferível remover um isolador
    de baixa prioridade a reduzir o Supino reto para duas séries".

    PRINCIPAL não é lista de nomes, e também não é "o primeiro composto do
    grupo" — essa foi a primeira versão e ela foi medida como errada. Puxada
    frente e remada curvada dividem o grupo `back`, e a regra rebaixava a
    remada a acessório só por vir depois: a sexta-feira do perfil de referência
    perdeu a remada curvada por causa disso.

    O que separa os dois é o número de séries que o CATÁLOGO pede. Quatro é
    principal, três é acessório, e isso vale para os 111 itens dos 15 modelos.
    O dado já existia — bastava não inventar um proxy ao lado dele.

    Não usa `secondary_muscles`, e isso também foi medido: ele dá TRÊS
    secundários para "Flexão de braço", que é acessório, e UM para
    "Leg press 45°", que é principal. Uma régua que erra nos dois sentidos não
    é régua.
    """
    # UM PRINCIPAL POR GRUPO, POR SESSÃO — e este limite é o que faltava.
    #
    # Sem ele, "quatro séries = principal" tornava intocáveis DOIS pressões de
    # peito no mesmo dia (supino reto e supino inclinado pedem quatro cada), e
    # com sete dias os dois sozinhos davam 24 séries diretas de peito na
    # semana: medido, 27 efetivas contra um teto de 20, sem nada que o laço
    # pudesse ceder.
    #
    # O segundo composto do mesmo grupo é justamente o que a missão manda
    # ajustar antes de tocar no principal — "quantidade de exercícios que
    # repetem o mesmo padrão". Ele vira ACESSÓRIO: continua na ficha quando cabe
    # e é o primeiro composto a sair quando não cabe.
    #
    # Quem é o principal: o de MAIOR dose no grupo, desempate pela ordem da
    # ficha. Assim o supino reto continua principal mesmo se alguém reordenar o
    # dia, e um grupo cujo primeiro composto seja leve não promove o leve.
    melhor_do_grupo = {}
    for posicao, item in enumerate(itens):
        if not item.exercise.is_compound:
            continue
        grupo = item.exercise.muscle_group
        atual = melhor_do_grupo.get(grupo)
        if atual is None or item.sets > itens[atual].sets:
            melhor_do_grupo[grupo] = posicao

    graus = []
    for posicao, item in enumerate(itens):
        if not item.exercise.is_compound:
            graus.append(ISOLADOR)
        elif melhor_do_grupo.get(item.exercise.muscle_group) == posicao:
            graus.append(PRINCIPAL)
        else:
            graus.append(ACESSORIO)
    return graus


#: Quanto a estimativa pode passar do tempo informado: 10% do orçamento, no
#: máximo 5 minutos.
#:
#: A tolerância existe porque o gerador só encurta em unidades discretas — ele
#: remove um exercício inteiro, e um exercício custa de 3,1 a 7,4 minutos no
#: catálogo (mediana 5,4). Sem folga nenhuma, uma sessão de 30,5 minutos para
#: quem tem 30 perderia um exercício inteiro. Medido em quatro dias: tolerância
#: zero entrega 61 séries semanais contra 65, e 80 contra 86 num orçamento de
#: 45 — quatro a seis séries a menos para economizar menos de cinco minutos.
#:
#: O teto de 5 minutos é a parte que importa, e é absoluto: nenhuma sessão passa
#: mais que isso do tempo informado, em nenhum orçamento. A porcentagem sozinha
#: seria ilimitada — o formulário aceita até 300 minutos, e 10% de 300 são 30.
#:
#: Uma versão anterior deste comentário justificava 10% puro dizendo que a folga
#: seria "sempre menor que um exercício". É falso: 10% de 90 são 9 minutos e o
#: exercício mais caro custa 7,4. Na prática as duas políticas dão o mesmo
#: resultado, porque só divergem acima de 50 minutos de orçamento e ali o teto
#: nunca chega a ser acionado — a maior sessão que o catálogo produz tem 51,7
#: minutos. O que decide entre elas é o limite em princípio, não o efeito hoje.
FOLGA_PROPORCIONAL = Decimal("0.10")
FOLGA_MAXIMA_MIN = Decimal("5")


def _teto_em_segundos(minutos_disponiveis) -> Decimal:
    """O teto em segundos. DURO: o que a tela promete é o que o motor obedece.

    A folga acima foi medida e era defensável enquanto o campo era um número
    único: quem digitava 45 queria "mais ou menos 45", e ceder um exercício
    inteiro para economizar dois minutos custava de quatro a seis séries por
    semana. O comentário de `FOLGA_PROPORCIONAL` guarda essa medição.

    O que mudou não foi a opinião sobre a folga — foi a PERGUNTA. `DuracaoTreino`
    passou a perguntar uma FAIXA, e numa faixa o piso é o alvo e o topo é o
    teto. "Padrão — 45 a 60" entrega ao motor os mesmos 60 minutos que a folga
    lhe dava quando a pessoa digitava 45, e agora ele pode prometer que não
    passa. O volume não cai; a frase deixa de ser mentira.

    Auditado em produção: 30 informados entregavam 32, 45 entregavam 48 e 60
    entregavam 61. As três eram a folga aparecendo na tela.
    """
    return Decimal(minutos_disponiveis) * 60


def _segundos_da_sessao(itens) -> int:
    """Ponte para a conta única, em `workouts.models.segundos_da_sessao`.

    Recebe tuplas `(séries, descanso, é_composto)`. Era uma CÓPIA da fórmula do
    modelo, mantida em sincronia por um teste; hoje é uma chamada. O número que
    o gerador usa para decidir é, por construção, o número que a tela exibe.
    """
    return segundos_da_sessao(itens)


def _quem_cede(elegiveis, itens, vivos_por_grupo) -> int:
    """Qual dos elegíveis sai: o último do grupo mais CHEIO da sessão.

    "Mais cheio" conta os exercícios que o grupo tem NA SESSÃO — não quantos
    deles estão elegíveis neste degrau. A diferença é a regra "distribua os
    exercícios de forma equilibrada", e ela foi medida em 10/09/2026 com a
    ficha "Pernas e ombros" a 60 minutos:

        contando elegíveis:  quads 3, posterior 2, ombro 1  (cedeu ombro)
        contando a sessão:   quads 2, posterior 2, ombro 2  (cedeu quadríceps)

    Contar elegíveis fazia o quadríceps — que tinha TRÊS exercícios, sendo dois
    compostos intocáveis — parecer o grupo mais magro da sessão, porque só a
    cadeira extensora estava no degrau que cedia. O corte então tirava o
    ombro, que tinha dois, e a ficha "Pernas e ombros" terminava com UM
    exercício de ombro.

    Dentro do grupo escolhido sai o ÚLTIMO, porque dentro do bloco a ordem do
    modelo desce por importância. Ver `escolher_para_o_tempo`.
    """
    maior = max(vivos_por_grupo[itens[i][0]] for i in elegiveis)
    return next(
        i for i in reversed(elegiveis) if vivos_por_grupo[itens[i][0]] == maior
    )


def escolher_para_o_tempo(itens, minutos_disponiveis, principais=None) -> list:
    """Quais exercícios da sessão ficam, dado o tempo que a pessoa tem.

    `itens` são tuplas (grupo_muscular, séries, descanso, grau) NA ORDEM DA
    FICHA — o grau vem de `prioridades_da_sessao`.
    Devolve pares `(índice, séries)`, em ordem.

    `principais` são os grupos que o TÍTULO da sessão anuncia — vem de
    `WorkoutTemplate.main_groups`. Tudo que está na ficha e não está nessa
    lista é COMPLEMENTAR, e a concessão acontece em CINCO CAMADAS, nesta ordem:

      1. excedente do complementar — a segunda panturrilha, o segundo abdominal;
      2. excedente do anunciado — do degrau mais baixo, do grupo mais cheio;
      3. redução de série, até o piso;
      4. o ÚLTIMO exercício de um grupo complementar;
      5. o último exercício de um grupo anunciado, e aí o título é reescrito.

    AS DUAS ORDENS QUE JÁ FORAM MEDIDAS E REPROVADAS, porque cada uma quebra um
    contrato diferente:

      - **sem a distinção anunciado/complementar**, o rodízio por grupo mais
        cheio derrubava o bíceps: "Costas e bíceps" a 60 minutos saía com
        bíceps=1 e trapézio=1, porque bíceps tinha três isoladores e o
        trapézio, com um só, estava protegido pela trava do último do grupo. A
        ficha protegia o que o título não promete;
      - **com o complementar cedendo INTEIRO na primeira camada**, panturrilha
        e abdômen ficavam órfãos da semana inteira em três, quatro e cinco
        dias, no perfil de dois grupos por dia com 45 a 60 minutos: a letra C
        cai uma vez só nessas frequências, e o que saía dela não voltava em
        lugar nenhum.

    A ordem em cinco camadas entrega os dois: costas=4 e bíceps=3 no perfil de
    referência, e ZERO grupo complementar órfão da semana em qualquer
    frequência de 45 minutos para cima.

    `principais` vazio ou ausente devolve o comportamento anterior — é o
    caminho de quem chama de fora (teste, shell) e de modelo sem a lista.

    O defeito que isto fecha: quem informava 30 minutos recebia sessão estimada
    em 47 a 51. O campo se chamava "Duração média" e o gerador nunca o leu — a
    interface fazia acreditar num limite que o motor ignorava.

    O CRITÉRIO DO CORTE custou uma auditoria, e a primeira resposta estava
    errada. A nota da divisão AB diz "priorize os exercícios do começo da
    ficha", e eu tratei isso como prova de que `order` é um ranking global de
    importância. Não é. Medindo os nove modelos do catálogo:

      - dois têm exercício isolado ANTES de um multiarticular;
      - oito pares têm as séries SUBINDO ao longo da ficha;
      - `abc C` é agachamento, leg press, extensora, stiff, mesa, flexora,
        panturrilha, panturrilha, prancha.

    A ordem agrupa por REGIÃO — bloco de quadríceps, bloco de posterior,
    panturrilha, core — e só dentro de cada bloco ela desce por importância.
    Cortar a cauda de `abc C` apagaria a panturrilha inteira e depois o
    posterior, deixando três exercícios de quadríceps: um dia de pernas que
    virou dia de quadríceps, sem nada avisando.

    Então o corte é por RODÍZIO entre os grupos: tira sempre do grupo que tem
    mais exercícios na sessão, e dentro dele o último — que aí sim é o menos
    prioritário, porque dentro do bloco a ordem vale. Nenhum grupo do dia
    desaparece enquanto outro ainda tiver dois.

    E o rodízio acontece DENTRO de um degrau de prioridade, não sobre a ficha
    inteira. As tuplas trazem o grau (`prioridades_da_sessao`) e o laço só
    considera o menor presente: isolador sai antes de composto acessório, que
    sai antes de composto principal. Sem isso, uma sessão apertada cedia o
    agachamento para poupar duas roscas — e a missão diz o contrário com todas
    as letras.

    Nunca devolve lista vazia: quem informou quinze minutos ainda merece o
    exercício principal do dia.
    """
    if not itens:
        return []

    # SEM TETO É SEM CORTE. `DuracaoTreino.LIVRE` chega aqui como `None`, e o
    # significado é "priorizar a ficha completa" — não um teto enorme. Tratar
    # ausência como um número grande funcionaria por acidente hoje e passaria a
    # cortar no dia em que o catálogo crescesse.
    if minutos_disponiveis is None:
        return [(i, itens[i][1]) for i in range(len(itens))]

    teto = _teto_em_segundos(minutos_disponiveis)
    ficam = list(range(len(itens)))
    # As séries que cada item ainda tem. Começa no que o catálogo pede e só
    # desce quando não há mais exercício que possa sair — ver o ramo de
    # redução abaixo.
    series = {i: itens[i][1] for i in range(len(itens))}

    anunciados = set(principais or ())

    def _e_complementar(grupo):
        return bool(anunciados) and grupo not in anunciados

    def _do_degrau_mais_baixo(candidatos):
        """Só os do menor grau presente entre os candidatos.

        Isolador antes de composto acessório, acessório antes de principal — o
        rodízio por grupo acontece DENTRO de um degrau, nunca sobre a ficha
        inteira. Sem isso uma sessão apertada cede o agachamento para poupar
        duas roscas.
        """
        grau = min(itens[i][3] for i in candidatos)
        return [i for i in candidatos if itens[i][3] == grau]

    while len(ficam) > 1:
        # A conta precisa saber se e composto: composto tem serie de
        # aproximacao, e ela ocupa o relogio.
        atual = [
            (series[i], itens[i][2], itens[i][3] >= ACESSORIO) for i in ficam
        ]
        if _segundos_da_sessao(atual) <= teto:
            break

        # PRIORIDADE PRIMEIRO, RODÍZIO DEPOIS — e nesta ordem, porque a missão
        # é explícita: "é preferível remover um isolador de baixa prioridade a
        # reduzir o Supino reto". O rodízio por grupo continua valendo, mas só
        # DENTRO do degrau que está cedendo; senão a sessão cede o composto
        # principal de pernas para poupar duas roscas.
        # NUNCA O ÚLTIMO EXERCÍCIO DE UM GRUPO — a trava que faltava aqui.
        #
        # `aparar_volume_semanal` já tinha esta trava; o corte por tempo, não.
        # Medido em 10/09/2026 com "até 30 minutos": a ficha "Peito, tríceps e
        # ombro" saía com Supino e Desenvolvimento e ZERO tríceps, com o
        # tríceps ainda no título; "Costas, bíceps, antebraço e trapézio"
        # perdia TRÊS dos quatro grupos anunciados. O rodízio tirava do grupo
        # mais cheio até o grupo mais cheio ser o único que ainda tinha dois —
        # e depois tirava o último dos outros.
        #
        # Com a trava, o tempo continua sendo teto e continua cortando; o que
        # ele não faz mais é apagar um músculo que o título promete.
        vivos_por_grupo = {}
        for i in ficam:
            vivos_por_grupo[itens[i][0]] = vivos_por_grupo.get(itens[i][0], 0) + 1

        # CAMADA 1 — O EXCEDENTE DO COMPLEMENTAR.
        #
        # Não é "o complementar inteiro": é a SEGUNDA panturrilha, o SEGUNDO
        # abdominal, o segundo antebraço. O grupo continua na sessão.
        #
        # Uma versão anterior desta função, de 10/09/2026, derrubava o
        # complementar inteiro nesta camada, e o resultado foi medido: no perfil
        # de dois grupos por dia com 45 a 60 minutos, panturrilha e abdômen
        # ficavam órfãos da semana INTEIRA em três, quatro e cinco dias — a
        # letra C cai uma vez só nessas frequências, e o que saía dela não
        # voltava em lugar nenhum. Eu tinha chamado isso de limitação
        # aritmética; a medição desmentiu, e a diferença era só a ordem.
        excedente = [
            i for i in ficam
            if _e_complementar(itens[i][0]) and vivos_por_grupo[itens[i][0]] > 1
        ]
        if excedente:
            ficam.remove(
                _quem_cede(_do_degrau_mais_baixo(excedente), itens, vivos_por_grupo)
            )
            continue

        # CAMADA 2 — O EXCEDENTE DO ANUNCIADO.
        #
        # Do degrau mais baixo primeiro (isolador antes de composto acessório,
        # acessório antes de principal), e do grupo mais cheio da sessão. Nunca
        # o último de um grupo: isso é a camada 5.
        excedente = [
            i for i in ficam
            if not _e_complementar(itens[i][0]) and vivos_por_grupo[itens[i][0]] > 1
        ]
        if excedente:
            ficam.remove(
                _quem_cede(_do_degrau_mais_baixo(excedente), itens, vivos_por_grupo)
            )
            continue

        # CAMADA 3 — REDUZIR SÉRIE, até o piso.
        #
        # Antes de qualquer grupo sair, inclusive complementar. É a ordem que a
        # especificação fixa — "reduza séries ou quantidade de exercícios de
        # forma equilibrada e mantenha cobertura mínima" — e ela vale aqui
        # porque, chegando neste ponto, TODO grupo da sessão está com um
        # exercício só: qualquer remoção apaga um músculo.
        #
        # Medido: é esta camada, e não a anterior, que salva a panturrilha do
        # `abc C` em três dias com "até 30 minutos". Cede sempre quem tem mais
        # série, e o piso respeita `PISO_COMPOSTO` — abaixo de três um composto
        # vira aquecimento.
        reduziveis = [
            i for i in ficam
            if series[i] > (PISO_COMPOSTO if itens[i][3] >= ACESSORIO else 2)
        ]
        if reduziveis:
            alvo = max(reduziveis, key=lambda i: (series[i], -i))
            series[alvo] -= 1
            continue

        # CAMADA 4 — O ÚLTIMO COMPLEMENTAR SAI.
        #
        # Aqui o grupo complementar deixa a sessão. Ele volta na outra passagem
        # da letra quando ela existe; quando não existe, some da semana, e é
        # `aviso_de_tempo` que diz isso à pessoa em vez de a ficha omitir.
        #
        # Que este caso EXISTE está medido: em `abc2 C` com "até 30 minutos",
        # os três compostos principais no PISO de série custam 28,2 minutos, e
        # o complementar mais barato do catálogo leva a sessão a 31,8 contra um
        # teto de 30.
        #
        # E a frase honesta não é "é impossível": cinco isoladores — extensora,
        # mesa flexora, elevação lateral, panturrilha sentado e prancha —
        # cobrem os cinco grupos em 20,7 minutos. O que isso não é, é um dia de
        # perna. Derrubar o agachamento e o stiff para encaixar o relógio é
        # exatamente o que o contrato proíbe, então a escolha é consciente e o
        # preço dela é `aviso_de_tempo` dizer o que ficou fora.
        ultimos = [i for i in ficam if _e_complementar(itens[i][0])]
        if ultimos:
            ficam.remove(
                _quem_cede(_do_degrau_mais_baixo(ultimos), itens, vivos_por_grupo)
            )
            continue

        # CAMADA 5 — ÚLTIMO RECURSO: um grupo ANUNCIADO cai.
        #
        # Já saiu todo excedente, já desceu toda série que podia descer e já
        # saiu todo complementar. O que resta é a aritmética — medido, `ab A`
        # tem oito exercícios em SETE grupos, e sete exercícios no piso de série
        # ainda dão 42 minutos contra um teto de 30.
        #
        # Aqui o relógio ganha, porque ele é o limite mais duro e a pessoa
        # combinou 30 minutos. `titulo_honesto` tira o grupo do nome da sessão e
        # `aviso_de_tempo` conta o que aconteceu.
        ficam.remove(
            _quem_cede(_do_degrau_mais_baixo(list(ficam)), itens, vivos_por_grupo)
        )

    # Devolve o índice E as séries: quando a redução entrou em cena, o número
    # do catálogo deixou de valer para aquele item, e quem prescreve precisa
    # saber disso.
    return [(i, series[i]) for i in ficam]


def volume_efetivo(itens) -> dict:
    """Séries efetivas por grupo muscular. Direta vale 1; secundária, metade.

    `itens` são tuplas `(grupo, secundarios, series)`.

    A regra é explícita porque a missão proíbe o contrário: "não conte uma
    série de tríceps no supino como se fosse idêntica a uma série direta de
    tríceps". Meia série é uma escolha — o que não podia continuar era não
    haver escolha nenhuma, com o secundário valendo zero ou um conforme quem
    olhasse.
    """
    volume = {}
    for grupo, secundarios, series in itens:
        volume[grupo] = volume.get(grupo, Decimal(0)) + series
        for outro in secundarios or ():
            volume[outro] = volume.get(outro, Decimal(0)) + series * PESO_SECUNDARIO
    return volume


def teto_semanal_de(user) -> int:
    """O teto de séries efetivas por grupo desta pessoa.

    Sai da EXPERIÊNCIA declarada. DOIS caminhos caem no valor do intermediário,
    e os dois de propósito: perfil ausente — quem monta ficha antes de o perfil
    existir — e `experiencia == ""`, que é o estado de quem ainda não
    respondeu. Vinte é o número que o app praticava antes desta pergunta
    existir, então nenhum dos dois tem a ficha reescrita. É o mesmo critério de
    `teto_de_minutos`.

    E o valor é TETO DE APARO, não promessa: `aparar_volume_semanal` só remove
    isolador direto e nunca o último de um grupo, então excesso vindo de
    secundário de composto principal fica. Ver `TETO_POR_EXPERIENCIA` em
    `accounts.models` para a medição.
    """
    perfil = getattr(user, "profile", None)
    nivel = getattr(perfil, "experiencia", None) or Experiencia.INTERMEDIARIO
    return TETO_POR_EXPERIENCIA.get(nivel, TETO_SEMANAL_POR_GRUPO)


def aparar_volume_semanal(candidatos, teto=None) -> set:
    """Quais itens da SEMANA ficam para nenhum grupo passar do teto.

    `candidatos` é uma lista de `(chave, grupo, secundarios, series, grau)`, na
    ordem em que aparecem na semana. Devolve o conjunto de chaves que FICA.

    Por que existe: com a dose do catálogo valendo por sessão, repetir a letra
    A duas vezes soma o peito duas vezes — 26 séries na semana, medido. A
    frequência maior é desejada; o volume dobrado não.

    Quem paga é o ISOLADOR, e é aí que esta função difere da solução anterior.
    `distribuir_series` cobrava do exercício principal, derrubando o supino de
    quatro séries para duas. Aqui o laço só remove itens do menor degrau
    presente e **nunca um composto principal**: se o excesso só puder ser
    resolvido cortando principal, o excesso fica.

    TRÊS TRAVAS, e as três vieram de medição no perfil de referência:

    1. **só sai quem treina o grupo DIRETAMENTE.** Sem isso, o laço tentava
       resolver o excesso de core apagando a prancha abdominal — e o excesso
       vinha de agachamento e stiff, que contam meia série cada para o core e
       continuavam lá. Apagar o único trabalho direto do grupo "com volume
       demais" é o avesso do objetivo;
    2. **nunca o último exercício direto de um grupo.** Sem isso, antebraço
       saía inteiro da semana. Grupo com um exercício só não tem gordura para
       cortar: se ele estoura, o excesso é secundário e a resposta é não mexer;
    3. **cede a sessão mais CHEIA, não a última da semana.** A primeira versão
       tirava sempre do fim; medido, a sexta-feira ficava com dois exercícios e
       onze minutos para quem informou noventa. Esvaziar a segunda passagem não
       é reduzir volume, é apagar um treino. Tirando da sessão mais cheia, as
       duas passagens afinam juntas.

       E ISSO NÃO É UMA PROMESSA DE VARIEDADE. Esta linha já disse que as
       passagens "ficam com exercícios DIFERENTES", e a frase chegou à tela em
       cima disso. Medido em 09/09/2026: em quatro dias a segunda passagem de A
       é SUBCONJUNTO da primeira; em cinco elas diferem; em sete as três saem
       IDÊNTICAS. O que a trava garante é que nenhuma passagem seja esvaziada —
       variedade, quando aparece, é consequência e não contrato.

    Determinístico de propósito: `prescrever_semana` é chamada pelo gerador E
    pela conferência de ficha atual, e uma divergência de um item faria a tela
    remontar a rotina em laço.
    """
    ficam = {c[0] for c in candidatos}

    while True:
        volume = volume_efetivo(
            [(c[1], c[2], c[3]) for c in candidatos if c[0] in ficam]
        )
        pendentes = sorted(
            (g for g, v in volume.items() if v > (teto or TETO_SEMANAL_POR_GRUPO)),
            key=lambda g: (volume[g], g),
            reverse=True,
        )

        alvo = None
        for pior in pendentes:
            diretos_vivos = {}
            for c in candidatos:
                if c[0] in ficam:
                    diretos_vivos[c[1]] = diretos_vivos.get(c[1], 0) + 1
            if diretos_vivos.get(pior, 0) <= 1:
                continue

            podem = [
                c
                for c in candidatos
                if c[0] in ficam and c[4] < PRINCIPAL and c[1] == pior
            ]
            if not podem:
                continue

            vivos_por_sessao = {}
            for c in candidatos:
                if c[0] in ficam:
                    vivos_por_sessao[c[0][0]] = vivos_por_sessao.get(c[0][0], 0) + 1

            grau_minimo = min(c[4] for c in podem)
            do_grau = [c for c in podem if c[4] == grau_minimo]
            mais_cheia = max(vivos_por_sessao[c[0][0]] for c in do_grau)
            alvo = [c for c in do_grau if vivos_por_sessao[c[0][0]] == mais_cheia][-1]
            break

        if alvo is None:
            # Nenhum grupo acima do teto tem o que ceder sem desmontar o treino.
            return ficam
        ficam.discard(alvo[0])


def repartir_ocorrencia(itens, indice, ocorrencias):
    """Os itens que ESTA passagem da letra recebe.

    O DEFEITO QUE ISTO FECHA, medido em 10/09/2026 no perfil de referência.
    Quando a letra repete na semana, as duas passagens recebiam a lista INTEIRA
    do modelo. O volume dobrava, `aparar_volume_semanal` cortava para o teto
    semanal caber — e o que ela cortava era variedade:

        7 dias, antes:  A1 e A2 dividiam 3 exercícios iguais dos 4 que tinham;
                        C1 e C2 dividiam 4; a semana fechava com 2 exercícios
                        distintos de peito, contra os 4 que o modelo lista.

    Repare que o catálogo não era o limite: `abcd A` já traz os QUATRO peitos e
    os TRÊS tríceps que o contrato pede. Eles entravam duas vezes e o aparo os
    derrubava. Quem estava errado era a duplicação, não o teto.

    A linha exata: `prescrever_semana` calculava `indice = vistas.get(label, 0)`
    e nunca usava. O número da ocorrência era conhecido e jogado fora.

    COMO REPARTE. Por GRUPO MUSCULAR, e não pela lista inteira: repartir o
    conjunto todo deixaria uma passagem sem peito e a outra sem tríceps. Dentro
    de cada grupo, distribuição em rodízio pela ordem do modelo — a passagem
    `i` de `n` leva as posições `i`, `i+n`, `i+2n`... Determinístico e estável:
    mesma entrada, mesma saída, sempre.

    QUANDO O GRUPO TEM MENOS EXERCÍCIOS QUE PASSAGENS, ele repete — e só aí.
    É a cláusula "só permitir repetição depois de esgotar o catálogo elegível",
    e ela é o que impede o outro defeito: `abc B` tem UM antebraço e UM
    trapézio, e reparti-los deixaria a segunda passagem anunciando dois
    músculos que ela não treina.
    """
    if ocorrencias <= 1:
        return list(itens)

    por_grupo = {}
    for item in itens:
        por_grupo.setdefault(item.exercise.muscle_group, []).append(item)

    escolhidos = []
    for grupo, do_grupo in por_grupo.items():
        if len(do_grupo) >= ocorrencias:
            escolhidos.extend(do_grupo[indice::ocorrencias])
        else:
            # Pool esgotado: cada passagem leva um, ciclando. Ninguém fica sem
            # o grupo, e a repetição é a saída de último caso, não a primeira.
            escolhidos.append(do_grupo[indice % len(do_grupo)])

    # Devolve na ORDEM DO MODELO. `prioridades_da_sessao` lê a ordem da ficha
    # para decidir o grau, e devolver agrupado por músculo mudaria o grau de
    # exercício que não mudou de lugar nenhum.
    posicao = {id(item): i for i, item in enumerate(itens)}
    return sorted(escolhidos, key=lambda item: posicao[id(item)])


#: Sentinela para `prescrever_semana`: `None` É um teto válido — significa
#: "sem limite rígido" —, então ele não pode servir de "não informado".
_NAO_INFORMADO = object()


def teto_de_minutos(user) -> int:
    """O teto de tempo desta pessoa, em minutos, ou `None` quando não há.

    Lê a FAIXA declarada no perfil e não o `duration_min` da sessão. O inteiro
    continua gravado — `plans/meal_planner.py` precisa dele para não marcar
    refeição no meio do treino —, mas ele deixou de ser a pergunta: quem
    respondeu "Padrão" declarou 45 a 60, e é o topo da faixa que o motor deve
    obedecer.

    Perfil ausente devolve `None`, que é "sem teto". É o caminho de quem monta
    ficha antes de o perfil existir, e ali prometer um teto seria inventar uma
    resposta que ninguém deu.
    """
    perfil = getattr(user, "profile", None)
    faixa = getattr(perfil, "duracao_treino", None) or DuracaoTreino.LIVRE
    return TETO_POR_DURACAO.get(faixa)


def prescrever_semana(sessoes, modelos, teto=_NAO_INFORMADO,
                      teto_semanal=None) -> dict:
    """O que cada sessão da semana manda fazer: {(sessão, exercício): séries}.

    Uma função só, chamada pelo gerador E pela conferência, porque as duas
    precisam da MESMA resposta. Enquanto eram dois trechos parecidos, qualquer
    divergência de um número fazia `routine_is_current` julgar a ficha obsoleta
    em toda visita — o gerador remontando a ficha várias vezes por dia, em
    silêncio, sem nenhum erro na tela.

    Junta as três decisões que moldam a ficha, nesta ordem:

    1. cada sessão nasce com a dose CHEIA do catálogo — `dose_da_sessao`. O
       número escrito no modelo é o que a pessoa faz naquele dia;
    2. `aparar_volume_semanal` tira ISOLADORES até nenhum grupo passar do teto
       da semana, porque repetir a letra multiplica o volume;
    3. `escolher_para_o_tempo` corta, também por prioridade, até a sessão caber
       no tempo informado.

    A ordem importa. O volume vem antes do relógio porque ele remove o que é
    redundante — o terceiro isolador de peito na segunda passagem do dia A —, e
    isso deixa menos trabalho para o corte por tempo, que é mais cego. O tempo
    é a última palavra porque é o limite mais duro: quem tem trinta minutos
    recebe menos exercício, não uma sessão de cinquenta.

    O QUE MUDOU EM 08/09/2026. A etapa 1 era `distribuir_series`, que repartia
    o número do catálogo entre as ocorrências da letra e derrubava o Supino reto
    para duas séries num perfil com noventa minutos livres. A frequência maior
    continua não podendo multiplicar o volume — mas quem paga isso agora é o
    isolador, na etapa 2, e não o exercício principal.
    """
    vistas = {}
    por_sessao = {}
    ordem_semanal = []
    # Quantas vezes cada letra aparece na semana — precisa ser sabido ANTES de
    # montar a primeira sessão, porque é ele que diz em quantas partes o modelo
    # se reparte. Ver `repartir_ocorrencia`.
    ocorrencias = {}
    for sessao in sessoes:
        ocorrencias[sessao.label] = ocorrencias.get(sessao.label, 0) + 1

    for sessao in sessoes:
        modelo = modelos.get(sessao.label)
        if modelo is None:
            return None
        indice = vistas.get(sessao.label, 0)
        vistas[sessao.label] = indice + 1

        # EXERCÍCIO INATIVO NÃO ENTRA EM PLANO NOVO, e esta linha é a trava
        # estrutural — não a limpeza do catálogo.
        #
        # Aposentar um exercício é `is_active=False`, porque apagar levaria o
        # histórico junto (`ExerciseLog.exercise` é CASCADE). Mas desativar
        # sozinho não o tirava das fichas: o modelo continuava apontando para
        # ele e o gerador copiava sem perguntar. Com este filtro, qualquer
        # exercício aposentado some das prescrições NOVAS no mesmo instante,
        # mesmo que algum modelo ainda o referencie.
        itens = [item for item in modelo.items.all() if item.exercise.is_active]
        # A REPARTIÇÃO VEM ANTES DO GRAU, e a ordem importa: o grau é da
        # SESSÃO ("o composto de maior dose de cada grupo, um por grupo"), e
        # calcular sobre a lista inteira daria a A2 o grau que A1 tem.
        itens = repartir_ocorrencia(itens, indice, ocorrencias[sessao.label])
        graus = prioridades_da_sessao(itens)
        candidatos = [
            (item, dose_da_sessao(item), grau)
            for item, grau in zip(itens, graus)
            if dose_da_sessao(item) > 0
        ]
        # OS GRUPOS QUE O TÍTULO ANUNCIA, guardados junto: o corte por tempo
        # precisa saber o que é promessa e o que é complementar, e quem sabe
        # isso é o modelo do catálogo.
        por_sessao[sessao.pk] = (
            sessao, candidatos, list(getattr(modelo, "main_groups", None) or ()),
        )
        for posicao, (item, series, grau) in enumerate(candidatos):
            ordem_semanal.append(
                (
                    (sessao.pk, item.exercise_id),
                    item.exercise.muscle_group,
                    tuple(item.exercise.secondary_muscles or ()),
                    Decimal(series),
                    grau,
                )
            )

    sobrevivem = aparar_volume_semanal(ordem_semanal, teto=teto_semanal)

    # O TETO VEM DE FORA quando quem chama já tem a pessoa em mãos.
    #
    # Derivá-lo de `sessoes[0].plan.user` custava DUAS consultas por
    # renderização — o usuário e o perfil, nenhum dos dois em cache nesse
    # caminho. Medido na tela de treino: 21 para 23. Os dois chamadores de
    # produção recebem o usuário como argumento, então passar o teto é de
    # graça; o padrão continua derivando, para quem chamar de fora (teste,
    # shell) não precisar saber disso.
    if teto is _NAO_INFORMADO:
        teto = teto_de_minutos(sessoes[0].plan.user) if sessoes else None

    prescricao = {}
    for sessao_pk, (sessao, candidatos, principais) in por_sessao.items():
        restantes = [
            (item, series, grau)
            for item, series, grau in candidatos
            if (sessao_pk, item.exercise_id) in sobrevivem
        ]
        ficam = escolher_para_o_tempo(
            [
                (item.exercise.muscle_group, series, item.rest_seconds, grau)
                for item, series, grau in restantes
            ],
            teto,
            principais=principais,
        )
        for i, series_finais in ficam:
            item, _series_do_catalogo, _grau = restantes[i]
            # `series_finais` e não o número do catálogo: quando a sessão só
            # coube reduzindo série, é a reduzida que a pessoa faz.
            prescricao[(sessao.pk, item.exercise_id)] = (series_finais, item)
    return prescricao


#: Como o TÍTULO chama cada grupo. Curto de propósito: `MuscleGroup.label`
#: existe para o admin e diz "Posterior de coxa e glúteo", que é preciso e não
#: cabe num nome de sessão.
NOME_CURTO_DO_GRUPO = {
    MuscleGroup.CHEST: "peito",
    MuscleGroup.BACK: "costas",
    MuscleGroup.QUADS: "quadríceps",
    MuscleGroup.HAMSTRINGS: "posterior",
    MuscleGroup.CALVES: "panturrilha",
    MuscleGroup.SHOULDERS: "ombros",
    MuscleGroup.BICEPS: "bíceps",
    MuscleGroup.TRICEPS: "tríceps",
    MuscleGroup.CORE: "abdômen",
    MuscleGroup.TRAPS: "trapézio",
    MuscleGroup.FOREARMS: "antebraço",
}


def _lista_em_portugues(palavras) -> str:
    """"a", "a e b", "a, b e c" — a vírgula de série do português."""
    palavras = list(palavras)
    if not palavras:
        return ""
    if len(palavras) == 1:
        return palavras[0]
    return "%s e %s" % (", ".join(palavras[:-1]), palavras[-1])


def _nomes_dos_grupos(grupos) -> list:
    """Os nomes curtos, com quadríceps e posterior colapsados em "pernas".

    Quem treina os dois no mesmo dia treinou PERNA, e "quadríceps e posterior e
    ombros" é a frase de quem está lendo um banco de dados em voz alta. O
    colapso acontece na posição do primeiro dos dois, para a ordem do título
    continuar sendo a ordem da ficha.
    """
    grupos = list(grupos)
    perna = {MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS}
    colapsa = perna <= set(grupos)
    nomes = []
    for grupo in grupos:
        if colapsa and grupo in perna:
            if "pernas" not in nomes:
                nomes.append("pernas")
            continue
        nome = NOME_CURTO_DO_GRUPO.get(grupo)
        if nome:
            nomes.append(nome)
    return nomes


def _frase_que_cabe(nomes, limite, molde=None) -> str:
    """A lista de nomes, encurtada até caber no limite da coluna.

    POR QUE ISTO EXISTE, e por que não basta "hoje cabe". Enquanto o nome da
    sessão vinha do catálogo, caber era responsabilidade de quem escrevia o
    catálogo — sessenta caracteres, conferidos uma vez. `titulo_honesto` MONTA
    o nome a partir dos grupos que sobreviveram, e uma lista cresce: medido
    sobre todos os subconjuntos dos onze grupos, a pior combinação dá 94
    caracteres contra os 60 da coluna. O PostgreSQL não trunca `varchar` — ele
    RECUSA a linha —, então isso não seria um título feio, seria a montagem da
    ficha estourando com `value too long`.

    No catálogo de hoje a pior combinação real dá 51, com nove de folga. Nove
    caracteres é exatamente o tipo de margem que uma divisão nova gasta sem
    ninguém perceber, e depender dela seria deixar o defeito armado.

    A saída não é truncar no meio de uma palavra — "Quadríceps, peito, cost" —
    e sim NOMEAR MENOS e contar o resto: "Quadríceps, peito e mais 4". Continua
    verdadeiro, continua legível, e a conta fecha em qualquer catálogo.
    """
    molde = molde or (lambda texto: texto)
    inteira = molde(_lista_em_portugues(nomes))
    if limite is None or len(inteira) <= limite:
        return inteira
    for quantos in range(len(nomes) - 1, 0, -1):
        # Vírgula e não `_lista_em_portugues` na parte que fica: com o "e" da
        # lista mais o "e mais", a frase saía "ombros e bíceps e mais 4".
        curta = molde(
            "%s e mais %d" % (", ".join(nomes[:quantos]), len(nomes) - quantos)
        )
        if len(curta) <= limite:
            return curta
    return ""


def _limite_de(campo) -> int:
    """O tamanho da coluna, lido do modelo.

    Escrito à mão, o número envelhece na primeira `AlterField` — e o dia em que
    envelhecesse seria o dia em que a ficha para de ser montada.
    """
    return TrainingSession._meta.get_field(campo).max_length


def titulo_honesto(nome_do_modelo, principais, presentes) -> str:
    """O nome da sessão, dizendo só o que ela tem.

    O DEFEITO QUE ISTO FECHA, e ele apareceu em produção em três formas:

      - "Corpo inteiro" com TRÊS exercícios. Em `full A` com trinta minutos, a
        aritmética não comporta os nove grupos — sete no piso de série ainda
        passam do teto —, e o que sobrava era agachamento, supino e puxada. A
        ficha continuava se chamando corpo inteiro;
      - "Costas, bíceps, antebraço e trapézio" sem antebraço. Não foi o
        relógio: `aparar_volume_semanal` tirou a rosca inversa de UMA das duas
        passagens porque a semana passou do teto, e a passagem ficou anunciando
        um grupo que ela não treina;
      - "Peito, tríceps e ombro" sem ombro, pelo mesmo motivo.

    A regra é uma frase: o título nomeia os grupos ANUNCIADOS que sobreviveram,
    na ordem em que o modelo os anuncia. Se todos sobreviveram, o nome curado
    do catálogo continua valendo — ele diz melhor do que uma lista ("Superior"
    é melhor que "peito, costas, ombros, bíceps e tríceps").

    Não olha os COMPLEMENTARES de propósito: o título não os prometeu, então a
    ausência deles não o torna mentira e a presença não muda o nome. Quem fala
    deles é a seção "Complementares desta sessão", na ficha.
    """
    anunciados = list(principais or ())
    if not anunciados:
        return nome_do_modelo
    sobreviventes = [grupo for grupo in anunciados if grupo in set(presentes)]
    if len(sobreviventes) == len(anunciados):
        return nome_do_modelo
    if not sobreviventes:
        # Nenhum grupo anunciado sobreviveu. Não deveria acontecer — o corte
        # protege o último exercício de cada grupo anunciado —, e mesmo assim
        # o nome não pode virar string vazia numa coluna que a tela imprime.
        return "Treino do dia"
    montado = _frase_que_cabe(
        _nomes_dos_grupos(sobreviventes),
        _limite_de("name"),
        molde=lambda texto: texto.capitalize(),
    )
    return montado or "Treino do dia"


def foco_honesto(presentes) -> str:
    """A linha de apoio, quando o texto curado do catálogo deixou de valer.

    Enumera o que a sessão TEM — inclusive os complementares, que o título não
    nomeia. Não afirma causa: um grupo pode ter saído pelo relógio ou pelo teto
    semanal, e a frase que explica isso é a nota do plano (`aviso_de_tempo`),
    que sabe qual dos dois foi.
    """
    nomes = _nomes_dos_grupos(presentes)
    if not nomes:
        return ""
    return _frase_que_cabe(
        nomes,
        _limite_de("focus"),
        molde=lambda texto: "Nesta sessão: %s." % texto,
    )


def ajustar_titulos(sessoes, prescricao) -> list:
    """Reescreve nome e foco das sessões que perderam um grupo anunciado.

    Devolve as sessões alteradas, para quem chama gravar em lote. Não grava:
    `create_routine` ainda vai escrever as linhas da ficha, e duas idas ao
    banco onde cabe uma é o tipo de coisa que `ScreenQueryBudgetTests` pega.
    """
    por_sessao = {}
    for (sessao_pk, _exercicio), (_series, item) in prescricao.items():
        por_sessao.setdefault(sessao_pk, []).append(item)

    mudaram = []
    for sessao in sessoes:
        itens = sorted(por_sessao.get(sessao.pk, []), key=lambda i: i.order)
        presentes = []
        for item in itens:
            grupo = item.exercise.muscle_group
            if grupo not in presentes:
                presentes.append(grupo)
        nome = titulo_honesto(sessao.name, sessao.main_groups, presentes)
        if nome == sessao.name:
            continue
        sessao.name = nome
        sessao.focus = foco_honesto(presentes)
        mudaram.append(sessao)
    return mudaram


#: Quantas vezes, por extenso. Vai até sete porque a semana tem sete dias.
VEZES = {2: "duas", 3: "três", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete"}


def nota_da_divisao(split, sessoes) -> str:
    """A nota da ficha, montada a partir do ciclo que ESTA ficha tem.

    Era um texto fixo por divisão, e o do ABC dizia "quem treina cinco vezes
    faz A, B, C, A, B". Quem treinava QUATRO lia isso na própria ficha e tinha
    que descobrir sozinho que no caso dele o ciclo era A-B-C-A: a nota
    descrevia a divisão em abstrato, não a semana que estava logo abaixo dela
    na tela. Essa frase saiu do texto fixo e virou esta função.

    A contagem é por rótulo e não uniforme, porque não é: sete dias em ABC
    dão A três vezes e B e C duas. A primeira versão desta função dizia "duas
    vezes" para os três e errava justamente no caso mais desequilibrado.

    Quando nada repete, a frase não existe — dizer "nenhum dia repete" seria
    ocupar espaço para informar ausência.
    """
    base = SPLIT_NOTE.get(split, "")
    rotulos = [sessao.label for sessao in sessoes]
    quantas = {r: rotulos.count(r) for r in dict.fromkeys(rotulos)}
    repetidos = {r: n for r, n in quantas.items() if n > 1}
    if not repetidos:
        return base

    # Agrupa por contagem para não repetir "duas vezes" três vezes seguidas.
    por_contagem = {}
    for rotulo, n in repetidos.items():
        por_contagem.setdefault(n, []).append(rotulo)

    trechos = []
    for n in sorted(por_contagem, reverse=True):
        letras = por_contagem[n]
        if len(letras) == 1:
            sujeito, verbo = letras[0], "cai"
        else:
            sujeito = "%s e %s" % (", ".join(letras[:-1]), letras[-1])
            verbo = "caem"
        trechos.append("%s %s %s vezes" % (sujeito, verbo, VEZES.get(n, n)))

    # A frase anterior terminava em "esses músculos recebem mais séries que os
    # outros", e era verdade: o gerador copiava a ficha inteira para cada
    # ocorrência. Deixou de ser com `distribuir_series`, e uma nota que descreve
    # comportamento que o motor não tem mais é pior que nota nenhuma.
    #
    # E A SEGUNDA VERSÃO CAIU NA MESMA ARMADILHA, uma linha abaixo do aviso.
    # Ela dizia "o volume semanal é distribuído entre as sessões", que é
    # exatamente o que `distribuir_series` fazia — a função que tinha acabado
    # de sair. Hoje cada sessão nasce com a dose CHEIA do catálogo e quem
    # segura a soma da semana é `aparar_volume_semanal`, com um teto por grupo.
    # A conclusão continuava certa; o mecanismo descrito, não.
    aviso = (
        "Na sua semana o ciclo fica %s: %s. O volume semanal de cada músculo "
        "tem um teto, então repetir o dia aumenta a frequência, não o total "
        "de séries." % ("-".join(rotulos), "; ".join(trechos))
    )
    return "%s %s" % (base, aviso) if base else aviso


def aviso_de_tempo(sessoes, prescricao, sem_relogio) -> str:
    """Uma frase quando o tempo informado apertou a ficha — ou nada.

    A pessoa precisa saber que o treino foi adaptado, senão ela compara com
    quem tem a mesma divisão e conclui que falta exercício na ficha dela.

    Duas frases diferentes porque são dois casos diferentes. Perder exercício é
    esperado e sem drama. Perder um GRUPO inteiro do dia é aritmética — um dia
    com quatro grupos precisa de pelo menos quatro exercícios, e quatro
    exercícios não cabem em quinze minutos — e aí vale dizer que aumentar o
    tempo muda o resultado, porque muda mesmo: com o catálogo de hoje, todos os
    grupos cabem a partir de 23 minutos em ABC, 35 em AB e 44 no corpo inteiro.

    A COMPARAÇÃO É CONTRA `sem_relogio`, E NÃO CONTRA O MODELO — foi o defeito
    que o QA de 09/09/2026 pegou na tela. `prescrever_semana` corta em DOIS
    lugares: `aparar_volume_semanal` tira isolador redundante por causa do teto
    semanal do grupo, e `escolher_para_o_tempo` tira o que não cabe no relógio.
    Medindo contra o modelo, o primeiro corte era creditado ao segundo, e quem
    respondeu "sem limite rígido" lia na própria ficha que ela "foi ajustada
    para caber no tempo que você informou" — um tempo que essa pessoa não
    informou, sobre um corte que o relógio não fez.

    `sem_relogio` é a MESMA prescrição com `teto=None`: o que sobra depois do
    volume e antes do relógio. Sem teto de tempo as duas são iguais e a frase
    não existe, que é a resposta certa.

    E o corte de volume continua sem frase de propósito: tirar o terceiro
    isolador de peito da segunda passagem do dia A é o programa funcionando, e
    não uma limitação imposta à pessoa. Aviso que aparece sempre vira ruído.
    """
    cortados = len(sem_relogio) - len(prescricao)

    def grupos(mapa, sessao_pk=None):
        return {
            item.exercise.muscle_group
            for (sessao_id, _), (_, item) in mapa.items()
            if sessao_pk is None or sessao_id == sessao_pk
        }

    perdidos = set()
    for sessao in sessoes:
        perdidos |= grupos(sem_relogio, sessao.pk) - grupos(prescricao, sessao.pk)

    # ÓRFÃOS DA SEMANA — o subconjunto que importa mais.
    #
    # Um grupo que sai da sexta e fica na segunda não some da vida da pessoa: a
    # letra repete e ele volta. Um grupo que o relógio tira de TODAS as sessões
    # some da semana inteira, e essa é uma adaptação de outro tamanho — ela
    # precisa ser dita com o nome do músculo, não com um "alguns grupos".
    #
    # Medido, é isto que acontece com panturrilha e abdômen em "até 30 minutos"
    # com três a cinco dias: os três compostos principais do dia de perna já
    # custam 28,2 minutos no piso de série, e o complementar mais barato leva a
    # sessão a 31,8 contra um teto de 30. Manter os dois exigiria derrubar o
    # agachamento e o stiff, que é o que o contrato proíbe — e o que a ficha
    # NÃO pode fazer é omitir a escolha.
    orfaos = perdidos - grupos(prescricao)

    if orfaos:
        verbo = "coube" if len(orfaos) == 1 else "couberam"
        return (
            "No tempo que você informou, %s não %s em nenhuma sessão desta "
            "semana. Aumentar o tempo disponível — ou treinar mais um dia — "
            "traz de volta."
            % (_lista_em_portugues(_nomes_dos_grupos(sorted(orfaos))), verbo)
        )
    if perdidos:
        verbo = "ficou" if len(perdidos) == 1 else "ficaram"
        return (
            "No tempo que você informou não cabem todos os grupos em todo dia: "
            "%s %s para outra sessão da semana."
            % (_lista_em_portugues(_nomes_dos_grupos(sorted(perdidos))), verbo)
        )
    if cortados:
        return "A ficha foi ajustada para caber no tempo que você informou."
    return ""


@transaction.atomic
def create_routine(user) -> TrainingPlan:
    """Cria a rotina ativa da pessoa, aposentando a anterior.

    A ordem dentro da transação importa pelo mesmo motivo do plano alimentar: o
    banco tem índice único parcial de uma rotina ativa por usuário, então a
    antiga precisa ser desativada antes de a nova entrar.
    """
    training_days = list(user.training_days.order_by("weekday"))
    if not training_days:
        raise NoTrainingDays("Nenhum dia de treino cadastrado.")

    split = split_for(len(training_days), _preferencia_de(user))
    templates = templates_for(split)
    if not templates:
        raise NoTrainingDays(f"A divisão {split} não está no catálogo.")

    TrainingPlan.objects.filter(user=user, is_active=True).update(is_active=False)
    plan = TrainingPlan.objects.create(
        user=user,
        is_active=True,
        split=split,
        days_per_week=len(training_days),
    )

    sessions = build_sessions(plan, training_days, templates)
    TrainingSession.objects.bulk_create(sessions)

    by_label = {template.label: template for template in templates}
    teto_semanal = teto_semanal_de(user)
    prescricao = prescrever_semana(
        sessions, by_label,
        teto=teto_de_minutos(user), teto_semanal=teto_semanal,
    )
    # A nota vem depois da prescrição porque descreve o que a prescrição fez:
    # `build_sessions` decide o ciclo e `prescrever_semana` decide o que coube
    # no tempo. Escrevê-la antes daria um texto sobre uma ficha que ainda não
    # existia.
    #
    # A SEGUNDA CHAMADA É A RÉGUA DA FRASE, e ela é de graça: `templates_for`
    # já traz `items__exercise` em cache, então rodar a prescrição sem teto de
    # tempo não custa consulta nenhuma. Ela responde "o que o relógio tirou",
    # que é a única pergunta que a frase tem o direito de responder.
    sem_relogio = prescrever_semana(
        sessions, by_label, teto=None, teto_semanal=teto_semanal,
    )
    plan.notes = " ".join(
        parte
        for parte in (
            nota_da_divisao(split, sessions),
            aviso_de_tempo(sessions, prescricao, sem_relogio),
        )
        if parte
    )
    plan.save(update_fields=["notes"])

    # O TÍTULO VEM DEPOIS DA PRESCRIÇÃO, pelo mesmo motivo que a nota vem: ele
    # descreve o que a prescrição fez. Escrevê-lo antes é o que produzia
    # "Corpo inteiro" com três exercícios.
    ajustadas = ajustar_titulos(sessions, prescricao)
    if ajustadas:
        TrainingSession.objects.bulk_update(ajustadas, ["name", "focus"])

    exercises = [
        SessionExercise(
            session_id=sessao_id,
            exercise_id=exercicio_id,
            sets=series,
            rep_min=item.rep_min,
            rep_max=item.rep_max,
            measure=item.measure,
            rest_seconds=item.rest_seconds,
            order=item.order,
        )
        for (sessao_id, exercicio_id), (series, item) in prescricao.items()
    ]
    SessionExercise.objects.bulk_create(exercises)
    return plan


def get_active_routine(user):
    return TrainingPlan.objects.filter(user=user, is_active=True).first()


def _prescricao_confere(sessoes, modelos, itens, user) -> bool:
    """A ficha gravada é a que `prescrever_semana` produziria hoje?

    Existe porque `sets` deixou de ser cópia do catálogo — é repartido entre as
    ocorrências da letra e aparado pelo tempo disponível. Antes bastava
    perguntar "esse número está no modelo?"; agora a resposta depende de quantas
    vezes a letra cai na semana desta pessoa e de quantos minutos ela tem.

    Compara contra a MESMA função que o gerador usa, e não contra uma cópia da
    regra: duas cópias da mesma conta é como as duas nasceram diferentes — e uma
    divergência de um número aqui faria toda visita à tela julgar a ficha
    obsoleta, remontando em laço e em silêncio.

    Recebe sessões e modelos já carregados. A primeira versão buscava os dois
    por conta própria e a tela de treino passou de 25 para 27 consultas, pego
    por `ScreenQueryBudgetTests`.
    """
    if not modelos:
        return False

    prescricao = prescrever_semana(
        sessoes, modelos,
        teto=teto_de_minutos(user), teto_semanal=teto_semanal_de(user),
    )
    if prescricao is None:
        return False

    gravado = {(i.session_id, i.exercise_id): i.sets for i in itens}
    esperado = {chave: series for chave, (series, _) in prescricao.items()}
    return gravado == esperado


def routine_is_current(plan, user) -> bool:
    """A rotina ativa ainda corresponde aos dias de treino de hoje?

    Compara o conjunto (dia da semana, horário, duração) — mudou qualquer coisa
    aí, a ficha é remontada. Sem o horário e a duração na comparação, trocar o
    treino da manhã para a noite deixaria a ficha dizendo o horário errado.
    """
    if plan is None or not plan.sessions.exists():
        return False
    if plan.sessions.filter(exercises__exercise__is_active=False).exists():
        # Exercício aposentado no catálogo: a ficha manda fazer o que saiu do
        # ar. Vale inclusive para ficha ajustada — aqui o gerador não está
        # desfazendo a escolha da pessoa, está avisando que o catálogo mudou
        # embaixo dela.
        return False
    # A prescrição do catálogo mudou embaixo da ficha?
    #
    # A faixa de repetições e o descanso são copiados do modelo quando a ficha
    # nasce, e ficavam congelados: mudar o descanso padrão no catálogo não
    # chegava a quem já tinha ficha. A pessoa continuava vendo "3 min" numa
    # versão do app que passou a prescrever 1:20.
    #
    # `sets` saiu desta comparação e ganhou a sua, logo abaixo, porque deixou
    # de ser cópia: `distribuir_series` divide o volume entre as ocorrências da
    # letra, então a ficha de quem treina quatro dias tem 7 séries de supino
    # onde o catálogo prescreve 14. Comparando contra o catálogo cru, TODA
    # ficha com letra repetida seria julgada obsoleta e remontada em cada
    # visita à tela — o gerador rodando em laço, silenciosamente.
    # Modelos e sessões carregados UMA vez e reaproveitados até o fim da
    # função: os dois são usados de novo pela conferência de séries e pela
    # comparação de horários lá embaixo.
    modelos = {t.label: t for t in templates_for(plan.split)}
    sessoes = sorted(plan.sessions.all(), key=lambda s: s.order)
    prescrito = {
        (i.exercise_id, i.rep_min, i.rep_max, i.rest_seconds)
        for template in modelos.values()
        for i in template.items.all()
    }
    itens = list(
        # Uma consulta, e não uma por sessão: esta função roda na entrada de
        # toda visita à tela de treino.
        SessionExercise.objects.filter(session__plan=plan).select_related("session")
    )
    na_ficha = {
        (i.exercise_id, i.rep_min, i.rep_max, i.rest_seconds) for i in itens
    }
    # Ficha ajustada à mão fica de fora: ali a divergência é a escolha da
    # pessoa, e remontar apagaria justamente o que ela mudou.
    if not plan.is_customized and not na_ficha <= prescrito:
        return False

    if not plan.is_customized and not _prescricao_confere(
        sessoes, modelos, itens, user
    ):
        return False
    if plan.is_customized:
        # Ficha ajustada à mão não é remontada pelo gerador. A pessoa trocou
        # aqueles exercícios por um motivo — joelho, equipamento ocupado,
        # preferência — e mudar o horário de terça-feira não é motivo para
        # descartar a escolha e voltar ao modelo do catálogo.
        return True
    if plan.split != split_for(user.training_days.count(), _preferencia_de(user)):
        return False

    atual = {
        (day.weekday, day.start_time, day.duration_min)
        for day in user.training_days.all()
    }
    na_ficha = {
        (session.weekday, session.start_time, session.duration_min)
        for session in sessoes
    }
    return atual == na_ficha


def treino_em_andamento(user, day=None) -> bool:
    """Já existe série anotada hoje?

    É o sinal de "estou treinando agora" que este app tem. Não existe botão de
    começar nem de terminar treino — a pessoa abre a ficha e vai anotando — e
    `ExerciseLog` é o único estado de execução que fica gravado.
    """
    day = day or timezone.localdate()
    return ExerciseLog.objects.filter(user=user, date=day).exists()


def sync_active_routine(user, day=None) -> tuple:
    """Garante uma rotina coerente com os dias de treino atuais.

    Devolve (rotina, mudou). Chamada na entrada da tela, como o plano alimentar:
    enquanto nada muda é só uma comparação de conjuntos em memória.

    Com série anotada hoje, a remontagem espera o dia virar. `create_routine`
    apaga as sessões e monta outras, e quem estava na terceira série de supino
    via a ficha trocar debaixo da mão: o exercício seguinte passava a ser outro,
    a contagem de séries mudava, e o descanso reiniciava. Os registros em si
    não se perdiam — `ExerciseLog` é por (usuário, exercício, dia) e não aponta
    para a sessão —, mas o treino que a pessoa estava executando deixava de
    existir no meio dele.

    A espera é de horas, não de dias: no dia seguinte não há registro de hoje e
    a rotina se acerta sozinha na primeira visita. E o gatilho quase sempre é a
    própria pessoa mexendo nos dias de treino — o pior momento possível para
    isso valer é justamente enquanto ela treina.
    """
    plan = get_active_routine(user)
    if routine_is_current(plan, user):
        return plan, False
    if plan is not None and treino_em_andamento(user, day):
        return plan, False
    return create_routine(user), True


def has_training_days(user) -> bool:
    return user.training_days.exists()


# --------------------------------------------------------------------------
# Registro de carga
# --------------------------------------------------------------------------

def remove_last_set(user, exercise, op_id="", day=None):
    """Desfaz a ultima serie anotada NAQUELE DIA, naquele exercicio.

    IDEMPOTENTE, e isso nao e enfeite: "desfazer" tambem entra na fila
    offline, e a fila REENVIA quando a resposta se perde no meio. Sem o
    `op_id`, um unico toque em desfazer reproduzido duas vezes apagaria DUAS
    series — a que a pessoa quis desfazer e a anterior, que ela queria manter.

    O registro do identificador mora na MESMA transacao que o `delete`, pelo
    motivo que `LogHydrationView` pagou caro para aprender: sem
    `ATOMIC_REQUESTS`, commitar o `op_id` antes do efeito faz uma falha no meio
    queimar o identificador sem apagar nada, e o reenvio e respondido com "ja
    aplicada".

    Devolve `(numero_apagado, aplicou)`. Fila vazia nao e erro: desfazer sem
    nada para desfazer e um no-op, e a tela ja decide o que dizer.
    """
    from accounts.models import SyncedOperation

    day = day or timezone.localdate()
    with transaction.atomic():
        if SyncedOperation.ja_aplicada(user, op_id):
            return None, False

        ultima = (
            ExerciseLog.objects.filter(user=user, exercise=exercise, date=day)
            .order_by("-set_number")
            .first()
        )
        if ultima is None:
            return None, True
        numero = ultima.set_number
        ultima.delete()
    return numero, True


def record_load(user, exercise, weight_kg, set_number=1, reps=None, day=None):
    """Anota a carga de uma série. Anotar de novo corrige em vez de duplicar."""
    day = day or timezone.localdate()
    log, _ = ExerciseLog.objects.update_or_create(
        user=user,
        exercise=exercise,
        date=day,
        set_number=set_number,
        defaults={"weight_kg": Decimal(str(weight_kg)), "reps": reps},
    )
    return log


def append_set(user, exercise, weight_kg, reps=None, op_id="", day=None):
    """Acrescenta UMA série ao dia. O número dela é do SERVIDOR.

    É a peça que faltava para a carga voltar à fila offline, e a diferença com
    `record_load` é de natureza: aquela recebe QUAL série gravar; esta recebe
    "fiz mais uma" e decide o número na hora de aplicar.

    Por que isso importa. O corpo que a fila guarda envelhece: quem completa
    três séries sem rede enfileira três pedidos, e todos eles nasceram na mesma
    página, com o mesmo número de série escrito no HTML. Com o número vindo do
    cliente, os três gravariam a MESMA linha — três toques, uma série. Com o
    número vindo daqui, os três viram 1, 2 e 3 na ordem em que a fila drena, e
    a fila já drena na ordem dos toques.

    A TRANSAÇÃO SOZINHA NÃO FECHA A CORRIDA, e esta frase já afirmou que
    fechava. Contar dentro dela não impede dois pedidos de lerem o mesmo
    "primeiro número livre" e tentarem gravá-lo: em READ COMMITTED nenhum dos
    dois enxerga a escrita não commitada do outro. Medido — oito chamadas
    simultâneas gravavam CINCO e perdiam três no `UniqueConstraint`.

    O que fecha é o laço: a colisão é esperada, o `IntegrityError` é retentado,
    e a releitura devolve o número seguinte. `select_for_update` não serve
    porque com o dia vazio não existe linha para travar.

    IDEMPOTÊNCIA. `ja_aplicada` grava e responde na mesma chamada, e mora
    dentro do mesmo `atomic` da escrita — porque este projeto não liga
    `ATOMIC_REQUESTS`, e registrar o identificador fora da transação faria uma
    falha no meio queimar o `op_id` sem gravar nada: o reenvio seria respondido
    com "já aplicada", a fila apagaria o item, e a série sumiria. É o mesmo
    motivo pelo qual `LogHydrationView.post` é transacional.

    Devolve `(log, criada)`. `criada=False` significa reenvio reconhecido, e
    não erro.
    """
    from accounts.models import SyncedOperation

    day = day or timezone.localdate()

    # A CORRIDA É REAL, E FOI MEDIDA. Oito `append_set` simultâneos contra o
    # banco de desenvolvimento gravaram CINCO e perderam três em
    # `IntegrityError`: duas threads leem o mesmo "primeiro número livre", as
    # duas tentam gravá-lo, e o `UniqueConstraint` — que está certo em existir
    # — derruba a segunda.
    #
    # `select_for_update` não resolve: quando o dia está vazio não há linha
    # para travar. O que resolve é aceitar a colisão e tentar de novo com o
    # conjunto de ocupadas RELIDO. Vinte tentativas porque vinte é o teto de
    # séries do dia: mais que isso não é disputa, é laço.
    ultimo_erro = None
    for _ in range(20):
        try:
            with transaction.atomic():
                if SyncedOperation.ja_aplicada(user, op_id):
                    return None, False

                # O PRIMEIRO BURACO LIVRE, e nao `maior + 1`. As duas contas
                # divergem para quem anotou fora de ordem — registrou a serie 3
                # e deixou a 1 em branco —, e a tela ONLINE ja resolve isso com
                # `_primeira_serie_livre`. Se o caminho da fila contasse
                # diferente, a mesma sequencia de toques daria resultados
                # diferentes conforme houvesse rede, que e exatamente a
                # equivalencia que esta campanha promete.
                #
                # O teto aqui e 20 (o do modelo) e nao o numero de series
                # PRESCRITAS: serie extra e coisa que acontece, e recusa-la
                # seria perder o registro de um treino que a pessoa fez.
                ocupadas = set(
                    ExerciseLog.objects.filter(
                        user=user, exercise=exercise, date=day
                    ).values_list("set_number", flat=True)
                )
                proxima = next(
                    (n for n in range(1, 21) if n not in ocupadas), 21
                )
                if proxima > 20:
                    # O modelo trava em 20 séries por exercício por dia.
                    # Estourar isso é dado corrompido ou dedo preso no botão, e
                    # recusar em silêncio seria pior: quem chama decide o que
                    # dizer na tela.
                    raise ValueError("limite de séries do dia atingido")

                log = ExerciseLog.objects.create(
                    user=user,
                    exercise=exercise,
                    date=day,
                    set_number=proxima,
                    weight_kg=Decimal(str(weight_kg)),
                    reps=reps,
                )
            return log, True
        except IntegrityError as erro:
            # A transação inteira caiu, então o registro do `op_id` caiu com
            # ela — a tentativa seguinte reabre as duas coisas juntas, que é a
            # propriedade que `AIdempotenciaCaiJuntoComOEfeitoTests` guarda.
            ultimo_erro = erro
            continue

    raise ultimo_erro


def load_history(user, exercises, day=None) -> dict:
    """Cargas de hoje e a comparação com o último treino, por exercício.

    Devolve, por exercício:

        {
          "hoje":     {série: log},            # o que preencher no formulário
          "anterior": {série: log},            # o mesmo dia de treino passado
          "melhor_hoje": Decimal|None,         # série mais pesada de hoje
          "melhor_anterior": Decimal|None,
          "delta": Decimal|None,               # subiu ou não subiu
          "data_anterior": date|None,
        }

    A comparação é entre as séries MAIS PESADAS de cada dia, e não série a série:
    a ordem em que a pessoa anota varia (às vezes a pesada é a primeira, às vezes
    a última), e o que responde "evoluí?" é o topo do dia.

    Tudo sai de uma consulta só — a tela mostra isso para vinte exercícios de
    uma vez, e vinte consultas por página é o caminho curto para a tela lenta.
    """
    day = day or timezone.localdate()
    ids = [exercise.pk for exercise in exercises]
    if not ids:
        return {}

    por_exercicio = {}
    logs = ExerciseLog.objects.filter(user=user, exercise_id__in=ids).order_by(
        "exercise_id", "-date", "set_number"
    )
    for log in logs:
        por_exercicio.setdefault(log.exercise_id, []).append(log)

    resultado = {}
    for exercise_id, registros in por_exercicio.items():
        hoje = {log.set_number: log for log in registros if log.date == day}
        anteriores = [log for log in registros if log.date < day]
        data_anterior = anteriores[0].date if anteriores else None
        anterior = {
            log.set_number: log for log in anteriores if log.date == data_anterior
        }

        melhor_hoje = max((l.weight_kg for l in hoje.values()), default=None)
        melhor_anterior = max((l.weight_kg for l in anterior.values()), default=None)
        resultado[exercise_id] = {
            "hoje": hoje,
            "anterior": anterior,
            "melhor_hoje": melhor_hoje,
            "melhor_anterior": melhor_anterior,
            "data_anterior": data_anterior,
            "delta": (melhor_hoje - melhor_anterior)
            if (melhor_hoje is not None and melhor_anterior is not None)
            else None,
        }
    return resultado


# ---------------------------------------------------------------------------
# Modo treino — "o que eu faço agora?"
# ---------------------------------------------------------------------------


@dataclass
class EstadoDoTreino:
    """Onde a pessoa está no treino de hoje.

    Tudo aqui é DERIVADO de `ExerciseLog`. Não existe tabela de sessão em
    andamento, e criar uma só para a tela ficar mais fácil seria inventar um
    estado que ninguém pode confirmar: quem fechou o app no meio da terceira
    série não avisou o servidor. O que o banco sabe é quais séries foram
    anotadas hoje, e é disso que sai a resposta.

    A consequência boa é que retomada é de graça: recarregar, voltar, fechar e
    abrir de novo recalculam a mesma coisa, porque a fonte não é a tela.
    """

    sessao: object = None
    itens: list = field(default_factory=list)
    atual: object = None
    proximo: object = None
    total_exercicios: int = 0
    exercicios_concluidos: int = 0
    total_series: int = 0
    series_feitas: int = 0
    pct: int = 0
    concluido: bool = False
    ultimo_log: object = None
    #: A prescrição a que `ultimo_log` pertence — quem recebeu a última série
    #: anotada hoje, que nem sempre é o exercício atual: fechada a última série
    #: de um exercício, a vez já passou para o seguinte e o desfazer precisa
    #: continuar apontando para o que acabou de receber a série.
    ultimo_item: object = None
    descanso_total: int = 0
    descanso_restante: int = 0
    minutos_entre_registros: int = 0

    @property
    def tem_treino(self) -> bool:
        return self.sessao is not None and bool(self.itens)

    @property
    def comecou(self) -> bool:
        return self.series_feitas > 0


def _primeira_serie_livre(feitas: dict, total: int):
    """A menor série de 1..N que ainda não foi anotada hoje.

    É a menor, e não `quantas + 1`, porque as duas divergem no caso real de
    quem anotou fora de ordem — registrou a série 3 e deixou a 1 em branco.
    Contar diria "próxima é a 2" e pularia a 1 para sempre; procurar o buraco
    devolve a 1, que é a série que de fato falta.
    """
    for numero in range(1, total + 1):
        if numero not in feitas:
            return numero
    return None


def _ultima_de_hoje(item):
    """O registro mais recente deste exercício HOJE, se houver."""
    feitas = (item.load or {}).get("hoje") or {}
    return feitas[max(feitas)] if feitas else None


def _sugestao_de_carga(item, serie):
    """Que carga já mostrar no campo, sem inventar número.

    Ordem: a série anterior DE HOJE, depois a mesma série do último treino,
    depois a mais pesada do último treino.

    Hoje vem primeiro porque é o que a pessoa está fazendo agora — ninguém
    troca de carga entre a primeira e a segunda série de propósito. Sem isso o
    campo voltava vazio a cada série e, como ele é obrigatório, o botão parava
    de funcionar até alguém digitar de novo: pego no navegador em 30/08/2026,
    com três toques em "Concluir série" que não gravaram nada.

    Nunca um chute. Sem nenhum histórico o campo fica vazio, porque preencher
    com um valor de fábrica faria a pessoa registrar, num toque só, um peso que
    ela não levantou.
    """
    if serie is None:
        return None
    de_hoje = _ultima_de_hoje(item)
    if de_hoje is not None:
        return de_hoje.weight_kg
    anterior = (item.load or {}).get("anterior") or {}
    registro = anterior.get(serie)
    if registro is not None:
        return registro.weight_kg
    return (item.load or {}).get("melhor_anterior")


def _sugestao_de_reps(item, serie):
    """As repetições da série anterior — de hoje primeiro, como na carga."""
    if serie is None:
        return None
    de_hoje = _ultima_de_hoje(item)
    if de_hoje is not None and de_hoje.reps:
        return de_hoje.reps
    registro = ((item.load or {}).get("anterior") or {}).get(serie)
    return registro.reps if registro is not None else None


def estado_do_treino(user, dia=None) -> EstadoDoTreino:
    """O treino de hoje com o ponto exato em que a pessoa parou.

    O exercício atual é o PRIMEIRO da ficha que ainda não tem todas as séries
    prescritas anotadas — não o primeiro sem nenhuma. A diferença aparece no
    caso mais comum do modo guiado: quem anotou duas de quatro séries do supino
    continua no supino, e a regra antiga (`not item.feitas`) já teria passado
    para o próximo exercício.
    """
    dia = dia or timezone.localdate()
    estado = EstadoDoTreino()

    plan = get_active_routine(user)
    if plan is None:
        return estado

    sessao = (
        TrainingSession.objects.filter(plan=plan, weekday=dia.weekday())
        .prefetch_related("exercises__exercise")
        .first()
    )
    if sessao is None:
        return estado

    itens = list(sessao.exercises.all())
    historico = load_history(user, [item.exercise for item in itens], day=dia)

    for item in itens:
        item.load = historico.get(item.exercise_id) or {}
        feitas = (item.load or {}).get("hoje") or {}
        item.series_hoje = feitas
        item.feitas = len(feitas)
        item.concluido = item.feitas >= item.sets
        item.proxima_serie = _primeira_serie_livre(feitas, item.sets)
        item.pct = (
            round(min(item.feitas, item.sets) * 100 / item.sets) if item.sets else 0
        )
        item.sugestao_carga = _sugestao_de_carga(item, item.proxima_serie)
        item.sugestao_reps = _sugestao_de_reps(item, item.proxima_serie)
        # Uma linha por série PRESCRITA, com o que foi anotado nela.
        #
        # A fileira de pastilhas da tela é isto: a carga aparece dentro da
        # pastilha, então dá para ver que a terceira série caiu de 62,5 para 60
        # sem abrir nada. Só cor diria "aconteceu" e reprovaria em daltonismo.
        item.set_rows = [
            {
                "number": numero,
                "weight": feitas[numero].weight_kg if numero in feitas else None,
                "reps": feitas[numero].reps if numero in feitas else None,
            }
            for numero in range(1, item.sets + 1)
        ]

    atual = next((item for item in itens if not item.concluido), None)
    proximo = None
    if atual is not None:
        depois = itens[itens.index(atual) + 1:]
        proximo = next((item for item in depois if not item.concluido), None)

    estado.sessao = sessao
    estado.itens = itens
    estado.atual = atual
    estado.proximo = proximo
    estado.total_exercicios = len(itens)
    estado.exercicios_concluidos = sum(1 for item in itens if item.concluido)
    estado.total_series = sum(item.sets for item in itens)
    # `min` para o percentual não passar de 100 quando alguém anota uma série a
    # mais do que a ficha prescreve — o que o modelo permite e a barra não deve
    # transformar em 110%.
    estado.series_feitas = sum(min(item.feitas, item.sets) for item in itens)
    estado.pct = (
        round(estado.series_feitas * 100 / estado.total_series)
        if estado.total_series
        else 0
    )
    estado.concluido = bool(itens) and atual is None

    # Quanto falta de descanso — contado do relógio, não de um cronômetro que
    # vive na aba.
    #
    # O instante em que a última série foi gravada está em `created_at`, então
    # "faltam 40 segundos" é subtração, não estado. É o que faz o descanso
    # sobreviver a recarregar a página, trocar de aba e voltar do bloqueio de
    # tela — um `setInterval` morreria em todos os três, e voltaria zerado
    # justamente quando a pessoa mais precisa saber se já pode puxar a próxima.
    carimbos = [
        log.created_at
        for item in itens
        for log in (item.series_hoje or {}).values()
    ]
    # Empate de `created_at` desempata pelo `pk`, e nao ao acaso.
    #
    # `auto_now_add` chama `timezone.now()` no Python, e no Windows o relogio
    # do sistema tem granularidade de milissegundos: duas series gravadas na
    # mesma janela recebem o MESMO carimbo. Pego ao semear estado de QA — a
    # quarta serie da puxada e a primeira da remada ficaram com o microssegundo
    # identico, e `max` devolveu a primeira que apareceu na iteracao, que era a
    # do exercicio anterior. Enquanto isto so alimentava o cronometro, escolher
    # errado custava alguns segundos de descanso; agora tambem decide qual
    # serie o botao "desfazer" apaga, e a escolha precisa ser a mesma sempre.
    #
    # `pk` cresce com a insercao, entao no empate ganha a linha gravada depois.
    ultimo = max(
        (
            log
            for item in itens
            for log in (item.series_hoje or {}).values()
        ),
        key=lambda log: (log.created_at, log.pk),
        default=None,
    )
    estado.ultimo_log = ultimo

    # Quanto tempo separou o primeiro registro do último.
    #
    # Sai de `created_at`, e só dele. A versão anterior desta tela pegava
    # `inicio` e `fim` de `health_export.resumo_da_sessao`, e aqueles dois NÃO
    # são medição: `inicio` é o horário cadastrado da ficha (ou 18h quando não
    # há), e `fim` é esse horário mais uma duração calculada por fórmula a
    # partir da contagem de séries. O próprio `health_export` avisa disso no
    # comentário. Pego em captura: registros separados por 1,1 minuto real
    # aparecendo na tela como "47 min".
    #
    # `carimbos` só contém registros de HOJE e dos exercícios DESTA sessão —
    # `series_hoje` é montado a partir da ficha do dia, então quem treinou
    # supino fora da ficha não entra na conta.
    #
    # Isto NÃO é "duração do treino": ninguém sabe quanto tempo a pessoa
    # passou na academia antes da primeira série ou depois da última. É o
    # intervalo entre dois instantes que o banco conhece, e o rótulo da tela
    # diz exatamente isso.
    if len(carimbos) >= 2:
        minutos = (max(carimbos) - min(carimbos)).total_seconds() / 60
        # Arredondar para baixo de 1 vira zero, e zero não vai para a tela:
        # "0 min entre o primeiro e o último registro" é ruído, não informação.
        estado.minutos_entre_registros = int(round(minutos))
    if ultimo is not None:
        prescricao = next(
            (item for item in itens if item.exercise_id == ultimo.exercise_id), None
        )
        estado.ultimo_item = prescricao
        total = prescricao.rest_seconds if prescricao else 60
        passados = (timezone.now() - ultimo.created_at).total_seconds()
        estado.descanso_total = total
        estado.descanso_restante = max(0, int(round(total - passados)))
    return estado
