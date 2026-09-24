# -*- coding: utf-8 -*-
"""O RECORTE da tela de Progresso: período escolhido, cortado pela vida da conta.

Até 23/09/2026 cada seção da tela tinha o próprio horizonte, e todos fixos:
`workouts.progresso.SEMANAS = 8`, `tracking.agua_por_semana(semanas=8)`,
`weight_trend` com a série inteira. Três consequências, todas medidas numa
conta de três dias em produção (e6194b7): vinte e quatro linhas de semana,
sete delas começando ANTES de a conta existir, dezoito "—" e "0,0 km".

"Buraco na série é informação" continua verdade — e vale para buraco DENTRO
da série. Fora dela não há buraco: não havia app. Uma semana de 03/08 numa
conta de 21/09 não diz "você não treinou", diz "eu não sei o que perguntar".

Este módulo é a régua única disso, e tudo que a tela desenha passa por ele:

    janela(user, periodo)        -> o recorte, já cortado pelo cadastro
    dias_da_janela(janela)       -> os dias, para os heatmaps
    semanas_da_janela(janela)    -> as semanas, para as barras

A SEMANA DO CADASTRO é marcada `parcial`. Sem isso a média dela sairia
dividida por sete numa semana que teve três dias — a mesma mentira que
`tracking.agua_por_semana` já documenta para o dia sem registro, um degrau
acima.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Count as _Count
from django.utils import timezone

from plans.streaks import primeiro_dia_da_conta

#: Os três períodos, na ordem em que o seletor os mostra.
PERIODOS = ("semana", "mes", "trimestre")

#: O padrão é o MÊS, e não a semana: a pergunta desta tela é "para onde isso
#: está indo", e sete pontos raramente mostram direção. Trimestre como padrão
#: abriria a tela com noventa dias de nada para quem acabou de chegar.
PADRAO = "mes"

ROTULOS = {"semana": "Semana", "mes": "Mês", "trimestre": "3 meses"}
DIAS = {"semana": 7, "mes": 30, "trimestre": 90}


@dataclass(frozen=True)
class Janela:
    """O recorte de verdade — `inicio` já respeita o cadastro."""

    periodo: str
    inicio: date
    fim: date
    #: Quantos dias o período pediria se a conta fosse velha o bastante.
    pedido: int

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    @property
    def truncada(self) -> bool:
        """A conta é mais nova que o período pedido."""
        return self.dias < self.pedido

    @property
    def rotulo(self) -> str:
        return ROTULOS[self.periodo]


@dataclass(frozen=True)
class Semana:
    """Uma semana DENTRO da janela — as pontas são aparadas por ela."""

    inicio: date
    fim: date
    #: Segunda-feira de calendário, mesmo quando `inicio` é outro dia. É por
    #: ela que as séries agrupam, e ela é a chave estável entre consultas.
    ancora: date

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    @property
    def parcial(self) -> bool:
        return self.dias < 7


def periodo_valido(pedido) -> str:
    """`?p=` vem da URL, então vem de qualquer um. Lista fechada, como o
    `DESTINOS` do `next` da água: o que não está nela cai no padrão."""
    return pedido if pedido in PERIODOS else PADRAO


def janela(user, periodo, hoje=None) -> Janela:
    periodo = periodo_valido(periodo)
    fim = hoje or timezone.localdate()
    pedido = DIAS[periodo]
    inicio = fim - timedelta(days=pedido - 1)
    nasceu = primeiro_dia_da_conta(user)
    if nasceu is not None and nasceu > inicio:
        inicio = nasceu
    # Conta criada "no futuro" (relógio do servidor atrás do da máquina que
    # semeou) devolveria uma janela invertida, e todo laço abaixo giraria zero
    # vezes sem dizer por quê.
    if inicio > fim:
        inicio = fim
    return Janela(periodo=periodo, inicio=inicio, fim=fim, pedido=pedido)


def dias_da_janela(janela: Janela) -> list:
    return [janela.inicio + timedelta(days=n) for n in range(janela.dias)]


def semanas_da_janela(janela: Janela) -> list:
    """As semanas do recorte, da mais antiga para a mais nova.

    A âncora é sempre a segunda-feira de calendário — é a chave com que as
    consultas agrupam —, mas `inicio` e `fim` são aparados pela janela: a
    primeira semana costuma começar no dia do cadastro e a última termina
    hoje, porque amanhã ainda não aconteceu.
    """
    semanas = []
    ancora = janela.inicio - timedelta(days=janela.inicio.weekday())
    while ancora <= janela.fim:
        inicio = max(ancora, janela.inicio)
        fim = min(ancora + timedelta(days=6), janela.fim)
        semanas.append(Semana(inicio=inicio, fim=fim, ancora=ancora))
        ancora += timedelta(weeks=1)
    return semanas


# ===========================================================================
# O MAPA DO DIA (heatmap) e as BARRAS DA SEMANA
# ===========================================================================
#
# Uma consulta por ÁREA, e não uma por dia nem uma por semana: o mapa do dia
# é montado em Python sobre o resultado agregado, e as barras da semana são
# montadas sobre o mapa do dia. A janela tem no máximo noventa dias, então
# somar noventa dicionários custa menos que uma ida ao banco — e o orçamento
# de consultas desta tela (`plans/test_stress.py`) é o que não pode crescer
# com o tamanho do período.

#: Os estados de um quadrado do mapa. `DESCANSO` não é falha: o dia sem
#: treino combinado É o plano, e a régua da ofensiva já dizia isso.
FEITO = "feito"
DESCANSO = "descanso"
FALTOU = "faltou"
SEM_REGISTRO = "sem-registro"

#: Direção de uma tendência. `SEM_DIRECAO` existe porque um ponto só não tem
#: direção, e desenhar uma seta ali seria afirmar o que não se sabe.
SUBINDO = "subindo"
CAINDO = "caindo"
PARADO = "parado"
SEM_DIRECAO = ""


@dataclass(frozen=True)
class DiaDoMapa:
    data: date
    estado: str
    #: 0 a 4 — os degraus de cor do heatmap. `0` é o quadrado apagado.
    intensidade: int = 0
    #: O que a leitura de tela anuncia e o `title` mostra.
    titulo: str = ""


@dataclass(frozen=True)
class BarraDaSemana:
    semana: Semana
    valor: float
    #: O texto já formatado (a barra não sabe se é kg, ml ou km).
    rotulo: str
    #: 0 a 100 — altura da barra, relativa ao maior valor da série.
    altura: int = 0


@dataclass(frozen=True)
class Tile:
    chave: str
    titulo: str
    valor: str
    unidade: str = ""
    frase: str = ""
    direcao: str = SEM_DIRECAO
    variacao: float = None
    #: Só o tile de peso desenha linha; os outros ficam com a frase.
    pontos: tuple = ()
    media_movel: tuple = ()


def _numero(valor, casas=2) -> str:
    """pt-BR: vírgula decimal e ponto de milhar (a régua do `CLAUDE.md`)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _degrau(fracao) -> int:
    """0 a 4. O degrau 1 começa em QUALQUER coisa acima de zero: registrar
    pouco é diferente de não registrar, e o mapa existe para mostrar isso."""
    if fracao <= 0:
        return 0
    if fracao < 0.35:
        return 1
    if fracao < 0.7:
        return 2
    if fracao < 1:
        return 3
    return 4


