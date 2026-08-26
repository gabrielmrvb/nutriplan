"""O assistente que reorganiza a ficha quando a academia não colabora.

O problema que ele resolve é banal e diário: a ficha diz leg press, o leg press
tem fila de quatro pessoas, e a pessoa fica parada decidindo entre esperar,
improvisar ou ir embora. Improvisar exige saber o que substitui o quê; ir
embora é o que costuma acontecer.

**Sobre o nome.** Isto é um motor de regras sobre o catálogo, não uma chamada a
modelo de linguagem. A escolha é deliberada e vale explicar: tudo que o
assistente precisa decidir — mesmo grupo muscular, equipamento diferente,
articulação poupada, tempo que a sessão leva — está em dados estruturados que o
app já tem, e uma regra determinística sobre eles é auditável, roda offline,
não custa por uso e cabe num teste. Um modelo de linguagem seria melhor numa
coisa só: entender pedido escrito em português livre. `interpretar()` é
justamente esse ponto, isolado de propósito — trocar o casamento por palavra-
chave por uma chamada de modelo depois muda uma função e nada mais.

O fluxo é sempre em dois tempos: `sugerir()` monta a proposta sem gravar nada,
a tela mostra, e só então `aplicar()` escreve. Ficha de treino é coisa que a
pessoa decorou; mudar sem perguntar é pior do que não mudar.
"""
from dataclasses import dataclass, field
from unicodedata import combining, normalize

from django.db import transaction
from django.utils import timezone

from .models import (
    ARTICULACOES,
    Equipment,
    Exercise,
    SEGUNDOS_ENTRE_EXERCICIOS,
    SEGUNDOS_POR_SERIE,
)

# ------------------------------------------------------------------- motivos
EQUIPAMENTO = "equipamento"
TEMPO = "tempo"
TROCA = "troca"
DESCONFORTO = "desconforto"

MOTIVOS = {
    EQUIPAMENTO: "Equipamento ocupado",
    TEMPO: "Pouco tempo",
    TROCA: "Trocar exercício",
    DESCONFORTO: "Desconforto",
}

#: Quanto o "treino express" tira da sessão. Trinta minutos é o pedido, e é
#: agressivo: numa ficha de 75 minutos são 40% do tempo.
CORTE_EXPRESS_MIN = 30

#: Piso da sessão. Abaixo disso não é treino curto, é aquecimento — e cortar
#: até lá desmontaria a ficha inteira em vez de encurtá-la.
MINIMO_DA_SESSAO_MIN = 30

#: Descanso mínimo por tipo de exercício. Composto pesado precisa do intervalo:
#: cortar o descanso do agachamento para 45 segundos não encurta o treino, faz
#: a pessoa falhar na terceira série e treinar menos.
DESCANSO_MINIMO = {True: 90, False: 45}

#: Séries mínimas num isolado depois do corte. Abaixo de duas o exercício
#: deixa de somar volume e vira gasto de deslocamento.
SERIES_MINIMAS = 2


def _sem_acento(texto: str) -> str:
    decomposto = normalize("NFD", (texto or "").lower())
    return "".join(c for c in decomposto if not combining(c))


@dataclass
class Mudanca:
    """Uma alteração proposta, com o porquê junto.

    O `porque` não é enfeite: a tela mostra a proposta antes de aplicar, e uma
    troca sem motivo escrito parece capricho do app.
    """

    item: object
    tipo: str  # "troca" | "ajuste" | "remocao" | "reordenar"
    porque: str
    novo_exercicio: object = None
    sets: int = None
    rest_seconds: int = None
    #: Em "reordenar", o exercício que troca de lugar com este.
    parceiro: object = None

    @property
    def de(self) -> str:
        return self.item.exercise.name

    @property
    def para(self) -> str:
        return self.novo_exercicio.name if self.novo_exercicio else self.de


