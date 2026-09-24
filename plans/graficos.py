# -*- coding: utf-8 -*-
"""UM sistema de gráfico para a tela inteira — a geometria, em Python puro.

A tela de Progresso tinha três gramáticas para a mesma pergunta ("como foi
cada semana?"): barra com classe de largura no treino, barra com classe de
largura na água, e lista de números na corrida. O `_progresso_agua.html` já
registrava o problema em prosa — "duas soluções para o mesmo problema na
MESMA tela é dívida de UX nascendo" — e depois a corrida virou a terceira.

Aqui a forma é decidida uma vez e cada área só escolhe a COR. Três formas:

    linha(pontos)   -> peso (e a média móvel por cima)
    colunas(itens)  -> o volume de cada semana, com eixo
    mapa(dias)      -> o calendário em grade (heatmap)

**Geometria, e não desenho.** Estas funções devolvem números — `d` de path,
`x`, `y`, altura, rótulos de eixo — e quem desenha é o template, com SVG
inline. Duas razões: SVG no template é inspecionável no navegador e entra no
tema pelos tokens de cor como qualquer outro elemento; e a régua de
`config/test_design_system.py` proíbe `style=` estático, mas não atributo de
SVG — `x="12"` é o dado, não um estilo escrito à mão.

**Sem biblioteca.** O app não tem build step (decisão do `CLAUDE.md`), e uma
biblioteca de gráfico é o tipo de peso que chega em 90 KB para desenhar seis
colunas. O maior gráfico desta tela tem noventa pontos.

O sistema de coordenadas é o mesmo em todos: viewBox de `LARGURA` × `ALTURA`
em unidades de usuário, com `preserveAspectRatio` deixado no padrão e o SVG
esticado por CSS. Isso faz o gráfico escalar de 320 a 1280 px sem recalcular
nada no servidor — e é por isso que a largura aqui é uma constante e não um
parâmetro que a tela precise adivinhar.
"""
from dataclasses import dataclass, field

#: Unidades de usuário do viewBox. Proporção 2:1, que é a que cabe num cartão
#: a 390px sem virar faixa fina nem comer meia tela.
LARGURA = 320
ALTURA = 160

#: O corpo do rótulo de eixo, em unidades de usuário. Ele sai como ATRIBUTO
#: do `<text>` e não como regra de CSS: é geometria do viewBox — escala junto
#: com o gráfico —, e não um degrau da escala tipográfica do app, que tem piso
#: de 11px para TEXTO DE INTERFACE.
TAMANHO_ROTULO = 9

#: Respiro para os rótulos dos eixos. O de baixo é maior porque leva data.
MARGEM_ESQ = 34
MARGEM_DIR = 6
MARGEM_TOPO = 10
MARGEM_BASE = 20


@dataclass(frozen=True)
class Ponto:
    x: float
    y: float
    #: O valor original, para `title`/`aria` — o pixel não se lê em voz alta.
    rotulo: str = ""


@dataclass(frozen=True)
class Marca:
    """Uma marca de eixo: onde fica, o que diz e por onde se ancora.

    `ancora` existe porque a marca das PONTAS do eixo x, centrada, sai da
    caixa: com o viewBox em 320 e o último ponto em 314, "21/09" saía
    cortado em "21/0" — MEDIDO na captura de 23/09/2026.
    """

    pos: float
    texto: str
    ancora: str = "middle"


@dataclass(frozen=True)
class Linha:
    pontos: tuple = ()
    caminho: str = ""
    media: tuple = ()
    caminho_media: str = ""
    eixo_x: tuple = ()
    eixo_y: tuple = ()
    largura: int = LARGURA
    altura: int = ALTURA
    #: Onde pousa o rótulo de data e onde a grade horizontal vai.
    base_rotulo: int = ALTURA - 6
    grade_inicio: int = MARGEM_ESQ
    grade_fim: int = LARGURA - MARGEM_DIR
    recuo_eixo: int = MARGEM_ESQ - 4
    #: Um ponto só não vira linha — a tela mostra o ponto e diz o que falta.
    unico: bool = False