# ------------------------------------------------------------------ treino
def mapa_de_treino(user, janela: Janela, dias_combinados=None) -> list:
    """Um quadrado por dia: treinado, descanso combinado ou falta.

    Duas consultas: os dias com série (agregada) e os dias combinados do
    perfil — e a segunda some quando quem chama já os tem na mão.
    """
    from workouts.models import ExerciseLog

    if dias_combinados is None:
        dias_combinados = set(
            user.training_days.values_list("weekday", flat=True)
        )
    por_dia = {
        linha["date"]: linha["series"]
        for linha in ExerciseLog.objects.filter(
            user=user, date__gte=janela.inicio, date__lte=janela.fim
        )
        .values("date")
        .annotate(series=_Count("pk"))
    }
    maior = max(por_dia.values(), default=0)
    mapa = []
    for dia in dias_da_janela(janela):
        series = por_dia.get(dia, 0)
        if series:
            estado, titulo = FEITO, "%d série%s" % (series, "s" if series > 1 else "")
            intensidade = _degrau(series / maior) if maior else 4
        elif dia.weekday() in dias_combinados:
            estado, intensidade, titulo = FALTOU, 0, "dia combinado, sem série"
        else:
            estado, intensidade, titulo = DESCANSO, 0, "descanso combinado"
        mapa.append(DiaDoMapa(data=dia, estado=estado, intensidade=intensidade,
                              titulo=titulo))
    return mapa


