"""Interpretação do que a pessoa falou.

**Por que o entendimento fica no servidor.** O navegador só faz a parte que ele
faz melhor: transformar som em texto, com a API de reconhecimento nativa. A
frase transcrita volta como texto e é lida aqui — em Python, onde a suíte de
testes vive. Um interpretador escrito em JavaScript dentro do template seria
testável só abrindo um navegador com microfone, o que na prática significa não
testado.

**O que ele entende, e o limite.** Água e marcação de refeição. Não existe
registro de alimento avulso neste app: o cardápio é montado por opções A e B, e
o que a tela oferece é "comi esta", "pulei" ou "comi outra coisa". Então
"200 g de frango no almoço" vira almoço marcado como comido fora do plano, com
a frase guardada na observação — que é o que o modelo comporta. Inventar
macros a partir de uma frase falada seria contaminar o histórico com número
chutado, e o histórico é o que sustenta todo o resto do app.

Nada é gravado direto: a fala vira uma proposta, a tela mostra, a pessoa
confirma. Reconhecimento de voz erra, e erra silenciosamente — "trezentos" e
"trezentos e cinquenta" saem parecidos num celular dentro da academia.
"""
from dataclasses import dataclass
from decimal import Decimal
from unicodedata import combining, normalize

#: Faixa que a fala aceita, em mililitros. Arredondada para a dezena.
#:
#: Os botões da tela têm três volumes porque tocar precisa de um conjunto
#: pequeno. Falar não: quem diz "trezentos mililitros" quis dizer trezentos, e
#: encaixar isso no botão de 250 faria o app ficar calado sobre 50 ml que a
#: pessoa registrou. O teto de 2 litros por frase é contra o erro de
#: transcrição — "dois" virando "dois mil" é o engano que o microfone comete.
VOZ_MIN_ML = 50
VOZ_MAX_ML = 2000

#: Recipientes com o volume que as pessoas querem dizer quando os citam.
RECIPIENTES = {
    "copo": 250,
    "copos": 250,
    "xicara": 250,
    "garrafinha": 500,
    "garrafinhas": 500,
    "garrafa": 750,
    "garrafas": 750,
    "litro": 1000,
    "litros": 1000,
}

#: Números por extenso até dez, mais "meio". Ninguém fala "1,5 litro de água" —
#: fala "um litro e meio".
NUMEROS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
    "meio": Decimal("0.5"), "meia": Decimal("0.5"),
}

#: O que a pessoa diz quando quer dizer cada status.
MARCACOES = (
    ("skipped", ("pulei", "nao comi", "nao almocei", "nao jantei", "perdi o",
                 "deixei de comer")),
    ("off_plan", ("comi outra", "comi fora", "fora do plano", "comi um",
                  "comi uma", "comi ", "almocei ", "jantei ", "tomei ")),
)

#: Como cada refeição é chamada em voz alta. Casado contra o NOME do horário no
#: plano da pessoa, e este mapa cobre os apelidos que o nome não tem.
APELIDOS = {
    "cafe": ("cafe", "cafe da manha", "manha", "desjejum"),
    "almoco": ("almoco", "almocei"),
    "jantar": ("jantar", "janta", "jantei", "noite"),
    "lanche": ("lanche", "lanchinho"),
    "ceia": ("ceia",),
}


def _limpo(texto: str) -> str:
    decomposto = normalize("NFD", (texto or "").lower().strip())
    return "".join(c for c in decomposto if not combining(c))


@dataclass
class Intencao:
    """O que a frase pediu, já pronto para virar uma proposta na tela."""

    tipo: str  # "agua" | "refeicao" | ""
    #: Água: mililitros, arredondados para a dezena.
    ml: int = 0
    #: Refeição: o horário e o status.
    slot_id: int = None
    slot_nome: str = ""
    status: str = ""
    #: O que sobrou da frase, guardado como observação da refeição.
    nota: str = ""
    #: O que a tela mostra antes de aplicar.
    resumo: str = ""
    #: Por que não deu para entender, quando não deu.
    erro: str = ""

    @property
    def entendeu(self) -> bool:
        return bool(self.tipo)


