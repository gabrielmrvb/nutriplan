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

from django.db import transaction
from django.utils import timezone

from accounts.models import SplitPreference

from .models import (
    SEGUNDOS_ENTRE_EXERCICIOS,
    SEGUNDOS_POR_SERIE,
    ExerciseLog,
    SessionExercise,
    Split,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplate,
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
#:   DOIS   quatro dias: peito+tríceps, costas+bíceps, pernas+ombros e um dia
#:          de complementares. É a divisão mais comum de academia.
#:   TRES   o ABC de sempre: empurrar, puxar e pernas, em três dias.
SPLIT_BY_PREFERENCE = {
    SplitPreference.UM: (
        (5, Split.ABCDE), (4, Split.ABCD), (3, Split.ABC), (2, Split.AB), (1, Split.FULL),
    ),
    SplitPreference.DOIS: (
        (4, Split.ABCD), (3, Split.ABC), (2, Split.AB), (1, Split.FULL),
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
                start_time=day.start_time,
                duration_min=day.duration_min,
                order=index,
            )
        )
    return sessions


#: A menor dose que o catálogo já considera treino.
#:
#: Não é número escolhido aqui: é o piso do que os modelos prescrevem. Nenhum
#: item de `WorkoutTemplateItem` pede menos de três séries, então "uma série"
#: é uma quantidade que o produto nunca autorizou — ela só apareceria como
#: subproduto de dividir o volume, e apareceu: 188 ocorrências na matriz de
#: 7 frequências × 4 preferências, com sete dos nove exercícios do dia A
#: caindo para uma série cada. Isso não é uma sessão de treino, é uma lista.
DOSE_MINIMA = 2


def distribuir_series(total, ocorrencias, ordem) -> list:
    """Como as `total` séries de um exercício se espalham pelas ocorrências.

    Devolve uma lista com uma posição por ocorrência da letra na semana. Zero
    significa que o exercício NÃO entra naquele dia — e quem chama não cria a
    linha, em vez de criar uma com zero séries.

    VOLUME PRIMEIRO, SESSÃO DEPOIS. O orçamento semanal de um grupo é o que a
    divisão prescreve numa passagem completa, número escrito no catálogo.
    Repetir a letra aumenta a FREQUÊNCIA; não pode multiplicar o volume junto —
    era o que acontecia, e quatro dias em ABC davam 28 séries de peito na
    semana contra as 14 prescritas. Sete dias davam 42.

    Duas decisões moram aqui, e as duas custaram uma medição:

    A dose mínima. Espalhar três séries por três ocorrências dá 1+1+1, e uma
    série é quantidade que o catálogo nunca prescreve. Então o exercício entra
    em MENOS dias, com dose cheia, em vez de entrar em todos diluído: as duas
    ocorrências do dia A passam a ter exercícios diferentes, e cada uma é uma
    sessão de verdade. A soma da semana não muda.

    O giro por `ordem`. Sem ele, todos os exercícios escolhem a mesma
    ocorrência e a primeira sessão fica cheia enquanto a última fica vazia.
    Girando pela posição do exercício na ficha, os dois dias A ficam
    equilibrados — 27 e 21 minutos com quatro dias, medidos com
    `_duracao_estimada`, contra 29 e 16 da versão sem giro.
    """
    # Em quantas ocorrências este exercício cabe sem furar a dose mínima.
    quantas = max(1, min(ocorrencias, total // DOSE_MINIMA))
    base, resto = divmod(total, quantas)

    espalhado = [0] * ocorrencias
    for i in range(quantas):
        espalhado[(i + ordem) % ocorrencias] = base + (1 if i < resto else 0)
    return espalhado


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
    orcamento = Decimal(minutos_disponiveis)
    folga = min(orcamento * FOLGA_PROPORCIONAL, FOLGA_MAXIMA_MIN)
    return (orcamento + folga) * 60


def _segundos_da_sessao(itens) -> int:
    """A mesma conta de `DurationMixin.estimated_minutes`, sobre tuplas.

    Repetida aqui, e não importada, porque o modelo calcula a partir de linhas
    já gravadas e o gerador precisa da conta ANTES de gravar — é justamente ela
    que decide o que gravar. As duas ficam presas pelo mesmo teste: o número
    que o gerador usou para decidir tem que ser o número que a tela exibe.
    """
    segundos = 0
    for sets, descanso in itens:
        segundos += sets * SEGUNDOS_POR_SERIE
        segundos += max(sets - 1, 0) * descanso
    return segundos + max(len(itens) - 1, 0) * SEGUNDOS_ENTRE_EXERCICIOS


def escolher_para_o_tempo(itens, minutos_disponiveis) -> list:
    """Quais exercícios da sessão ficam, dado o tempo que a pessoa tem.

    `itens` são tuplas (grupo_muscular, séries, descanso) NA ORDEM DA FICHA.
    Devolve os índices que ficam, em ordem.

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

    Nunca devolve lista vazia: quem informou quinze minutos ainda merece o
    exercício principal do dia.
    """
    if not itens:
        return []

    teto = _teto_em_segundos(minutos_disponiveis)
    ficam = list(range(len(itens)))

    while len(ficam) > 1:
        atual = [(itens[i][1], itens[i][2]) for i in ficam]
        if _segundos_da_sessao(atual) <= teto:
            break
        # O grupo com mais exercícios cede o último deles. Empate resolve pelo
        # que aparece mais tarde na ficha — a ordem vale dentro do bloco.
        quantos = {}
        for i in ficam:
            quantos[itens[i][0]] = quantos.get(itens[i][0], 0) + 1
        maior = max(quantos.values())
        alvo = next(
            i for i in reversed(ficam) if quantos[itens[i][0]] == maior
        )
        ficam.remove(alvo)

    return ficam


def prescrever_semana(sessoes, modelos) -> dict:
    """O que cada sessão da semana manda fazer: {(sessão, exercício): séries}.

    Uma função só, chamada pelo gerador E pela conferência, porque as duas
    precisam da MESMA resposta. Enquanto eram dois trechos parecidos, qualquer
    divergência de um número fazia `routine_is_current` julgar a ficha obsoleta
    em toda visita — o gerador remontando a ficha várias vezes por dia, em
    silêncio, sem nenhum erro na tela.

    Junta as três decisões que moldam a ficha, nesta ordem:

    1. `distribuir_series` reparte o volume semanal entre as ocorrências da
       letra, para repetir o dia aumentar a frequência e não o total;
    2. exercício sem séries nesta ocorrência não entra — ficou para a outra;
    3. `caber_no_tempo` corta a cauda até a sessão caber no tempo informado.

    A ordem importa: o tempo é a última palavra porque é o limite mais duro. O
    orçamento de volume diz o que a divisão QUER; o relógio diz o que a pessoa
    TEM. Quando os dois brigam, quem tem trinta minutos recebe menos exercício,
    não uma sessão de cinquenta.
    """
    ocorrencias = {}
    for sessao in sessoes:
        ocorrencias[sessao.label] = ocorrencias.get(sessao.label, 0) + 1

    vistas = {}
    prescricao = {}
    for sessao in sessoes:
        modelo = modelos.get(sessao.label)
        if modelo is None:
            return None
        indice = vistas.get(sessao.label, 0)
        vistas[sessao.label] = indice + 1

        candidatos = []
        for ordem, item in enumerate(modelo.items.all()):
            series = distribuir_series(
                item.sets, ocorrencias[sessao.label], ordem
            )[indice]
            if series:
                candidatos.append((item, series))

        ficam = escolher_para_o_tempo(
            [
                (item.exercise.muscle_group, series, item.rest_seconds)
                for item, series in candidatos
            ],
            sessao.duration_min,
        )
        for i in ficam:
            item, series = candidatos[i]
            prescricao[(sessao.pk, item.exercise_id)] = (series, item)
    return prescricao


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
    aviso = (
        "Na sua semana o ciclo fica %s: %s. O volume semanal é distribuído "
        "entre as sessões, então repetir o dia aumenta a frequência, não o "
        "total de séries." % ("-".join(rotulos), "; ".join(trechos))
    )
    return "%s %s" % (base, aviso) if base else aviso


def aviso_de_tempo(sessoes, modelos, prescricao) -> str:
    """Uma frase quando o tempo informado apertou a ficha — ou nada.

    A pessoa precisa saber que o treino foi adaptado, senão ela compara com
    quem tem a mesma divisão e conclui que falta exercício na ficha dela.

    Duas frases diferentes porque são dois casos diferentes. Perder exercício é
    esperado e sem drama. Perder um GRUPO inteiro do dia é aritmética — um dia
    com quatro grupos precisa de pelo menos quatro exercícios, e quatro
    exercícios não cabem em quinze minutos — e aí vale dizer que aumentar o
    tempo muda o resultado, porque muda mesmo: com o catálogo de hoje, todos os
    grupos cabem a partir de 23 minutos em ABC, 35 em AB e 44 no corpo inteiro.
    """
    cortados = 0
    grupos_perdidos = False
    for sessao in sessoes:
        modelo = modelos.get(sessao.label)
        if modelo is None:
            continue
        previstos = {
            item.exercise.muscle_group
            for item in modelo.items.all()
        }
        ficaram = [
            item
            for (sessao_id, _), (_, item) in prescricao.items()
            if sessao_id == sessao.pk
        ]
        cortados += len(modelo.items.all()) - len(ficaram)
        if previstos - {item.exercise.muscle_group for item in ficaram}:
            grupos_perdidos = True

    if grupos_perdidos:
        return (
            "No tempo que você informou não cabem todos os grupos do dia — a "
            "ficha ficou com os exercícios principais. Aumentar o tempo "
            "disponível traz os outros de volta."
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
    prescricao = prescrever_semana(sessions, by_label)
    # A nota vem depois da prescrição porque descreve o que a prescrição fez:
    # `build_sessions` decide o ciclo e `prescrever_semana` decide o que coube
    # no tempo. Escrevê-la antes daria um texto sobre uma ficha que ainda não
    # existia.
    plan.notes = " ".join(
        parte
        for parte in (
            nota_da_divisao(split, sessions),
            aviso_de_tempo(sessions, by_label, prescricao),
        )
        if parte
    )
    plan.save(update_fields=["notes"])
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


def _prescricao_confere(sessoes, modelos, itens) -> bool:
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

    prescricao = prescrever_semana(sessoes, modelos)
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

    if not plan.is_customized and not _prescricao_confere(sessoes, modelos, itens):
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