# ------------------------------------------------------------------- peso
def tile_de_peso(user, janela: Janela, pesagens=None) -> Tile:
    """Peso de hoje e a variação DENTRO do período — nunca desde sempre.

    "−0,5 kg" tem de responder à pergunta que o seletor faz. Com a série
    inteira, trocar de "Semana" para "3 meses" não mudaria o número, e o
    seletor viraria enfeite.
    """
    if pesagens is None:
        pesagens = list(
            user.weight_entries.filter(
                date__gte=janela.inicio, date__lte=janela.fim
            ).order_by("date").values("date", "weight_kg")
        )
    pontos = tuple((p["date"], float(p["weight_kg"])) for p in pesagens)
    if not pontos:
        return Tile(
            chave="peso", titulo="Peso", valor="—",
            frase="Registre uma pesagem para a linha começar.",
        )
    atual = pontos[-1][1]
    tile = {
        "chave": "peso", "titulo": "Peso", "valor": _numero(atual), "unidade": "kg",
        "pontos": pontos, "media_movel": _media_movel(pontos),
    }
    if len(pontos) == 1:
        return Tile(**tile, frase="Primeira pesagem — a tendência vem na segunda.")
    variacao = round(atual - pontos[0][1], 2)
    direcao = PARADO if abs(variacao) < 0.1 else (CAINDO if variacao < 0 else SUBINDO)
    sinal = "+" if variacao > 0 else "−"
    return Tile(
        **tile, variacao=variacao, direcao=direcao,
        frase="%s%s kg desde o início do período" % (sinal, _numero(abs(variacao))),
    )


#: Sete dias, como manda a prática de balança — e só a partir de TRÊS
#: pesagens: com duas a "média móvel" seria a própria linha, deslocada.
JANELA_DA_MEDIA = 7
MINIMO_PARA_MEDIA = 3


def _media_movel(pontos) -> tuple:
    """Vazia quando ela seria a PRÓPRIA linha, deslocada de nada.

    Com pesagem semanal — que é o que a maioria faz — cada janela de sete
    dias contém um ponto só, e a "média móvel" sai idêntica à série: uma
    segunda linha invisível embaixo da primeira, e uma legenda prometendo
    o que não se vê. MEDIDO na captura de 23/09/2026, com quatro pesagens
    espaçadas de sete dias.
    """
    if len(pontos) < MINIMO_PARA_MEDIA:
        return ()
    if not any(
        sum(1 for d, _ in pontos[: n + 1] if d >= dia - timedelta(days=JANELA_DA_MEDIA - 1)) > 1
        for n, (dia, _) in enumerate(pontos)
    ):
        return ()
    saida = []
    for n, (dia, _) in enumerate(pontos):
        limite = dia - timedelta(days=JANELA_DA_MEDIA - 1)
        janela_de_pontos = [v for d, v in pontos[: n + 1] if d >= limite]
        saida.append((dia, round(sum(janela_de_pontos) / len(janela_de_pontos), 2)))
    return tuple(saida)


