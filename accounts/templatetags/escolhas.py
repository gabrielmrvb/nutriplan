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
    # accounts.models.Goal
    "cut": (
        "chama",
        "Emagrecer",
        "Perder gordura mantendo o máximo de músculo.",
    ),
    "bulk": (
        "halter",
        "Ganhar massa",
        "Construir músculo com superávit controlado.",
    ),
    "recomp": (
        "raio",
        "Os dois ao mesmo tempo",
        "Perder gordura e ganhar músculo — mais lento, e possível.",
    ),
    "maintain": (
        "balanca",
        "Manter o peso",
        "Ficar onde está, comendo o que gasta.",
    ),
    # accounts.models.SplitPreference
    #
    # Os rótulos dizem a DIVISÃO e não "1 grupo por dia", "2 grupos por dia".
    # A contagem por dia seria mais fácil de escolher e mentiria: com este
    # catálogo, "poucos grupos" é empurrar/puxar/pernas, que dá dois a três
    # grupos por sessão. Prometer um número que a ficha não entrega é pior do
    # que pedir dez segundos a mais de leitura.
    "focused": (
        "alvo",
        "Poucos grupos por dia",
        "Empurrar, puxar e pernas em dias separados. Sessões mais curtas e "
        "cada grupo treinado com mais atenção.",
        True,
    ),
    "upper_lower": (
        "metades",
        "Superior e inferior",
        "Metade de cima num dia, metade de baixo no outro. Treinando quatro "
        "ou mais vezes, cada metade repete na semana.",
    ),
    "full_body": (
        "corpo",
        "Corpo todo, toda vez",
        "Tudo na mesma sessão. É o que rende mais quando dá para treinar só "
        "uma ou duas vezes por semana.",
    ),
    # accounts.models.MealStyle
    "quick": (
        "relogio",
        "Rápida e econômica",
        "Pão, ovo, frango, arroz, feijão, aveia e banana. Café e lanche em "
        "até dez minutos.",
        True,
    ),
    "varied": (
        "panela",
        "Variada e elaborada",
        "Abre o cardápio para atum, tilápia, tapioca e preparos mais longos.",
    ),
    # accounts.models.ActivityLevel
    "sedentary": (
        "escrivaninha",
        "Sedentário / pouco ativo",
        "Passo a maior parte do dia sentado — escritório, home office ou "
        "dirigindo — e me movimento pouco.",
    ),
    "light": (
        "bicicleta",
        "Moderadamente ativo",
        "Faço caminhadas diárias, tarefas domésticas frequentes ou passo boa "
        "parte do dia em pé.",
    ),
    "active": (
        "ferramentas",
        "Altamente ativo",
        "Trabalho braçal, fico em pé o dia todo ou tenho alto gasto físico "
        "diário.",
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
        # Quarta posição opcional: a maioria das opções não é recomendada, e
        # escrever `False` em cada uma seria ruído que ninguém lê.
        "recomendado": len(dados) > 3 and dados[3],
    }