@dataclass
class Sugestao:
    motivo: str
    mudancas: list = field(default_factory=list)
    resumo: str = ""
    #: Quando o app não consegue resolver o que foi pedido e precisa dizer isso
    #: em vez de fingir. Aparece em destaque na tela.
    aviso: str = ""
    minutos_antes: int = 0
    minutos_depois: int = 0

    @property
    def tem_proposta(self) -> bool:
        return bool(self.mudancas)


@dataclass
class Intencao:
    """O que o texto livre pediu, depois de lido."""

    motivo: str
    item: object = None
    articulacao: str = None
    #: O texto nomeou um exercício do catálogo que não está nesta ficha.
    #: Guardado para a tela poder dizer isso em vez de responder outra coisa.
    fora_da_ficha: str = None


# ==========================================================================
# Leitura do pedido livre
# ==========================================================================

_PISTAS = (
    # A ordem importa: "não tenho tempo, o supino está ocupado" é sobre o
    # supino. Equipamento e desconforto vêm antes de tempo porque são
    # específicos — citam um aparelho ou uma parte do corpo —, e tempo é o
    # motivo genérico que sobra.
    (DESCONFORTO, ("dor", "doi", "doendo", "desconforto", "incomod", "machuc",
                   "lesao", "estalo", "inflam")),
    (EQUIPAMENTO, ("ocupad", "cheia", "cheio", "fila", "lotad", "quebrad",
                   "sem maquina", "ninguem sai", "esperando")),
    (TEMPO, ("tempo", "correndo", "rapido", "atrasad", "pressa", "curto",
             "express", "meia hora")),
    (TROCA, ("troca", "trocar", "substitu", "mudar", "outro exercicio",
             "enjoad", "cansei")),
)


def interpretar(pedido: str, session=None) -> Intencao:
    """Lê o pedido escrito e devolve motivo, exercício e articulação.

    É casamento por palavra-chave, e o limite disso está declarado: entende
    "troque o leg press, dói o joelho" e não entende ironia, negação ou frase
    subordinada. Quando não reconhece o motivo, cai em `TROCA` — que é o pedido
    mais comum e o menos destrutivo dos quatro.

    O ponto de troca por um modelo de linguagem é exatamente aqui: mesma
    assinatura, mesma `Intencao` de volta, nada mais do módulo muda.
    """
    texto = _sem_acento(pedido)

    motivo = TROCA
    for candidato, pistas in _PISTAS:
        if any(pista in texto for pista in pistas):
            motivo = candidato
            break

    articulacao = None
    for chave, termos in ARTICULACOES.items():
        if any(_sem_acento(termo) in texto for termo in termos):
            articulacao = chave
            break

    item = _achar_exercicio(texto, session) if session else None

    # Nomeou um exercício que existe no catálogo mas não está nesta ficha.
    # Sem esta checagem o assistente escolhia outro exercício qualquer e
    # respondia sobre ele — uma resposta convincente para uma pergunta que
    # ninguém fez, que é o pior desfecho possível.
    fora = None
    if session is not None and item is None:
        fora = _nome_no_catalogo(texto)

    # "Dói o joelho" sem citar exercício não dá para atender: o assistente não
    # adivinha qual dos seis exercícios do dia é o culpado.
    if motivo == DESCONFORTO and item is None and articulacao is None:
        motivo = TROCA

    return Intencao(
        motivo=motivo, item=item, articulacao=articulacao, fora_da_ficha=fora
    )


def _nome_no_catalogo(texto: str):
    """O exercício do catálogo que o texto cita, se houver.

    Serve só para uma coisa: distinguir "não entendi o que você quer trocar" de
    "entendi, e isso não está no treino de hoje". São situações diferentes e
    merecem respostas diferentes.
    """
    melhor, melhor_peso = None, 0
    for exercicio in Exercise.objects.filter(is_active=True):
        limpo = _sem_acento(exercicio.name)
        if limpo in texto:
            return exercicio.name
        palavras = [
            p for p in limpo.split()
            if len(p) >= 4 and p not in ("com", "para", "barra", "polia",
                                         "halteres", "halter", "maquina")
        ]
        peso = sum(1 for p in palavras if p in texto)
        if peso > melhor_peso:
            melhor, melhor_peso = exercicio.name, peso
    return melhor