def barras(semanas, valor_por_dia, formato, media=False) -> list:
    """As barras da semana, montadas SOBRE o mapa do dia — zero consultas.

    `valor_por_dia` é `{data: número}`. `media=True` divide pelos dias que
    TÊM valor, e não pelos sete da semana: é a mesma regra que
    `tracking.agua_por_semana` já documentava, e a razão é a mesma — quem
    esqueceu de anotar não bebeu zero, o app só não sabe. Com `media=False`
    a barra é a soma (km, séries), onde o dia sem registro é zero de verdade.
    """
    linhas = []
    for semana in semanas:
        dias = [
            valor_por_dia.get(semana.inicio + timedelta(days=n), 0)
            for n in range(semana.dias)
        ]
        com_valor = [v for v in dias if v]
        if media:
            valor = sum(com_valor) / len(com_valor) if com_valor else 0
        else:
            valor = sum(dias)
        linhas.append(BarraDaSemana(semana=semana, valor=valor, rotulo=formato(valor)))
    maior = max((linha.valor for linha in linhas), default=0)
    return [
        BarraDaSemana(
            semana=linha.semana, valor=linha.valor, rotulo=linha.rotulo,
            altura=int(round(linha.valor * 100 / maior)) if maior else 0,
        )
        for linha in linhas
    ]


def sequencia_atual(mapa) -> int:
    """Dias seguidos, de hoje para trás, sem falha. `DESCANSO` não quebra —
    descansar no dia combinado para descansar é cumprir o plano."""
    conta = 0
    for dia in reversed(mapa):
        if dia.estado == FALTOU:
            break
        if dia.estado == FEITO:
            conta += 1
    return conta


# ------------------------------------------------------------- alimentação
def mapa_de_dieta(user, janela: Janela, linhas=None) -> list:
    """Um quadrado por dia, com a aderência daquele dia como intensidade.

    Reusa `tracking.history`, que já devolve por dia o feito e o previsto
    pelo PLANO daquele dia — e é a mesma leitura que a tabela "dia a dia"
    imprime. Duas telas, uma fonte.
    """
    from plans import tracking

    if linhas is None:
        linhas = tracking.history(user, days=janela.dias)
    por_dia = {linha["date"]: linha for linha in linhas}
    mapa = []
    for dia in dias_da_janela(janela):
        linha = por_dia.get(dia)
        if not linha or not linha.get("previstas"):
            mapa.append(DiaDoMapa(data=dia, estado=SEM_REGISTRO,
                                  titulo="sem registro"))
            continue
        fracao = linha["done"] / linha["previstas"]
        mapa.append(DiaDoMapa(
            data=dia, estado=FEITO if linha["done"] else SEM_REGISTRO,
            intensidade=_degrau(fracao),
            titulo="%d de %d refeições" % (linha["done"], linha["previstas"]),
        ))
    return mapa


def receitas_mais_registradas(user, janela: Janela, quantas=3) -> list:
    """"O que mais você registrou" — uma consulta agregada.

    `recipe_name` e não a opção: o nome é COPIADO para o registro no momento
    da marcação (plano é retrato), então ele continua certo mesmo depois de o
    cardápio ser remontado.
    """
    from plans.models import MealLog, MealStatus

    return list(
        MealLog.objects.filter(
            user=user, date__gte=janela.inicio, date__lte=janela.fim,
            status=MealStatus.DONE,
        )
        .exclude(recipe_name="")
        .values("recipe_name")
        .annotate(vezes=_Count("pk"))
        .order_by("-vezes", "recipe_name")[:quantas]
    )


