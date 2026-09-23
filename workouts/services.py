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
import copy
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
import hashlib
from pathlib import Path

from django.db import IntegrityError, transaction
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
)
from django.utils import timezone

from accounts.models import (
    TETO_POR_DURACAO,
    TETO_POR_EXPERIENCIA,
    DuracaoTreino,
    Experiencia,
    SplitPreference,
)

from . import adaptacao
from .models import (
    SEGUNDOS_ENTRE_EXERCICIOS,
    SEGUNDOS_POR_SERIE,
    Equipment,
    Exercise,
    ExerciseLog,
    Measure,
    MuscleGroup,
    familia_de_opcoes,
    SessionExercise,
    Split,
    TrainingPlan,
    TrainingSession,
    WorkoutTemplate,
    IDADE_CAUTELOSA,
    instrucao_de_esforco,
    segundos_da_sessao,
    EscolhaDeTreino,
    TrocaDeExercicio,
    VersaoDoTreino,
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
# O preço dessa escolha foi medido quando a tabela nasceu: quatro dias viravam
# A-B-C-A e o peito saía com 28 séries na semana. Hoje isso NÃO acontece —
# `prescrever_semana` monta a dose cheia e `aparar_volume_semanal` remove
# isoladores até nenhum grupo passar de `TETO_SEMANAL_POR_GRUPO` séries
# efetivas (12/20/24 pela experiência), com as três travas do CLAUDE.md.
# Esta tabela é só o caminho de quem tem plano anterior à pergunta de
# preferência existir: `split_for` lê `SPLIT_BY_PREFERENCE` quando há
# preferência, e é lá que ABC2, ABCD e ABCDE moram.
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
    # ORGANIZAÇÃO, não fisiologia. A versão anterior dizia que peito e costas
    # "são antagonistas, e treinar um cansa o outro pela metade" — a
    # meta-análise de supersets agonista-antagonista (Zhang 2025) mede o
    # oposto, e o próprio `ab A` treina supino e remada juntos. A frase
    # afirma o que a divisão FAZ: separar os movimentos por dia.
    Split.ABC: (
        "A divisão clássica por sinergia: empurrar num dia, puxar no outro, "
        "pernas no terceiro. Cada movimento tem o dia dele, e os músculos que "
        "ajudam — tríceps no empurrar, bíceps no puxar — treinam junto."
    ),
    # O ABCDE de hoje é UM grupo por dia. A nota descrevia o modelo antigo
    # (ABCD mais um dia "para o que sobra"), que o catálogo não tem mais.
    Split.ABCDE: (
        "Cinco treinos, um grupo por dia: peito, costas, pernas, ombros e "
        "braços. Cada músculo recebe a sessão inteira e uma semana de "
        "descanso até voltar — é a divisão de quem quer volume alto num dia "
        "só e tem cinco dias para isso."
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

    Hoje isso responde `False` para 0, 1 e 2 dias e `True` de 3 em diante
    (medido em 15/09/2026; foi "de 4 em diante" até `abc2` caber em três
    dias): com dois dias toda preferência vira superior/inferior, porque a
    divisão não pode inventar dias que a semana não tem. Perguntar ali é pedir
    uma escolha que o app vai ignorar — e o onboarding fica mais longo em
    troca de nada. `accounts.views.MINIMO_DE_DIAS_PARA_DIVISAO` lê daqui.
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


def inicio_do_ciclo_de(hoje, dias):
    """A posição zero do ciclo: o primeiro dia de treino da SEMANA em que o
    plano nasce (segunda a domingo). Assim a primeira semana é exatamente a
    que as linhas guardam (A na segunda, B na terça...), e a rotação começa
    a valer da segunda semana em diante — quem entra na quarta faz o treino
    de quarta, como sempre fez, e na semana seguinte o ciclo continua."""
    segunda = hoje - timedelta(days=hoje.weekday())
    return segunda + timedelta(days=min(dias))


def letras_do_ciclo(sessoes) -> list:
    """As letras da divisão na ordem do ciclo (A, B, C), sem repetição."""
    letras = []
    for sessao in sorted(sessoes, key=lambda s: s.order):
        if sessao.label not in letras:
            letras.append(sessao.label)
    return letras


def dias_de_treino_de(sessoes) -> list:
    """Os dias da semana do plano, em ordem (o retrato que as linhas guardam)."""
    return sorted({s.weekday for s in sessoes})


def posicao_no_ciclo(inicio, dia, dias) -> int:
    """Quantos dias de treino há entre `inicio` (posição zero) e `dia`,
    contando pelo CALENDÁRIO — dia de treino que a pessoa pulou conta do
    mesmo jeito, como o quadro da academia. Data anterior ao início dá
    posição negativa, e a sequência continua coerente para trás."""
    delta = (dia - inicio).days
    semanas, resto = divmod(delta, 7)
    marcados = set(dias)
    parcial = sum(1 for k in range(resto) if (inicio.weekday() + k) % 7 in marcados)
    return semanas * len(dias) + parcial


def ciclo_roda(plan) -> bool:
    """O plano tem rotação contínua? Só o nascido com `inicio_do_ciclo` e
    NÃO ajustado à mão: a ficha ajustada pode ter A1 ≠ A2 de verdade (a
    pessoa mexeu na ocorrência de quinta), e "a linha da letra" deixaria de
    dizer o que ela faz na quinta. Ajustada, a ficha fica presa ao dia da
    semana — como o plano de antes da rotação."""
    return plan is not None and plan.inicio_do_ciclo is not None and not plan.is_customized


def letra_do_dia(plan, dia, sessoes=None):
    """A letra que cai em `dia`, ou `None` se não é dia de treino.

    Plano com `inicio_do_ciclo`: a letra da POSIÇÃO do dia no ciclo
    (rotação contínua). Plano antigo: a letra presa ao dia da semana.
    """
    if plan is None:
        return None
    sessoes = list(sessoes if sessoes is not None else plan.sessions.all())
    dias = dias_de_treino_de(sessoes)
    if dia.weekday() not in dias:
        return None
    if not ciclo_roda(plan):
        return next(s.label for s in sessoes if s.weekday == dia.weekday())
    letras = letras_do_ciclo(sessoes)
    return letras[posicao_no_ciclo(plan.inicio_do_ciclo, dia, dias) % len(letras)]


def _no_dia(sessao, molde, dia=None):
    """Uma cópia em memória da sessão da LETRA vestindo o dia, o horário e a
    duração do dia da semana `molde` — o que a tela e o AGORA leem. O
    `pk` é o da letra (a escolha e a ficha apontam para ela); o cache dos
    exercícios é compartilhado, então nada é consultado de novo."""
    if sessao.pk == molde.pk:
        vestida = sessao
    else:
        vestida = copy.copy(sessao)
        vestida.weekday = molde.weekday
        vestida.start_time = molde.start_time
        vestida.duration_min = molde.duration_min
        vestida.order = molde.order
    vestida.data = dia
    return vestida


def sessao_do_dia(plan, dia, sessoes=None):
    """A sessão de `dia` — a linha da LETRA daquele dia, vestindo horário e
    duração do dia da semana —, ou `None` em dia sem treino."""
    if plan is None:
        return None
    sessoes = list(sessoes if sessoes is not None else plan.sessions.all())
    molde = next((s for s in sessoes if s.weekday == dia.weekday()), None)
    if molde is None:
        return None
    if not ciclo_roda(plan):
        molde.data = dia
        return molde
    letra = letra_do_dia(plan, dia, sessoes)
    da_letra = next(s for s in sorted(sessoes, key=lambda s: s.order) if s.label == letra)
    return _no_dia(da_letra, molde, dia)


def sessoes_da_semana(plan, hoje, sessoes=None) -> list:
    """As sessões da semana que INTERESSA em `hoje` (segunda a domingo), uma
    por dia de treino, na ordem dos dias: as próprias linhas no plano antigo,
    e no plano com rotação a letra de cada dia vestindo o dia (`_no_dia`) — é
    a lista que o painel, a ficha e a leitura do exercício desenham.

    A semana que interessa é a de hoje enquanto ela ainda tem dia de treino
    de hoje em diante; passado o último (sábado e domingo em quem treina de
    segunda a sexta), é a semana que VEM. Auditoria em produção de 20/09/2026,
    um domingo: o cartão "Próximo treino" dizia "C · amanhã" (a letra da
    rotação, certa) e a faixa e os cartões logo abaixo diziam "A ·
    Segunda-feira" — a semana que acabou, com a letra velha. Duas verdades na
    mesma tela sobre a mesma segunda-feira."""
    sessoes = list(sessoes if sessoes is not None else plan.sessions.all())
    if not ciclo_roda(plan):
        return sorted(sessoes, key=lambda s: s.order)
    segunda = hoje - timedelta(days=hoje.weekday())
    if sessoes and all(molde.weekday < hoje.weekday() for molde in sessoes):
        segunda += timedelta(days=7)
    semana = []
    for molde in sorted(sessoes, key=lambda s: s.order):
        dia = segunda + timedelta(days=molde.weekday)
        semana.append(sessao_do_dia(plan, dia, sessoes))
    return semana


def ocorrencias_das_letras(sessoes) -> dict:
    """Quantas vezes cada letra cai numa semana — a PIOR semana do ciclo.

    Plano antigo: a contagem das linhas (A B C A B: A=2, B=2, C=1). Com a
    rotação toda letra cai o máximo em alguma semana (C A B C A tem C
    duas vezes), então toda letra recebe o máximo: é a semana que o teto
    semanal e o número de opções têm de comportar.
    """
    contagem = {}
    for sessao in sessoes:
        contagem[sessao.label] = contagem.get(sessao.label, 0) + 1
    plan = sessoes[0].plan if sessoes else None
    if ciclo_roda(plan) and contagem:
        maximo = max(contagem.values())
        return {letra: maximo for letra in contagem}
    return contagem


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
#: secundária pela metade — para um grupo que cai UMA vez na semana, no
#: intermediário. Desde 17/09/2026 vem do `TREINO.md` (tabela B), e o grupo
#: que cai duas ou três vezes tem teto maior (`tetos_da_semana`). O número
#: é um TETO, não uma meta: ficha que já cabe embaixo dele não é tocada.
TETO_SEMANAL_POR_GRUPO = TETO_POR_EXPERIENCIA[Experiencia.INTERMEDIARIO]

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


def marcar_quem_abre_o_grupo(itens, main_groups) -> None:
    """Escreve `abre_o_grupo` em cada item: o PRIMEIRO composto de cada grupo
    anunciado, na ordem da ficha — e só ele.

    É o selo "Principal" da ficha (17/09/2026, pedido do dono): até então o
    selo marcava todo `is_compound`, e com quatro pressões de peito por
    opção "Principal" aparecia em cinco de sete linhas — não orientava mais
    ninguém por onde começar. Não é `prioridades_da_sessao`: aquela régua é
    do APARO (o composto de maior dose), esta é da LEITURA (o que abre o
    grupo). Complementar não anunciado não recebe selo, mesmo composto.
    """
    anunciados = set(main_groups or ())
    ja_abriu = set()
    for item in itens:
        grupo = item.exercise.muscle_group
        item.abre_o_grupo = (
            item.exercise.is_compound
            and grupo not in ja_abriu
            and (not anunciados or grupo in anunciados)
        )
        if item.abre_o_grupo:
            ja_abriu.add(grupo)


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
    #
    # E o grupo aqui é a FAMÍLIA (`models.FAMILIA_DE_OPCOES`): a cadeia
    # posterior tem UM principal por sessão — stiff ou elevação pélvica —,
    # como sempre teve. Com glúteo e posterior contando separados, a versão
    # da letra que ficava com a elevação pélvica ganhava um segundo principal
    # (o bom dia), e em Rápido três principais de três séries são os 30
    # minutos inteiros: o "Inferior" de dois dias perdia a segunda opção
    # (medido em 21/09/2026).
    melhor_do_grupo = {}
    for posicao, item in enumerate(itens):
        if not item.exercise.is_compound:
            continue
        grupo = familia_de_opcoes(item.exercise.muscle_group)
        atual = melhor_do_grupo.get(grupo)
        if atual is None or item.sets > itens[atual].sets:
            melhor_do_grupo[grupo] = posicao

    graus = []
    for posicao, item in enumerate(itens):
        if not item.exercise.is_compound:
            graus.append(ISOLADOR)
        elif melhor_do_grupo.get(familia_de_opcoes(item.exercise.muscle_group)) == posicao:
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
      2. redução de série, do degrau mais BAIXO para o mais alto, até o piso;
      3. o ÚLTIMO exercício de um grupo complementar;
      4. excedente do anunciado — do degrau mais baixo, do grupo mais cheio;
      5. o último exercício de um grupo anunciado, e aí o título é reescrito.

    E no fim, a DEVOLUÇÃO: série volta enquanto couber, na ordem inversa.

    A PRIORIDADE QUE ESTA ORDEM CODIFICA, e ela levou três tentativas:

        grupos principais e variedade contratada
          -> movimentos compostos
            -> redução equilibrada de séries
              -> complementares
                -> aviso explícito do que não coube

    AS TRÊS ORDENS ANTERIORES, medidas e reprovadas, cada uma por quebrar um
    contrato diferente:

      - **sem a distinção anunciado/complementar**, o rodízio por grupo mais
        cheio derrubava o bíceps: "Costas e bíceps" a 60 minutos saía com
        bíceps=1 e trapézio=1, porque bíceps tinha três isoladores e o
        trapézio, com um só, estava travado. A ficha protegia o que o título
        não promete;
      - **com o complementar cedendo INTEIRO na primeira camada**, panturrilha
        e abdômen ficavam órfãos da semana inteira em três, quatro e cinco
        dias: a letra C cai uma vez só nessas frequências, e o que saía dela
        não voltava em lugar nenhum;
      - **com a remoção do excedente ANUNCIADO antes da redução de série**,
        saíam DOIS exercícios de bíceps para caber trapézio e antebraço, e a
        semana fechava com bíceps=1 contra os três do contrato. Encaixar
        complementar às custas da variedade contratada troca um defeito por
        outro, e foi o que esta ordem corrigiu por último.

    Medido em três preferências × sete frequências, a 45-60 minutos: quatro
    peitos, quatro costas, três tríceps e três bíceps distintos por semana em
    TODAS elas, com o supino reto em quatro séries, e nenhuma sessão passando
    do teto.

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

    # A FAMÍLIA (`models.FAMILIA_DE_OPCOES`): glúteo conta como posterior
    # aqui — no "grupo mais cheio" e no anunciado — e só aqui e nas opções.
    itens = [(familia_de_opcoes(grupo), *resto) for grupo, *resto in itens]
    anunciados = {familia_de_opcoes(g) for g in (principais or ())}

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
        # abdominal, o segundo antebraço. O grupo continua na sessão, e nenhum
        # exercício de grupo anunciado foi tocado para isso.
        excedente = [
            i for i in ficam
            if _e_complementar(itens[i][0]) and vivos_por_grupo[itens[i][0]] > 1
        ]
        if excedente:
            ficam.remove(
                _quem_cede(_do_degrau_mais_baixo(excedente), itens, vivos_por_grupo)
            )
            continue

        # CAMADA 2 — REDUZIR SÉRIE, e ela vem ANTES de qualquer remoção de
        # exercício anunciado.
        #
        # É a correção de 10/09/2026, e ela desfaz uma troca que eu tinha feito
        # errado. A ordem anterior removia o excedente ANUNCIADO nesta altura, e
        # o preço estava medido: no dia de puxar com três ou quatro dias, saíam
        # DOIS exercícios de bíceps para caber trapézio e antebraço, e a semana
        # fechava com bíceps=1 contra os três que o contrato pede. Encaixar
        # complementar às custas da variedade contratada é o contrário da
        # prioridade — grupos principais e variedade vêm primeiro.
        #
        # A REDUÇÃO É GRADUADA, e sem isso ela produz o outro defeito. Cedendo
        # sempre "quem tem mais série", o primeiro a cair é o composto
        # PRINCIPAL, que é justamente quem tem quatro — o agachamento perdia
        # série antes da rosca. Aqui cede o degrau mais baixo primeiro:
        # isolador, depois composto acessório, e o principal por último.
        #
        # Medido no dia de puxar a 60 minutos com três dias: quatro costas,
        # três bíceps, trapézio e antebraço cabem em 60 exatos, com as roscas
        # em duas séries e as costas intactas.
        reduziveis = [
            i for i in ficam
            if series[i] > (PISO_COMPOSTO if itens[i][3] >= ACESSORIO else 2)
        ]
        if reduziveis:
            alvo = min(reduziveis, key=lambda i: (itens[i][3], -series[i], i))
            series[alvo] -= 1
            continue

        # CAMADA 3 — O ÚLTIMO COMPLEMENTAR SAI.
        #
        # Só aqui, com toda série já no piso. O grupo complementar deixa a
        # sessão; ele volta na outra passagem da letra quando ela existe, e
        # quando não existe some da semana — e aí é `aviso_de_tempo` que diz
        # isso com o nome do músculo, em vez de a ficha omitir.
        ultimos = [i for i in ficam if _e_complementar(itens[i][0])]
        if ultimos:
            ficam.remove(
                _quem_cede(_do_degrau_mais_baixo(ultimos), itens, vivos_por_grupo)
            )
            continue

        # CAMADA 4 — O EXCEDENTE DO ANUNCIADO.
        #
        # Do degrau mais baixo e do grupo mais CHEIO da sessão. Chegando aqui,
        # já não há complementar nenhum na ficha e toda série está no piso: o
        # que sobra é escolher qual músculo anunciado perde variedade.
        excedente = [i for i in ficam if vivos_por_grupo[itens[i][0]] > 1]
        if excedente:
            ficam.remove(
                _quem_cede(_do_degrau_mais_baixo(excedente), itens, vivos_por_grupo)
            )
            continue

        # CAMADA 5 — ÚLTIMO RECURSO: um grupo ANUNCIADO cai inteiro.
        #
        # Medido, `ab A` tem oito exercícios em SETE grupos, e sete exercícios
        # no piso de série ainda dão 42 minutos contra um teto de 30. Aqui o
        # relógio ganha, porque ele é o limite mais duro e a pessoa combinou
        # trinta. `titulo_honesto` tira o grupo do nome da sessão.
        ficam.remove(
            _quem_cede(_do_degrau_mais_baixo(list(ficam)), itens, vivos_por_grupo)
        )

    # E DEVOLVE SÉRIE ENQUANTO COUBER.
    #
    # A redução aconteceu para a sessão caber, e DEPOIS dela um exercício pode
    # ter saído — e o que saiu abriu espaço que ninguém reocupou. Sem esta
    # passada a ficha paga o preço da concessão sem a razão dela: medido, o dia
    # de puxar a 30 minutos terminava com 24 minutos e todas as séries no piso,
    # desperdiçando seis minutos do que a pessoa tinha.
    #
    # Devolve na ordem INVERSA da que tirou — principal, acessório, isolador —,
    # e confere a cada devolução, porque o teto continua duro. Nunca passa do
    # que o catálogo pede: `series[i] >= itens[i][1]` é o limite de cima.
    houve_devolucao = True
    while houve_devolucao:
        houve_devolucao = False
        for i in sorted(ficam, key=lambda i: (-itens[i][3], i)):
            if series[i] >= itens[i][1]:
                continue
            series[i] += 1
            cabe = _segundos_da_sessao(
                [
                    (series[j], itens[j][2], itens[j][3] >= ACESSORIO)
                    for j in ficam
                ]
            ) <= teto
            if cabe:
                houve_devolucao = True
            else:
                series[i] -= 1

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


def volume_da_semana(plan) -> dict:
    """Séries EFETIVAS por grupo na semana deste plano, no PIOR CASO.

    Uma opção por ocorrência da letra — a mais pesada no grupo —, nunca as
    duas somadas: ninguém faz os dois treinos no mesmo dia. É a conta que
    `aparar_opcoes` fecha no teto, e é a que todo teste de teto semanal deve
    usar; somar `session.exercises.all()` conta um treino que não existe.
    """
    from . import opcoes as motor_de_opcoes

    por_letra = {}
    sessoes = list(plan.sessions.all().prefetch_related("exercises__exercise"))
    for sessao in sessoes:
        if sessao.label not in por_letra:
            por_letra[sessao.label] = [
                [(item, item.sets, 0) for item in sessao.da_opcao(k)] for k in sessao.opcoes
            ]
    return motor_de_opcoes.volume_semanal_pior_caso(por_letra, ocorrencias_das_letras(sessoes))


def nivel_de(user) -> str:
    """A experiência declarada, ou o intermediário para quem não respondeu —
    e para o perfil ausente, que é quem monta ficha antes de o perfil
    existir. É o mesmo critério de `teto_de_minutos`."""
    perfil = getattr(user, "profile", None)
    return getattr(perfil, "experiencia", None) or Experiencia.INTERMEDIARIO


def duracao_de(user) -> str:
    """A faixa de duração declarada (`DuracaoTreino`), ou vazio."""
    perfil = getattr(user, "profile", None)
    return getattr(perfil, "duracao_treino", None) or ""


def equipamento_de(user) -> str:
    """O perfil de equipamento (`accounts.models.Equipamento`), ou "completa"
    — o padrão do campo e a verdade de quem monta ficha sem perfil."""
    from . import doutrina

    perfil = getattr(user, "profile", None)
    return getattr(perfil, "equipamento", None) or doutrina.COMPLETA


def permitidos_de(user) -> frozenset:
    """O que o perfil de equipamento da pessoa pode usar (chaves de
    `Exercise.equipment`), pelo mapa do `TREINO.md`."""
    from . import doutrina

    return doutrina.equipamentos_de(equipamento_de(user))


#: O equipamento mais PRÓXIMO do item trocado vem primeiro (17/09/2026): o
#: supino reto com barra vira supino com halteres antes de virar flexão, e
#: a máquina vira polia antes de virar halter. Dentro do mesmo degrau, o
#: nome desempata — a escolha precisa ser determinística, porque a
#: conferência refaz a conta do gerador.
PROXIMIDADE_DE_EQUIPAMENTO = {
    Equipment.BARBELL: (Equipment.DUMBBELL, Equipment.MACHINE, Equipment.CABLE, Equipment.BODYWEIGHT),
    Equipment.DUMBBELL: (Equipment.BARBELL, Equipment.MACHINE, Equipment.CABLE, Equipment.BODYWEIGHT),
    Equipment.MACHINE: (Equipment.CABLE, Equipment.DUMBBELL, Equipment.BARBELL, Equipment.BODYWEIGHT),
    Equipment.CABLE: (Equipment.MACHINE, Equipment.DUMBBELL, Equipment.BARBELL, Equipment.BODYWEIGHT),
    Equipment.BODYWEIGHT: (Equipment.DUMBBELL, Equipment.CABLE, Equipment.MACHINE, Equipment.BARBELL),
}


def _distancia_de_equipamento(de, para) -> int:
    ordem = PROXIMIDADE_DE_EQUIPAMENTO.get(de, ())
    return ordem.index(para) if para in ordem else len(ordem)


def trocas_de(user) -> dict:
    """{id do original: Exercise substituto} — as trocas da pessoa, UMA consulta."""
    return {
        troca.original_id: troca.substituto
        for troca in TrocaDeExercicio.objects.filter(user=user).select_related("substituto")
    }


def aplicar_trocas(user, sessoes, trocas=None) -> dict:
    """Veste as linhas com as trocas da pessoa, EM MEMÓRIA (17/09/2026):
    o item cujo exercício foi trocado passa a apontar para o substituto —
    `item.exercise` (e `exercise_id`) — e guarda o de origem em
    `item.original`; séries, faixa, descanso e ordem não mudam. Nada é
    gravado: a ficha continua retrato, e a conferência do catálogo
    (`_prescricao_bate`) lê as linhas cruas. Chamada UMA vez por tela,
    logo depois de carregar as linhas do plano — o painel, a ficha, a
    execução e a leitura passam pelo mesmo caminho, então contagem de
    séries, "Principal" e histórico enxergam o exercício FEITO.

    Devolve o mapa (para quem precisa saber se houve troca) e custa a
    consulta de `trocas_de` quando não a recebe pronta."""
    if trocas is None:
        trocas = trocas_de(user)
    if trocas:
        for sessao in sessoes:
            for item in sessao.exercises.all():
                substituto = trocas.get(item.exercise_id)
                if substituto is not None and getattr(item, "original", None) is None:
                    item.original = item.exercise
                    item.exercise = substituto
    return trocas


def _linha_do_exercicio(user, sessao_pk, opcao, exercise_id):
    """As linhas da opção do dia que RESPONDEM por `exercise_id`: a linha
    dele, ou a linha do original que a pessoa trocou por ele
    (`TrocaDeExercicio`), na MESMA consulta — o orçamento do POST da série
    é de 20, e uma consulta a mais pelas trocas o estourava."""
    return SessionExercise.objects.filter(session_id=sessao_pk, opcao=opcao).filter(
        Q(exercise_id=exercise_id)
        | Q(exercise__trocas_como_original__user=user, exercise__trocas_como_original__substituto_id=exercise_id)
    )


def alternativas_de(user, exercicio, fora=(), permitidos=None) -> list:
    """"Outras formas": os exercícios ATIVOS do mesmo `padrao` e grupo,
    dentro do que o perfil tem para treinar (`permitidos_de`), fora do
    próprio e dos que já estão na sessão (`fora`, ids). O equipamento mais
    próximo do atual vem primeiro (`PROXIMIDADE_DE_EQUIPAMENTO`), o nome
    desempata. Uma consulta (`permitidos` já calculado poupa a do perfil)."""
    if permitidos is None:
        permitidos = permitidos_de(user)
    excluidos = {exercicio.pk, *fora}
    candidatos = Exercise.objects.filter(
        is_active=True, padrao=exercicio.padrao, muscle_group=exercicio.muscle_group,
        equipment__in=list(permitidos),
    ).exclude(pk__in=excluidos)
    return sorted(candidatos, key=lambda e: (_distancia_de_equipamento(exercicio.equipment, e.equipment), e.name, e.id))


def escada_de(exercicio) -> list:
    """A ESCADA DE PROGRESSÃO do movimento (decisão 1 da avaliação de UX,
    20/09/2026): os exercícios ATIVOS do mesmo `progressao["movimento"]`, do
    mais fácil ao mais difícil (por `nivel`), cada um com `atual` (é o que a
    pessoa está vendo) e `relativo` ("mais_facil"/"aqui"/"mais_dificil"). É o
    que deixa quem faz peso do corpo trocar por uma versão que consegue fazer,
    ou subir quando a atual ficar fácil.

    Vazio quando o exercício não pertence a uma escada — a maioria dos que
    usam aparelho, onde a progressão é a carga, e as escadas de um degrau só.
    Uma consulta."""
    movimento = (exercicio.progressao or {}).get("movimento")
    if not movimento:
        return []
    degraus = sorted(
        Exercise.objects.filter(is_active=True, progressao__movimento=movimento),
        key=lambda e: ((e.progressao or {}).get("nivel", 0), e.name),
    )
    if len(degraus) < 2:
        return []
    nivel_atual = (exercicio.progressao or {}).get("nivel", 0)
    escada = []
    for e in degraus:
        nivel = (e.progressao or {}).get("nivel", 0)
        if e.pk == exercicio.pk:
            relativo = "aqui"
        elif nivel < nivel_atual:
            relativo = "mais_facil"
        else:
            relativo = "mais_dificil"
        escada.append({"exercicio": e, "atual": e.pk == exercicio.pk, "relativo": relativo})
    return escada


def contar_outras_formas(user, itens, permitidos=None) -> None:
    """Escreve `item.outras_formas` (quantas alternativas o exercício tem
    no equipamento da pessoa, fora dos que já estão nesta lista) em cada
    item — UMA consulta para a ficha inteira, para a linha só anunciar
    "outras formas" quando a porta leva a alguma."""
    if permitidos is None:
        permitidos = permitidos_de(user)
    na_lista = {item.exercise_id for item in itens}
    por_padrao = {}
    for pk, padrao, grupo in Exercise.objects.filter(
        is_active=True, equipment__in=list(permitidos),
    ).values_list("pk", "padrao", "muscle_group"):
        por_padrao.setdefault((padrao, grupo), set()).add(pk)
    for item in itens:
        exercicio = item.exercise
        candidatos = por_padrao.get((exercicio.padrao, exercicio.muscle_group), set())
        item.outras_formas = len(candidatos - na_lista - {exercicio.pk})


class TrocaInvalida(ValueError):
    """O POST pediu uma troca que a ficha não comporta."""


def registrar_troca(user, original, substituto):
    """Cria ou ATUALIZA a troca (estado absoluto): `original` tem de estar
    na ficha ativa da pessoa, `substituto` tem de ser uma das alternativas
    dele (mesmo padrão e grupo, dentro do equipamento, fora da sessão).
    Não toca em `SessionExercise` nem em `customized_at`."""
    plan = get_active_routine(user)
    if plan is None or not SessionExercise.objects.filter(session__plan=plan, exercise=original).exists():
        raise TrocaInvalida("Esse exercício não está na sua ficha.")
    # Fora do que já está na MESMA LISTA (sessão + opção) em que o original
    # cai — a régua da ficha e da leitura.
    listas = SessionExercise.objects.filter(session__plan=plan, exercise=original).values_list("session_id", "opcao")
    filtro = Q()
    for sessao_id, opcao in listas:
        filtro |= Q(session_id=sessao_id, opcao=opcao)
    na_sessao = set(SessionExercise.objects.filter(filtro).values_list("exercise_id", flat=True))
    if substituto.pk not in {e.pk for e in alternativas_de(user, original, na_sessao)}:
        raise TrocaInvalida("Esse exercício não é uma forma deste movimento no seu equipamento.")
    troca, _ = TrocaDeExercicio.objects.update_or_create(
        user=user, original=original, defaults={"substituto": substituto},
    )
    return troca


def desfazer_troca(user, original) -> bool:
    """Volta ao original; idempotente (desfazer o que não existe é nada)."""
    apagadas, _ = TrocaDeExercicio.objects.filter(user=user, original=original).delete()
    return bool(apagadas)


def catalogo_permitido(permitidos):
    """Os exercícios ativos que o perfil pode usar, em ordem determinística —
    UMA consulta, compartilhada por todos os modelos de uma prescrição. `None`
    quando o perfil é o catálogo inteiro (nada a substituir, nada a consultar)."""
    if permitidos is None or frozenset(Equipment.values) <= frozenset(permitidos):
        return None
    return list(Exercise.objects.filter(is_active=True, equipment__in=list(permitidos)).order_by("name", "id"))


def substituir_por_equipamento(itens, permitidos, catalogo=None) -> list:
    """Os itens de um modelo com o que está FORA do perfil de equipamento
    trocado por exercício ativo do MESMO `padrao` e do mesmo grupo, dentro do
    perfil, que ainda não esteja no modelo — com a dose do item trocado
    (séries, repetições, descanso, ordem). Sem substituto, o item SAI.

    Substituição, e não filtro (17/09/2026): a prescrição copia modelos
    curados de `splits.json`, e tirar sem repor abria buraco no modelo —
    medido em 10/09, oito modelos perdiam grupo em "casa com halteres" e
    `abcde-C` ficava vazio. Trocar pelo mesmo padrão é o que mantém a
    régua de `equivalentes` (mesmos padrões compostos nos grupos anunciados)
    satisfazível com o catálogo restrito.

    `permitidos=None` ou o conjunto inteiro devolve os itens como estão, sem
    consulta: o perfil "completa" custa zero. Com perfil restrito e ao menos
    um item fora, UMA consulta ao catálogo (ou o `catalogo` já carregado).
    Entre candidatos, o equipamento mais PRÓXIMO do trocado vence
    (`PROXIMIDADE_DE_EQUIPAMENTO`) e o nome desempata — determinístico,
    porque a conferência (`_prescricao_confere`) refaz esta conta.
    """
    itens = list(itens)
    if permitidos is None or frozenset(Equipment.values) <= frozenset(permitidos):
        return itens
    if all(item.exercise.equipment in permitidos for item in itens):
        return itens
    if catalogo is None:
        catalogo = catalogo_permitido(permitidos)
    usados = {item.exercise_id for item in itens}
    resultado = []
    for item in itens:
        if item.exercise.equipment in permitidos:
            resultado.append(item)
            continue
        candidatos = [
            e for e in catalogo
            if e.padrao == item.exercise.padrao
            and e.muscle_group == item.exercise.muscle_group
            and e.id not in usados
        ]
        if not candidatos:
            # Sem substituto no grupo, a FAMÍLIA (`models.FAMILIA_DE_OPCOES`)
            # responde: um terceiro stiff sem barra vira ponte de glúteo, que
            # é o mesmo padrão (extensão de quadril) — como era antes de
            # 21/09/2026, quando os dois eram um grupo só. O grupo certo vem
            # PRIMEIRO: o stiff troca por stiff enquanto houver.
            candidatos = [
                e for e in catalogo
                if e.padrao == item.exercise.padrao
                and familia_de_opcoes(e.muscle_group) == familia_de_opcoes(item.exercise.muscle_group)
                and e.id not in usados
            ]
        substituto = min(
            candidatos,
            key=lambda e: (_distancia_de_equipamento(item.exercise.equipment, e.equipment), e.name, e.id),
            default=None,
        )
        if substituto is None:
            continue
        usados.add(substituto.id)
        copia = copy.copy(item)
        copia.pk = None
        copia.exercise = substituto
        resultado.append(copia)
    return resultado


#: Até que degrau da escada um iniciante recebe de saída. As escadas do
#: peso do corpo vão de 1 (mais fácil) a 5 (`Exercise.progressao`); 3 é a
#: versão "padrão" do movimento (flexão de braço, barra fixa negativa,
#: afundo) — com 2 a letra A da persona ficava em duas opções de dois
#: exercícios (medido em 22/09/2026); com 3 fica em 3 + 3, sem paralelas,
#: sem parada de mão, sem arqueiro.
DEGRAU_DO_INICIANTE = 3


def ajustar_degrau_do_iniciante(itens, nivel, permitidos, catalogo=None) -> list:
    """O iniciante que treina só com o peso do corpo começa pelo degrau mais
    fácil da escada (22/09/2026).

    Achado #5 das personas: a iniciante de 78 kg, "só o peso do corpo",
    recebia MERGULHO NAS PARALELAS (degrau 4), flexão parada de mão (5) e
    barra fixa pronada (5) — a leitura mostrava a escada com "você está
    aqui", mas a ficha a punha no topo. A doutrina fica: o iniciante faz os
    MESMOS movimentos; o que muda é o degrau. Só para `iniciante` e só
    quando o perfil é `peso_corporal` — na academia a progressão é a carga.
    Cada item com `progressao` acima de `DEGRAU_DO_INICIANTE` é trocado
    pelo degrau mais baixo do MESMO movimento e grupo que ainda não esteja
    na lista, com a dose do item trocado — um degrau DENTRO do alcance do
    iniciante, e não só "um abaixo": o arqueiro (5) não vira hindu (4). Sem
    degrau livre, o item SAI —
    quatro flexões numa letra viram duas fáceis, e `preencher_ate_a_faixa`
    devolve as séries aos exercícios que ficaram —, exceto quando é o
    último exercício do grupo na lista (um grupo anunciado não pode ficar
    sem nada; o degrau alto fica, e a leitura mostra o degrau de baixo).
    Roda no gerador E na conferência, como `substituir_por_equipamento`.
    """
    itens = list(itens)
    if nivel != Experiencia.INICIANTE or permitidos is None:
        return itens
    if frozenset(permitidos) != frozenset({Equipment.BODYWEIGHT}):
        return itens
    if catalogo is None:
        catalogo = catalogo_permitido(permitidos)
    usados = {item.exercise_id for item in itens}
    resultado = []
    for item in itens:
        escada = item.exercise.progressao or {}
        nivel_do_item = escada.get("nivel") or 0
        if nivel_do_item <= DEGRAU_DO_INICIANTE:
            resultado.append(item)
            continue
        candidatos = [
            e for e in catalogo
            if (e.progressao or {}).get("movimento") == escada.get("movimento")
            and e.muscle_group == item.exercise.muscle_group
            and (e.progressao or {}).get("nivel", 99) <= DEGRAU_DO_INICIANTE
            and e.id not in usados
        ]
        mais_facil = min(candidatos, key=lambda e: ((e.progressao or {}).get("nivel", 99), e.name, e.id), default=None)
        if mais_facil is None:
            outros_do_grupo = [
                r for r in resultado if r.exercise.muscle_group == item.exercise.muscle_group
            ] + [
                r for r in itens[itens.index(item) + 1:] if r.exercise.muscle_group == item.exercise.muscle_group
            ]
            if outros_do_grupo:
                usados.discard(item.exercise_id)
                continue
            resultado.append(item)
            continue
        usados.add(mais_facil.id)
        copia = copy.copy(item)
        copia.pk = None
        copia.exercise = mais_facil
        resultado.append(copia)
    return resultado


#: O que decide a prescrição SEM a pessoa: o catálogo de exercícios, os
#: modelos e a doutrina. Mudou um deles, mudou o que o gerador produziria.
_ARQUIVOS_DO_CATALOGO = (
    Path(__file__).resolve().parent / "data" / "exercises.json",
    Path(__file__).resolve().parent / "data" / "splits.json",
    Path(__file__).resolve().parent.parent / "docs" / "briefs" / "treino" / "TREINO.md",
)


@lru_cache(maxsize=1)
def versao_do_catalogo() -> str:
    """Impressão digital do catálogo que o deploy carrega — a de HOJE, lida
    do disco uma vez por processo. `TrainingPlan.catalogo` guarda a de quando
    a ficha nasceu; iguais, nada mudou embaixo dela e a Home não precisa
    represcrever a semana a cada visita para saber (17/09/2026: eram onze
    consultas por visita para um aviso que quase nunca aparece)."""
    resumo = hashlib.sha256()
    for arquivo in _ARQUIVOS_DO_CATALOGO:
        resumo.update(arquivo.read_bytes())
    return resumo.hexdigest()[:16]


def grupos_treinados(exercicios) -> set:
    """Os grupos que uma sessão TREINA: o direto de cada exercício e os
    secundários — de TODO exercício, a mesma conta de `volume_efetivo`, para
    todo grupo que recebe volume ter um teto (o face pull é isolador e dá
    meia série ao trapézio). É a frequência que a Tabela B do TREINO.md
    conta — o ombro de "Pernas e ombros" cai uma vez anunciado e mais quatro
    dentro dos supinos e das remadas, e o teto de uma vez só (23) o aparava
    a dois exercícios enquanto o secundário sozinho já somava vinte."""
    grupos = set()
    for exercicio in exercicios:
        grupos.add(exercicio.muscle_group)
        grupos.update(exercicio.secondary_muscles or ())
    return grupos


def tetos_da_semana(plan) -> dict:
    """O teto de séries efetivas de cada grupo NESTE plano: o do nível da
    pessoa para a FREQUÊNCIA com que o grupo é treinado na semana
    (`TREINO.md`, tabela B; `grupos_treinados`) — um grupo que cai duas vezes
    tem teto maior que o que cai uma. É a régua que `volume_da_semana` deve
    respeitar, grupo a grupo."""
    from . import doutrina

    nivel = nivel_de(plan.user)
    sessoes = list(plan.sessions.prefetch_related("exercises__exercise"))
    ocorrencias = ocorrencias_das_letras(sessoes)
    frequencia = {}
    for sessao in sessoes:
        if sessao.label in {s.label for s in sessoes if s.order < sessao.order}:
            continue  # a letra repetida já contou pelas ocorrências
        for grupo in grupos_treinados(item.exercise for item in sessao.exercises.all()):
            frequencia[grupo] = frequencia.get(grupo, 0) + ocorrencias[sessao.label]
    return {grupo: doutrina.teto_semanal(nivel, vezes) for grupo, vezes in frequencia.items()}


def teto_semanal_de(user) -> int:
    """O teto de séries efetivas por grupo desta pessoa, para um grupo que
    cai UMA vez na semana — a identidade do nível. Grupo que cai duas ou
    três vezes tem teto maior (`tetos_da_semana`, `doutrina.teto_semanal`).

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
    return TETO_POR_EXPERIENCIA.get(nivel_de(user), TETO_SEMANAL_POR_GRUPO)


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


def _encaixar(atuais, item, series, grau, limite):
    """Tenta pôr um item a mais nesta sessão. Devolve as linhas, ou `None`.

    Reduz série de ISOLADOR e ACESSÓRIO para abrir espaço, nunca do composto
    PRINCIPAL e nunca abaixo do piso. É a permissão exata que a especificação
    dá — "reduza somente séries de isoladores/acessórios para encaixar uma
    prancha, sem ultrapassar 60 minutos" — e o teto continua duro: se não
    couber nem assim, a resposta é `None` e o aviso conta o que faltou.
    """
    linhas = [[i, s, g] for i, s, g in atuais]
    linhas.append([item, series, grau])

    def custa():
        return _segundos_da_sessao(
            [(s, i.rest_seconds, g >= ACESSORIO) for i, s, g in linhas]
        )

    while custa() > limite:
        reduziveis = [
            linha for linha in linhas
            if linha[2] < PRINCIPAL
            and linha[1] > (PISO_COMPOSTO if linha[2] >= ACESSORIO else 2)
        ]
        if not reduziveis:
            return None
        alvo = min(reduziveis, key=lambda linha: (linha[2], -linha[1]))
        alvo[1] -= 1
    return linhas


def realocar_complementares_orfaos(por_sessao, prescricao, descartados, teto):
    """O complementar que o relógio tirou de uma sessão procura OUTRA.

    O DEFEITO QUE ISTO FECHA, e ele era meu raciocínio, não o código. Medido
    que o abdômen não cabia no dia de perna como décimo exercício, eu concluí
    que ele não cabia na SEMANA e mandei a ficha avisar que ele ficou de fora.
    As duas coisas não são a mesma, e a diferença estava à vista: com quatro
    dias, `A2` fecha em 24 minutos de 60 — trinta e seis minutos ociosos ao
    lado de uma prancha descartada.

    ABDÔMEN NÃO PERTENCE AO DIA DE PERNA; ele só estava listado ali. Prancha no
    fim do treino de peito é tão sensata quanto no fim do de perna, e é assim
    que academia inteira programa. O mesmo vale para trapézio e antebraço: o
    modelo diz onde eles CABEM melhor, não onde eles PODEM estar.

    O QUE ESTA FUNÇÃO NÃO FAZ, e cada limite é um contrato de outra parte:

      - não inventa exercício: o candidato é o item que o relógio descartou,
        com o nome e a dose do catálogo;
      - não mexe no volume semanal. O descartado já passou por
        `aparar_volume_semanal` — ele está em `sobrevivem` —, então mudá-lo de
        sessão preserva o total da semana por construção;
      - não toca em grupo anunciado: só reduz série de isolador e acessório
        para abrir espaço, e nunca do composto principal;
      - não põe duas vezes o mesmo grupo na mesma sessão, nem repete um
        exercício que já esteja lá;
      - não ultrapassa o teto. `_encaixar` devolve `None` e o grupo continua
        órfão — aí, e só aí, o aviso de `aviso_de_tempo` é a resposta certa.

    A sessão escolhida é a de MAIOR FOLGA, que é o que distribui de verdade: em
    quatro e cinco dias as segundas passagens `A2` e `B2` são as mais vazias, e
    é nelas que a prancha cai.
    """
    limite = _teto_em_segundos(teto)
    graus, anunciados = {}, {}
    for pk, (_sessao, candidatos, principais) in por_sessao.items():
        anunciados[pk] = set(principais or ())
        for item, _series, grau in candidatos:
            graus[(pk, item.exercise_id)] = grau

    def linhas_de(pk):
        return [
            (item, series, graus.get((pk, item.exercise_id), ISOLADOR))
            for (sessao_pk, _e), (series, item) in prescricao.items()
            if sessao_pk == pk
        ]

    def folga(pk):
        atuais = linhas_de(pk)
        if not atuais:
            return limite
        return limite - _segundos_da_sessao(
            [(s, i.rest_seconds, g >= ACESSORIO) for i, s, g in atuais]
        )

    presentes = {
        item.exercise.muscle_group for (_p, _e), (_s, item) in prescricao.items()
    }
    orfaos = {}
    for pk, dispensados in descartados.items():
        for item, series, grau in dispensados:
            grupo = item.exercise.muscle_group
            if grupo in presentes or grupo in anunciados[pk]:
                continue
            orfaos.setdefault(grupo, []).append((item, series, grau))

    for grupo in sorted(orfaos):
        # O mais barato primeiro: uma prancha de três séries entra onde um
        # encolhimento de quatro não entraria.
        candidatos = sorted(
            orfaos[grupo], key=lambda t: t[1] * (t[0].rest_seconds + 40)
        )
        for pk in sorted(por_sessao, key=folga, reverse=True):
            atuais = linhas_de(pk)
            if any(i.exercise.muscle_group == grupo for i, _s, _g in atuais):
                continue
            ja_estao = {i.exercise_id for i, _s, _g in atuais}
            for item, series, grau in candidatos:
                if item.exercise_id in ja_estao:
                    continue
                encaixe = _encaixar(atuais, item, series, grau, limite)
                if encaixe is None:
                    continue
                ordem = max([i.order for i, _s, _g in atuais] or [0]) + 1
                for linha_item, linha_series, _g in encaixe:
                    chave = (pk, linha_item.exercise_id)
                    if linha_item.exercise_id == item.exercise_id:
                        # Uma CÓPIA não salva, só para levar a posição do fim
                        # da ficha: o item veio do modelo de outra letra e a
                        # `order` dele é de lá. Nada é gravado no catálogo.
                        copia = copy.copy(item)
                        copia.order = ordem
                        prescricao[chave] = (linha_series, copia)
                    else:
                        prescricao[chave] = (linha_series, linha_item)
                break
            else:
                continue
            break
    return prescricao


#: Sentinela para `prescrever_semana`: `None` É um teto válido — significa
#: "sem limite rígido" —, então ele não pode servir de "não informado".
_NAO_INFORMADO = object()


def teto_completo_de(user):
    """O teto de minutos da SESSÃO COMPLETA desta pessoa.

    Quem escolheu uma faixa fica com a faixa dela — a escolha não é
    sobrescrita. Quem não tem teto ("sem limite rígido", ou nunca respondeu)
    recebe `TETO_COMPLETO_MIN` (65): a sessão completa mira perto de uma
    hora, e "sem limite" não é "sem tamanho". `None` NÃO sai daqui: no
    motor, `None` significa sem relógio — a referência da nota de tempo.
    """
    from .opcoes import TETO_COMPLETO_MIN

    teto = teto_de_minutos(user)
    return teto if teto is not None else TETO_COMPLETO_MIN


def teto_de_minutos(user) -> int:
    """O teto de tempo desta pessoa, em minutos, ou `None` quando não há.

    Lê a FAIXA declarada no perfil e não o `duration_min` da sessão. O inteiro
    continua gravado — `plans/meal_planner.py` precisa dele para não marcar
    refeição no meio do treino —, mas ele deixou de ser a pergunta: quem
    respondeu "Padrão" declarou "até 60", e é esse teto que o motor deve
    obedecer.

    Perfil ausente devolve `None`, que é "sem teto". É o caminho de quem monta
    ficha antes de o perfil existir, e ali prometer um teto seria inventar uma
    resposta que ninguém deu.
    """
    perfil = getattr(user, "profile", None)
    faixa = getattr(perfil, "duracao_treino", None) or DuracaoTreino.LIVRE
    return TETO_POR_DURACAO.get(faixa)


def _nivel_do_teto(teto_semanal, sessoes):
    """O nível por trás de um `teto_semanal` recebido — a chamada antiga
    passa o número, e o número é a identidade do nível (o teto de UMA
    ocorrência). `None` lê o perfil; um teto absurdo (≥ 1000) é "sem teto"."""
    if teto_semanal is None:
        return nivel_de(sessoes[0].plan.user) if sessoes else Experiencia.INTERMEDIARIO
    if teto_semanal >= 1000:
        return None
    for nivel, valor in TETO_POR_EXPERIENCIA.items():
        if valor == teto_semanal:
            return nivel
    return Experiencia.INTERMEDIARIO


def prescrever_opcoes(sessoes, modelos, teto=_NAO_INFORMADO,
                      teto_semanal=None, nivel=_NAO_INFORMADO, permitidos=None) -> dict:
    """O que cada OPÇÃO de cada sessão manda fazer:
    `{(sessão.pk, opção, exercício): (séries, item)}`.

    UMA LETRA, ATÉ DUAS OPÇÕES (15/09/2026, `workouts/opcoes.py`). A
    repartição por ocorrência (`repartir_ocorrencia`) dava a cada passagem da
    letra METADE do modelo com a dose cheia: sessões curtas, "A1" e "A2" como
    dias obrigatórios. Aqui a repartição vira duas VERSÕES da mesma letra,
    cada uma completa (piso de 15 séries, teto de 18), equivalentes (mesmos
    grupos, ≤ 1 série por grupo e ≤ 5 minutos de diferença, metade dos
    exercícios próprios), e a pessoa faz UMA por ocorrência. Sem catálogo
    para duas assim, a letra sai com uma opção só.

    A ordem das decisões:

    1. cada letra é repartida em opções (`montar_opcoes`), com os graus da
       SESSÃO (`prioridades_da_sessao` sobre a opção, não sobre o modelo);
    2. cada opção sobe até o piso de séries pelo isolador e acessório dos
       grupos anunciados (`preencher_ate_a_faixa`), dentro do tempo;
    3. o pior caso da semana — cada ocorrência fazendo a opção mais pesada no
       grupo — cabe no teto semanal (`aparar_opcoes`), com as três travas;
       as opções NUNCA são somadas;
    4. cada opção cabe no tempo (`escolher_para_o_tempo`, cinco camadas);
    5. as opções são equilibradas e conferidas (`equivalentes`); se ainda
       assim não forem, a letra fica com a opção 1.

    `permitidos` (17/09/2026) é o que o perfil de equipamento pode usar
    (`permitidos_de`): o item do modelo fora dele é trocado pelo mesmo
    padrão dentro dele ANTES de tudo (`substituir_por_equipamento`) — a
    cadeia inteira roda sobre a ficha que a pessoa consegue fazer. `None` é
    o catálogo inteiro, o perfil "completa".

    Determinística, e chamada pelo gerador E pela conferência.
    """
    from . import opcoes as motor_de_opcoes

    ocorrencias = ocorrencias_das_letras(sessoes)
    catalogo = None
    if permitidos is not None and not frozenset(Equipment.values) <= frozenset(permitidos):
        if any(
            item.exercise.equipment not in permitidos
            for label in ocorrencias if modelos.get(label) is not None
            for item in modelos[label].items.all() if item.exercise.is_active
        ):
            catalogo = catalogo_permitido(permitidos)
    if teto is _NAO_INFORMADO:
        teto = teto_completo_de(sessoes[0].plan.user) if sessoes else None
    # `None` é SEM RELÓGIO — a referência que `aviso_de_tempo` compara e que
    # os testes usam como "ficha natural". A faixa "livre" da pessoa NÃO
    # chega aqui como `None`: `teto_completo_de` a traduz em 65 minutos.
    teto_completo = teto
    from . import doutrina

    if nivel is _NAO_INFORMADO:
        nivel = _nivel_do_teto(teto_semanal, sessoes)
    sem_teto = nivel is None
    letras = list(ocorrencias)
    itens_de = {}
    principais_de = {}
    faixa_de = {}
    for label in letras:
        modelo = modelos.get(label)
        if modelo is None:
            return None
        itens_de[label] = ajustar_degrau_do_iniciante(
            substituir_por_equipamento(
                [item for item in modelo.items.all() if item.exercise.is_active],
                permitidos, catalogo,
            ),
            nivel, permitidos, catalogo,
        )
        principais_de[label] = list(getattr(modelo, "main_groups", None) or ())
        # A FAIXA É DO TIPO DE DIA E DO NÍVEL (TREINO.md, tabela A): "Peito e
        # tríceps" do intermediário quer 21–28 séries diretas; "Peito" de
        # cinco dias, 14–20; o corpo inteiro de um dia, 20–26.
        tipo = doutrina.tipo_de_dia(getattr(modelo, "split", ""), label)
        # Fora do contrato (`abcd D`, só complementares): dose do catálogo,
        # sem preenchimento e sem teto de sessão.
        faixa_de[label] = (
            doutrina.faixa_de_series(nivel or doutrina.NIVEL_PADRAO, tipo) if tipo else (0, 10_000)
        )

    def limites_de(por_letra):
        """O teto de cada grupo pela FREQUÊNCIA com que ele é treinado na
        semana (TREINO.md, tabela B; `grupos_treinados`): a letra que se
        repete soma o grupo duas ou três vezes, e o teto acompanha."""
        if sem_teto:
            return {"*": 10_000}
        frequencia = {}
        for label, opcoes in por_letra.items():
            grupos = grupos_treinados(item.exercise for op in opcoes for item, _, _ in op)
            for grupo in grupos:
                frequencia[grupo] = frequencia.get(grupo, 0) + ocorrencias.get(label, 1)
        return {grupo: doutrina.teto_semanal(nivel, vezes) for grupo, vezes in frequencia.items()}

    def montar(letras_com_duas):
        """Passa a semana inteira pela cadeia, com duas opções nas letras
        pedidas e uma (o modelo inteiro) nas demais. Devolve `{letra: opções}`
        já no tempo — a conferência de equivalência é do chamador."""
        por_letra = {}
        for label in letras:
            itens = itens_de[label]
            opcoes = [list(itens)]
            if label in letras_com_duas:
                # TANTAS OPÇÕES QUANTAS OCORRÊNCIAS (mínimo duas): com a letra
                # três vezes na semana, duas opções de meio modelo cada
                # dariam, no pior caso, 1,5 modelo por semana — e o teto
                # esvaziava as duas até a letra ficar com um exercício de
                # peito. Com três opções de um terço, repetir a preferida
                # três vezes é exatamente a dose do modelo.
                # Tenta com o número de ocorrências; sem catálogo para
                # tantas opções distintas, tenta duas; só então uma.
                for n in sorted({max(2, ocorrencias[label]), 2}, reverse=True):
                    candidatas, compartilhados = motor_de_opcoes.montar_opcoes(
                        itens, n=n, principais=principais_de[label],
                    )
                    if motor_de_opcoes.distintas_o_bastante(candidatas, compartilhados):
                        opcoes = candidatas
                        break
            linhas_por_opcao = []
            for op in opcoes:
                graus = prioridades_da_sessao(op)
                linhas = [
                    (item, dose_da_sessao(item), grau)
                    for item, grau in zip(op, graus)
                    if dose_da_sessao(item) > 0
                ]
                # O preenchimento até a faixa é da sessão de ~60 minutos. Com
                # "até 30" ele enchia os anunciados e o relógio tirava os
                # complementares em seguida: a 30 minutos, abc2 de cinco dias
                # ficava sem panturrilha, abdômen, antebraço e trapézio na
                # semana inteira. Abaixo de 45 minutos a dose é a do catálogo.
                if teto_completo is None or teto_completo >= motor_de_opcoes.MINUTOS_PARA_PREENCHER:
                    linhas = motor_de_opcoes.preencher_ate_a_faixa(
                        linhas, teto_completo, principais_de[label], faixa=faixa_de[label],
                        por_exercicio=doutrina.series_por_exercicio(nivel or doutrina.NIVEL_PADRAO),
                    )
                linhas_por_opcao.append(linhas)
            por_letra[label] = linhas_por_opcao
        por_letra = motor_de_opcoes.aparar_opcoes(
            por_letra, ocorrencias, limites_de(por_letra), dose_da_sessao
        )
        no_tempo = {}
        descartados = {}
        for label, opcoes in por_letra.items():
            principais = principais_de[label]
            prontas = []
            descartados[label] = []
            for linhas in opcoes:
                ficam = escolher_para_o_tempo(
                    [(item.exercise.muscle_group, series, item.rest_seconds, grau)
                     for item, series, grau in linhas],
                    teto_completo,
                    principais=principais,
                )
                ficaram = {i for i, _ in ficam}
                prontas.append([(linhas[i][0], series, linhas[i][2]) for i, series in ficam])
                # O que o relógio dispensou, guardado: um complementar que não
                # coube aqui pode caber noutra letra (`realocar_orfaos_nas_opcoes`).
                descartados[label].append([l for i, l in enumerate(linhas) if i not in ficaram])
            if len(prontas) > 1:
                prontas = motor_de_opcoes.equilibrar(
                    prontas, principais, teto_completo, teto_series=faixa_de[label][1]
                )
            no_tempo[label] = prontas
        motor_de_opcoes.realocar_orfaos_nas_opcoes(no_tempo, descartados, principais_de, teto_completo)
        # Equilibrar pode ter DADO série: o teto semanal é conferido de novo,
        # e o que ele tirar de uma opção é acompanhado pela outra (só tirando).
        no_tempo = motor_de_opcoes.aparar_opcoes(
            no_tempo, ocorrencias, limites_de(no_tempo), dose_da_sessao
        )
        return {
            label: (
                motor_de_opcoes.equilibrar(
                    opcoes, principais_de[label], teto_completo, dar=False, teto_series=faixa_de[label][1]
                )
                if len(opcoes) > 1 else opcoes
            )
            for label, opcoes in no_tempo.items()
        }

    # Primeiro com duas opções em toda letra; a letra que não fechar as
    # réguas de equivalência volta a UMA opção — o modelo inteiro, e não a
    # metade que sobrou —, e a semana é montada de novo, porque o teto é
    # partilhado entre as letras.
    com_duas = set(letras)
    for _ in range(len(letras) + 1):
        semana = montar(com_duas)
        reprovadas = {
            label for label, opcoes in semana.items()
            if len(opcoes) > 1 and not motor_de_opcoes.equivalentes(opcoes, principais_de[label])
        }
        if not reprovadas:
            break
        com_duas -= reprovadas
    prescricao = {}
    for label, opcoes in semana.items():
        for sessao in sessoes:
            if sessao.label != label:
                continue
            for k, linhas in enumerate(opcoes, start=1):
                for item, series, _grau in linhas:
                    prescricao[(sessao.pk, k, item.exercise_id)] = (series, item)
    return prescricao


def prescrever_semana(sessoes, modelos, teto=_NAO_INFORMADO,
                      teto_semanal=None, nivel=_NAO_INFORMADO, permitidos=None) -> dict:
    """A OPÇÃO 1 de cada sessão: `{(sessão.pk, exercício): (séries, item)}`.

    Desde 15/09/2026 quem prescreve é `prescrever_opcoes`; esta é a projeção
    da primeira opção, que os títulos (`ajustar_titulos`), a nota da divisão
    e o aviso de tempo leem — as opções são equivalentes por construção, então
    o que vale para a 1 vale para a 2. Tudo abaixo desta docstring é a
    história da prescrição por ocorrência, mantida porque cada decisão dela
    continua valendo dentro de cada opção.

    O que cada sessão da semana manda fazer: {(sessão, exercício): séries}.

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
    completa = prescrever_opcoes(
        sessoes, modelos, teto=teto, teto_semanal=teto_semanal, nivel=nivel, permitidos=permitidos,
    )
    if completa is None:
        return None
    return {
        (sessao_pk, exercicio_id): valor
        for (sessao_pk, opcao, exercicio_id), valor in completa.items()
        if opcao == 1
    }


def _prescrever_por_ocorrencia(sessoes, modelos, teto=_NAO_INFORMADO,
                               teto_semanal=None) -> dict:
    """A prescrição por OCORRÊNCIA da letra (A1 ≠ A2), como era até 15/09/2026.

    Fica como referência medida de `repartir_ocorrencia`,
    `aparar_volume_semanal` e `realocar_complementares_orfaos` — as três
    continuam existindo e testadas, mas quem prescreve em produção é
    `prescrever_opcoes`, cujas peças homônimas estão em `workouts/opcoes.py`
    (`montar_opcoes`, `aparar_opcoes`, `realocar_orfaos_nas_opcoes`). Nenhum
    caminho de produção chama isto.
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
    descartados = {}
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
        ficaram = {i for i, _series in ficam}
        for i, series_finais in ficam:
            item, _series_do_catalogo, _grau = restantes[i]
            # `series_finais` e não o número do catálogo: quando a sessão só
            # coube reduzindo série, é a reduzida que a pessoa faz.
            prescricao[(sessao.pk, item.exercise_id)] = (series_finais, item)
        # O QUE O RELÓGIO DISPENSOU, guardado — e não jogado fora.
        #
        # Um complementar que não coube AQUI pode caber noutra sessão da
        # semana, e a folga costuma existir: com quatro dias, `A2` fecha em 24
        # minutos de 60. Ver `realocar_complementares_orfaos`.
        descartados[sessao_pk] = [
            linha for i, linha in enumerate(restantes) if i not in ficaram
        ]

    if teto is not None:
        realocar_complementares_orfaos(
            por_sessao, prescricao, descartados, teto
        )
    return prescricao


#: Como o TÍTULO chama cada grupo. Curto de propósito: `MuscleGroup.label`
#: existe para o admin e diz "Posterior de coxa", que é preciso e não cabe
#: num nome de sessão.
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
    MuscleGroup.GLUTES: "glúteo",
}


def _lista_em_portugues(palavras) -> str:
    """"a", "a e b", "a, b e c" — a vírgula de série do português."""
    palavras = list(palavras)
    if not palavras:
        return ""
    if len(palavras) == 1:
        return palavras[0]
    return "%s e %s" % (", ".join(palavras[:-1]), palavras[-1])


def _nomes_dos_grupos(grupos, por_familia=False) -> list:
    """Os nomes curtos, com quadríceps e posterior colapsados em "pernas".

    Quem treina os dois no mesmo dia treinou PERNA, e "quadríceps e posterior e
    ombros" é a frase de quem está lendo um banco de dados em voz alta. O
    colapso acontece na posição do primeiro dos dois, para a ordem do título
    continuar sendo a ordem da ficha. O glúteo (21/09/2026) entra no colapso
    junto com os dois, e sozinho é "glúteo".

    `por_familia` é do TÍTULO (`titulo_honesto`): ali o glúteo vira
    "posterior", como o título sempre disse — é UM título para as duas
    versões da letra, e a versão com o stiff e a com a elevação pélvica têm
    a mesma cadeia. O aviso do que não coube e o foco NÃO passam por aí:
    "posterior não coube" com o stiff na ficha seria mentira.
    """
    grupos = [familia_de_opcoes(grupo) if por_familia else grupo for grupo in grupos]
    perna = {MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS, MuscleGroup.GLUTES}
    colapsa = {MuscleGroup.QUADS, MuscleGroup.HAMSTRINGS} <= set(grupos)
    nomes = []
    for grupo in grupos:
        if colapsa and grupo in perna:
            if "pernas" not in nomes:
                nomes.append("pernas")
            continue
        nome = NOME_CURTO_DO_GRUPO.get(grupo)
        if nome and nome not in nomes:
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

    E o grupo aqui é a FAMÍLIA (`models.FAMILIA_DE_OPCOES`), pelo mesmo
    motivo das opções: o título é UM por sessão e vale para as duas versões
    da letra, e a versão com o stiff e a versão com a elevação pélvica têm
    a mesma cadeia posterior — o título a nomeia como "posterior", que é o
    que dizia antes de o glúteo virar grupo (21/09/2026). Sem isto, com
    trinta minutos a letra virava "Quadríceps e glúteo" com a outra versão
    sem glúteo nenhum.
    """
    anunciados = list(principais or ())
    if not anunciados:
        return nome_do_modelo
    familias_presentes = {familia_de_opcoes(grupo) for grupo in presentes}
    sobreviventes = [grupo for grupo in anunciados if familia_de_opcoes(grupo) in familias_presentes]
    if len(sobreviventes) == len(anunciados):
        return nome_do_modelo
    if not sobreviventes:
        # Nenhum grupo anunciado sobreviveu. Não deveria acontecer — o corte
        # protege o último exercício de cada grupo anunciado —, e mesmo assim
        # o nome não pode virar string vazia numa coluna que a tela imprime.
        return "Treino do dia"
    montado = _frase_que_cabe(
        _nomes_dos_grupos(sobreviventes, por_familia=True),
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


def nota_da_divisao(split, sessoes, teto_semanal=None) -> str:
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
    # A CAUSA, quando a experiência esvazia a passagem repetida. Com o teto
    # do iniciante (12 séries efetivas por grupo) três dias já fecham a
    # semana; o quarto e o quinto ficam com o que sobra — medido em
    # 13/09/2026: cinco dias em ABC2 dão [30, 24, 60, 14, 24] minutos, com
    # A2 reduzida a um exercício. "Corte de volume continua sem frase" vale
    # para o aparo comum; aqui a pessoa vê uma sessão de treze minutos e
    # precisa saber por quê — e a frase só entra quando há passagem repetida.
    if teto_semanal is not None and teto_semanal <= TETO_POR_EXPERIENCIA[Experiencia.INICIANTE] and repetidos:
        base = "%s Com o volume de quem está começando, três dias já entregam a semana inteira — as passagens repetidas ficam mais curtas de propósito, e crescem quando você mudar o nível no Perfil." % base
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

    # SÉRIE REDUZIDA TAMBÉM É AJUSTE, e por um tempo o aviso não a via.
    #
    # `cortados` conta EXERCÍCIO removido, e essa era a única forma de ajuste
    # até 10/09/2026. Quando a redução de série subiu na ordem de concessão —
    # para preservar a variedade contratada —, passou a existir ficha
    # fortemente ajustada com ZERO remoções: medido, três dias com 55 minutos
    # cabem inteiros baixando série, e a nota ficava muda. A pessoa via
    # números menores que os do catálogo e nada explicando.
    reduzidos = sum(
        1
        for chave, (series, _item) in prescricao.items()
        if chave in sem_relogio and series < sem_relogio[chave][0]
    )

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
    if cortados or reduzidos:
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
        # Retrato das entradas: com que catálogo, nível e faixa ela nasceu.
        catalogo=versao_do_catalogo(),
        nivel=nivel_de(user),
        duracao=duracao_de(user),
        equipamento=equipamento_de(user),
        # A posição zero do ciclo: o primeiro dia de treino desta semana.
        inicio_do_ciclo=inicio_do_ciclo_de(
            timezone.localdate(), [day.weekday for day in training_days]
        ),
    )

    sessions = build_sessions(plan, training_days, templates)
    TrainingSession.objects.bulk_create(sessions)

    by_label = {template.label: template for template in templates}
    teto_semanal = teto_semanal_de(user)
    permitidos = permitidos_de(user)
    completa = prescrever_opcoes(
        sessions, by_label,
        teto=teto_completo_de(user), teto_semanal=teto_semanal, nivel=nivel_de(user),
        permitidos=permitidos,
    )
    prescricao = {
        (sessao_pk, exercicio_id): valor
        for (sessao_pk, opcao, exercicio_id), valor in completa.items()
        if opcao == 1
    }
    # A nota vem depois da prescrição porque descreve o que a prescrição fez:
    # `build_sessions` decide o ciclo e `prescrever_semana` decide o que coube
    # no tempo. Escrevê-la antes daria um texto sobre uma ficha que ainda não
    # existia.
    #
    # A SEGUNDA CHAMADA É A RÉGUA DA FRASE, e ela é de graça: `templates_for`
    # já traz `items__exercise` em cache, então rodar a prescrição sem teto de
    # tempo não custa consulta nenhuma. Ela responde "o que o relógio tirou",
    # que é a única pergunta que a frase tem o direito de responder.
    # A referência SEM RELÓGIO da nota de tempo. Quem escolheu "sem limite
    # rígido" não informou tempo nenhum: a sessão completa dele é a de 65
    # minutos (`teto_completo_de`) e não há corte a avisar — comparar com
    # `None` faria a nota dizer "para caber no tempo que você informou" a
    # quem não informou.
    sem_relogio = (
        prescrever_semana(
            sessions, by_label, teto=None, teto_semanal=teto_semanal, nivel=nivel_de(user),
            permitidos=permitidos,
        )
        if teto_de_minutos(user) is not None else prescricao
    )
    plan.notes = " ".join(
        parte
        for parte in (
            nota_da_divisao(split, sessions, teto_semanal=teto_semanal),
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
            opcao=opcao,
        )
        for (sessao_id, opcao, exercicio_id), (series, item) in completa.items()
    ]
    SessionExercise.objects.bulk_create(exercises)
    return plan


def get_active_routine(user):
    return TrainingPlan.objects.filter(user=user, is_active=True).first()


def linhas_do_plano(plan) -> list:
    """As sessões do plano com os itens e o exercício de cada um, em DUAS
    consultas: `prefetch_related("exercises__exercise")` eram três, e o
    exercício é chave direta do item — entra por JOIN (21/09/2026)."""
    return list(
        plan.sessions.prefetch_related(
            Prefetch("exercises", queryset=SessionExercise.objects.select_related("exercise"))
        )
    )


def rotina_ativa_com_linhas(user) -> tuple:
    """(plano ativo, linhas, trocas) numa consulta SÓ — a Home (21/09/2026).

    Os itens trazem a sessão e o plano por JOIN; as sessões são remontadas
    em memória, na ordem do plano, com os itens já no cache de `exercises`
    (o mesmo que `prefetch_related` deixaria, então `opcoes`, `da_opcao` e
    tudo que lê `session.exercises.all()` continua sem consulta). Plano
    ativo cujas sessões não têm item nenhum não aparece por aqui, e o
    caminho de sempre (`get_active_routine` + `linhas_do_plano`) o encontra.
    """
    # A troca da pessoa viaja NA MESMA consulta (`substituto_id`, uma
    # subconsulta por linha): `trocas_de` era mais uma ida ao banco para
    # todo mundo, e a maioria não trocou nada. Quem trocou paga UMA consulta
    # pelos exercícios substitutos — só ela.
    substituto = TrocaDeExercicio.objects.filter(
        user=user, original_id=OuterRef("exercise_id")
    ).values("substituto_id")[:1]
    itens = list(
        SessionExercise.objects.filter(session__plan__user=user, session__plan__is_active=True)
        .select_related("session__plan", "exercise")
        .annotate(substituto_id=Subquery(substituto))
        .order_by("session__weekday", "session__pk", "opcao", "order", "pk")
    )
    if not itens:
        plan = get_active_routine(user)
        return plan, (linhas_do_plano(plan) if plan is not None else []), {}
    plan = itens[0].session.plan
    ids_substitutos = {item.substituto_id for item in itens if item.substituto_id}
    substitutos = Exercise.objects.in_bulk(ids_substitutos) if ids_substitutos else {}
    trocas = {
        item.exercise_id: substitutos[item.substituto_id]
        for item in itens
        if item.substituto_id in substitutos
    }
    linhas, por_sessao = [], {}
    for item in itens:
        sessao = por_sessao.get(item.session_id)
        if sessao is None:
            sessao = item.session
            sessao.plan = plan
            por_sessao[item.session_id] = sessao
            linhas.append(sessao)
            sessao._prefetched_objects_cache = {"exercises": sessao.exercises.all()}
            sessao._prefetched_objects_cache["exercises"]._result_cache = []
            sessao._prefetched_objects_cache["exercises"]._prefetch_done = True
        item.session = sessao
        sessao._prefetched_objects_cache["exercises"]._result_cache.append(item)
    linhas.sort(key=lambda s: (s.weekday, s.pk))
    return plan, linhas, trocas


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

    prescricao = prescrever_opcoes(
        sessoes, modelos,
        teto=teto_completo_de(user), teto_semanal=teto_semanal_de(user), nivel=nivel_de(user),
        permitidos=permitidos_de(user),
    )
    if prescricao is None:
        return False

    gravado = {(i.session_id, i.opcao, i.exercise_id): i.sets for i in itens}
    esperado = {chave: series for chave, (series, _) in prescricao.items()}
    return gravado == esperado


def rotina_invalida(plan, user) -> bool:
    """A rotina ativa NÃO PODE ficar de pé: é o que `sync_active_routine`
    remonta sozinho (17/09/2026).

    Inválida é sem sessão, com exercício aposentado numa sessão, com divisão
    que não corresponde mais à frequência, ou com dias/horários/durações
    diferentes dos cadastrados. Prescrição diferente NÃO é inválida — é
    `rotina_desatualizada`, e essa a pessoa decide (aviso na Home).
    """
    if plan is None or not plan.sessions.exists():
        return True
    if plan.sessions.filter(exercises__exercise__is_active=False).exists():
        # Exercício aposentado no catálogo: a ficha manda fazer o que saiu do
        # ar. Vale inclusive para ficha ajustada — aqui o gerador não está
        # desfazendo a escolha da pessoa, está avisando que o catálogo mudou
        # embaixo dela.
        return True
    if plan.is_customized:
        # Ficha ajustada à mão não é remontada pelo gerador. A pessoa trocou
        # aqueles exercícios por um motivo — joelho, equipamento ocupado,
        # preferência — e mudar o horário de terça-feira não é motivo para
        # descartar a escolha e voltar ao modelo do catálogo.
        return False
    # A pessoa mudou a PRÓPRIA entrada — nível ou faixa de duração — depois
    # de a ficha nascer: é o mesmo caso dos dias de treino, e remonta. Em
    # branco é ficha de antes de 17/09/2026: desconhecido não invalida.
    if plan.nivel and plan.nivel != nivel_de(user):
        return True
    if plan.duracao and plan.duracao != duracao_de(user):
        return True
    # O equipamento nunca fica em branco (default "completa" nos dois
    # lados): mudou no perfil, remonta.
    if plan.equipamento != equipamento_de(user):
        return True
    if plan.split != split_for(user.training_days.count(), _preferencia_de(user)):
        return True
    sessoes = plan.sessions.all()
    atual = {
        (day.weekday, day.start_time, day.duration_min)
        for day in user.training_days.all()
    }
    na_ficha = {
        (session.weekday, session.start_time, session.duration_min)
        for session in sessoes
    }
    return atual != na_ficha


def rotina_desatualizada(plan, user) -> bool:
    """A prescrição do catálogo mudou embaixo de uma ficha VÁLIDA?

    É a pergunta do aviso "Seu treino pode ficar mais completo — regenerar?".
    Até 17/09/2026 isso remontava a ficha na entrada do painel, sem ninguém
    pedir — o deploy que ativou 28 exercícios trocaria a ficha de todo mundo
    no meio da semana. Agora a ficha fica (plano é retrato) e a pessoa
    decide. Ficha ajustada à mão não conta: ali a divergência é escolha.
    """
    if plan is None or plan.is_customized:
        return False
    if plan.inicio_do_ciclo is None and plan.days_per_week > len(letras_do_ciclo(plan.sessions.all())):
        # Plano de antes da rotação contínua, com letra repetida na semana:
        # a ficha nova roda o ciclo; esta continua presa ao dia da semana.
        return True
    if plan.catalogo and plan.catalogo == versao_do_catalogo():
        # O mesmo catálogo com que ela nasceu: nada mudou embaixo dela, e a
        # conferência exata (represcrever a semana) seria onze consultas
        # para confirmar o que a impressão digital já diz. Antes de
        # `rotina_invalida` de propósito: com o plano em mãos, a resposta
        # de todo dia custa ZERO consultas.
        return False
    if rotina_invalida(plan, user):
        return False
    if not _prescricao_bate(plan, user):
        return True
    # A conferência exata disse "igual": o plano recebe a impressão digital
    # de HOJE, para a próxima visita responder com zero consultas. Sem isso,
    # todo deploy que toca o TREINO.md (a doutrina entra na impressão)
    # cobrava as onze consultas de toda ficha antiga em TODA visita à Home,
    # até a pessoa regenerar — e ela não tinha por que regenerar, porque
    # nada mudou. Continua retrato das entradas: a ficha É a que o catálogo
    # de hoje produziria; só o nome do catálogo se atualiza, uma vez.
    hoje = versao_do_catalogo()
    if plan.catalogo != hoje:
        TrainingPlan.objects.filter(pk=plan.pk).update(catalogo=hoje)
        plan.catalogo = hoje
    return False


def routine_is_current(plan, user) -> bool:
    """A rotina ativa é válida E a prescrição ainda bate — a pergunta
    antiga, que hoje é as duas de cima somadas. `sync_active_routine` só
    olha `rotina_invalida`; quem quer saber se há coisa melhor no catálogo
    olha `rotina_desatualizada`."""
    return not rotina_invalida(plan, user) and not rotina_desatualizada(plan, user)


def _prescricao_bate(plan, user) -> bool:
    """A prescrição gravada é a que o motor produziria hoje?"""
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
    # Os itens que o motor VÊ: com o perfil de equipamento aplicado (17/09/
    # 2026). Sem isso o afundo que substituiu o agachamento — com a dose do
    # agachamento — reprovava aqui, e toda ficha de perfil restrito nascida
    # de outro catálogo ficava "desatualizada" para sempre.
    permitidos = permitidos_de(user)
    catalogo = catalogo_permitido(permitidos)
    nivel = nivel_de(user)
    prescrito = {
        (i.exercise_id, i.rep_min, i.rep_max, i.rest_seconds)
        for template in modelos.values()
        for i in ajustar_degrau_do_iniciante(
            substituir_por_equipamento(
                [i for i in template.items.all() if i.exercise.is_active], permitidos, catalogo,
            ),
            nivel, permitidos, catalogo,
        )
    }
    itens = list(
        # Uma consulta, e não uma por sessão: esta função roda na entrada de
        # toda visita à tela de treino.
        SessionExercise.objects.filter(session__plan=plan).select_related("session")
    )
    na_ficha = {
        (i.exercise_id, i.rep_min, i.rep_max, i.rest_seconds) for i in itens
    }
    if not na_ficha <= prescrito:
        return False
    return _prescricao_confere(sessoes, modelos, itens, user)


def ultima_serie_anterior(carga) -> dict | None:
    """`{"peso", "reps", "data"}` da série mais PESADA do último treino deste
    exercício, ou `None` (primeira vez).

    Em memória, sobre o balde `anterior` que `load_history` já trouxe: zero
    consulta. A ficha usa para dizer "42,5 kg × 6" em cada card (era o
    motivo de abrir os nove exercícios um a um) e a execução, para dizer a
    mesma coisa logo ACIMA do campo de carga — onde se escolhe a anilha.
    A mais pesada, e não a última anotada: a ordem de anotar varia.
    """
    anterior = (carga or {}).get("anterior") or {}
    com_carga = [log for log in anterior.values() if log.weight_kg is not None]
    if not com_carga:
        # Peso do corpo: não há anilha, mas há repetições — e "12 reps na
        # última vez" é a informação que existe para esse exercício.
        com_reps = [log for log in anterior.values() if log.reps]
        if not com_reps:
            return None
        melhor = max(com_reps, key=lambda log: log.reps)
        return {"peso": None, "reps": melhor.reps, "data": melhor.date}
    melhor = max(com_carga, key=lambda log: log.weight_kg)
    return {"peso": melhor.weight_kg, "reps": melhor.reps, "data": melhor.date}


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
    # O PEDIDO ADIADO DE ONTEM É CUMPRIDO HOJE (22/09/2026). "Regenerar" com
    # série anotada não remonta na hora — grava `regenerar_pedido_em` — e é
    # aqui que a promessa "sua ficha muda amanhã" vira verdade, na primeira
    # visita de um dia sem série. Vem antes da conferência porque o pedido é
    # sobre a PRESCRIÇÃO, que nunca invalida nada sozinha.
    if plan is not None and plan.regenerar_pedido_em is not None and not treino_em_andamento(user, day):
        return create_routine(user), True
    # SÓ O INVÁLIDO É REMONTADO (17/09/2026). Prescrição diferente — o
    # catálogo cresceu, a faixa de séries mudou — fica para a pessoa decidir
    # na Home ("regenerar?"); plano é retrato, e ninguém tem a ficha trocada
    # no meio da semana por um deploy.
    if not rotina_invalida(plan, user):
        return plan, False
    if plan is not None and treino_em_andamento(user, day):
        return plan, False
    return create_routine(user), True


def pedir_para_regenerar(user, day=None) -> tuple:
    """"Regenerar" — na hora, ou amanhã se a pessoa está treinando.

    Devolve `(plano, adiado)`. Com série anotada hoje, o pedido é gravado no
    plano ATIVO e a ficha fica como está: `create_routine` desliga o plano e
    monta outro, e quem estava na terceira série via a ficha aberta responder
    404 e o cartão do dia virar outra letra com 0 % (relato do dono,
    22/09/2026). Sem série, remonta agora, como sempre foi.
    """
    plan = get_active_routine(user)
    if plan is not None and treino_em_andamento(user, day):
        plan.regenerar_pedido_em = timezone.now()
        plan.save(update_fields=["regenerar_pedido_em"])
        return plan, True
    return create_routine(user), False


def aviso_de_regenerar(user, plan=None) -> bool:
    """A Home deve oferecer "regenerar?" a esta pessoa agora?"""
    plan = get_active_routine(user) if plan is None else plan
    if plan is None or plan.aviso_dispensado_em is not None:
        return False
    return rotina_desatualizada(plan, user)


def has_training_days(user) -> bool:
    return user.training_days.exists()


def acertar_rotina(user) -> tuple:
    """Os dias de treino acabaram de ser salvos: a ficha nasce, se remonta ou desliga.

    É o chamador que faltava. `sync_active_routine` só rodava na entrada das
    telas de Treino, e a Home — que consome `estado_do_treino` sem montar
    nada, de propósito — negava o treino de hoje a toda conta recém-criada:
    "Hoje não tem treino na sua ficha", até a pessoa abrir a aba de Treino
    por conta própria (auditoria de UX, P1-01, 14/09/2026). O lugar certo de
    montar é onde a ENTRADA muda: o fim do wizard e a edição dos dias.

    A outra metade é o inverso (P1-02): quem remove todos os dias ficava com o
    plano ativo, e a Home e a ofensiva (`plans.streaks._dias_de_treino` lê o
    plano ativo) seguiam cobrando um treino que a pessoa disse que não vai
    fazer. Plano é retrato: ele não é apagado, é DESLIGADO — o histórico de
    carga não aponta para a sessão, e o plano continua consultável.

    Devolve `(plano, mudou)` como `sync_active_routine`; sem dias, `plano` é
    `None` e `mudou` diz se havia um ativo para desligar.
    """
    if has_training_days(user):
        return sync_active_routine(user)
    plano = get_active_routine(user)
    if plano is None:
        return None, False
    plano.is_active = False
    plano.save(update_fields=["is_active"])
    return None, True


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


def append_set(user, exercise, weight_kg, reps=None, op_id="", day=None, nota="", falhou=False):
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
                    # A nota e a falha viajam no MESMO corpo da série, então
                    # a fila offline as reenvia sem contrato novo; item
                    # antigo, sem os campos, cai no default.
                    nota=(nota or "")[:120],
                    falhou=bool(falhou),
                )
            return log, True
        except IntegrityError as erro:
            # A transação inteira caiu, então o registro do `op_id` caiu com
            # ela — a tentativa seguinte reabre as duas coisas juntas, que é a
            # propriedade que `AIdempotenciaCaiJuntoComOEfeitoTests` guarda.
            ultimo_erro = erro
            continue

    raise ultimo_erro


def ultima_vez_do_movimento(user, exercicio):
    """A última série registrada em OUTRO exercício do mesmo `padrao` — a
    referência de quem nunca fez este, mas já fez o movimento (auditoria de
    20/09/2026: as duas opções da letra não repetem exercício, e a "última
    carga" ficava muda por duas semanas). A mais recente; no mesmo dia, a
    mais pesada. `None` sem histórico do padrão. Uma consulta, e só quando o
    exercício em foco não tem histórico próprio (a view decide)."""
    log = (
        ExerciseLog.objects.filter(user=user, exercise__padrao=exercicio.padrao)
        .exclude(exercise=exercicio)
        .select_related("exercise")
        .order_by("-date", "-weight_kg", "-set_number")
        .first()
    )
    if log is None:
        return None
    return {
        "exercicio": log.exercise,
        "padrao": exercicio.get_padrao_display(),
        "data": log.date,
        "peso": log.weight_kg,
        "reps": log.reps,
    }


def load_history(user, exercises, day=None) -> dict:
    """Cargas de hoje e a comparação com o último treino, por exercício.

    Devolve, por exercício:

        {
          "hoje":     {série: log},            # o que preencher no formulário
          "anterior": {série: log},            # o mesmo dia de treino passado
          "melhor_hoje": Decimal|None,         # série mais pesada de hoje
          "melhor_anterior": Decimal|None,
          "recorde_anterior": Decimal|None,    # a maior carga em QUALQUER data anterior
          "melhor_serie_anterior": Decimal|None,  # maior reps×carga de UMA série anterior
          "melhor_serie_peso": Decimal|None,      # a carga dessa série
          "melhor_serie_reps": int|None,          # as reps dessa série
          "delta": Decimal|None,               # subiu ou não subiu
          "data_anterior": date|None,
          "sessoes": [(date, {série: log})],   # as últimas datas ANTERIORES, da mais
                                               # recente para trás (≤ SESSOES_LIDAS)
          "ultimo_registro": log|None,         # o registro mais recente antes de `day`
          "dia": date,                         # o `day` da leitura
        }

    `sessoes` e `ultimo_registro` são o que `adaptacao.ajuste` lê (T2.1):
    saem do MESMO laço, sem consulta a mais — a adaptação é leitura.

    `recorde_anterior` é o contrato de `achievements.regras._recorde` — maior
    carga já registrada, não 1RM nem volume — lido do mesmo laço, para a
    execução dizer "recorde: 65 kg" e marcar a série que o supera sem uma
    consulta a mais.

    `melhor_serie_anterior` é a SEGUNDA espécie, o contrato de
    `achievements.regras._melhor_serie` — o maior reps×carga de UMA série,
    não soma de volume — do mesmo laço, pela mesma razão: a execução diz
    "melhor série: 60 kg × 12" e marca a série de hoje que a supera.

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
        recorde_anterior = max(
            (l.weight_kg for l in anteriores if l.weight_kg is not None), default=None
        )
        # A série (não só o produto) porque a tela mostra "60 kg × 12", e
        # guardar só o número perderia a carga e as reps que o compõem.
        melhor_registro = max(
            (l for l in anteriores if l.weight_kg is not None and l.reps is not None),
            key=lambda l: l.weight_kg * l.reps,
            default=None,
        )
        melhor_serie_anterior = (
            melhor_registro.weight_kg * melhor_registro.reps
            if melhor_registro
            else None
        )
        # As últimas datas, agrupadas — `anteriores` já vem por `-date`.
        sessoes = []
        for log in anteriores:
            if not sessoes or sessoes[-1][0] != log.date:
                if len(sessoes) == adaptacao.SESSOES_LIDAS:
                    break
                sessoes.append((log.date, {}))
            sessoes[-1][1][log.set_number] = log
        resultado[exercise_id] = {
            "hoje": hoje,
            "anterior": anterior,
            "melhor_hoje": melhor_hoje,
            "melhor_anterior": melhor_anterior,
            "recorde_anterior": recorde_anterior,
            "melhor_serie_anterior": melhor_serie_anterior,
            "melhor_serie_peso": melhor_registro.weight_kg if melhor_registro else None,
            "melhor_serie_reps": melhor_registro.reps if melhor_registro else None,
            "data_anterior": data_anterior,
            "delta": (melhor_hoje - melhor_anterior)
            if (melhor_hoje is not None and melhor_anterior is not None)
            else None,
            "sessoes": sessoes,
            "ultimo_registro": anteriores[0] if anteriores else None,
            "dia": day,
        }
    return resultado


# ---------------------------------------------------------------------------
# Modo treino — "o que eu faço agora?"
# ---------------------------------------------------------------------------


@dataclass
class Placar:
    """O placar do treino fechado — o que entra na folha de recompensa.

    Tudo é CONTAGEM sobre o que `load_history` já carregou para a tela;
    nenhuma consulta a mais. `carga_total` é a tonelagem de hoje (peso ×
    repetições, série a série); `carga_anterior` é a mesma conta sobre a
    última vez que CADA exercício foi feito — é o "vs. última" da tela, e
    fica `None` quando nenhum exercício tem passado; `recordes` conta os
    exercícios cuja série mais pesada de hoje passou a maior carga de
    qualquer data anterior (a régua de `achievements.regras._recorde`).
    Exercício sem carga (peso do corpo) soma zero, não some.
    """

    carga_total: Decimal = Decimal("0")
    carga_anterior: object = None
    recordes: int = 0
    #: Repetições de hoje, série a série — o herói de quem treina com o
    #: peso do corpo (22/09/2026): "0 kg levantados" em 72 px depois de um
    #: treino inteiro era o placar dizendo que nada aconteceu (achado #5).
    repeticoes: int = 0
    series: int = 0

    @property
    def tem_carga(self) -> bool:
        return self.carga_total > 0

    @property
    def heroi(self):
        """`(número, rótulo)` do número grande: o kg quando houve carga, as
        repetições quando o dia foi todo sem anilha — e as séries quando nem
        repetição foi anotada (a série gravada sem número existe)."""
        if self.tem_carga:
            return (self.carga_total, "kg levantados")
        if self.repeticoes:
            return (self.repeticoes, "repetições feitas")
        return (self.series, "séries feitas")

    @property
    def delta_pct(self):
        """Variação percentual contra a última vez, inteira; `None` sem base."""
        if not self.carga_anterior:
            return None
        return int(round((self.carga_total - self.carga_anterior) * 100 / self.carga_anterior))


def _tonelagem(logs):
    return sum(((log.weight_kg or 0) * (log.reps or 0) for log in logs), Decimal("0"))


def placar_do_treino(itens) -> Placar:
    """Placar a partir dos itens da sessão com `load` (o dicionário de
    `load_history`) já preenchido — o mesmo objeto que a execução usa."""
    placar = Placar()
    anterior = Decimal("0")
    tem_anterior = False
    for item in itens:
        load = getattr(item, "load", None) or {}
        de_hoje = (load.get("hoje") or {}).values()
        placar.carga_total += _tonelagem(de_hoje)
        placar.repeticoes += sum((log.reps or 0) for log in de_hoje)
        placar.series += len(de_hoje)
        de_antes = (load.get("anterior") or {}).values()
        if de_antes:
            tem_anterior = True
            anterior += _tonelagem(de_antes)
        melhor_hoje = load.get("melhor_hoje")
        recorde = load.get("recorde_anterior")
        if melhor_hoje is not None and recorde is not None and melhor_hoje > recorde:
            placar.recordes += 1
    placar.carga_anterior = anterior if tem_anterior else None
    return placar


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
    #: A rotina ativa, já carregada — quem precisa dela depois (o aviso de
    #: regenerar na Home) não a busca de novo.
    plan: object = None
    #: As linhas do plano (uma por dia da semana, com os itens), já lidas —
    #: para quem precisa dos dias previstos sem reler (a ofensiva da Home).
    linhas: list = field(default_factory=list)
    itens: list = field(default_factory=list)
    atual: object = None
    proximo: object = None
    total_exercicios: int = 0
    exercicios_concluidos: int = 0
    #: A posição do exercício em foco na ficha, de 1 em diante — 0 sem foco.
    #:
    #: Ela existe porque a pessoa passou a ESCOLHER o exercício. Enquanto a
    #: tela só sabia abrir o próximo pendente, "Exercício 3/9" podia sair de
    #: `exercicios_concluidos + 1`: os concluídos eram sempre os anteriores.
    #: Escolhendo o último de uma ficha sem nada feito, aquela conta dizia
    #: "Exercício 1/2" na tela do segundo movimento.
    posicao_atual: int = 0
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
    #: O placar da folha de recompensa; só faz sentido com `concluido`.
    placar: object = None
    #: A opção da letra que está sendo feita hoje: a pinada pela primeira
    #: série (`escolha`), senão a variação do ciclo (`variacao_do_dia`).
    #: É contabilidade interna — a tela nunca imprime o número.
    opcao: int = 1
    opcoes: list = field(default_factory=list)
    versao: str = "completo"
    escolha: object = None
    #: Os exercícios que a versão rápida deixou de fora, nomeados na tela.
    removidos: list = field(default_factory=list)
    #: Os exercícios da ficha sem NENHUMA série hoje — o que o placar do
    #: treino parcial nomeia. Em memória, sobre os itens já carregados.
    pulados: list = field(default_factory=list)
    #: Os vizinhos na ordem da ficha, para as setas ‹ › da execução.
    item_anterior: object = None
    item_seguinte: object = None
    #: A pessoa tocou "Encerrar treino" hoje (`EscolhaDeTreino.encerrado_em`).
    #: Separa o placar de quem FECHOU a ficha inteira do de quem decidiu que
    #: acabou — a tela diz coisas diferentes, e "retomar" só existe no
    #: segundo caso.
    encerrado: bool = False

    @property
    def tem_duas_opcoes(self) -> bool:
        return len(self.opcoes) > 1

    @property
    def rapida(self) -> bool:
        return self.versao == VersaoDoTreino.RAPIDO
    #: Existe um plano ativo? Separa "hoje é descanso" de "a ficha ainda não
    #: foi montada" — dois estados que a Home mostrava com a mesma frase, e o
    #: segundo era o de toda conta recém-criada até abrir a aba de Treino.
    tem_ficha: bool = False

    @property
    def tem_treino(self) -> bool:
        return self.sessao is not None and bool(self.itens)

    @property
    def comecou(self) -> bool:
        return self.series_feitas > 0

    @property
    def descanso_relogio(self) -> str:
        """O descanso em `m:ss`, UM formato só (22/09/2026).

        A tela mostrava "79s" e virava "1:13" no meio da contagem — dois
        formatos para o mesmo número, e a pessoa relê para entender. O
        JavaScript escreve o mesmo formato a cada segundo; este aqui é o
        primeiro quadro, o que o servidor manda pronto."""
        minutos, segundos = divmod(max(0, int(self.descanso_restante)), 60)
        return "%d:%02d" % (minutos, segundos)


def proximo_treino(sessions, plan=None, hoje=None, linhas=None):
    """Qual treino vem a seguir, para o dia em que hoje é descanso.

    Sai de `weekday`, que a pessoa escolheu no cadastro — não é previsão. Anda
    os sete dias seguintes e devolve o primeiro que tem sessão, com quantos
    dias faltam, para a tela poder dizer "amanhã" em vez de repetir o nome do
    dia da semana. Com a rotação contínua a letra do próximo dia sai da DATA
    dele (`sessao_do_dia`): a segunda-feira que vem pode ser C, e não a A
    desta semana.
    """
    if not sessions:
        return None

    if ciclo_roda(plan):
        hoje_data = hoje or timezone.localdate()
        for adiante in range(1, 8):
            sessao = sessao_do_dia(plan, hoje_data + timedelta(days=adiante), linhas)
            if sessao is not None:
                return {"session": sessao, "dias": adiante}
        return None

    hoje = timezone.localdate().weekday()
    for adiante in range(1, 8):
        alvo = (hoje + adiante) % 7
        sessao = next((s for s in sessions if s.weekday == alvo), None)
        if sessao is not None:
            return {"session": sessao, "dias": adiante}
    return None


def escolha_do_dia(user, dia=None):
    """A opção que a pessoa escolheu hoje, ou `None`."""
    dia = dia or timezone.localdate()
    return (
        EscolhaDeTreino.objects.filter(user=user, date=dia)
        .select_related("session")
        .first()
    )


def usos_recentes(nome: str, dias: int = 30) -> tuple[int, int]:
    """(usos, pessoas) de um `EventoDeProduto` nos últimos `dias` — hoje
    inclusive, então `dias=30` cobre 30 dias corridos. Uso é pessoa × dia
    (a constraint do modelo já colapsa o toque repetido); pessoa é distinta.
    É a conta que `medir_progressao` imprime para decidir a versão rápida."""
    from .models import EventoDeProduto

    desde = timezone.localdate() - timedelta(days=dias - 1)
    eventos = EventoDeProduto.objects.filter(nome=nome, date__gte=desde)
    return eventos.count(), eventos.values("user_id").distinct().count()


def variacao_do_dia(plan, dia, sessao, sessoes=None) -> int:
    """A opção da letra em `dia` — decidida pelo CICLO, não pela pessoa
    (ficha única por letra, 17/09/2026).

    Com a rotação contínua, `p` é a posição do dia no ciclo e `n` o número
    de letras: a letra cai a cada `n` posições, então `p // n` é quantas
    vezes ela já caiu desde a posição zero — a primeira ocorrência faz a
    opção 1, a segunda a 2, a terceira a 1 de novo. No plano preso ao dia
    da semana (antigo ou ajustado à mão) a ocorrência é a linha da letra
    dentro da semana, em ordem, mais as semanas desde a criação do plano.
    Com uma opção só, é ela.
    """
    opcoes = sessao.opcoes
    if len(opcoes) < 2:
        return opcoes[0]
    sessoes = list(sessoes if sessoes is not None else plan.sessions.all())
    if ciclo_roda(plan):
        dias = dias_de_treino_de(sessoes)
        letras = letras_do_ciclo(sessoes)
        ocorrencia = posicao_no_ciclo(plan.inicio_do_ciclo, dia, dias) // len(letras)
    else:
        da_letra = sorted((s for s in sessoes if s.label == sessao.label), key=lambda s: s.order)
        indice = next((k for k, s in enumerate(da_letra) if s.weekday == dia.weekday()), 0)
        criado = timezone.localtime(plan.created_at).date()
        semanas = (dia - timedelta(days=dia.weekday())) - (criado - timedelta(days=criado.weekday()))
        ocorrencia = max(0, semanas.days // 7) * len(da_letra) + indice
    return opcoes[ocorrencia % len(opcoes)]


def opcao_do_dia(user, sessao, dia=None, sessoes=None, escolha=_NAO_INFORMADO) -> int:
    """A opção que vale HOJE para esta sessão: a gravada pela primeira
    série (o dia fica pinado — a ficha não muda no meio do treino), senão
    a variação do ciclo. `escolha` já carregada evita a consulta."""
    dia = dia or timezone.localdate()
    if escolha is _NAO_INFORMADO:
        escolha = escolha_do_dia(user, dia)
    # Sem conferir `in sessao.opcoes`: `registrar_escolha` já gravou uma
    # opção válida, e a conferência custaria a consulta dos itens quando a
    # sessão veio de `escolha.session` (medido no POST da série: 21 > 20).
    if escolha is not None and escolha.session_id == sessao.pk:
        return escolha.opcao
    return variacao_do_dia(sessao.plan, dia, sessao, sessoes)


def registrar_escolha(user, sessao, opcao, versao=VersaoDoTreino.COMPLETO, dia=None):
    """Grava (ou atualiza) a escolha do dia. Uma por dia; idempotente."""
    dia = dia or timezone.localdate()
    if opcao not in sessao.opcoes:
        opcao = sessao.opcoes[0]
    if versao not in VersaoDoTreino.values:
        versao = VersaoDoTreino.COMPLETO
    escolha, criada = EscolhaDeTreino.objects.get_or_create(
        user=user, date=dia,
        defaults={"session": sessao, "opcao": opcao, "versao": versao},
    )
    if not criada and (escolha.session_id != sessao.pk or escolha.opcao != opcao or escolha.versao != versao):
        escolha.session = sessao
        escolha.opcao = opcao
        escolha.versao = versao
        escolha.save(update_fields=["session", "opcao", "versao"])
    return escolha


def encerrar_treino(user, sessao, dia=None):
    """A pessoa disse que acabou: o dia fecha e o placar abre (22/09/2026).

    Até aqui "concluído" era só a ficha inteira coberta, e quem parava no
    sexto de nove exercícios não tinha como fechar — a tela ficava em
    "Exercício 6/9" para sempre e o resumo do que foi feito nunca aparecia.
    O fecho é um carimbo na escolha do dia (uma linha por pessoa por dia,
    que já existe); nada é apagado, e retomar é tirar o carimbo.
    """
    dia = dia or timezone.localdate()
    escolha = escolha_do_dia(user, dia)
    if escolha is None:
        escolha = registrar_escolha(user, sessao, opcao_do_dia(user, sessao, dia), dia=dia)
    escolha.encerrado_em = timezone.now()
    escolha.save(update_fields=["encerrado_em"])
    return escolha


def retomar_treino(user, dia=None):
    """Encerrou sem querer: o carimbo sai e o treino continua de onde parou.

    Sem isto, um toque errado no "Encerrar" trancaria a pessoa no placar até
    o dia virar — e o app não apaga nada para "desfazer"."""
    dia = dia or timezone.localdate()
    escolha = escolha_do_dia(user, dia)
    if escolha is None or escolha.encerrado_em is None:
        return None
    escolha.encerrado_em = None
    escolha.save(update_fields=["encerrado_em"])
    return escolha


def series_registradas_hoje(user, sessao, dia=None) -> int:
    """Quantas séries de exercícios DESTA sessão a pessoa anotou hoje —
    qualquer opção. É o que decide se trocar de opção pede confirmação."""
    dia = dia or timezone.localdate()
    exercicios = {item.exercise_id for item in sessao.exercises.all()}
    return ExerciseLog.objects.filter(user=user, date=dia, exercise_id__in=exercicios).count()


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


def linhas_de_serie(item, load) -> list:
    """Uma linha por série PRESCRITA: o que foi anotado hoje e o que foi
    anotado NA MESMA SÉRIE da última vez.

    A fileira de pastilhas da tela é isto. A carga e as reps de hoje ficam
    dentro da pastilha — dá para ver que a terceira série caiu de 62,5 para 60
    sem abrir nada, e só cor diria "aconteceu" e reprovaria em daltonismo. A
    série da última vez entra em cinza enquanto a de hoje não existe: é o
    número que a pessoa está procurando na hora de escolher a anilha, e
    `load_history` já o trazia por série sem que tela nenhuma o lesse.

    Existiam DUAS cópias disto — aqui e em `views.set_rows` — e elas
    divergiam: uma carregava a série anterior, a outra não. A pesquisa de
    13/09/2026 achou a divergência; esta é a única cópia, e `views.set_rows`
    aponta para cá.

    Montado em Python e não no template porque a linguagem de template não
    sabe indexar por variável.
    """
    hoje = (load or {}).get("hoje") or {}
    anterior = (load or {}).get("anterior") or {}
    recorde = (load or {}).get("recorde_anterior")
    melhor = (load or {}).get("melhor_serie_anterior")
    linhas = []
    for numero in range(1, item.sets + 1):
        registro = hoje.get(numero)
        passado = anterior.get(numero)
        linhas.append(
            {
                "number": numero,
                "weight": registro.weight_kg if registro else None,
                "reps": registro.reps if registro else None,
                "antes_peso": passado.weight_kg if passado else None,
                "antes_reps": passado.reps if passado else None,
                # Só SUPERAR conta — a estreia num exercício é, tecnicamente,
                # a maior carga dele, e chamar isso de recorde seria confete
                # de estreia (`achievements.regras._recorde`).
                "recorde": bool(
                    registro is not None and recorde is not None
                    and registro.weight_kg is not None and registro.weight_kg > recorde
                ),
                # Segunda espécie, ao lado de "recorde": o maior reps×carga
                # de UMA série (achievements.regras._melhor_serie) — não é
                # a mesma pergunta que "recorde" (que só olha a carga).
                "melhor_serie": bool(
                    registro is not None and melhor is not None
                    and registro.weight_kg is not None and registro.reps is not None
                    and registro.weight_kg * registro.reps > melhor
                ),
                # O que a pessoa anotou naquela série (22/09/2026): a
                # observação e a falha vêm do registro de hoje, e é a tela
                # que decide mostrar. Sem consulta — já estão no `load`.
                "nota": getattr(registro, "nota", "") if registro else "",
                "falhou": bool(getattr(registro, "falhou", False)) if registro else False,
            }
        )
    return linhas


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
    # A adaptação decide a ABERTURA da sessão: o campo abre com o número da
    # frase — a carga nova ao subir, a maior da última vez ao manter (60/60/55
    # abre com 60 nas três séries, e não com 55 na terceira: frase == campo).
    # Hoje continua mandando — `ajuste` devolve `None` com série anotada hoje.
    progressao = getattr(item, "progressao", None)
    if progressao is not None:
        return progressao.valor
    anterior = (item.load or {}).get("anterior") or {}
    registro = anterior.get(serie)
    if registro is not None:
        return registro.weight_kg
    return (item.load or {}).get("melhor_anterior")


#: A REGRA MORA EM `workouts/adaptacao.py` (T2.1, 17/09/2026): módulo puro,
#: sem banco nem relógio, com o estado nomeado (`Estado`, `MUDA_CARGA`). Os
#: nomes seguem exportados daqui porque os testes de 13/09 os leem.
GRUPOS_INFERIORES = adaptacao.GRUPOS_INFERIORES
DEGRAU_MINIMO = adaptacao.DEGRAU_MINIMO
Progressao = adaptacao.Progressao


def proxima_carga(item):
    """Dupla progressão para a próxima sessão — o alias de `adaptacao.ajuste`
    sobre o que `load_history` já carregou no item (`sessoes`,
    `ultimo_registro`, `dia`). Compatível com o `load` antigo, que só tinha
    `anterior`: vira uma sessão de uma data só.

    A regra, dita inteira, está no módulo: RETOMAR com 21 dias ou mais sem
    série (mesma carga, a confirmar; SUBIR suspenso), SUBIR quando todas as
    séries prescritas da referência fecharam `rep_max` na MESMA carga
    (60/60/55 mantém 60 e diz por quê), ESTAGNADO depois de três sessões na
    mesma carga sem ganhar repetição (manter e dizer), MANTER com a razão
    quando não, `None` sem sessão completa recente, com série hoje, sem
    anilha. O prefill das reps é o risco conhecido: ao subir e ao retomar,
    `_sugestao_de_reps` volta ao piso da faixa, e a próxima subida exige
    fechar a faixa de novo.
    """
    load = item.load or {}
    sessoes = load.get("sessoes")
    if sessoes is None:
        anterior = load.get("anterior") or {}
        sessoes = [(load.get("data_anterior"), anterior)] if anterior else []
    return adaptacao.ajuste(item, sessoes, load.get("ultimo_registro"), load.get("dia"))


def _sugestao_de_reps(item, serie):
    """As repetições da série anterior — de hoje primeiro, como na carga."""
    if serie is None:
        return None
    de_hoje = _ultima_de_hoje(item)
    if de_hoje is not None and de_hoje.reps:
        return de_hoje.reps
    # Carga nova, reps no PISO da faixa: é a dupla progressão, e é o que
    # segura o prefill — subir de novo exige fechar a faixa de novo. Ao
    # RETOMAR (T2.3) também: a carga é a mesma, a confirmar, e o piso é o
    # teste de que ela ainda fecha.
    progressao = getattr(item, "progressao", None)
    if progressao is not None and progressao.estado in adaptacao.REPS_NO_PISO:
        return item.rep_min
    registro = ((item.load or {}).get("anterior") or {}).get(serie)
    if registro is not None:
        return registro.reps
    # SEM HISTÓRICO NENHUM, o piso da faixa (22/09/2026): o campo vazio com
    # o placeholder "6-10" gravava série sem repetição para quem tocava
    # "Concluir" sem digitar — e o placar do peso do corpo fechava em "0
    # repetições feitas". O piso é a mesma regra da carga nova.
    return item.rep_min or None


#: Quantas datas o histórico da leitura mostra. Doze é o que cabe numa tela
#: sem virar relatório; o Progresso é quem responde "estou evoluindo?".
DATAS_DO_HISTORICO = 12


def historico_do_exercicio(user, exercise, datas=DATAS_DO_HISTORICO) -> list:
    """As últimas `datas` sessões deste exercício: data, carga e reps por série.

    UMA consulta, limitada no banco a `datas × 10` linhas (dez é o teto de
    séries por dia de `append_set`) e cortada em Python por data — o limite
    por data não existe em SQL sem janela, e a janela custaria mais que as
    poucas linhas a mais. Sem série registrada, lista vazia.

    "Como fui neste exercício?" é a pergunta; a resposta é o registro cru
    ("03/09 · 60 × 10, 10, 9"), sem e1RM nem volume — `progresso.py` já
    decidiu que a tela não inventa métrica.
    """
    linhas = (
        ExerciseLog.objects.filter(user=user, exercise=exercise)
        .order_by("-date", "set_number")[: datas * 10]
    )
    por_data = {}
    for log in linhas:
        if log.date not in por_data:
            if len(por_data) == datas:
                break
            por_data[log.date] = {"data": log.date, "carga": log.weight_kg, "reps": []}
        sessao = por_data[log.date]
        sessao["carga"] = max(sessao["carga"], log.weight_kg) if log.weight_kg is not None else sessao["carga"]
        sessao["reps"].append(log.reps if log.reps is not None else "—")
    return list(por_data.values())


def prescricao_de_hoje(user, exercise_id, dia=None):
    """Quantas séries este exercício pede HOJE, na opção e versão do dia.

    A sessão guarda as opções; `.first()` sem filtro devolveria a opção 1
    mesmo quando a pessoa está fazendo a 2, e a versão rápida reduz série
    só em memória. Devolve `None` fora da sessão de hoje. Custa a consulta
    da escolha mais a da linha; na versão rápida, mais a lista da opção.
    """
    from . import opcoes as motor_de_opcoes

    dia = dia or timezone.localdate()
    escolha = escolha_do_dia(user, dia)
    sessao = escolha.session if escolha is not None else sessao_do_dia(get_active_routine(user), dia)
    if sessao is None:
        return None
    # A opção do dia: a pinada, senão a variação do ciclo (ficha única).
    opcao = opcao_do_dia(user, sessao, dia, escolha=escolha)
    linhas = SessionExercise.objects.filter(session_id=sessao.pk, opcao=opcao)
    # A linha que responde pelo exercício: a dele, ou a do original que a
    # pessoa trocou por ele ("outras formas") — mesma dose.
    item = _linha_do_exercicio(user, sessao.pk, opcao, exercise_id).first()
    if item is None:
        return None
    if escolha is not None and escolha.versao == VersaoDoTreino.RAPIDO:
        da_opcao = list(linhas.select_related("exercise", "session").order_by("order", "id"))
        graus = prioridades_da_sessao(da_opcao)
        sessao = da_opcao[0].session if da_opcao else None
        ficam, _ = motor_de_opcoes.versao_rapida(
            [(i, i.sets, g) for i, g in zip(da_opcao, graus)],
            sessao.main_groups if sessao else (),
        )
        reduzidas = {i.exercise_id: series for i, series in ficam}
        return reduzidas.get(item.exercise_id, 0)
    return item.sets


def series_de_hoje(user, exercise, dia=None) -> tuple:
    """(séries anotadas hoje, séries prescritas) deste exercício na sessão de hoje.

    UMA consulta no caminho comum: a prescrição da sessão de hoje com a
    contagem de hoje em subconsulta. Roda a cada série gravada — é o que
    decide se a tela diz "concluído · 4/4" —, e o orçamento do POST é
    medido em `test_recorde_na_hora`. Fora da sessão de hoje (série extra
    num exercício que não é de hoje) devolve `(anotadas, 0)` com uma segunda
    consulta: não há prescrição para fechar.
    """
    dia = dia or timezone.localdate()
    # DESDE 15/09/2026 a prescrição é a da OPÇÃO do dia: a escolha (uma
    # consulta) filtra a linha, e a contagem continua em subconsulta. Na
    # versão rápida a prescrição é a reduzida (`prescricao_de_hoje`).
    escolha = escolha_do_dia(user, dia)
    if escolha is not None and escolha.versao == VersaoDoTreino.RAPIDO:
        prescritas = prescricao_de_hoje(user, exercise.pk, dia)
        feitas = ExerciseLog.objects.filter(user=user, exercise=exercise, date=dia).count()
        return feitas, prescritas or 0
    # A contagem é do exercício FEITO (o pedido), e não do da linha: com
    # "outras formas" a linha é a do original e a série está no substituto.
    contagem = (
        ExerciseLog.objects.filter(user=user, exercise_id=exercise.pk, date=dia)
        .order_by().values("user").annotate(n=Count("pk")).values("n")[:1]
    )
    # A sessão de hoje é a da LETRA de hoje: a escolha gravada já a traz;
    # sem escolha, `sessao_do_dia` a acha (plano + linhas, duas consultas
    # a mais só na primeira série do dia).
    sessao = escolha.session if escolha is not None else sessao_do_dia(get_active_routine(user), dia)
    if sessao is None:
        return ExerciseLog.objects.filter(user=user, exercise=exercise, date=dia).count(), 0
    linhas = _linha_do_exercicio(user, sessao.pk, opcao_do_dia(user, sessao, dia, escolha=escolha), exercise.pk)
    item = linhas.annotate(feitas=Subquery(contagem)).values_list("sets", "feitas").first()
    if item is None:
        return ExerciseLog.objects.filter(user=user, exercise=exercise, date=dia).count(), 0
    prescritas, feitas = item
    return feitas or 0, prescritas


def serie_pendente(user, exercise_id, dia=None) -> bool:
    """Este exercício ainda tem série por fazer HOJE?

    É a pergunta que `ConcluirSerieView` faz para devolver a pessoa ao
    exercício em foco depois de gravar: enquanto houver série pendente, a
    tela reabre nele; fechada a última, o parâmetro sobraria e a tela volta a
    escolher o próximo sozinha. Duas consultas (a sessão do dia e a contagem
    de hoje), e não o `estado_do_treino` inteiro, porque isto roda a cada
    série gravada. Exercício que não é da sessão de hoje responde `False`.
    """
    dia = dia or timezone.localdate()
    prescritas = prescricao_de_hoje(user, exercise_id, dia)
    if not prescritas:
        return False
    feitas = ExerciseLog.objects.filter(
        user=user, exercise_id=exercise_id, date=dia
    ).count()
    return feitas < prescritas


def supera_recorde(user, exercise, weight_kg, reps=None, dia=None) -> set:
    """Que recordes esta série supera: `{"carga"}`, `{"melhor_serie"}`, os dois, ou nada.

    Duas espécies, o mesmo contrato de `achievements.regras._recorde`: só
    SUPERAR conta, contra dias ANTERIORES a `dia`; estreia é o conjunto vazio.
    "carga" é a maior carga já registrada; "melhor_serie" é o maior produto
    reps×carga de UMA série — 60 kg × 12 supera 60 kg × 10 sem mexer na carga,
    que é o segundo eixo da dupla progressão e o que Hevy e Strong celebram
    (BENCHMARK-2026-09, padrão a).

    É a pergunta barata que decide se vale rodar `achievements.avaliar` na
    hora: o catálogo inteiro custa 43 consultas (medido em 13/09/2026), e as
    únicas regras que dependem do DIA são estas duas — as outras têm chave
    sem data e podem esperar a próxima visita a /conquistas/. Uma consulta
    aqui contra 43 em toda série; quando um recorde acontece, o catálogo roda.

    Uma consulta com duas agregações, porque isto roda em TODA série
    concluída (`ConcluirSerieView`) e o orçamento do POST é medido.
    """
    dia = dia or timezone.localdate()
    anteriores = ExerciseLog.objects.filter(
        user=user, exercise=exercise, date__lt=dia, weight_kg__isnull=False
    )
    agregado = anteriores.aggregate(
        maior=Max("weight_kg"),
        melhor=Max(
            ExpressionWrapper(
                F("weight_kg") * F("reps"),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            filter=Q(reps__isnull=False),
        ),
    )
    especies = set()
    if agregado["maior"] is not None and weight_kg > agregado["maior"]:
        especies.add("carga")
    if (
        reps is not None
        and agregado["melhor"] is not None
        and weight_kg * reps > agregado["melhor"]
    ):
        especies.add("melhor_serie")
    return especies


class ExercicioForaDaSessao(LookupError):
    """Pediram um exercício que não é do treino de hoje desta pessoa.

    É uma condição de PEDIDO, não de dados: o id chegou pela barra de endereço.
    Ela cobre num lugar só o link velho, o id inventado, o exercício de outra
    sessão e o de outra conta — porque `estado_do_treino` só enxerga a sessão
    de hoje do próprio usuário, e "não está aqui" é a mesma resposta para os
    quatro.

    Quem a converte em 404 é `ModoTreinoView`. O serviço não sabe de HTTP.
    """


def estado_do_treino(user, dia=None, escolhido=None, opcao=None, versao=None) -> EstadoDoTreino:
    """O treino de hoje com o ponto exato em que a pessoa parou.

    O exercício atual é o PRIMEIRO da ficha que ainda não tem todas as séries
    prescritas anotadas — não o primeiro sem nenhuma. A diferença aparece no
    caso mais comum do modo guiado: quem anotou duas de quatro séries do supino
    continua no supino, e a regra antiga (`not item.feitas`) já teria passado
    para o próximo exercício.

    `escolhido` é o id do EXERCÍCIO que a pessoa tocou na ficha, e ele vence a
    escolha automática. O fluxo do app passou a ser "ficha primeiro, exercício
    depois": a tela de treino leva à ficha, a ficha lista tudo, e é a pessoa
    que escolhe por onde começar. Sem este argumento a execução só sabia abrir
    o próximo pendente, e quem quisesse fazer a panturrilha antes do
    agachamento não tinha como pedir.

    ID QUE NÃO É DA SESSÃO DE HOJE LEVANTA `ExercicioForaDaSessao`, e não cai
    na escolha automática. A primeira versão desta função fazia `pedido or
    atual`, e o silêncio era o defeito: um link velho, um id de outra sessão ou
    um id de outra conta abriam a tela do PRIMEIRO PENDENTE — com o vídeo dele
    tocando — como se nada tivesse acontecido. A pessoa via um exercício que
    não pediu e não tinha como saber; e um link quebrado que "funciona" nunca
    é consertado.

    O que ele NÃO faz: não grava nada, não muda progresso e não reordena a
    ficha. É uma leitura — o mesmo `EstadoDoTreino` derivado de `ExerciseLog`,
    com outro item em foco. Escolher um exercício JÁ CONCLUÍDO é legítimo (a
    pessoa quer conferir a carga que fez), e não corrompe contagem nenhuma:
    `exercicios_concluidos`, `concluido` e `proximo` continuam saindo da ficha
    inteira, e não do item em foco.
    """
    dia = dia or timezone.localdate()
    estado = EstadoDoTreino()

    # O plano, as sessões, os itens e as trocas numa consulta só (21/09/2026).
    plan, linhas, trocas = rotina_ativa_com_linhas(user)
    if plan is None:
        # SEM FICHA NÃO HÁ ESCOLHA VÁLIDA. O retorno adiantado pulava a
        # validação: pedir um exercício num dia sem treino devolvia a tela de
        # descanso com 200, e o link quebrado continuava parecendo bom.
        if escolhido is not None:
            raise ExercicioForaDaSessao(escolhido)
        return estado
    estado.tem_ficha = True
    estado.plan = plan

    # A sessão de HOJE é a da LETRA de hoje (rotação contínua), vestindo o
    # dia da semana: todas as linhas da semana, que é o que `sessao_do_dia`
    # precisa para achar a posição — já vieram com o plano.
    estado.linhas = linhas
    # "Outras formas": a troca da pessoa veste as linhas ANTES de tudo, então
    # a execução, a contagem e o histórico são do exercício feito.
    aplicar_trocas(user, linhas, trocas)
    sessao = sessao_do_dia(plan, dia, linhas)
    if sessao is None:
        if escolhido is not None:
            raise ExercicioForaDaSessao(escolhido)
        return estado

    # A OPÇÃO DO DIA: a pedida, senão a gravada hoje, senão a recomendada.
    # A versão rápida é a opção passando por `versao_rapida` — os itens são
    # os mesmos objetos, com `sets` reduzido em memória (nada é gravado), e o
    # que saiu fica nomeado em `removidos`.
    from . import opcoes as motor_de_opcoes

    escolha = escolha_do_dia(user, dia)
    if escolha is not None and escolha.session_id != sessao.pk:
        escolha = None
    estado.escolha = escolha
    estado.opcoes = sessao.opcoes
    if opcao is None:
        opcao = opcao_do_dia(user, sessao, dia, linhas, escolha=escolha)
    if opcao not in estado.opcoes:
        opcao = estado.opcoes[0]
    if versao is None:
        versao = escolha.versao if escolha is not None else VersaoDoTreino.COMPLETO
    estado.opcao = opcao
    estado.versao = versao
    itens = sessao.da_opcao(opcao)
    if versao == VersaoDoTreino.RAPIDO and itens:
        graus = prioridades_da_sessao(itens)
        ficam, removidos = motor_de_opcoes.versao_rapida(
            [(item, item.sets, grau) for item, grau in zip(itens, graus)],
            sessao.main_groups,
        )
        for item, series in ficam:
            item.sets = series
        estado.removidos = removidos
        itens = [item for item, _ in ficam]
    historico = load_history(user, [item.exercise for item in itens], day=dia)
    # `getattr` e não `user.profile`: quem chega aqui já passou pelo
    # onboarding, mas o perfil pode não estar em cache, e `""` (não
    # respondeu) tem de virar o texto do intermediário, nunca um erro.
    perfil = getattr(user, "profile", None)
    experiencia = getattr(perfil, "experiencia", "") or ""
    # 65+ nunca lê "falha" (T2.2): a idade sai do perfil já carregado, no
    # mesmo ponto que a experiência — zero consulta a mais.
    cauteloso = (
        perfil is not None
        and getattr(perfil, "birth_date", None) is not None
        and perfil.age >= IDADE_CAUTELOSA
    )

    for item in itens:
        item.load = historico.get(item.exercise_id) or {}
        feitas = (item.load or {}).get("hoje") or {}
        item.series_hoje = feitas
        item.feitas = len(feitas)
        item.concluido = item.feitas >= item.sets
        item.proxima_serie = _primeira_serie_livre(feitas, item.sets)
        # A série que a tela PREVÊ registrar. Com série livre é ela; com o
        # exercício concluído é a seguinte — a extra que a pessoa pode pedir
        # (`?extra=1`). `proxima_serie` continua `None` no concluído, e é isso
        # que o template lê para trocar o formulário pelo ramo "concluído":
        # "Série None de 4" foi o que a tela mostrava sem esse ramo (UX P1-06).
        item.serie_prevista = item.proxima_serie or item.feitas + 1
        item.pct = (
            round(min(item.feitas, item.sets) * 100 / item.sets) if item.sets else 0
        )
        # A progressão vem ANTES das sugestões: as duas a leem.
        item.progressao = proxima_carga(item)
        # A última vez, para a tela dizer "42,5 kg × 6" ACIMA do campo de
        # carga — que é onde se escolhe a anilha. Em memória, sobre o que
        # `load_history` já trouxe.
        item.ultima_vez = ultima_serie_anterior(item.load)
        item.sugestao_carga = _sugestao_de_carga(item, item.serie_prevista)
        item.sugestao_reps = _sugestao_de_reps(item, item.serie_prevista)
        # A instrução de esforço da série da vez, pelo nível da pessoa. Uma
        # leitura do perfil para a sessão inteira, feita acima.
        item.esforco = instrucao_de_esforco(item, item.serie_prevista, experiencia, cauteloso)
        item.set_rows = linhas_de_serie(item, item.load)

    pendente = next((item for item in itens if not item.concluido), None)
    atual = pendente
    if escolhido is not None:
        atual = next(
            (item for item in itens if item.exercise_id == escolhido), None
        )
        if atual is None:
            # SEM FALLBACK. Ver a docstring: cair no próximo pendente aqui
            # abriria o vídeo de um exercício que ninguém pediu.
            raise ExercicioForaDaSessao(escolhido)

    proximo = None
    if atual is not None:
        depois = itens[itens.index(atual) + 1:]
        proximo = next((item for item in depois if not item.concluido), None)
        # NADA PENDENTE DEPOIS, mas ainda há pendente ANTES — acontece quando a
        # pessoa escolhe um exercício já concluído no fim da ficha. "Depois:
        # último exercício do treino" seria mentira com três séries faltando lá
        # em cima, então o ponteiro volta para o primeiro que falta.
        if proximo is None and pendente is not None and pendente is not atual:
            proximo = pendente

    estado.sessao = sessao
    estado.itens = itens
    estado.atual = atual
    estado.proximo = proximo
    # NAVEGAR SEM SAIR DA EXECUÇÃO (22/09/2026): os vizinhos na ORDEM da
    # ficha, e não o "próximo pendente" — as setas são o índice do treino, e
    # pular o que já foi feito faria a seta esquerda voltar para lugares
    # diferentes conforme o que já está registrado. Em memória.
    if atual is not None:
        posicao = itens.index(atual)
        estado.item_anterior = itens[posicao - 1] if posicao > 0 else None
        estado.item_seguinte = itens[posicao + 1] if posicao + 1 < len(itens) else None
    estado.total_exercicios = len(itens)
    estado.posicao_atual = itens.index(atual) + 1 if atual is not None else 0
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
    # `concluido` continua olhando a FICHA, não o item em foco: escolher um
    # exercício já feito não pode fazer a tela dizer que o treino acabou, nem o
    # contrário.
    #
    # E DESDE 22/09/2026 ele também é verdade quando a pessoa DISSE que
    # acabou (`EscolhaDeTreino.encerrado_em`): quem para no sexto de nove
    # exercícios terminou o treino dela, e a tela precisa saber fechar. O
    # placar sabe a diferença — ele conta séries feitas CONTRA prescritas e
    # nomeia o que ficou de fora.
    estado.encerrado = escolha is not None and escolha.encerrado_em is not None
    estado.pulados = [item for item in itens if not item.feitas]
    estado.concluido = bool(itens) and (
        estado.encerrado or not any(not item.concluido for item in itens)
    )

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
    # O placar da recompensa (CORTE, T3.6): só quando a ficha inteira está
    # coberta — e sem consulta nova, porque `item.load` já tem tudo.
    if estado.concluido:
        estado.placar = placar_do_treino(itens)
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