def _achar_exercicio(texto: str, session):
    """O exercício da sessão que o texto está citando.

    Casa pelo nome inteiro e, se falhar, pela palavra mais distintiva dele —
    ninguém escreve "Leg press 45°", escreve "leg press". A palavra precisa ter
    quatro letras ou mais para "com", "com barra" e "na polia" não casarem com
    metade da ficha.
    """
    itens = list(session.exercises.select_related("exercise").all())

    for item in itens:
        if _sem_acento(item.exercise.name) in texto:
            return item

    melhor, melhor_peso = None, 0
    for item in itens:
        palavras = [
            p for p in _sem_acento(item.exercise.name).split()
            if len(p) >= 4 and p not in ("com", "para", "barra", "polia",
                                         "halteres", "halter", "maquina")
        ]
        peso = sum(1 for p in palavras if p in texto)
        if peso > melhor_peso:
            melhor, melhor_peso = item, peso
    return melhor


# ==========================================================================
# Escolha do substituto
# ==========================================================================

def candidatos_para(item, *, evitar_equipamento=False, articulacao=None, excluir=()):
    """Os substitutos possíveis, do melhor para o pior.

    As regras duras vêm primeiro e não são negociáveis:

    1. **Mesmo grupo muscular.** Trocar peito por bíceps não é substituição, é
       outro treino.
    2. **Ativo no catálogo e com demonstração.** Um substituto sem animação
       resolveria o equipamento e quebraria a única coisa que ensina a execução
       — o pedido é trocar sem quebrar a mídia.
    3. **Não pode já estar na sessão.** Sugerir o que a pessoa vai fazer daqui
       a dois exercícios é sugerir fazer duas vezes.

    O que vem depois é preferência, e é onde o motivo do pedido pesa.
    """
    exercicio = item.exercise
    ja_na_sessao = set(
        item.session.exercises.exclude(pk=item.pk).values_list("exercise_id", flat=True)
    )
    ja_na_sessao.update(excluir)

    pool = [
        candidato
        for candidato in Exercise.objects.filter(
            is_active=True, muscle_group=exercicio.muscle_group
        ).exclude(pk=exercicio.pk)
        if candidato.pk not in ja_na_sessao and candidato.animation_kind
    ]

    def peso(candidato):
        pontos = 0

        # Poupar a articulação citada é o critério mais forte quando existe:
        # quem disse que o joelho dói não quer o segundo melhor equipamento.
        if articulacao:
            if articulacao not in (candidato.joints or []):
                pontos -= 100
            pontos += len(candidato.joints or [])

        # Composto troca por composto. Substituir agachamento por cadeira
        # extensora muda o treino de lugar, não o exercício.
        if candidato.is_compound != exercicio.is_compound:
            pontos += 10

        if evitar_equipamento:
            # O que importa não é ser um equipamento diferente, é ser um
            # equipamento que não tem fila. Trocar polia por máquina é
            # diferente e é inútil: numa academia cheia as duas estão tomadas.
            if candidato.disputa_equipamento:
                pontos += 30
            else:
                pontos -= 30
            if candidato.equipment == exercicio.equipment:
                pontos += 20

        # Desempate estável: sem isto a mesma pergunta devolve respostas
        # diferentes conforme a ordem que o banco resolver usar.
        return (pontos, candidato.name)

    return sorted(pool, key=peso)


# ==========================================================================
# As três propostas
# ==========================================================================

def _minutos(session) -> int:
    itens = list(session.exercises.all())
    if not itens:
        return 0
    segundos = 0
    for item in itens:
        segundos += item.sets * SEGUNDOS_POR_SERIE
        segundos += max(item.sets - 1, 0) * item.rest_seconds
    segundos += max(len(itens) - 1, 0) * SEGUNDOS_ENTRE_EXERCICIOS
    return round(segundos / 60)