# -------------------------------------------------------------------- água
def mapa_de_agua(user, janela: Janela, meta_ml=0) -> list:
    """Um quadrado por dia, com a fração da meta como intensidade."""
    from plans.models import HydrationLog

    por_dia = {
        linha["date"]: linha["ml"]
        for linha in HydrationLog.objects.filter(
            user=user, date__gte=janela.inicio, date__lte=janela.fim, ml__gt=0
        ).values("date", "ml")
    }
    mapa = []
    for dia in dias_da_janela(janela):
        ml = por_dia.get(dia, 0)
        if not ml:
            mapa.append(DiaDoMapa(data=dia, estado=SEM_REGISTRO, titulo="sem registro"))
            continue
        mapa.append(DiaDoMapa(
            data=dia, estado=FEITO,
            intensidade=_degrau(ml / meta_ml) if meta_ml else 4,
            titulo="%s ml" % _numero(ml, 0),
        ))
    return mapa


# ----------------------------------------------------------------- corrida
def mapa_de_corrida(user, janela: Janela) -> list:
    """Um quadrado por dia, com a distância como intensidade."""
    from workouts.models import Corrida

    por_dia = {}
    for corrida in Corrida.objects.filter(
        user=user, comecou_em__date__gte=janela.inicio,
        comecou_em__date__lte=janela.fim,
    ).values("comecou_em", "distancia_m", "duracao_s"):
        dia = timezone.localtime(corrida["comecou_em"]).date()
        acumulado = por_dia.setdefault(dia, {"m": 0, "s": 0})
        acumulado["m"] += corrida["distancia_m"] or 0
        acumulado["s"] += corrida["duracao_s"] or 0
    maior = max((v["m"] for v in por_dia.values()), default=0)
    mapa = []
    for dia in dias_da_janela(janela):
        dados = por_dia.get(dia)
        if not dados:
            mapa.append(DiaDoMapa(data=dia, estado=SEM_REGISTRO, titulo="sem corrida"))
            continue
        mapa.append(DiaDoMapa(
            data=dia, estado=FEITO,
            intensidade=_degrau(dados["m"] / maior) if maior else 4,
            titulo="%s km" % _numero(dados["m"] / 1000, 1),
        ))
    return mapa, por_dia


# --------------------------------------------------------------- recordes
def recordes(user, quantos=5) -> list:
    """A carga máxima por exercício, com a data — e de SEMPRE, não do período.

    Recorde que expira com o seletor não é recorde; o que o período recorta é
    a evolução, não a marca. `DISTINCT ON` é do PostgreSQL, que é o banco
    deste projeto em dev, staging e produção: uma consulta devolve a linha
    inteira do máximo de cada exercício, com data, sem um segundo passe.
    """
    from workouts.models import ExerciseLog

    melhores = (
        ExerciseLog.objects.filter(user=user, weight_kg__gt=0)
        .order_by("exercise_id", "-weight_kg", "-date")
        .distinct("exercise_id")
        .values("exercise__name", "weight_kg", "reps", "date")
    )
    return sorted(melhores, key=lambda r: r["weight_kg"], reverse=True)[:quantos]


# ===========================================================================
# OS QUATRO TILES DO CABEÇALHO
# ===========================================================================
#
# Eles substituem a faixa de três números que misturava HOJE com HISTÓRICO
# ("2/3 refeições hoje" ao lado de "1301 kcal/dia" e "1 dias com registro").
# Cada um responde pelo PERÍODO escolhido, e cada um traz direção — que é o
# que transformava a faixa num extrato.


def tile_de_treino(mapa, dias_combinados) -> Tile:
    feitos = sum(1 for dia in mapa if dia.estado == FEITO)
    previstos = sum(1 for dia in mapa if dia.estado in (FEITO, FALTOU))
    if not previstos:
        return Tile(chave="treino", titulo="Treinos", valor=str(feitos),
                    frase="Sem dia de treino combinado no período.")
    direcao = SUBINDO if feitos >= previstos else (PARADO if feitos else CAINDO)
    return Tile(
        chave="treino", titulo="Treinos", valor=str(feitos),
        unidade="de %d" % previstos, direcao=direcao,
        frase="%d dia%s combinado%s no período"
              % (previstos, "s" if previstos > 1 else "", "s" if previstos > 1 else ""),
    )