@dataclass(frozen=True)
class Coluna:
    x: float
    y: float
    largura: float
    altura: float
    rotulo: str
    valor_texto: str
    #: O centro da barra, para o rótulo do eixo x. O template NÃO faz conta:
    #: filtro de aritmética em template é infraestrutura nova para uma soma.
    centro: float = 0
    #: Destaca a barra da semana corrente.
    atual: bool = False


@dataclass(frozen=True)
class Colunas:
    barras: tuple = ()
    eixo_y: tuple = ()
    largura: int = LARGURA
    altura: int = ALTURA
    #: Onde o rótulo de cada barra pousa, e onde a grade começa e termina.
    base_rotulo: int = ALTURA - 6
    grade_inicio: int = MARGEM_ESQ
    grade_fim: int = LARGURA - MARGEM_DIR
    #: Linha de base do texto do eixo y (a marca mais o meio da altura da fonte).
    recuo_eixo: int = MARGEM_ESQ - 4


def _escala(valores, folga=0.08):
    """Mínimo e máximo do eixo, com folga para a linha não encostar na borda.

    Série constante (toda pesagem igual) teria amplitude zero e dividiria por
    zero: aí o eixo abre um quilo para cada lado, que é o que faz a linha
    aparecer no meio em vez de sumir na borda.
    """
    menor, maior = min(valores), max(valores)
    if maior == menor:
        return menor - 1, maior + 1
    margem = (maior - menor) * folga
    return menor - margem, maior + margem


def linha(pontos, media=(), rotulo_x=None, rotulo_y=None) -> Linha:
    """A curva do peso: um `path` pelos pontos, outro pela média móvel.

    `pontos` é `[(date, valor)]` em ordem crescente de data.
    """
    if not pontos:
        return Linha()
    rotulo_x = rotulo_x or (lambda d: d.strftime("%d/%m"))
    rotulo_y = rotulo_y or (lambda v: ("%.1f" % v).replace(".", ","))

    valores = [v for _, v in pontos] + [v for _, v in media]
    piso, teto = _escala(valores)
    primeiro, ultimo = pontos[0][0], pontos[-1][0]
    vao_dias = max((ultimo - primeiro).days, 1)
    util_x = LARGURA - MARGEM_ESQ - MARGEM_DIR
    util_y = ALTURA - MARGEM_TOPO - MARGEM_BASE

    def em_x(dia):
        if len(pontos) == 1:
            return MARGEM_ESQ + util_x / 2
        return MARGEM_ESQ + util_x * (dia - primeiro).days / vao_dias

    def em_y(valor):
        return MARGEM_TOPO + util_y * (1 - (valor - piso) / (teto - piso))

    def caminho_de(serie):
        return " ".join(
            "%s %.1f %.1f" % ("M" if n == 0 else "L", em_x(d), em_y(v))
            for n, (d, v) in enumerate(serie)
        )

    desenhados = tuple(
        Ponto(x=round(em_x(d), 1), y=round(em_y(v), 1),
              rotulo="%s em %s" % (rotulo_y(v), rotulo_x(d)))
        for d, v in pontos
    )
    marcas_y = tuple(
        Marca(pos=round(em_y(piso + (teto - piso) * f), 1),
              texto=rotulo_y(piso + (teto - piso) * f))
        for f in (0, 0.5, 1)
    )
    if len(pontos) == 1:
        marcas_x = (Marca(pos=round(em_x(primeiro), 1), texto=rotulo_x(primeiro)),)
    else:
        marcas_x = (
            Marca(pos=round(em_x(primeiro), 1), texto=rotulo_x(primeiro), ancora="start"),
            Marca(pos=round(em_x(ultimo), 1), texto=rotulo_x(ultimo), ancora="end"),
        )
    return Linha(
        pontos=desenhados, caminho=caminho_de(pontos),
        media=tuple(Ponto(x=round(em_x(d), 1), y=round(em_y(v), 1)) for d, v in media),
        caminho_media=caminho_de(media) if media else "",
        eixo_x=marcas_x, eixo_y=marcas_y, unico=len(pontos) == 1,
    )


