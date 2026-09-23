"""A ofensiva: quantos dias seguidos a pessoa cumpriu o combinado.

O que a torna honesta é o que ela decide NÃO cobrar.

**Dia de descanso não quebra treino.** A rotina prevê três dias por semana; se
o contador exigisse treino todo dia, a sequência morreria toda quarta-feira e
o número viraria ruído. Num dia sem treino previsto, treino está cumprido por
definição — descansar É o plano.

**O dia de hoje nunca quebra.** Às sete da manhã ninguém almoçou, treinou nem
bebeu três litros. Um contador que zerasse ao amanhecer seria um contador que
pune por acordar cedo. Hoje só ENTRA na conta quando já está cumprido; enquanto
não está, ele é o dia em risco, e é sobre ele que o aviso fala.

**Sem meta, sem cobrança.** Quem não tem plano alimentar não é reprovado em
dieta. Metas que a pessoa não tem não podem quebrar a sequência dela.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from workouts.models import Corrida, ExerciseLog, TrainingPlan

from . import tracking
from .models import HydrationLog, MealLog, MealStatus

#: Quanto da meta calórica conta como dia cumprido. Oitenta por cento das
#: refeições marcadas como feitas — não 100%: exigir perfeição de um contador
#: de constância é a forma mais rápida de a pessoa desistir dele.
ADESAO_MINIMA_PCT = 80

#: O piso de refeições marcadas SAIU, e a ausência é a correção.
#:
#: Ele existia para impedir que uma única refeição marcada desse 100% — o que
#: só era possível porque o denominador era "o que a pessoa marcou". Com o
#: denominador vindo do PLANO, uma refeição de cinco dá 20%, e o piso vira
#: remendo de um problema que não existe mais.
#:
#: Mantê-lo seria pior que inútil: ele descartava o dia INTEIRO quando havia
#: menos de três marcações, transformando "marquei pouco" em "não conta" em vez
#: de "aderência baixa".

#: Da meta de água. Noventa por cento porque a meta já é estimativa (35 ml/kg),
#: e cobrar o número cheio de uma estimativa é falsa precisão.
HIDRATACAO_MINIMA_PCT = 90

#: Até onde olhar para trás. Uma sequência de um ano é possível e a consulta
#: precisa de um teto.
DIAS_NO_HISTORICO = 400


@dataclass
class Dia:
    """Um dia e o que ele cumpriu."""

    data: object
    treino: bool
    dieta: bool
    agua: bool
    #: Havia treino previsto? Muda a leitura de `treino=True`.
    treino_previsto: bool
    #: Havia ALGO a cumprir — uma rotina de treino (o descanso entre os dias
    #: previstos é o plano), um cardápio ou uma meta de água? Um dia sem
    #: nenhum dos três não fecha: não há o que ter cumprido (22/09/2026; era
    #: o que fazia os dias sem plano e sem meta contarem).
    mensuravel: bool = True

    @property
    def completo(self) -> bool:
        """DOIS DOS TRÊS pilares fecham o dia, e o treino é obrigatório no
        dia em que está previsto (decisão do dono, 20/09/2026).

        Até então o dia exigia treino E dieta E água. A auditoria de 20/09
        simulou uma semana de uso real — 4 refeições de 5, 1,5 L de uma meta
        de 3 L, treino feito — e a Home dizia "0 dias — Comece hoje" no
        sétimo dia: a água (90 % de 35 ml/kg) dominava a régua, e a ofensiva
        que existe para dar vontade de voltar só sabia dizer não. Agora
        dieta e água compensam uma à outra; o treino não, porque é o pilar
        que tem hora marcada — e no dia sem treino previsto descansar
        continua sendo o plano (`treino=True` vem de `avaliar`), então o
        dia de descanso fecha com um dos dois outros. `manage.py
        simular_ofensiva` reproduz a semana auditada sob as duas regras.
        """
        return self.mensuravel and self.treino and (self.dieta or self.agua)

    @property
    def pendencias(self) -> list:
        """O que FECHA o dia — não a lista de tudo que não foi feito."""
        faltando = []
        if not self.treino:
            faltando.append("treino")
        if not (self.dieta or self.agua):
            faltando.append("dieta ou água")
        return faltando


#: As letras de segunda a domingo, na convenção que o app já usa nas telas de
#: treino. Elas REPETEM (S de segunda e de sábado, Q de quarta e de quinta) e
#: por isso a letra é decoração: quem ouve a tela recebe `nome`, que é o dia
#: por extenso com a data.
LETRAS_DA_SEMANA = ("S", "T", "Q", "Q", "S", "S", "D")
NOMES_DA_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)


@dataclass
class DiaDaSemana:
    """Um dos sete dias da semana em que hoje cai, pronto para desenhar.

    A MESMA leitura serve a DUAS tiras de sete pontos — a faixa da ofensiva
    ("o dia fechou?") e o cartão de Treino ("havia treino, e foi feito?") —, e
    é por isso que ela mora aqui e não em cada uma: as duas perguntas são
    sobre os mesmos dias, e responder cada uma no seu canto era a garantia de
    que um dia elas discordariam na virada da meia-noite.

    Custo: ZERO consulta. `calcular` já leu o histórico inteiro para a
    sequência e para o recorde; estes sete dias saem da mesma leitura.
    """

    data: object
    dia: object
    letra: str
    nome: str
    hoje: bool
    futuro: bool
    antes_da_conta: bool

    @property
    def estado(self) -> str:
        """Para a faixa da OFENSIVA: o dia fechou?

        Quatro estados, e nenhum deles é só uma cor na tela — a faixa desenha
        preenchido, anel, vazado e risca (ver `_pontos_da_semana.html`).
        """
        if self.antes_da_conta:
            return "antes"
        if self.futuro:
            return "futuro"
        if self.dia.completo:
            return "fechado"
        return "aberto"

    @property
    def estado_do_treino(self) -> str:
        """Para o cartão de TREINO: havia treino previsto, e ele foi feito?

        HOJE com treino previsto e nenhuma série ainda é `previsto`, e nunca
        `faltou`: o dia não acabou, e um app que marca falta às sete da manhã
        está cobrando por acordar cedo — a mesma regra que a ofensiva aplica
        ao não deixar hoje quebrar a sequência.
        """
        if self.antes_da_conta or not self.dia.treino_previsto:
            return "descanso"
        if self.dia.treino:
            return "feito"
        if self.futuro or self.hoje:
            return "previsto"
        return "faltou"

    @property
    def legenda(self) -> str:
        """O dia por extenso e o que ele diz — o texto de quem ouve a tela."""
        quando = "%s, %s" % (self.nome, self.data.strftime("%d/%m"))
        return "%s: %s" % (quando, LEGENDA_DO_ESTADO[self.estado])

    @property
    def legenda_do_treino(self) -> str:
        quando = "%s, %s" % (self.nome, self.data.strftime("%d/%m"))
        return "%s: %s" % (quando, LEGENDA_DO_TREINO[self.estado_do_treino])


#: O que cada estado QUER DIZER, em palavras. É o que a tela de leitura
#: anuncia, e é por isso que ele mora ao lado da regra: um ponto verde sem
#: legenda é uma informação que só existe para quem enxerga.
LEGENDA_DO_ESTADO = {
    "fechado": "dia fechado",
    "aberto": "dia não fechado",
    "futuro": "ainda não chegou",
    "antes": "antes do seu cadastro",
}
LEGENDA_DO_TREINO = {
    "feito": "treino registrado",
    "previsto": "treino previsto",
    "faltou": "treino previsto, sem registro",
    "descanso": "dia de descanso",
}


@dataclass
class Ofensiva:
    dias: int
    recorde: int
    #: O dia de hoje já está fechado?
    hoje_completo: bool
    #: O que falta hoje para a sequência continuar.
    falta_hoje: list
    ultimo_dia: object = None
    #: O que faltou ONTEM quando a sequência está em zero e ontem existia
    #: (a conta já estava aberta): a Home diz "ontem faltou água" em vez de
    #: "comece hoje" para quem já vinha usando (achado #11 das personas).
    #: `None` quando ontem não conta — primeiro dia de uso.
    falta_ontem: list = None
    #: Os sete dias da semana em que hoje cai (segunda a domingo), para as
    #: duas tiras de pontos. Lista de `DiaDaSemana`.
    semana: list = None

    @property
    def em_risco(self) -> bool:
        """Tem sequência viva e hoje ainda não fechou."""
        return self.dias > 0 and not self.hoje_completo

    @property
    def mensagem(self) -> str:
        """O texto do topo do painel.

        Muda com o tamanho da sequência porque a mesma frase repetida por
        quarenta dias deixa de ser lida. E nunca é ríspida: o contador existe
        para dar vontade de voltar, não para cobrar.
        """
        if self.dias == 0:
            if self.falta_ontem:
                # A ORDEM É A DECISÃO (22/09/2026): o convite primeiro, o que
                # faltou depois. A frase era "Ontem faltou X. Hoje recomeça:
                # …", e a auditoria de UX a encontrou como o PRIMEIRO lugar em
                # que o treino aparecia com destaque na Home — como bronca,
                # num cartão de zero dias. A informação fica (ela é honesta e
                # útil), mas quem abre o app de manhã lê primeiro o que fazer
                # hoje, e não o que não fez ontem.
                faltou = " e ".join(self.falta_ontem)
                return (
                    "Recomeça hoje: treino no dia de treino, mais dieta ou "
                    f"água. Ontem faltou {faltou}."
                )
            return "Comece hoje: treino no dia de treino, mais dieta ou água, e a contagem começa."
        if self.em_risco:
            falta = ", ".join(self.falta_hoje)
            return f"Falta {falta} para manter a sequência hoje."
        if self.dias == 1:
            return "Primeiro dia fechado. O segundo é o que costuma escapar."
        if self.dias < 7:
            return f"{self.dias} dias seguidos. Uma semana está logo ali."
        if self.dias < 30:
            return f"{self.dias} dias seguidos. Isso já é rotina, não esforço."
        return f"{self.dias} dias seguidos. Você virou outra pessoa nesse intervalo."


def _dias_de_treino(user) -> set:
    """Os dias da semana em que há treino previsto (0 = segunda)."""
    plano = TrainingPlan.objects.filter(user=user, is_active=True).first()
    if plano is None:
        return set()
    return set(plano.sessions.values_list("weekday", flat=True))


@dataclass
class JaLido:
    """O que a tela já leu e a ofensiva NÃO precisa reler (21/09/2026).

    A Home carregava o plano de treino, as sessões, as corridas, a água e o
    plano alimentar para desenhar a tela, e `calcular` relia os cinco para a
    ofensiva — dez consultas para cinco tabelas. Cada campo aqui é opcional:
    o que vier preenchido é usado; o que vier `None` é lido como sempre.
    `corridas` são os instantes de início desde `inicio` (o mesmo `inicio`
    de `calcular`: `DIAS_NO_HISTORICO` atrás de hoje); `agua_por_dia` é
    `{data: total_ml}` no mesmo período.
    """

    previstos: set = None
    corridas: list = None
    agua_por_dia: dict = None
    tem_plano: bool = None


def _ler(user, inicio, meta_agua_ml, ja_lido=None):
    """Os conjuntos de dias cumpridos por pilar, numa passada só de consultas."""
    ja_lido = ja_lido or JaLido()
    previstos = ja_lido.previstos if ja_lido.previstos is not None else _dias_de_treino(user)

    # --------------------------------------------------------- treino
    treinou = set(
        ExerciseLog.objects.filter(user=user, date__gte=inicio).values_list(
            "date", flat=True
        )
    )
    # Correu conta: a régua da ofensiva é "moveu-se", não "fez a letra". Uma
    # consulta, no mesmo ponto que decide a musculação (BENCHMARK-2026-09, d).
    inicios = (
        ja_lido.corridas
        if ja_lido.corridas is not None
        else Corrida.objects.filter(user=user, comecou_em__date__gte=inicio).values_list(
            "comecou_em", flat=True
        )
    )
    treinou |= {timezone.localtime(c).date() for c in inicios}

    # ---------------------------------------------------------- dieta
    #
    # O DENOMINADOR É O PLANO, e essa é a correção inteira.
    #
    # Antes ele era "refeições que a pessoa marcou de alguma forma", e isso
    # invertia o incentivo do app:
    #
    #     3 feitas + 2 "comi outra coisa"  ->  3/5 = 60%  ->  quebrava
    #     3 feitas + 2 SEM MARCAR NADA     ->  3/3 = 100% ->  mantinha
    #
    # Quem registrava honestamente perdia a sequência; quem não abria o app a
    # mantinha. Num módulo cuja primeira linha diz que "o que a torna honesta é
    # o que ela decide NÃO cobrar", isso era uma contradição interna.
    #
    # Com o denominador vindo do plano, o resultado não depende mais do que foi
    # marcado — só do que foi CUMPRIDO. Os dois casos acima dão 3/5, e omitir
    # deixa de ser vantagem. Essa é a propriedade, e há um teste que a fixa.
    #
    # Qual plano: o que estava ativo NAQUELE dia, alcançado pelo próprio
    # registro (`slot__plan`). Não é o plano de hoje — quem passou de cinco para
    # quatro refeições seria julgado pela régua errada no passado.
    #
    # Dia sem nenhuma marcação não entra no dicionário e, portanto, não é
    # aderente. É o mesmo destino de quem marcou tudo fora do plano, que é
    # exatamente o ponto.
    # DUAS consultas, e nunca mais que duas. A primeira versão desta correção
    # chamava `log.slot.plan.slots.count()` dentro do laço, o que dá uma
    # consulta por dia — e `test_the_streak_does_not_query_per_day` reprovou,
    # que é exatamente para isso que ele existe. A ofensiva olha 400 dias para
    # trás: um N+1 aqui é 400 idas ao banco na tela mais visitada do app.
    dieta_ok = set()
    # O denominador viaja NA MESMA consulta (`tracking.previstas_do_plano`,
    # a mesma conta de `previstas_por_plano`, como subconsulta): era uma
    # segunda ida ao banco para contar os horários de cada plano visto.
    registros = list(
        MealLog.objects.filter(user=user, date__gte=inicio)
        .values("date", "status", "slot__plan_id")
        .annotate(previstas=tracking.previstas_do_plano())
    )
    # A MESMA conta que o histórico usa (`previstas_por_plano`): duas cópias
    # desta consulta foi exatamente como as duas telas passaram a discordar
    # sobre a aderência da mesma pessoa — e a subconsulta é a mesma fonte.

    por_dia = {}
    for r in registros:
        registro = por_dia.setdefault(r["date"], {"feitas": 0, "previstas": 0})
        if r["status"] == MealStatus.DONE:
            registro["feitas"] += 1
        if not registro["previstas"]:
            registro["previstas"] = r["previstas"] or 0

    for data, registro in por_dia.items():
        previstas = registro["previstas"]
        if not previstas:
            # Registro órfão de plano (histórico antigo). Sem denominador
            # confiável, não afirmamos nada sobre o dia.
            continue
        if registro["feitas"] * 100 / previstas >= ADESAO_MINIMA_PCT:
            dieta_ok.add(data)

    # ----------------------------------------------------------- água
    agua_ok = set()
    if meta_agua_ml:
        alvo = meta_agua_ml * HIDRATACAO_MINIMA_PCT / 100
        agua_por_dia = (
            ja_lido.agua_por_dia
            if ja_lido.agua_por_dia is not None
            else agua_por_dia_desde(user, inicio)
        )
        agua_ok = {data for data, total in agua_por_dia.items() if (total or 0) >= alvo}
    return previstos, treinou, dieta_ok, agua_ok


def agua_por_dia_desde(user, inicio) -> dict:
    """`{data: total_ml}` desde `inicio` — a leitura que a ofensiva e o
    cartão de água da Home compartilham (o total de hoje é `.get(hoje, 0)`).
    `HydrationLog` é UMA linha por dia (`uma_hidratacao_por_dia`), então não
    há o que somar: cada linha é o total do dia."""
    return {
        data: ml or 0
        for data, ml in HydrationLog.objects.filter(user=user, date__gte=inicio).values_list("date", "ml")
    }


def _avaliar(user, data, previstos, treinou, dieta_ok, agua_ok, meta_agua_ml) -> Dia:
    previsto = data.weekday() in previstos
    return Dia(
        data=data,
        # Descansar é o plano nos dias sem treino previsto.
        treino=(data in treinou) if previsto else True,
        # Sem plano alimentar não há meta de dieta para cobrar.
        dieta=(data in dieta_ok) if _tem_plano(user) else True,
        agua=(data in agua_ok) if meta_agua_ml else True,
        treino_previsto=previsto,
        # Há uma rotina de treino (qualquer dia previsto na semana — o
        # descanso entre eles é o plano), um cardápio ou uma meta de água.
        mensuravel=bool(previstos or _tem_plano(user) or meta_agua_ml),
    )


def avaliar_dia(user, dia, meta_agua_ml=None) -> Dia:
    """Um dia só, com o que ele cumpriu — para `simular_ofensiva` medir a
    régua antiga e a nova sobre os MESMOS pilares lidos."""
    inicio = dia - timedelta(days=DIAS_NO_HISTORICO)
    return _avaliar(user, dia, *_ler(user, inicio, meta_agua_ml), meta_agua_ml)


def inicio_do_historico(hoje):
    """O primeiro dia que a ofensiva olha — para quem lê as tabelas antes."""
    return hoje - timedelta(days=DIAS_NO_HISTORICO)


def primeiro_dia_da_conta(user):
    """O dia em que a conta nasceu, no fuso local — o limite absoluto da
    ofensiva e do recorde (22/09/2026).

    Antes disso a pessoa não usava o app, e um dia sem treino previsto,
    sem cardápio e sem meta de água FECHA sozinho (descansar é o plano;
    sem meta não há o que cobrar). Somado aos 400 dias de histórico, isso
    dava "401 / 3" nas Conquistas de quem se cadastrou hoje sem dia de
    treino, e "3 dias de ofensiva" na segunda de manhã para quem treina —
    os dois de graça, no primeiro dia (achado #4 das personas). Lê o campo
    do usuário já carregado: zero consultas."""
    entrou = getattr(user, "date_joined", None)
    if entrou is None:
        return None
    return timezone.localtime(entrou).date()


def calcular(user, hoje=None, meta_agua_ml=None, *, ja_lido=None) -> Ofensiva:
    """Percorre os dias de trás para frente até achar o primeiro furo."""
    hoje = hoje or timezone.localdate()
    inicio = inicio_do_historico(hoje)
    if ja_lido is not None and ja_lido.tem_plano is not None:
        user._streak_tem_plano = ja_lido.tem_plano
    previstos, treinou, dieta_ok, agua_ok = _ler(user, inicio, meta_agua_ml, ja_lido)

    def avaliar(data) -> Dia:
        return _avaliar(user, data, previstos, treinou, dieta_ok, agua_ok, meta_agua_ml)

    dia_de_hoje = avaliar(hoje)

    # Hoje só entra quando já está fechado. Enquanto não está, a contagem
    # começa em ontem — e hoje é o dia em risco.
    sequencia = 0
    cursor = hoje if dia_de_hoje.completo else hoje - timedelta(days=1)
    limite = _limite(user, hoje)
    ultimo = None
    while cursor >= limite:
        dia = avaliar(cursor)
        if not dia.completo:
            break
        if ultimo is None:
            ultimo = cursor
        sequencia += 1
        cursor -= timedelta(days=1)

    ontem = hoje - timedelta(days=1)
    falta_ontem = None
    if sequencia == 0 and ontem >= limite:
        falta_ontem = avaliar(ontem).pendencias

    return Ofensiva(
        semana=_semana_de(hoje, avaliar, limite),
        dias=sequencia,
        recorde=max(sequencia, _recorde(user, hoje, previstos, treinou, dieta_ok,
                                        agua_ok, meta_agua_ml, limite)),
        hoje_completo=dia_de_hoje.completo,
        falta_hoje=dia_de_hoje.pendencias,
        ultimo_dia=ultimo,
        falta_ontem=falta_ontem,
    )


def _semana_de(hoje, avaliar, limite) -> list:
    """Os sete dias da semana em que hoje cai, de segunda a domingo.

    Segunda a domingo, e não "os últimos sete dias": a tira responde "como
    está a MINHA semana", que é a pergunta que alguém faz na quarta olhando
    para sexta — e uma janela deslizante não tem sexta.

    `avaliar` é o fechamento que `calcular` já montou sobre o histórico lido:
    sete chamadas, zero consultas. O dia FUTURO também é avaliado, e só o
    `treino_previsto` dele é lido — é o que permite a tira do treino mostrar
    o que ainda vem na semana sem afirmar nada sobre o que não aconteceu.
    """
    segunda = hoje - timedelta(days=hoje.weekday())
    dias = []
    for passo in range(7):
        data = segunda + timedelta(days=passo)
        dias.append(
            DiaDaSemana(
                data=data,
                dia=avaliar(data),
                letra=LETRAS_DA_SEMANA[passo],
                nome=NOMES_DA_SEMANA[passo],
                hoje=data == hoje,
                futuro=data > hoje,
                antes_da_conta=data < limite,
            )
        )
    return dias


def _tem_plano(user) -> bool:
    # Import tardio: `services` importa `models`, e subir isto para o topo
    # fecharia o ciclo.
    from .services import get_active_plan

    if not hasattr(user, "_streak_tem_plano"):
        user._streak_tem_plano = get_active_plan(user) is not None
    return user._streak_tem_plano


def _limite(user, hoje):
    """Até onde a ofensiva olha para trás: os 400 dias de histórico, nunca
    antes de a conta existir."""
    limite = hoje - timedelta(days=DIAS_NO_HISTORICO)
    entrada = primeiro_dia_da_conta(user)
    if entrada is not None and entrada > limite:
        limite = entrada
    return limite


def _recorde(user, hoje, previstos, treinou, dieta_ok, agua_ok, meta_agua_ml, limite=None) -> int:
    """A maior sequência já feita, para a atual ter contra o que se medir."""
    tem_plano = _tem_plano(user)
    melhor = atual = 0
    cursor = limite if limite is not None else _limite(user, hoje)
    while cursor <= hoje:
        previsto = cursor.weekday() in previstos
        # A MESMA régua de `Dia.completo`, inclusive "houve algo a cumprir".
        completo = (
            bool(previstos or tem_plano or meta_agua_ml)
            and ((cursor in treinou) if previsto else True)
            and ((cursor in dieta_ok) if tem_plano else True)
            and ((cursor in agua_ok) if meta_agua_ml else True)
        )
        if completo:
            atual += 1
            melhor = max(melhor, atual)
        else:
            atual = 0
        cursor += timedelta(days=1)
    return melhor