def tile_de_dieta(mapa_dieta, linhas) -> Tile:
    """Aderência dos dias FECHADOS, pela mesma régua de `tracking.adherence`:
    hoje ainda está acontecendo e não é nota."""
    fechados = [linha for linha in linhas if not linha.get("is_today")]
    feitas = sum(linha["done"] for linha in fechados)
    previstas = sum(linha.get("previstas", 0) for linha in fechados)
    if not previstas:
        return Tile(chave="dieta", titulo="Cardápio", valor="—",
                    frase="Marque uma refeição para a aderência começar.")
    pct = int(round(feitas * 100 / previstas))
    direcao = SUBINDO if pct >= 80 else (PARADO if pct >= 50 else CAINDO)
    return Tile(
        chave="dieta", titulo="Cardápio", valor=str(pct), unidade="%",
        direcao=direcao,
        frase="%d de %d refeições nos dias fechados" % (feitas, previstas),
    )


def tile_de_agua(mapa_agua, por_dia_ml, meta_ml) -> Tile:
    com_registro = [v for v in por_dia_ml.values() if v]
    if not com_registro:
        return Tile(chave="agua", titulo="Água", valor="—",
                    frase="Nenhum copo registrado no período.")
    media = sum(com_registro) / len(com_registro)
    direcao = SEM_DIRECAO
    if meta_ml:
        direcao = SUBINDO if media >= meta_ml * 0.9 else (
            PARADO if media >= meta_ml * 0.6 else CAINDO)
    frase = "média dos %d dia%s com registro" % (
        len(com_registro), "s" if len(com_registro) > 1 else "")
    if meta_ml:
        frase = "meta %s ml · %s" % (_numero(meta_ml, 0), frase)
    return Tile(chave="agua", titulo="Água", valor=_numero(media, 0),
                unidade="ml", direcao=direcao, frase=frase)


# ===========================================================================
# reunir(): TUDO que a tela precisa, com o custo escrito
# ===========================================================================


@dataclass
class Area:
    """Uma seção da tela: mapa do dia, barras da semana e o que mais couber.

    `grade` e `colunas` são a GEOMETRIA (de `plans/graficos.py`), montada
    aqui e não no template: o template desenha o que já está calculado, que
    é o que evita um filtro de aritmética em HTML.
    """

    chave: str
    titulo: str
    mapa: list = field(default_factory=list)
    barras: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    tem_dado: bool = False
    grade: object = None
    colunas: object = None


#: O texto do "?" de cada área (item 8): ele diz o que o número É e o que ele
#: NÃO é. São as mesmas frases dos parágrafos fixos que ficavam debaixo de
#: cada cartão — o que mudou é que agora elas só aparecem para quem pergunta.
AJUDA = {
    "dieta": "Cada quadrado é um dia, e a cor é quanto do cardápio daquele dia "
             "você registrou. A barra da semana é a média de calorias dos dias "
             "com registro — dia sem registro não é dia sem comer, é dia sem "
             "registro.",
    "treino": "Cada quadrado é um dia. Aceso, você anotou pelo menos uma série; "
              "vazado, era dia combinado e não houve série; apagado, era dia de "
              "descanso — e descansar no dia de descanso é cumprir o combinado. "
              "A barra da semana é o total de séries.",
    "agua": "Cada quadrado é um dia, e a cor é quanto da meta você registrou. A "
            "barra da semana é a média dos dias com registro, e não dos sete: "
            "dividir por sete transformaria 'três litros nos dois dias em que "
            "anotei' num comportamento que não aconteceu.",
    "corrida": "Cada quadrado é um dia com corrida, e a cor é a distância. A "
               "barra da semana soma os quilômetros registrados e importados.",
}