def _minutos_com(itens) -> int:
    if not itens:
        return 0
    segundos = 0
    for sets, rest in itens:
        segundos += sets * SEGUNDOS_POR_SERIE
        segundos += max(sets - 1, 0) * rest
    segundos += max(len(itens) - 1, 0) * SEGUNDOS_ENTRE_EXERCICIOS
    return round(segundos / 60)


def _trocar(session, item, *, motivo, articulacao=None, evitar_equipamento=False,
            excluir=()) -> Sugestao:
    sugestao = Sugestao(motivo=motivo)
    opcoes = candidatos_para(
        item,
        evitar_equipamento=evitar_equipamento,
        articulacao=articulacao,
        excluir=excluir,
    )

    if not opcoes:
        # Aparelho ocupado tem uma segunda saída, e ela é melhor que a
        # primeira: não fazer agora não é o mesmo que não fazer.
        if motivo == EQUIPAMENTO:
            return _reordenar(session, item)

        sugestao.aviso = (
            f"Todos os exercícios de "
            f"{item.exercise.get_muscle_group_display()} do catálogo já estão "
            f"nesta ficha — não há substituto. Se estiver incomodando, pule "
            f"este hoje: o histórico de carga não se perde."
        )
        return sugestao

    escolhido = opcoes[0]

    # Nenhuma alternativa está realmente livre: adiar resolve, substituir não.
    if motivo == EQUIPAMENTO and escolhido.disputa_equipamento:
        return _reordenar(session, item)

    if motivo == DESCONFORTO and articulacao:
        poupou = articulacao not in (escolhido.joints or [])
        if poupou:
            porque = (
                f"{escolhido.name} trabalha o mesmo músculo sem carregar "
                f"{_nome_da_articulacao(articulacao)}."
            )
        else:
            # A hora de dizer a verdade em vez de fingir que resolveu.
            porque = f"{escolhido.name} é a opção com menos articulações envolvidas."
            sugestao.aviso = (
                f"Todo exercício de {item.exercise.get_muscle_group_display()} "
                f"carrega {_nome_da_articulacao(articulacao)} — não há troca que "
                f"resolva isso. Se doer de novo, pare o exercício e procure um "
                f"profissional; o app não substitui avaliação."
            )
    elif motivo == EQUIPAMENTO:
        porque = (
            f"{escolhido.name} usa {escolhido.get_equipment_display()} e costuma "
            f"estar livre quando a academia enche."
        )
    else:
        porque = f"{escolhido.name} trabalha o mesmo músculo com estímulo parecido."

    sugestao.mudancas = [
        Mudanca(item=item, tipo="troca", porque=porque, novo_exercicio=escolhido)
    ]
    sugestao.resumo = f"Substituir {item.exercise.name} por {escolhido.name}"
    return sugestao


def _reordenar(session, item) -> Sugestao:
    """Empurra o exercício bloqueado para depois de um que esteja livre.

    O parceiro é o primeiro exercício seguinte que não disputa aparelho — se
    todos os seguintes também disputarem, vale o último da ficha: melhor voltar
    ao supino no fim do treino do que ficar parado esperando agora.
    """
    itens = list(session.exercises.select_related("exercise").order_by("order"))
    if len(itens) < 2:
        return Sugestao(
            motivo=EQUIPAMENTO,
            aviso="Esta ficha tem um exercício só — não há por onde reorganizar.",
        )

    posicao = next(i for i, x in enumerate(itens) if x.pk == item.pk)
    depois = itens[posicao + 1:]

    parceiro = next(
        (x for x in depois if not x.exercise.disputa_equipamento),
        depois[-1] if depois else itens[0],
    )

    sugestao = Sugestao(motivo=EQUIPAMENTO)
    sugestao.mudancas = [
        Mudanca(
            item=item,
            tipo="reordenar",
            porque=(
                f"Faça {parceiro.exercise.name} agora e volte ao "
                f"{item.exercise.name} depois — o aparelho costuma liberar."
            ),
            parceiro=parceiro,
        )
    ]
    sugestao.resumo = (
        f"Adiar {item.exercise.name} e puxar {parceiro.exercise.name} para agora"
    )
    return sugestao