def _numero_em(texto: str):
    """O primeiro número da frase, em algarismo ou por extenso."""
    palavras = texto.split()
    for i, p in enumerate(palavras):
        digitos = "".join(c for c in p if c.isdigit())
        if digitos:
            return Decimal(digitos), i
        if p in NUMEROS:
            return Decimal(NUMEROS[p]), i
    return None, -1


def _agua(texto: str) -> Intencao:
    """Quanta água a frase pediu, em mililitros."""
    quantidade, pos = _numero_em(texto)
    palavras = texto.split()

    ml = None
    if "ml" in texto or "mililitro" in texto:
        if quantidade:
            ml = int(quantidade)
    else:
        # Recipiente: "um copo", "meio litro", "duas garrafinhas".
        for nome, volume in RECIPIENTES.items():
            if nome in palavras:
                ml = int((quantidade or 1) * volume)
                break

    if ml is None and quantidade and quantidade >= 100:
        # "trezentos de água" — sem unidade, mas o número já é mililitro.
        ml = int(quantidade)

    if not ml:
        return Intencao(
            tipo="",
            erro="Não entendi quanta água. Tente \"300 ml de água\" ou \"um copo de água\".",
        )

    # Dezena mais próxima: a transcrição devolve o número que ouviu, e ninguém
    # mede água em unidades de mililitro.
    escolhido = int(round(ml / 10) * 10)
    if escolhido < VOZ_MIN_ML or escolhido > VOZ_MAX_ML:
        return Intencao(
            tipo="",
            erro=f"Entendi {escolhido} ml, e isso está fora da faixa de "
                 f"{VOZ_MIN_ML} a {VOZ_MAX_ML} ml por vez. Repita o número.",
        )

    return Intencao(tipo="agua", ml=escolhido, resumo=f"Somar {escolhido} ml de água")


def _casa_refeicao(texto: str, slots):
    """O horário do plano que a frase está citando."""
    for slot in slots:
        if _limpo(slot.name) in texto:
            return slot

    for chave, termos in APELIDOS.items():
        if not any(t in texto for t in termos):
            continue
        for slot in slots:
            nome = _limpo(slot.name)
            if chave in nome or any(t in nome for t in termos):
                return slot
    return None


def interpretar(frase: str, slots=()) -> Intencao:
    """Lê a frase e devolve o que fazer — sem fazer.

    A ordem importa: água é conferida antes de refeição porque "tomei água" tem
    o verbo de comer dentro dele, e sem a precedência viraria "tomei" =
    refeição fora do plano.
    """
    texto = _limpo(frase)
    if not texto:
        return Intencao(tipo="", erro="Não ouvi nada.")

    if "agua" in texto:
        return _agua(texto)

    slots = list(slots)
    slot = _casa_refeicao(texto, slots)

    status = ""
    for candidato, termos in MARCACOES:
        if any(t in texto for t in termos):
            status = candidato
            break

    if slot is None:
        if status:
            return Intencao(
                tipo="",
                erro="Entendi o que você comeu, mas não em qual refeição. "
                     "Diga o horário: \"no almoço\", \"no jantar\".",
            )
        return Intencao(
            tipo="",
            erro="Não entendi. Tente \"300 ml de água\" ou "
                 "\"comi frango no almoço\".",
        )

    if not status:
        status = "off_plan"

    # A frase inteira vira a observação. Guardar o que foi dito, e não uma
    # extração, é o que permite a pessoa reler amanhã e entender o registro —
    # "200 g de frango" sozinho perde o "no almoço" que dava sentido a ele.
    nota = frase.strip()
    if len(nota) > 180:
        nota = nota[:177] + "..."

    rotulo = {
        "skipped": f"Marcar {slot.name} como pulada",
        "off_plan": f"Marcar {slot.name} como comida fora do plano",
    }[status]

    return Intencao(
        tipo="refeicao",
        slot_id=slot.pk,
        slot_nome=slot.name,
        status=status,
        nota=nota if status == "off_plan" else "",
        resumo=rotulo,
    )