VAZIO = {
    "dieta": ("Nenhuma refeição registrada ainda. Assim que você marcar a "
              "primeira, a aderência ao cardápio começa aqui.",
              "plans:alimentacao", "Abrir o cardápio de hoje"),
    "treino": ("Nenhuma série anotada ainda. Cada série registrada no treino "
               "vira um dia aceso aqui — é o mapa da sua constância.",
               "workouts:routine", "Abrir o treino de hoje"),
    "agua": ("Nenhum registro de água ainda. Cada copo marcado no dia vira a "
             "média da semana aqui.",
             "plans:hydration", "Registrar o primeiro copo"),
    "corrida": ("Nenhuma corrida registrada ainda.",
                "workouts:corridas", "Abrir as corridas"),
}


def reunir(user, periodo, hoje=None, perfil=None, plano=None) -> dict:
    """O painel inteiro, com UMA consulta por área.

    O custo é constante no tamanho do período: as barras da semana são
    somadas em Python sobre o mapa do dia, e a janela tem no máximo noventa
    dias. É o que faz `Semana → 3 meses` não mexer no orçamento de consultas
    desta tela (`plans/test_stress.py`).

    Consultas, por área: treino 2 (séries por dia + dias combinados) e 1 dos
    recordes; alimentação 2 (`tracking.history`) e 1 das receitas; água 1;
    corrida 1; peso 1. As de `tracking.history` já eram pagas pela tabela
    "dia a dia" e continuam sendo as mesmas — a tela não lê duas vezes.
    """
    from plans import tracking, weight_trend

    recorte = janela(user, periodo, hoje=hoje)
    dias_combinados = set(user.training_days.values_list("weekday", flat=True))
    semanas = semanas_da_janela(recorte)
    meta_ml = weight_trend.hidratacao_ml(plano.weight_kg) if plano else 0

    # --- treino
    mapa_treino = mapa_de_treino(user, recorte, dias_combinados=dias_combinados)
    series_por_dia = {
        dia.data: _series_do_titulo(dia) for dia in mapa_treino
    }
    treino = Area(
        chave="treino", titulo="Treino", mapa=mapa_treino,
        barras=barras(semanas, series_por_dia, lambda v: "%d séries" % round(v)),
        extra={
            "recordes": recordes(user),
            "sequencia": sequencia_atual(mapa_treino),
            "combinados": len(dias_combinados),
        },
        tem_dado=any(d.estado == FEITO for d in mapa_treino),
    )

    # --- alimentação
    linhas = tracking.history(user, days=recorte.dias)
    mapa_dieta = mapa_de_dieta(user, recorte, linhas=linhas)
    kcal_por_dia = {linha["date"]: linha["kcal"] for linha in linhas}
    dieta = Area(
        chave="dieta", titulo="Alimentação", mapa=mapa_dieta,
        barras=barras(semanas, kcal_por_dia, lambda v: "%s kcal" % _numero(v, 0),
                      media=True),
        extra={
            "receitas": receitas_mais_registradas(user, recorte),
            "meta_kcal": plano.target_kcal if plano else 0,
            "linhas": linhas,
        },
        tem_dado=any(d.intensidade for d in mapa_dieta),
    )

    # --- água
    mapa_agua = mapa_de_agua(user, recorte, meta_ml=meta_ml)
    ml_por_dia = {
        dia.data: _ml_do_titulo(dia) for dia in mapa_agua
    }
    agua = Area(
        chave="agua", titulo="Água", mapa=mapa_agua,
        barras=barras(semanas, ml_por_dia, lambda v: "%s ml" % _numero(v, 0),
                      media=True),
        extra={"meta_ml": meta_ml},
        tem_dado=any(d.estado == FEITO for d in mapa_agua),
    )

    # --- corrida
    mapa_corrida, corridas_por_dia = mapa_de_corrida(user, recorte)
    km_por_dia = {d: v["m"] / 1000 for d, v in corridas_por_dia.items()}
    corrida = Area(
        chave="corrida", titulo="Corrida", mapa=mapa_corrida,
        barras=barras(semanas, km_por_dia, lambda v: "%s km" % _numero(v, 1)),
        extra={"ritmo": _ritmo_por_semana(semanas, corridas_por_dia)},
        tem_dado=bool(corridas_por_dia),
    )

    for area in (dieta, treino, agua, corrida):
        _vestir(area, recorte)

    peso = tile_de_peso(user, recorte)
    return {
        "janela": recorte,
        "periodos": [
            {"chave": chave, "rotulo": ROTULOS[chave], "atual": chave == recorte.periodo}
            for chave in PERIODOS
        ],
        "tiles": [
            peso,
            tile_de_treino(mapa_treino, dias_combinados),
            tile_de_dieta(mapa_dieta, linhas),
            tile_de_agua(mapa_agua, ml_por_dia, meta_ml),
        ],
        "peso": peso,
        "areas": [dieta, treino, agua, corrida],
        "tem_corrida": corrida.tem_dado,
    }