#: Vão entre colunas, em unidades de usuário.
VAO = 4


def colunas(itens, rotulo_y=None) -> Colunas:
    """As barras por semana. `itens` é `[(rotulo, valor, valor_texto, atual)]`."""
    if not itens:
        return Colunas()
    rotulo_y = rotulo_y or (lambda v: "%d" % round(v))
    teto = max((v for _, v, _, _ in itens), default=0) or 1
    util_x = LARGURA - MARGEM_ESQ - MARGEM_DIR
    util_y = ALTURA - MARGEM_TOPO - MARGEM_BASE
    passo = util_x / len(itens)
    largura_barra = max(passo - VAO, 2)

    barras = []
    for n, (rotulo, valor, texto, atual) in enumerate(itens):
        altura = util_y * (valor / teto)
        barras.append(Coluna(
            x=round(MARGEM_ESQ + n * passo + (passo - largura_barra) / 2, 1),
            y=round(MARGEM_TOPO + util_y - altura, 1),
            largura=round(largura_barra, 1),
            # Uma barra de zero não desenha nada; 0,8 é o fio que diz "a
            # semana existiu e o valor foi zero", que é diferente de ausente.
            altura=round(max(altura, 0.8), 1),
            rotulo=rotulo, valor_texto=texto, atual=atual,
            centro=round(MARGEM_ESQ + n * passo + passo / 2, 1),
        ))
    marcas = tuple(
        Marca(pos=round(MARGEM_TOPO + util_y * (1 - f), 1), texto=rotulo_y(teto * f))
        for f in (0, 0.5, 1)
    )
    return Colunas(barras=tuple(barras), eixo_y=marcas)


@dataclass(frozen=True)
class Celula:
    """Um quadrado do mapa, com o lugar já calculado."""

    dia: object
    x: int
    y: int


@dataclass(frozen=True)
class Mapa:
    """O calendário em grade — uma coluna por semana, sete linhas por dia."""

    colunas: tuple = ()
    rotulos: tuple = ()
    #: Lado do quadrado e vão, em unidades de usuário.
    lado: int = 12
    vao: int = 3
    largura: int = 0
    altura: int = 0
    semanas: int = 0


def mapa(dias, rotulo_semana=None) -> Mapa:
    """`dias` é a lista de `DiaDoMapa` em ordem crescente.

    A coluna é a SEMANA e a linha é o dia da semana — a grade do GitHub, que
    é a convenção que ninguém precisa aprender. A primeira coluna costuma
    começar no meio (a conta não nasceu numa segunda), e é isso que faz o
    mapa dizer "aqui começou" sem escrever nada.
    """
    if not dias:
        return Mapa()
    rotulo_semana = rotulo_semana or (lambda d: d.strftime("%d/%m"))
    lado, vao = 12, 3
    colunas_de_dias = []
    atual = [None] * 7
    ancora = None
    for dia in dias:
        if ancora is None:
            ancora = dia.data
        if dia.data.weekday() == 0 and any(x is not None for x in atual):
            colunas_de_dias.append((ancora, tuple(atual)))
            atual = [None] * 7
            ancora = dia.data
        atual[dia.data.weekday()] = dia
    colunas_de_dias.append((ancora, tuple(atual)))
    passo = lado + vao
    colunas = tuple(
        tuple(
            Celula(dia=dia, x=n * passo, y=linha * passo) if dia is not None else None
            for linha, dia in enumerate(coluna)
        )
        for n, (_, coluna) in enumerate(colunas_de_dias)
    )
    return Mapa(
        colunas=colunas,
        rotulos=tuple(rotulo_semana(inicio) for inicio, _ in colunas_de_dias),
        lado=lado, vao=vao, semanas=len(colunas_de_dias),
        largura=len(colunas_de_dias) * passo - vao,
        altura=7 * passo - vao,
    )