def _nome_da_articulacao(chave: str) -> str:
    return {
        "knee": "o joelho",
        "shoulder": "o ombro",
        "elbow": "o cotovelo",
        "wrist": "o punho",
        "lower_back": "a lombar",
        "hip": "o quadril",
        "ankle": "o tornozelo",
    }.get(chave, "essa articulação")


def _encurtar(session) -> Sugestao:
    """Tira tempo da sessão sem tirar o treino dela.

    A ordem do corte é a ordem do que se perde menos:

    1. **Descanso dos isolados.** É o tempo mais barato da ficha — rosca
       martelo com 45 segundos de intervalo continua sendo rosca martelo.
    2. **Descanso dos compostos**, até 90 segundos e não menos. Cortar abaixo
       disso não encurta o treino: faz falhar na terceira série.
    3. **Séries dos isolados**, até duas.

    E para por aí. Nada é removido da ficha, e isso é decisão, não limitação:
    a versão anterior apagava exercícios para fechar a conta dos 30 minutos, e
    apagava de verdade — uma terça-feira corrida deletava a panturrilha da
    rotina inteira, e a pessoa descobriria semanas depois sem ligar uma coisa à
    outra. Um botão de pressa não pode destruir a rotina.

    Quando o corte reversível não alcança o alvo, o assistente diz o número que
    alcançou. Menos ambicioso e verdadeiro.

    O que também nunca é tocado: as séries dos compostos. Eles são o treino —
    uma sessão de peito sem supino não é uma sessão de peito curta, é outra
    coisa.
    """
    itens = list(session.exercises.select_related("exercise").order_by("order"))
    sugestao = Sugestao(motivo=TEMPO)
    if not itens:
        return sugestao

    antes = _minutos(session)
    sugestao.minutos_antes = antes
    alvo = max(antes - CORTE_EXPRESS_MIN, MINIMO_DA_SESSAO_MIN)

    if antes <= MINIMO_DA_SESSAO_MIN:
        sugestao.minutos_depois = antes
        sugestao.aviso = (
            f"Esta sessão já leva {antes} minutos — não dá para encurtar sem "
            f"desmontar o treino."
        )
        return sugestao

    # Estado de trabalho: (item, sets, rest).
    estado = {item.pk: [item, item.sets, item.rest_seconds] for item in itens}

    def agora():
        return _minutos_com([(s, r) for _, s, r in estado.values()])

    def isolados():
        return [l for l in estado.values() if not l[0].exercise.is_compound]

    def compostos():
        return [l for l in estado.values() if l[0].exercise.is_compound]

    for linha in isolados():
        if agora() <= alvo:
            break
        linha[2] = min(linha[2], DESCANSO_MINIMO[False])

    for linha in compostos():
        if agora() <= alvo:
            break
        linha[2] = min(linha[2], DESCANSO_MINIMO[True])

    for linha in isolados():
        while agora() > alvo and linha[1] > SERIES_MINIMAS:
            linha[1] -= 1

    for item, sets, rest in estado.values():
        if sets != item.sets or rest != item.rest_seconds:
            partes = []
            if sets != item.sets:
                partes.append(f"{item.sets} → {sets} séries")
            if rest != item.rest_seconds:
                partes.append(f"descanso {item.rest_seconds}s → {rest}s")
            sugestao.mudancas.append(
                Mudanca(
                    item=item,
                    tipo="ajuste",
                    porque=", ".join(partes),
                    sets=sets,
                    rest_seconds=rest,
                )
            )

    sugestao.minutos_depois = agora()
    sugestao.resumo = (
        f"Encurtar de {antes} para cerca de {sugestao.minutos_depois} minutos"
    )

    if not sugestao.mudancas:
        sugestao.aviso = "Não achei o que cortar aqui sem desmontar o treino."
    elif sugestao.minutos_depois > alvo:
        # Dizer o número alcançado em vez de forçar a conta apagando
        # exercício. Nenhum exercício sai da ficha por causa de um dia corrido.
        sugestao.aviso = (
            f"Dá para tirar {antes - sugestao.minutos_depois} minutos cortando "
            f"descanso e séries. Chegar aos {CORTE_EXPRESS_MIN} exigiria "
            f"remover exercícios da ficha, e o assistente não faz isso — se "
            f"precisar, pule o último exercício hoje."
        )
    return sugestao