def _vestir(area: Area, recorte: Janela) -> None:
    """A geometria e o texto de uma área — o que o template só desenha."""
    from django.urls import reverse

    from plans import graficos

    area.grade = graficos.mapa(area.mapa)
    area.colunas = graficos.colunas([
        (barra.semana.fim.strftime("%d/%m"), barra.valor, barra.rotulo,
         barra.semana.fim == recorte.fim)
        for barra in area.barras
    ])
    area.extra["ajuda"] = AJUDA.get(area.chave, "")
    vazio, rota, texto = VAZIO.get(area.chave, ("", "", ""))
    area.extra["vazio"] = vazio
    area.extra["porta"] = reverse(rota) if rota else ""
    area.extra["porta_texto"] = texto
    if area.chave == "corrida":
        ritmo = area.extra.get("ritmo") or []
        area.extra["ritmo_texto"] = _minutos_por_km(ritmo[-1][1]) if ritmo else ""


def _minutos_por_km(minutos) -> str:
    """5,83 min/km vira "5'50"" — que é como quem corre lê ritmo."""
    inteiros = int(minutos)
    segundos = int(round((minutos - inteiros) * 60))
    if segundos == 60:
        inteiros, segundos = inteiros + 1, 0
    return "%d'%02d\"" % (inteiros, segundos)


def _series_do_titulo(dia) -> int:
    """O mapa guarda o texto ("3 séries"); a barra quer o número.

    Guardar os dois no `DiaDoMapa` seria duas verdades para o mesmo fato, e a
    segunda envelheceria — o título é o que a tela anuncia."""
    if dia.estado != FEITO:
        return 0
    return int(dia.titulo.split()[0])


def _ml_do_titulo(dia) -> int:
    if dia.estado != FEITO:
        return 0
    return int(dia.titulo.split()[0].replace(".", ""))


def _ritmo_por_semana(semanas, corridas_por_dia) -> list:
    """Minutos por quilômetro de cada semana — a linha que a corrida ganha.

    Ritmo é tempo TOTAL sobre distância TOTAL, e não a média dos ritmos: com
    uma corrida de 10 km e outra de 1 km, a média dos ritmos daria peso igual
    às duas e descreveria um treino que não houve.
    """
    saida = []
    for semana in semanas:
        metros = segundos = 0
        for n in range(semana.dias):
            dados = corridas_por_dia.get(semana.inicio + timedelta(days=n))
            if dados:
                metros += dados["m"]
                segundos += dados["s"]
        if metros:
            seg_por_km = segundos / (metros / 1000)
            saida.append((semana.fim, round(seg_por_km / 60, 2)))
    return saida
