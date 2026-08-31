"""O catálogo de conquistas — em código, porque conquista é regra.

CADA REGRA AQUI PRECISA SER PROVÁVEL COM O QUE O BANCO JÁ TEM. Não existe
conquista de corrida, de passos, de medida corporal, de sono nem de desafio,
porque nenhum desses dados existe no NutriPlan hoje — e uma conquista que o app
não consegue verificar é uma promessa que ele vai quebrar.

O que sustenta as regras de treino é um contrato que já estava no projeto e não
foi reinventado aqui: **um dia conta como treinado quando existe pelo menos um
`ExerciseLog` naquela data.** É exatamente o que `plans/streaks.py` usa para a
ofensiva, e ter duas definições de "treinou" seria a forma mais rápida de o
número da tela discordar do número do card.

COMO ACRESCENTAR UMA CONQUISTA
------------------------------

Escreva um detector `def _minha(dados) -> list[tuple[chave, contexto]]` e
acrescente uma `Regra` ao `CATALOGO`. Nada de migration, nada de seed: o
catálogo é esta lista. Se a conquista precisar de um dado que `Dados` ainda não
carrega, o campo entra lá — e é nesse momento que se descobre se ela é mesmo
verificável.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Callable


class Familia:
    """Para agrupar na tela e para o card saber que cara ter.

    As quatro últimas não têm regra nenhuma ainda. Estão escritas porque o
    lugar delas já é conhecido, e porque enum que nasce fechado é enum que vira
    migration quando o produto cresce.
    """

    TREINO = "treino"
    OFENSIVA = "ofensiva"
    META = "meta"
    RECORDE = "recorde"

    # Reservadas. Sem regra e sem dado — ver o cabeçalho deste arquivo.
    DIETA = "dieta"
    PESO = "peso"
    CORRIDA = "corrida"
    DESAFIO = "desafio"


@dataclass(frozen=True)
class Dados:
    """Tudo o que os detectores precisam, lido UMA vez.

    Existe para a avaliação custar um punhado de consultas fixas em vez de uma
    por regra: `plans/test_stress.py` mede teto de consultas por tela, e uma
    lista de conquistas que cresce não pode arrastar o painel junto.
    """

    hoje: date
    #: Dias distintos com pelo menos uma série registrada.
    dias_treinados: int
    #: Dias de treino previstos no perfil (0 = segunda).
    previstos: frozenset
    #: Sequência atual da ofensiva, de `plans.streaks`.
    ofensiva: int
    #: Há ficha ATIVA? A ofensiva conta descanso como cumprido, e sem ficha
    #: não existe dia previsto — todo dia viraria descanso.
    tem_plano: bool = False
    #: Segunda-feira de cada semana em que TODOS os dias previstos foram
    #: treinados. Só semanas já fechadas ou a atual quando já completou.
    semanas_completas: tuple = ()
    #: Exercícios que ganharam recorde HOJE: (id, nome). A carga não entra —
    #: ver `_recorde`.
    recordes_hoje: tuple = ()


@dataclass(frozen=True)
class Regra:
    slug: str
    titulo: str
    #: A frase que explica, já pronta para a tela e para o card.
    frase: str
    emoji: str
    familia: str
    detectar: Callable
    #: Repetível pode acontecer mais de uma vez, com `chave` diferente.
    repetivel: bool = False
    #: Para a tela mostrar progresso honesto quando der. `None` = sem número.
    alvo: int = None
    #: De onde sai o "quanto já tenho" do progresso.
    progresso: Callable = None


# --------------------------------------------------------------- detectores


def _acumulado(campo, alvo, rotulo):
    """Detector de limiar: desbloqueia quando o número chega no alvo.

    Uma vez só, para sempre — a `chave` fica vazia e a constraint faz o resto.
    Cair de 10 treinos para 9 é impossível (não se apaga passado), mas mesmo
    que fosse, a conquista não seria retirada: ela registra que aconteceu.
    """

    def detectar(dados):
        atual = getattr(dados, campo)
        if atual >= alvo:
            return [("", {rotulo: alvo})]
        return []

    return detectar


def _ofensiva(alvo):
    """Limiar de ofensiva, com uma guarda que o limiar comum nao tem.

    `plans/streaks.py` conta descanso como dia cumprido — e faz certo, porque
    descansar E o plano num dia sem treino previsto. Mas isso tem uma
    consequencia na ponta: quem nao tem ficha ativa nao tem NENHUM dia
    previsto, todo dia vira descanso, e a sequencia cresce sozinha sem ninguem
    treinar.

    Na ofensiva do painel isso quase nao aparece, porque quem termina o
    onboarding ganha ficha. Numa CONQUISTA aparece muito: "30 dias de
    ofensiva" para quem nunca abriu o app seria a conquista se desmentindo
    sozinha. Entao aqui a sequencia so vale se existir pelo menos um dia
    treinado de verdade.
    """

    def detectar(dados):
        if not dados.tem_plano:
            return []
        if dados.dias_treinados >= 1 and dados.ofensiva >= alvo:
            return [("", {"dias": alvo})]
        return []

    return detectar


def _semana_completa(dados):
    """Cumpriu todos os dias de treino previstos de uma semana.

    Repetível, uma por semana, e a `chave` é a segunda-feira em formato ISO.
    Semana sem nenhum dia previsto não conta: quem não tem treino marcado não
    "completou" nada, e premiar isso tornaria a conquista uma mentira gentil.
    """
    return [
        (segunda.isoformat(), {"dias": len(dados.previstos)})
        for segunda in dados.semanas_completas
    ]


def _recorde(dados):
    """Nova carga máxima num exercício.

    CONTRATO, escrito porque "recorde" é ambíguo de propósito no mundo real:

      recorde = MAIOR CARGA JÁ REGISTRADA naquele exercício.

    Não é 1RM estimado, não é volume, não é carga por repetição. 100 kg × 1
    conta mais que 90 kg × 10 nesta definição, e isso é uma escolha — a
    alternativa seria uma fórmula escondida que ninguém consegue conferir
    olhando a própria ficha.

    E só conta quando SUPERA uma carga anterior. A primeira vez que alguém
    registra um exercício também é, tecnicamente, a maior carga dele ali; mas
    chamar isso de recorde transformaria a conquista em confete de estreia.

    A `chave` é `exercício:data`, e não `exercício:carga`. Dois motivos, e o
    segundo é o que decide: assim a carga não precisa ser persistida, e não
    pode vazar para dentro de um card que a pessoa manda para um grupo.
    """
    return [
        ("%d:%s" % (exercicio_id, dados.hoje.isoformat()), {"exercicio": nome})
        for exercicio_id, nome in dados.recordes_hoje
    ]


# ------------------------------------------------------------------ catálogo

_TREINOS = ((5, "5 treinos"), (10, "10 treinos"), (25, "25 treinos"),
            (50, "50 treinos"))
_OFENSIVAS = ((3, "3 dias"), (7, "7 dias"), (14, "14 dias"), (30, "30 dias"))

CATALOGO = [
    Regra(
        slug="primeiro-treino",
        titulo="Primeiro treino",
        frase="Você registrou seu primeiro treino.",
        emoji="\U0001f3c6",
        familia=Familia.TREINO,
        detectar=_acumulado("dias_treinados", 1, "treinos"),
        alvo=1,
        progresso=lambda d: d.dias_treinados,
    ),
]

CATALOGO += [
    Regra(
        slug="treinos-%d" % n,
        # Sem `.upper()`: ao lado de "Primeiro treino" e "Semana completa",
        # um "5 TREINOS" gritado quebra a consistencia da lista.
        titulo=rotulo.capitalize(),
        frase="Você treinou em %d dias diferentes." % n,
        emoji="\U0001f4aa",
        familia=Familia.TREINO,
        detectar=_acumulado("dias_treinados", n, "treinos"),
        alvo=n,
        progresso=lambda d: d.dias_treinados,
    )
    for n, rotulo in _TREINOS
]

CATALOGO += [
    Regra(
        slug="ofensiva-%d" % n,
        titulo="%s de ofensiva" % rotulo,
        frase="Você manteve a ofensiva por %d dias seguidos." % n,
        emoji="\U0001f525",
        familia=Familia.OFENSIVA,
        detectar=_ofensiva(n),
        alvo=n,
        progresso=lambda d: d.ofensiva,
    )
    for n, rotulo in _OFENSIVAS
]

CATALOGO += [
    Regra(
        slug="semana-completa",
        titulo="Semana completa",
        frase="Você cumpriu todos os treinos previstos da semana.",
        emoji="\U0001f4c5",
        familia=Familia.META,
        detectar=_semana_completa,
        repetivel=True,
    ),
    Regra(
        slug="novo-recorde",
        titulo="Novo recorde",
        frase="Você bateu sua maior carga num exercício.",
        emoji="\U0001f3cb",
        familia=Familia.RECORDE,
        detectar=_recorde,
        repetivel=True,
    ),
]

POR_SLUG = {regra.slug: regra for regra in CATALOGO}