def sugerir(session, motivo, *, item=None, articulacao=None, pedido="",
            excluir=()) -> Sugestao:
    """A proposta, sem gravar nada.

    Devolver sem persistir é o desenho todo: ficha de treino é coisa que a
    pessoa decorou, e mudar sem perguntar assusta mais do que ajuda.
    """
    if motivo == TEMPO:
        return _encurtar(session)

    if item is None:
        # Sem alvo, o assistente escolhe o exercício com mais chance de ser o
        # problema: no caso de equipamento, o primeiro que disputa aparelho.
        candidatos = list(session.exercises.select_related("exercise").order_by("order"))
        if motivo == EQUIPAMENTO:
            candidatos = [c for c in candidatos if c.exercise.disputa_equipamento] or candidatos
        if not candidatos:
            return Sugestao(motivo=motivo, aviso="Esta ficha está sem exercícios.")
        item = candidatos[0]

    return _trocar(
        session,
        item,
        motivo=motivo,
        articulacao=articulacao,
        evitar_equipamento=(motivo == EQUIPAMENTO),
        excluir=excluir,
    )


def sugerir_do_texto(session, pedido: str) -> Sugestao:
    """Atalho para o campo livre: lê o pedido e já devolve a proposta."""
    intencao = interpretar(pedido, session=session)

    if intencao.fora_da_ficha:
        return Sugestao(
            motivo=intencao.motivo,
            aviso=(
                f"{intencao.fora_da_ficha} não está no Treino {session.label}. "
                f"Abra a ficha do dia em que ele aparece para trocá-lo."
            ),
        )

    return sugerir(
        session,
        intencao.motivo,
        item=intencao.item,
        articulacao=intencao.articulacao,
        pedido=pedido,
    )


# ==========================================================================
# Aplicação
# ==========================================================================

@transaction.atomic
def aplicar(session, mudancas) -> int:
    """Grava as mudanças confirmadas e marca a ficha como ajustada.

    O histórico de carga não é tocado, e isso é a garantia que importa: os
    `ExerciseLog` apontam para o exercício e para a data, não para a linha da
    ficha. Trocar supino por crucifixo não apaga nem reescreve nenhuma série
    já anotada — o supino de semana passada continua lá, com a carga que teve.
    """
    aplicadas = 0
    for mudanca in mudancas:
        item = mudanca.item
        if mudanca.tipo == "troca" and mudanca.novo_exercicio:
            item.exercise = mudanca.novo_exercicio
            item.save(update_fields=["exercise"])
        elif mudanca.tipo == "ajuste":
            campos = []
            if mudanca.sets is not None:
                item.sets = mudanca.sets
                campos.append("sets")
            if mudanca.rest_seconds is not None:
                item.rest_seconds = mudanca.rest_seconds
                campos.append("rest_seconds")
            if not campos:
                continue
            item.save(update_fields=campos)
        elif mudanca.tipo == "reordenar":
            parceiro = mudanca.parceiro
            if parceiro is None or parceiro.session_id != item.session_id:
                continue
            item.order, parceiro.order = parceiro.order, item.order
            item.save(update_fields=["order"])
            parceiro.save(update_fields=["order"])
        elif mudanca.tipo == "remocao":
            if item.session.exercises.count() <= 1:
                continue
            item.delete()
        else:
            continue
        aplicadas += 1

    if aplicadas:
        plano = session.plan
        plano.customized_at = timezone.now()
        plano.save(update_fields=["customized_at"])
    return aplicadas
