"""Título, subtítulo e ícone de cada opção do onboarding.

Por que aqui e não no modelo: `Goal.CUT.label` é "Emagrecer", e esse texto é
usado no perfil, no plano e no admin. O cartão precisa de três coisas — um
título curto, uma linha de explicação e um desenho — e nenhuma delas é o nome
do objetivo. Enfiar isso no `TextChoices` faria a camada de dados carregar
decisão de tela.

O ícone é o `id` de um `<symbol>` do sprite em `partials/icones.html`. Repetir
o mesmo desenho em vários lugares custaria bytes e desencontraria versões.
"""
from django import template

register = template.Library()

#: valor da escolha -> (ícone, título do cartão, linha de apoio)
#:
#: Uma quarta posição, opcional, marca a opção recomendada. Ela mora aqui e não
#: numa lista separada porque é a MESMA decisão de tela que o ícone e o texto —
#: em dois lugares, uma opção acaba recomendada no onboarding e não na edição
#: do perfil, e ninguém percebe até alguém reclamar.
DETALHES = {
    # accounts.models.Pilar — as cinco areas do NutriPlan.
    #
    # O titulo aqui NAO repete o `label` do TextChoices de proposito: o label
    # e o nome curto que o painel e o perfil usam, e o cartao precisa de uma
    # frase que diga o que a area FAZ. "Alimentacao" e o nome; "o cardapio do
    # dia e o que voce marcou" e a promessa.
    "dieta": (
        "panela",
        "Alimentação",
        "O cardápio do dia e o que você já marcou.",
    ),
    "treino": (
        "halter",
        "Musculação",
        "A ficha da semana, as cargas e as séries.",
    ),
    "corrida": (
        "bicicleta",
        "Corrida",
        "Suas corridas registradas e o ritmo delas.",
    ),
    "hidratacao": (
        "gota",
        "Hidratação",
        "Quanto você bebeu hoje e como foi a semana.",
    ),
    "progresso": (
        "alvo",
        "Evolução",
        "Peso, aderência e o que mudou no tempo.",
    ),
    # accounts.models.Goal
    "cut": (
        "chama",
        "Emagrecer",
        "Perder gordura mantendo o músculo.",
    ),
    "bulk": (
        "halter",
        "Ganhar massa",
        "Músculo, comendo acima do gasto.",
    ),
    "recomp": (
        "raio",
        "Os dois juntos",
        "Os dois juntos, mais devagar.",
    ),
    "maintain": (
        "balanca",
        "Manter o peso",
        "Comer o que gasta, e ficar.",
    ),
    # accounts.models.SplitPreference
    #
    # O exemplo de acoplamento é o que faz a escolha ser possível sem saber
    # jargão. "2 grupos por dia" não diz nada; "Peito+Tríceps | Costas+Bíceps"
    # diz tudo, e em uma linha.
    #
    # A barra separa DIAS e o "+" separa grupos dentro do dia. São dois níveis
    # na mesma linha, e o "·" que estava aqui não distinguia um do outro — a
    # barra é mais alta que o texto e corta a linha visualmente, que é
    # exatamente o que um limite de dia precisa fazer.
    #
    # O exemplo de "1 grupo por dia" mostra os CINCO dias e não três. Escrever
    # "Dia A: Peito | Dia B: Costas | Dia C: Pernas" caberia melhor e diria
    # que a divisão tem três dias, quando ela tem cinco — ombro e braço têm
    # dia próprio, que é justamente o que "um grupo por dia" significa.
    #
    # A contagem ignora os secundários de propósito. Trapézio, antebraço,
    # panturrilha e abdômen têm um ou dois exercícios no catálogo e entram nos
    # acoplamentos lógicos — o dia de peito e tríceps que termina com abdominal
    # continua sendo dois grupos. Chamar de três assustaria por causa de três
    # séries no fim do treino.
    "two": (
        "metades",
        "2 grupos por dia",
        "Pares clássicos, volume equilibrado.",
        True,
        "Peito+Tríceps | Costas+Bíceps | Pernas+Ombros",
        "Mais popular",
    ),
    "one": (
        "alvo",
        "1 grupo por dia",
        "Sessões intensas, um músculo por vez.",
        False,
        "Peito | Costas | Pernas | Ombros | Braços",
    ),
    "three": (
        "corpo",
        "3 grupos por dia",
        "Agrupa complementares, em menos dias.",
        False,
        "Peito+Tríceps+Ombro | Costas+Bíceps+Antebraço",
    ),
    # accounts.models.MealStyle
    "quick": (
        "relogio",
        "Rápida e econômica",
"Pão, ovo, frango, arroz e feijão. Rápido.",
        True,
    ),
    "varied": (
        "panela",
        "Variada e elaborada",
        "Abre para atum, tilápia e preparos longos.",
    ),
    # accounts.models.ActivityLevel
    #
    # Nenhuma das três cita frequência de TREINO, e isso é regra do app, não
    # descuido: os dias de treino são perguntados no passo seguinte, e o fator
    # de atividade já os inclui. Escrever "treinos 3 a 5x por semana" aqui
    # faria a pessoa declarar a mesma coisa duas vezes — e o comentário em
    # `ActivityLevel` registra que o "+ academia" foi REMOVIDO destes rótulos
    # exatamente por isso.
    #
    # São três níveis, e não quatro. Um quarto mudaria o fator calórico, que é
    # decisão de nutrição e não de texto: os fatores foram deliberadamente
    # conservadores em 24/08/2026, porque errar para cima faz a pessoa não
    # emagrecer e concluir que dieta não funciona.
    "sedentary": (
        "escrivaninha",
        "Pouco ativo",
"Trabalho sentado, quase sem caminhar.",
    ),
    "light": (
        "bicicleta",
        "Moderadamente ativo",
"Caminho bastante ou fico em pé.",
    ),
    "active": (
        "ferramentas",
        "Altamente ativo",
"Trabalho braçal ou em pé o dia todo.",
    ),
}


@register.filter
def detalhe(valor):
    """O que desenhar no cartão desta opção.

    Devolve `None` para valor desconhecido, e o template cai no rótulo comum —
    uma escolha nova aparece sem ícone em vez de sumir da tela.
    """
    dados = DETALHES.get(str(valor))
    if not dados:
        return None
    icone, titulo, apoio = dados[:3]
    return {
        "icone": icone,
        "titulo": titulo,
        "apoio": apoio,
        # As três últimas são opcionais, e a maioria das opções não usa
        # nenhuma delas: escrever `False`, `""`, `""` em cada uma seria ruído
        # que ninguém lê.
        "recomendado": len(dados) > 3 and bool(dados[3]),
        "exemplo": dados[4] if len(dados) > 4 else "",
        "selo": dados[5] if len(dados) > 5 else "Recomendado",
    }
